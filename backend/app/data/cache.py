"""
Simple in-memory TTL cache to avoid redundant API calls within a pipeline cycle.
Not distributed — just a dict with expiration timestamps.
"""

import time
from typing import Any, Optional


class TTLCache:
    def __init__(self, default_ttl: int = 300) -> None:
        """
        Args:
            default_ttl: Default time-to-live in seconds (default: 5 minutes).
        """
        self._store: dict[str, tuple[Any, float]] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Optional[Any]:
        if key not in self._store:
            return None
        value, expires_at = self._store[key]
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl = ttl if ttl is not None else self._default_ttl
        self._store[key] = (value, time.time() + ttl)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None


# Module-level cache shared across a pipeline run
pipeline_cache = TTLCache(default_ttl=600)  # 10 min TTL — one pipeline cycle
