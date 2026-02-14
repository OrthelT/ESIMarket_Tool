"""
ESI HTTP client — all Eve Online API communication lives here.

Provides ESIClient (async context manager) for fetching market orders,
market history, and SDE names via aiohttp.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

import aiohttp
from rich.progress import Progress

from cache import HistoryCache
from config import AppConfig
from rate_limiter import TokenBucketRateLimiter

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """Container for results of an ESI fetch operation."""
    data: list[dict] = field(default_factory=list)
    pages_fetched: int = 0
    error_count: int = 0
    total_retries: int = 0
    elapsed_seconds: float = 0.0
    failed_items: list[int] = field(default_factory=list)
    cache_hits: int = 0


class ESIClient:
    """Handles all HTTP communication with the EVE ESI API.

    Use as an async context manager to ensure the session is properly closed::

        async with ESIClient(config, token) as esi:
            result = await esi.fetch_market_orders(...)
    """

    def __init__(
        self,
        config: AppConfig,
        token: dict,
        rate_limiter: TokenBucketRateLimiter | None = None,
        history_cache: HistoryCache | None = None,
    ):
        self._config = config
        self._token = token
        self._rate_limiter = rate_limiter or TokenBucketRateLimiter()
        self._history_cache = history_cache
        self._max_retries = config.rate_limiting.max_retries
        self._retry_delay = config.rate_limiting.retry_delay
        self._retry_backoff = config.rate_limiting.retry_backoff_factor
        ua = config.user_agent.format_header()
        self._auth_headers = {
            'Authorization': f'Bearer {token["access_token"]}',
            'Content-Type': 'application/json',
            'User-Agent': ua,
        }
        self._public_headers = {
            'accept': 'application/json',
            'User-Agent': ua,
        }
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> 'ESIClient':
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def fetch_market_orders(
        self,
        structure_id: int,
        progress: Progress | None = None,
    ) -> FetchResult:
        """Fetch all market orders from a structure.

        Args:
            structure_id: The structure to fetch orders from
            progress: Optional Rich Progress instance for progress display

        Returns:
            FetchResult with orders data and fetch statistics
        """
        start = datetime.now()
        url_base = f'https://esi.evetech.net/latest/markets/structures/{structure_id}/?page='

        page = 1
        total_pages = 1
        retries = 0
        result = FetchResult()
        task_id = progress.add_task("Market orders", total=None) if progress else None

        logger.info("Fetching market orders...")

        while page <= total_pages:
            await self._rate_limiter.acquire()
            async with self._session.get(url_base + str(page), headers=self._auth_headers) as response:
                if 'X-Pages' in response.headers:
                    total_pages = int(response.headers['X-Pages'])
                    if progress and task_id is not None:
                        progress.update(task_id, total=total_pages)

                if progress and task_id is not None:
                    progress.update(task_id, completed=page)

                # Check ESI error limits
                errors_left = int(response.headers.get('X-ESI-Error-Limit-Remain', 0))
                error_reset = int(response.headers.get('X-ESI-Error-Limit-Reset', 0))

                if errors_left == 0:
                    logger.error("Error limit reached. Stopping requests.")
                    break
                elif errors_left < 10:
                    logger.warning(f'Low error limit remaining: {errors_left}. Reset in {error_reset}s.')

                # Handle non-200 responses
                if response.status != 200:
                    result.error_count += 1
                    try:
                        body = await response.json(content_type=None)
                        error_msg = body.get('error', 'Unknown error')
                    except Exception:
                        error_msg = f'HTTP {response.status}'

                    logger.error(f"Error on page {page}: {error_msg}. Retry {retries}/{self._max_retries}")

                    if retries < self._max_retries:
                        delay = self._retry_delay * (self._retry_backoff ** retries)
                        retries += 1
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(f'Max retries reached for page {page}. Giving up.')
                        break

                result.total_retries += retries
                retries = 0

                # Decode response
                try:
                    orders = await response.json(content_type=None)
                except ValueError:
                    logger.error(f"Failed to decode JSON from page {page}")
                    result.error_count += 1
                    continue

            if not orders:
                logger.info(f"No orders on page {page}")
                break

            result.data.extend(orders)
            result.pages_fetched += 1
            page += 1

        result.elapsed_seconds = (datetime.now() - start).total_seconds()

        logger.info(f"Market orders complete: {result.pages_fetched} pages, "
                     f"{len(result.data)} orders, {result.error_count} errors, "
                     f"{result.total_retries} retries, {result.elapsed_seconds:.1f}s")

        return result

    async def fetch_market_history(
        self,
        region_id: int,
        type_ids: list[int],
        progress: Progress | None = None,
        type_names: dict[int, str] | None = None,
        on_item: Callable[[str], None] | None = None,
    ) -> FetchResult:
        """Fetch market history for a list of type IDs.

        Supports HTTP conditional requests (ETag/If-None-Match) when a
        HistoryCache is injected. Returns 304-cached data alongside fresh
        200 responses transparently.

        Args:
            region_id: The region to fetch history from
            type_ids: List of item type IDs to fetch history for
            progress: Optional Rich Progress instance for progress display
            type_names: Optional dict mapping type_id -> name for progress display

        Returns:
            FetchResult with history data and fetch statistics
        """
        start = datetime.now()
        url_base = f'https://esi.evetech.net/latest/markets/{region_id}/history/?datasource=tranquility&type_id='
        timeout = aiohttp.ClientTimeout(total=10)

        item_count = len(type_ids)
        logger.info(f"Fetching market history for {item_count} items...")
        if self._history_cache:
            logger.info(f"Cache loaded with {self._history_cache.entry_count} entries")

        result = FetchResult()
        retries = 0
        items_processed = 0
        task_id = progress.add_task("Market history", total=item_count) if progress else None

        for item in type_ids:
            items_processed += 1

            if progress and task_id is not None:
                progress.update(task_id, completed=items_processed)

            # Notify caller of current item (for display on a separate line)
            if on_item:
                item_name = (type_names or {}).get(item, str(item))
                on_item(item_name)

            page = 1
            max_pages = 1
            skip_cache = False

            while page <= max_pages:
                try:
                    # Build request headers, merging conditional cache headers
                    req_headers = dict(self._public_headers)
                    if self._history_cache and not skip_cache:
                        cond_headers = self._history_cache.get_conditional_headers(item)
                        req_headers.update(cond_headers)

                    await self._rate_limiter.acquire()
                    async with self._session.get(
                        url_base + str(item),
                        headers=req_headers,
                        timeout=timeout,
                    ) as response:
                        code = response.status
                        logger.debug(f"type_id: {item}, status: {code}")

                        error_limit_remain = response.headers.get('X-ESI-Error-Limit-Remain')
                        error_limit_reset = response.headers.get('X-ESI-Error-Limit-Reset')

                        if 'X-Pages' in response.headers:
                            max_pages = int(response.headers['X-Pages'])

                        # Handle 304 Not Modified — use cached data
                        if code == 304 and self._history_cache:
                            if self._history_cache.has_data(item):
                                cached = self._history_cache.get(item)
                                result.data.extend(cached.data)
                                result.cache_hits += 1
                                result.pages_fetched += 1
                                logger.debug(f"Cache hit (304) for type_id {item}")
                                break
                            else:
                                # Safety valve: got 304 but no cached data
                                logger.warning(f"304 for type_id {item} but no cached data, retrying fresh")
                                skip_cache = True
                                continue

                        if code != 200:
                            result.error_count += 1
                            try:
                                body = await response.json(content_type=None)
                                error_msg = body.get('error', 'Unknown')
                            except Exception:
                                error_msg = f'HTTP {code}'

                            logger.error(f"Error for type_id {item}: {error_msg}")

                            if error_limit_remain is not None and int(error_limit_remain) < 2:
                                sleep_time = int(error_limit_reset) if error_limit_reset else 60
                                logger.error(f"Error limit nearly reached. Sleeping {sleep_time}s.")
                                await asyncio.sleep(sleep_time)
                                continue
                            elif retries < self._max_retries:
                                delay = self._retry_delay * (self._retry_backoff ** retries)
                                retries += 1
                                await asyncio.sleep(delay)
                                continue
                            else:
                                logger.error(f"Failed type_id {item} after {self._max_retries} attempts")
                                result.failed_items.append(item)
                                break

                        data = await response.json(content_type=None)

                        # Store in cache on successful 200
                        if self._history_cache:
                            etag = response.headers.get('ETag', '')
                            last_mod = response.headers.get('Last-Modified', '')
                            # Cache data with type_id already injected
                            cache_data = []
                            if data:
                                for entry in data:
                                    entry_copy = dict(entry)
                                    entry_copy['type_id'] = item
                                    cache_data.append(entry_copy)
                            self._history_cache.put(item, etag, last_mod, cache_data)

                    if data:
                        for entry in data:
                            entry['type_id'] = item
                        result.data.extend(data)
                        logger.debug(f"Retrieved {len(data)} history records for type_id {item}")
                    else:
                        logger.warning(f"No history data for type_id {item}")

                    retries = 0
                    result.pages_fetched += 1
                    page += 1

                except asyncio.TimeoutError:
                    logger.error(f"Timeout for type_id {item}")
                    if retries < self._max_retries:
                        delay = self._retry_delay * (self._retry_backoff ** retries)
                        retries += 1
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(f"Failed type_id {item} after {self._max_retries} timeout retries")
                        result.failed_items.append(item)
                        break

            result.total_retries += retries
            retries = 0

        result.elapsed_seconds = (datetime.now() - start).total_seconds()

        logger.info(f"Market history complete: {result.pages_fetched} items, "
                     f"{len(result.data)} records, {result.error_count} errors, "
                     f"{result.total_retries} retries, {result.cache_hits} cache hits, "
                     f"{result.elapsed_seconds:.1f}s")
        if result.failed_items:
            logger.warning(f"Failed items: {result.failed_items}")

        return result

    async def fetch_sde_names(self, type_ids: list[int]) -> dict[int, str]:
        """Fetch item names from the ESI universe/names endpoint.

        Args:
            type_ids: List of type IDs to resolve to names

        Returns:
            Dict mapping type_id -> type_name. Returns empty dict on failure.
        """
        if not type_ids:
            return {}

        url = 'https://esi.evetech.net/latest/universe/names/?datasource=tranquility'
        headers = {**self._public_headers, 'Content-Type': 'application/json'}

        try:
            async with self._session.post(url, headers=headers, json=type_ids) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)
                return {item['id']: item['name'] for item in data}
        except aiohttp.ClientError as e:
            logger.error(f"Failed to fetch SDE names: {e}")
            return {}
        except (KeyError, ValueError) as e:
            logger.error(f"Failed to parse SDE names response: {e}")
            return {}

    async def test_connectivity(self, structure_id: int) -> dict:
        """Quick connectivity test — fetch 1 page of orders from a structure.

        Returns:
            Dict with 'success', 'order_count', 'total_pages', and 'error' keys.
        """
        url = f'https://esi.evetech.net/latest/markets/structures/{structure_id}/?page=1'
        try:
            async with self._session.get(url, headers=self._auth_headers) as response:
                if response.status != 200:
                    body = await response.json(content_type=None)
                    return {
                        'success': False,
                        'error': body.get('error', f'HTTP {response.status}'),
                    }
                data = await response.json(content_type=None)
                total_pages = int(response.headers.get('X-Pages', 1))
                return {
                    'success': True,
                    'order_count': len(data),
                    'total_pages': total_pages,
                }
        except Exception as e:
            return {'success': False, 'error': str(e)}
