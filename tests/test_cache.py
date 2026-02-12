"""Unit tests for HistoryCache."""

import json

import pytest

from cache import HistoryCache, CacheEntry


class TestHistoryCacheLoadSave:
    """Tests for load/save operations."""

    def test_load_missing_file(self, tmp_cache_path):
        """Loading a non-existent file should start with empty cache."""
        cache = HistoryCache(tmp_cache_path)
        cache.load()
        assert cache.entry_count == 0

    def test_load_empty_file(self, tmp_cache_path):
        """Loading an empty JSON object should result in empty cache."""
        tmp_cache_path.write_text("{}")
        cache = HistoryCache(tmp_cache_path)
        cache.load()
        assert cache.entry_count == 0

    def test_save_load_roundtrip(self, tmp_cache_path, sample_history_data, sample_etag, sample_last_modified):
        """Data saved should be loadable and identical."""
        cache = HistoryCache(tmp_cache_path)
        cache.put(34, sample_etag, sample_last_modified, sample_history_data)
        cache.save()

        cache2 = HistoryCache(tmp_cache_path)
        cache2.load()
        assert cache2.entry_count == 1

        entry = cache2.get(34)
        assert entry is not None
        assert entry.etag == sample_etag
        assert entry.last_modified == sample_last_modified
        assert len(entry.data) == 2
        assert entry.data[0]["date"] == "2026-01-15"

    def test_corrupt_file_handling(self, tmp_cache_path):
        """Corrupt JSON should not crash; cache starts fresh."""
        tmp_cache_path.write_text("not valid json {{{")
        cache = HistoryCache(tmp_cache_path)
        cache.load()
        assert cache.entry_count == 0

    def test_corrupt_structure_handling(self, tmp_cache_path):
        """JSON with wrong structure should not crash."""
        tmp_cache_path.write_text(json.dumps({"34": "not_a_dict"}))
        cache = HistoryCache(tmp_cache_path)
        cache.load()
        # Should handle gracefully (either skip or start fresh)
        # The current implementation will fail on .get("etag") on a string

    def test_save_creates_parent_directory(self, tmp_path):
        """Save should create parent directories if they don't exist."""
        nested_path = tmp_path / "a" / "b" / "cache.json"
        cache = HistoryCache(nested_path)
        cache.put(34, '"etag"', "last-mod", [{"test": 1}])
        cache.save()
        assert nested_path.exists()


class TestHistoryCacheGetPut:
    """Tests for get/put/has_data operations."""

    def test_get_nonexistent(self, tmp_cache_path):
        """Getting a non-existent entry returns None."""
        cache = HistoryCache(tmp_cache_path)
        assert cache.get(99999) is None

    def test_put_and_get(self, tmp_cache_path, sample_history_data, sample_etag, sample_last_modified):
        """Put then get should return the same data."""
        cache = HistoryCache(tmp_cache_path)
        cache.put(34, sample_etag, sample_last_modified, sample_history_data)

        entry = cache.get(34)
        assert entry is not None
        assert entry.etag == sample_etag
        assert entry.last_modified == sample_last_modified
        assert entry.data == sample_history_data

    def test_put_overwrites(self, tmp_cache_path):
        """Putting the same type_id twice should overwrite."""
        cache = HistoryCache(tmp_cache_path)
        cache.put(34, '"old"', "old-date", [{"old": True}])
        cache.put(34, '"new"', "new-date", [{"new": True}])

        entry = cache.get(34)
        assert entry.etag == '"new"'
        assert entry.data == [{"new": True}]

    def test_has_data_with_data(self, tmp_cache_path, sample_history_data):
        """has_data should be True when data records exist."""
        cache = HistoryCache(tmp_cache_path)
        cache.put(34, '"etag"', "last-mod", sample_history_data)
        assert cache.has_data(34) is True

    def test_has_data_empty_list(self, tmp_cache_path):
        """has_data should be False when data is an empty list."""
        cache = HistoryCache(tmp_cache_path)
        cache.put(34, '"etag"', "last-mod", [])
        assert cache.has_data(34) is False

    def test_has_data_missing_entry(self, tmp_cache_path):
        """has_data should be False for non-existent type_id."""
        cache = HistoryCache(tmp_cache_path)
        assert cache.has_data(99999) is False

    def test_entry_count(self, tmp_cache_path):
        """entry_count should reflect number of stored items."""
        cache = HistoryCache(tmp_cache_path)
        assert cache.entry_count == 0
        cache.put(34, "", "", [])
        assert cache.entry_count == 1
        cache.put(35, "", "", [])
        assert cache.entry_count == 2
        cache.put(34, "", "", [])  # overwrite
        assert cache.entry_count == 2


class TestConditionalHeaders:
    """Tests for get_conditional_headers."""

    def test_headers_with_full_entry(self, tmp_cache_path, sample_history_data, sample_etag, sample_last_modified):
        """Should return both If-None-Match and If-Modified-Since when available."""
        cache = HistoryCache(tmp_cache_path)
        cache.put(34, sample_etag, sample_last_modified, sample_history_data)

        headers = cache.get_conditional_headers(34)
        assert headers["If-None-Match"] == sample_etag
        assert headers["If-Modified-Since"] == sample_last_modified

    def test_headers_etag_only(self, tmp_cache_path, sample_history_data, sample_etag):
        """Should return only If-None-Match when last_modified is empty."""
        cache = HistoryCache(tmp_cache_path)
        cache.put(34, sample_etag, "", sample_history_data)

        headers = cache.get_conditional_headers(34)
        assert "If-None-Match" in headers
        assert "If-Modified-Since" not in headers

    def test_headers_last_modified_only(self, tmp_cache_path, sample_history_data, sample_last_modified):
        """Should return only If-Modified-Since when etag is empty."""
        cache = HistoryCache(tmp_cache_path)
        cache.put(34, "", sample_last_modified, sample_history_data)

        headers = cache.get_conditional_headers(34)
        assert "If-None-Match" not in headers
        assert "If-Modified-Since" in headers

    def test_headers_missing_entry(self, tmp_cache_path):
        """Should return empty dict for non-existent type_id."""
        cache = HistoryCache(tmp_cache_path)
        assert cache.get_conditional_headers(99999) == {}

    def test_safety_valve_no_data(self, tmp_cache_path, sample_etag, sample_last_modified):
        """Should return empty dict when entry exists but data is empty.

        This is the safety valve: if we somehow have metadata but no data,
        we force a fresh fetch by not sending conditional headers.
        """
        cache = HistoryCache(tmp_cache_path)
        cache.put(34, sample_etag, sample_last_modified, [])

        headers = cache.get_conditional_headers(34)
        assert headers == {}
