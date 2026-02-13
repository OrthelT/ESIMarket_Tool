"""Integration tests for ESI client caching with mocked HTTP responses."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from cache import HistoryCache
from config import AppConfig
from esi_client import ESIClient, FetchResult
from rate_limiter import TokenBucketRateLimiter


@pytest.fixture
def mock_config():
    """Minimal AppConfig for testing."""
    return AppConfig()


@pytest.fixture
def mock_token():
    return {"access_token": "test_token_123"}


@pytest.fixture
def fast_rate_limiter():
    """Rate limiter that doesn't actually throttle."""
    return TokenBucketRateLimiter(burst_size=1000, tokens_per_second=1000.0)


def _make_mock_response(status, data=None, headers=None):
    """Create a mock aiohttp response."""
    resp = AsyncMock()
    resp.status = status
    resp.headers = headers or {}

    async def json_func(content_type=None):
        return data or []
    resp.json = json_func

    # Support async context manager
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


class TestCacheHitOn304:
    """Test that 304 responses correctly use cached data."""

    @pytest.mark.asyncio
    async def test_304_uses_cached_data(self, tmp_path, mock_config, mock_token, fast_rate_limiter):
        """When ESI returns 304, cached data should be used."""
        cache = HistoryCache(tmp_path / "cache.json")
        cached_data = [
            {"date": "2026-01-15", "type_id": 34, "highest": 10.5, "lowest": 8.2,
             "average": 9.3, "volume": 1000000, "order_count": 150}
        ]
        cache.put(34, '"abc123"', "Thu, 15 Jan 2026", cached_data)

        mock_resp = _make_mock_response(304, headers={})

        client = ESIClient(
            config=mock_config,
            token=mock_token,
            rate_limiter=fast_rate_limiter,
            history_cache=cache,
        )
        client._session = MagicMock()
        client._session.get = MagicMock(return_value=mock_resp)

        result = await client.fetch_market_history(
            region_id=10000003,
            type_ids=[34],
        )

        assert result.cache_hits == 1
        assert len(result.data) == 1
        assert result.data[0]["type_id"] == 34
        assert result.error_count == 0

    @pytest.mark.asyncio
    async def test_304_without_cached_data_retries_fresh(self, tmp_path, mock_config, mock_token, fast_rate_limiter):
        """304 with no cached data should retry without conditional headers."""
        cache = HistoryCache(tmp_path / "cache.json")
        # Put entry with empty data (simulates corrupted cache)
        cache.put(34, '"abc123"', "Thu, 15 Jan 2026", [])

        fresh_data = [
            {"date": "2026-01-15", "highest": 10.5, "lowest": 8.2,
             "average": 9.3, "volume": 1000000, "order_count": 150}
        ]

        # First call returns 304 (but cache has no data), second returns 200
        resp_304 = _make_mock_response(304, headers={})
        resp_200 = _make_mock_response(200, data=fresh_data, headers={
            "ETag": '"new_etag"',
            "Last-Modified": "Thu, 16 Jan 2026",
        })

        call_count = 0

        def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # safety valve: no data, so no conditional headers, but
                # this is the first request with empty data
                return resp_304
            return resp_200

        client = ESIClient(
            config=mock_config,
            token=mock_token,
            rate_limiter=fast_rate_limiter,
            history_cache=cache,
        )
        client._session = MagicMock()
        client._session.get = mock_get

        result = await client.fetch_market_history(
            region_id=10000003,
            type_ids=[34],
        )

        # Should have retried and got fresh data
        assert result.cache_hits == 0
        assert len(result.data) == 1
        assert result.error_count == 0

    @pytest.mark.asyncio
    async def test_304_does_not_increment_error_count(self, tmp_path, mock_config, mock_token, fast_rate_limiter):
        """304 should never be counted as an error."""
        cache = HistoryCache(tmp_path / "cache.json")
        cache.put(34, '"etag"', "date", [{"type_id": 34, "date": "2026-01-15"}])

        mock_resp = _make_mock_response(304, headers={})

        client = ESIClient(
            config=mock_config,
            token=mock_token,
            rate_limiter=fast_rate_limiter,
            history_cache=cache,
        )
        client._session = MagicMock()
        client._session.get = MagicMock(return_value=mock_resp)

        result = await client.fetch_market_history(
            region_id=10000003,
            type_ids=[34],
        )

        assert result.error_count == 0
        assert result.cache_hits == 1


