"""Shared fixtures for ESI Market Tool tests."""

import sys
from pathlib import Path

import pytest

# Add project root to path so we can import modules directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def tmp_cache_path(tmp_path):
    """Provide a temporary path for cache files."""
    return tmp_path / "history_cache.json"


@pytest.fixture
def sample_type_ids():
    """Common type IDs used in tests."""
    return [34, 35, 36]


@pytest.fixture
def sample_history_data():
    """Sample ESI market history response data for type_id 34."""
    return [
        {
            "date": "2026-01-15",
            "type_id": 34,
            "highest": 10.5,
            "lowest": 8.2,
            "average": 9.3,
            "volume": 1000000,
            "order_count": 150,
        },
        {
            "date": "2026-01-14",
            "type_id": 34,
            "highest": 10.8,
            "lowest": 8.0,
            "average": 9.4,
            "volume": 950000,
            "order_count": 140,
        },
    ]


@pytest.fixture
def sample_etag():
    return '"abc123def456"'


@pytest.fixture
def sample_last_modified():
    return "Thu, 15 Jan 2026 12:00:00 GMT"
