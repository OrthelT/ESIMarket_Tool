"""
ESI HTTP client — all Eve Online API communication lives here.

Provides ESIClient for fetching market orders, market history, and SDE names.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import requests
from requests import ReadTimeout

from config import AppConfig

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


class ESIClient:
    """Handles all HTTP communication with the EVE ESI API."""

    MAX_RETRIES = 5
    RETRY_DELAY = 3  # seconds

    def __init__(self, config: AppConfig, token: dict):
        self._config = config
        self._token = token
        self._auth_headers = {
            'Authorization': f'Bearer {token["access_token"]}',
            'Content-Type': 'application/json',
        }

    def fetch_market_orders(
        self,
        structure_id: int,
        wait_time: float = 0.1,
        progress_callback: Callable[[str], None] | None = None,
    ) -> FetchResult:
        """Fetch all market orders from a structure.

        Args:
            structure_id: The structure to fetch orders from
            wait_time: Seconds to wait between page requests
            progress_callback: Optional callback for progress messages (receives a string)

        Returns:
            FetchResult with orders data and fetch statistics
        """
        start = datetime.now()
        url_base = f'https://esi.evetech.net/latest/markets/structures/{structure_id}/?page='

        page = 1
        total_pages = 1  # Updated from X-Pages header on first response
        retries = 0
        result = FetchResult()

        logger.info("Fetching market orders...")

        while page <= total_pages:
            response = requests.get(url_base + str(page), headers=self._auth_headers)

            if 'X-Pages' in response.headers:
                total_pages = int(response.headers['X-Pages'])

            percent = round((page / total_pages) * 100)

            if progress_callback:
                progress_callback(f"\rFetching page {page} of {total_pages} ({percent}% complete)")

            # Check ESI error limits
            errors_left = int(response.headers.get('X-ESI-Error-Limit-Remain', 0))
            error_reset = int(response.headers.get('X-ESI-Error-Limit-Reset', 0))

            if errors_left == 0:
                logger.error("Error limit reached. Stopping requests.")
                break
            elif errors_left < 10:
                logger.warning(f'Low error limit remaining: {errors_left}. Reset in {error_reset}s.')

            # Handle non-200 responses
            if response.status_code != 200:
                result.error_count += 1
                try:
                    error_msg = response.json().get('error', 'Unknown error')
                except Exception:
                    error_msg = f'HTTP {response.status_code}'

                logger.error(f"Error on page {page}: {error_msg}. Retry {retries}/{self.MAX_RETRIES}")

                if retries < self.MAX_RETRIES:
                    retries += 1
                    time.sleep(self.RETRY_DELAY)
                    continue
                else:
                    logger.error(f'Max retries reached for page {page}. Giving up.')
                    break

            result.total_retries += retries
            retries = 0

            # Decode response
            try:
                orders = response.json()
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
            time.sleep(wait_time)

        result.elapsed_seconds = (datetime.now() - start).total_seconds()

        logger.info(f"Market orders complete: {result.pages_fetched} pages, "
                     f"{len(result.data)} orders, {result.error_count} errors, "
                     f"{result.total_retries} retries, {result.elapsed_seconds:.1f}s")

        return result

    def fetch_market_history(
        self,
        region_id: int,
        type_ids: list[int],
        wait_time: float = 0.3,
        progress_callback: Callable[[str], None] | None = None,
    ) -> FetchResult:
        """Fetch market history for a list of type IDs.

        Args:
            region_id: The region to fetch history from
            type_ids: List of item type IDs to fetch history for
            wait_time: Seconds to wait between requests
            progress_callback: Optional callback for progress messages

        Returns:
            FetchResult with history data and fetch statistics
        """
        start = datetime.now()
        url_base = f'https://esi.evetech.net/latest/markets/{region_id}/history/?datasource=tranquility&type_id='
        headers = {'accept': 'application/json'}
        timeout = 10

        item_count = len(type_ids)
        logger.info(f"Fetching market history for {item_count} items...")
        est_minutes = round(item_count * 0.54 / 60)

        if progress_callback:
            progress_callback(f"Querying ESI history for {item_count} items. ~{est_minutes} min estimated.")

        result = FetchResult()
        retries = 0
        average_duration = None
        items_processed = 0

        for item in type_ids:
            items_processed += 1
            percent = round((items_processed / item_count) * 100)

            if progress_callback:
                progress_callback(f"\rFetching history: item {items_processed}/{item_count} ({percent}%)")

            page = 1
            max_pages = 1

            while page <= max_pages:
                try:
                    req_start = datetime.now()
                    response = requests.get(url_base + str(item), headers=headers, timeout=timeout)
                    code = response.status_code
                    logger.debug(f"type_id: {item}, status: {code}")

                    error_limit_remain = response.headers.get('X-ESI-Error-Limit-Remain')
                    error_limit_reset = response.headers.get('X-ESI-Error-Limit-Reset')

                    if 'X-Pages' in response.headers:
                        max_pages = int(response.headers['X-Pages'])

                    if code != 200:
                        result.error_count += 1
                        try:
                            error_msg = response.json().get('error', 'Unknown')
                        except Exception:
                            error_msg = f'HTTP {code}'

                        logger.error(f"Error for type_id {item}: {error_msg}")

                        if error_limit_remain is not None and int(error_limit_remain) < 2:
                            sleep_time = int(error_limit_reset) if error_limit_reset else 60
                            logger.error(f"Error limit nearly reached. Sleeping {sleep_time}s.")
                            time.sleep(sleep_time)
                            continue
                        elif retries < self.MAX_RETRIES:
                            retries += 1
                            time.sleep(self.RETRY_DELAY)
                            continue
                        else:
                            logger.error(f"Failed type_id {item} after {self.MAX_RETRIES} attempts")
                            result.failed_items.append(item)
                            break

                    data = response.json()
                    req_duration = datetime.now() - req_start

                    # Track request rate
                    if average_duration is not None:
                        average_duration = (average_duration * (items_processed - 1) + req_duration) / items_processed
                        rpm = 60 / average_duration.total_seconds() if average_duration.total_seconds() > 0 else 0
                        if rpm > 290:
                            logger.warning(f"Rate limit approaching ({rpm:.0f} req/min). Sleeping 10s.")
                            time.sleep(10)
                    else:
                        average_duration = req_duration

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
                    time.sleep(wait_time)

                except ReadTimeout:
                    logger.error(f"Timeout for type_id {item}")
                    if retries < self.MAX_RETRIES:
                        retries += 1
                        time.sleep(self.RETRY_DELAY)
                        continue
                    else:
                        logger.error(f"Failed type_id {item} after {self.MAX_RETRIES} timeout retries")
                        result.failed_items.append(item)
                        break

            result.total_retries += retries
            retries = 0

        result.elapsed_seconds = (datetime.now() - start).total_seconds()

        logger.info(f"Market history complete: {result.pages_fetched} items, "
                     f"{len(result.data)} records, {result.error_count} errors, "
                     f"{result.total_retries} retries, {result.elapsed_seconds:.1f}s")
        if result.failed_items:
            logger.warning(f"Failed items: {result.failed_items}")

        return result

    @staticmethod
    def fetch_sde_names(type_ids: list[int]) -> dict[int, str]:
        """Fetch item names from the ESI universe/names endpoint.

        Args:
            type_ids: List of type IDs to resolve to names

        Returns:
            Dict mapping type_id -> type_name. Returns empty dict on failure.
        """
        if not type_ids:
            return {}

        url = 'https://esi.evetech.net/latest/universe/names/?datasource=tranquility'
        headers = {'Content-Type': 'application/json'}

        try:
            response = requests.post(url, headers=headers, json=type_ids)
            response.raise_for_status()
            data = response.json()
            return {item['id']: item['name'] for item in data}
        except requests.RequestException as e:
            logger.error(f"Failed to fetch SDE names: {e}")
            return {}
        except (KeyError, ValueError) as e:
            logger.error(f"Failed to parse SDE names response: {e}")
            return {}
