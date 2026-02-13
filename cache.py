"""
HTTP conditional request cache for ESI market history.

Stores ETag/Last-Modified headers and response data per type_id,
enabling 304 Not Modified responses on subsequent requests.
"""

import json
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A single cached history response for one type_id."""
    etag: str = ""
    last_modified: str = ""
    data: list[dict] = field(default_factory=list)


class HistoryCache:
    """Manages a JSON file cache of ESI market history responses.

    Each type_id maps to its ETag, Last-Modified, and response data.
    On subsequent requests, conditional headers trigger HTTP 304 when
    data hasn't changed, avoiding redundant downloads.

    Usage::

        cache = HistoryCache(Path("data/history_cache.json"))
        cache.load()
        headers = cache.get_conditional_headers(34)
        # ... make request with headers ...
        if response.status == 304:
            data = cache.get(34).data
        else:
            cache.put(34, etag, last_modified, data)
        cache.save()
    """

    def __init__(self, path: Path):
        self._path = path
        self._entries: dict[int, CacheEntry] = {}

    @property
    def entry_count(self) -> int:
        """Number of cached type_ids."""
        return len(self._entries)

    def load(self) -> None:
        """Load cache from disk. Tolerant of missing or corrupt files."""
        if not self._path.exists():
            logger.info(f"No cache file at {self._path}, starting fresh")
            return

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            for key, value in raw.items():
                if not isinstance(value, dict):
                    logger.warning(f"Skipping corrupt cache entry for type_id {key}")
                    continue
                self._entries[int(key)] = CacheEntry(
                    etag=value.get("etag", ""),
                    last_modified=value.get("last_modified", ""),
                    data=value.get("data", []),
                )
            logger.info(f"Loaded cache with {len(self._entries)} entries from {self._path}")
        except (json.JSONDecodeError, ValueError, TypeError, KeyError) as e:
            logger.warning(f"Corrupt cache file {self._path}, starting fresh: {e}")
            self._entries.clear()

    def save(self) -> None:
        """Write cache to disk atomically (temp file + rename)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

        serializable = {}
        for type_id, entry in self._entries.items():
            serializable[str(type_id)] = {
                "etag": entry.etag,
                "last_modified": entry.last_modified,
                "data": entry.data,
            }

        # Atomic write: write to temp file in same directory, then rename
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=self._path.parent,
                prefix=".cache_",
                suffix=".tmp",
            )
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(serializable, f, separators=(",", ":"))
            Path(tmp_path).replace(self._path)
            logger.info(f"Saved cache with {len(self._entries)} entries to {self._path}")
        except OSError as e:
            logger.error(f"Failed to save cache: {e}")
            # Clean up temp file if it exists
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass

    def get(self, type_id: int) -> CacheEntry | None:
        """Get cached entry for a type_id, or None if not cached."""
        return self._entries.get(type_id)

    def put(self, type_id: int, etag: str, last_modified: str, data: list[dict]) -> None:
        """Store or update a cache entry."""
        self._entries[type_id] = CacheEntry(
            etag=etag,
            last_modified=last_modified,
            data=data,
        )

    def has_data(self, type_id: int) -> bool:
        """True only when cached response records exist for this type_id."""
        entry = self._entries.get(type_id)
        return entry is not None and len(entry.data) > 0

    def get_conditional_headers(self, type_id: int) -> dict[str, str]:
        """Build If-None-Match / If-Modified-Since headers for a type_id.

        Returns empty dict when:
        - No cache entry exists
        - Metadata exists but data is missing (safety valve: forces fresh fetch)
        """
        entry = self._entries.get(type_id)
        if entry is None:
            return {}

        # Safety valve: if we have headers but no data, don't send conditional
        # headers — force a fresh fetch to repopulate the data
        if not entry.data:
            return {}

        headers: dict[str, str] = {}
        if entry.etag:
            headers["If-None-Match"] = entry.etag
        if entry.last_modified:
            headers["If-Modified-Since"] = entry.last_modified
        return headers