class TestCacheStoreOn200:
    """Test that 200 responses are stored in cache."""

    @pytest.mark.asyncio
    async def test_200_stores_in_cache(self, tmp_path, mock_config, mock_token, fast_rate_limiter):
        """Successful 200 response should be stored in cache."""
        cache = HistoryCache(tmp_path / "cache.json")

        fresh_data = [
            {"date": "2026-01-15", "highest": 10.5, "lowest": 8.2,
             "average": 9.3, "volume": 1000000, "order_count": 150}
        ]

        mock_resp = _make_mock_response(200, data=fresh_data, headers={
            "ETag": '"fresh_etag"',
            "Last-Modified": "Thu, 15 Jan 2026",
        })

        client = ESIClient(
            config=mock_config,
            token=mock_token,
            rate_limiter=fast_rate_limiter,
            history_cache=cache,
        )
        client._session = MagicMock()
        client._session.get = MagicMock(return_value=mock_resp)

        result = await client.fetch_market_history(
            region_id=10000003,
            type_ids=[34],
        )

        assert result.cache_hits == 0
        assert len(result.data) == 1

        # Verify data was stored in cache
        entry = cache.get(34)
        assert entry is not None
        assert entry.etag == '"fresh_etag"'
        assert entry.last_modified == "Thu, 15 Jan 2026"
        assert len(entry.data) == 1
        assert entry.data[0]["type_id"] == 34


class TestCacheHitsCounter:
    """Test cache_hits counter accuracy."""

    @pytest.mark.asyncio
    async def test_multiple_items_mixed(self, tmp_path, mock_config, mock_token, fast_rate_limiter):
        """Mix of 304 and 200 responses should count cache_hits correctly."""
        cache = HistoryCache(tmp_path / "cache.json")
        # Pre-populate cache for type_id 34 and 35
        cache.put(34, '"etag34"', "date", [{"type_id": 34, "date": "2026-01-15"}])
        cache.put(35, '"etag35"', "date", [{"type_id": 35, "date": "2026-01-15"}])

        fresh_data_36 = [{"date": "2026-01-15", "highest": 5.0, "lowest": 4.0,
                          "average": 4.5, "volume": 500000, "order_count": 50}]

        call_count = 0

        def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            headers = kwargs.get("headers", {})
            if "If-None-Match" in headers:
                return _make_mock_response(304, headers={})
            return _make_mock_response(200, data=fresh_data_36, headers={
                "ETag": '"etag36"',
                "Last-Modified": "Thu, 15 Jan 2026",
            })

        client = ESIClient(
            config=mock_config,
            token=mock_token,
            rate_limiter=fast_rate_limiter,
            history_cache=cache,
        )
        client._session = MagicMock()
        client._session.get = mock_get

        result = await client.fetch_market_history(
            region_id=10000003,
            type_ids=[34, 35, 36],
        )

        assert result.cache_hits == 2  # 34 and 35 got 304
        assert len(result.data) == 3  # 2 cached + 1 fresh


class TestCacheDisabled:
    """Test behavior when caching is disabled (history_cache=None)."""

    @pytest.mark.asyncio
    async def test_no_conditional_headers_without_cache(self, mock_config, mock_token, fast_rate_limiter):
        """Without a cache, no conditional headers should be sent."""
        fresh_data = [{"date": "2026-01-15", "highest": 10.5, "lowest": 8.2,
                       "average": 9.3, "volume": 1000000, "order_count": 150}]

        mock_resp = _make_mock_response(200, data=fresh_data, headers={
            "ETag": '"some_etag"',
        })

        captured_headers = {}

        def mock_get(*args, **kwargs):
            captured_headers.update(kwargs.get("headers", {}))
            return mock_resp

        client = ESIClient(
            config=mock_config,
            token=mock_token,
            rate_limiter=fast_rate_limiter,
            history_cache=None,  # Caching disabled
        )
        client._session = MagicMock()
        client._session.get = mock_get

        result = await client.fetch_market_history(
            region_id=10000003,
            type_ids=[34],
        )

        assert "If-None-Match" not in captured_headers
        assert "If-Modified-Since" not in captured_headers
        assert result.cache_hits == 0
        assert len(result.data) == 1
