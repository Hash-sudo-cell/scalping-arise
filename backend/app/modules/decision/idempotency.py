"""
Scalping Arise — Idempotency Cache

Ensures that repeated evaluations with the same inputs produce
the same outputs, preventing duplicate processing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Optional

from app.modules.decision.models import FinalDecision

logger = logging.getLogger(__name__)


class IdempotencyCache:
    """
    Bounded LRU cache for idempotency enforcement.

    Maps input hashes to decision IDs. If a matching hash is found,
    the cached decision ID is returned instead of re-evaluating.
    """

    def __init__(
        self,
        max_size: int = 5000,
        ttl_seconds: int = 600,
    ) -> None:
        self._cache: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._hits = 0
        self._misses = 0

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses

    @property
    def size(self) -> int:
        return len(self._cache)

    def compute_key(
        self,
        signal_id: str,
        plan_id: Optional[str] = None,
        intelligence_id: Optional[str] = None,
    ) -> str:
        """
        Compute a deterministic idempotency key.

        Same inputs always produce the same key.
        """
        payload = {
            "signal_id": signal_id,
            "plan_id": plan_id or "",
            "intelligence_id": intelligence_id or "",
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def lookup(self, key: str) -> Optional[str]:
        """
        Look up a decision ID by idempotency key.

        Returns the decision_id if found and not expired, None otherwise.
        """
        if key not in self._cache:
            self._misses += 1
            return None

        decision_id, created_at = self._cache[key]

        # Check TTL
        if time.time() - created_at > self._ttl_seconds:
            # Expired — remove it
            del self._cache[key]
            self._misses += 1
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        self._hits += 1
        return decision_id

    def store(self, key: str, decision_id: str) -> None:
        """
        Store a decision ID in the cache.

        Evicts oldest entries if the cache is full.
        """
        # If key already exists, update it
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = (decision_id, time.time())
            return

        # Evict oldest if at capacity
        while len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)

        self._cache[key] = (decision_id, time.time())

    def invalidate(self, key: str) -> bool:
        """
        Remove a specific key from the cache.

        Returns True if the key was found and removed.
        """
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries from the cache.

        Returns the number of entries removed.
        """
        now = time.time()
        expired_keys = [
            key for key, (_, created_at) in self._cache.items()
            if now - created_at > self._ttl_seconds
        ]
        for key in expired_keys:
            del self._cache[key]
        return len(expired_keys)

    def clear(self) -> int:
        """Clear the entire cache. Returns the number of entries removed."""
        count = len(self._cache)
        self._cache.clear()
        return count

    def get_stats(self) -> dict:
        """Get cache statistics."""
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
            "ttl_seconds": self._ttl_seconds,
        }
