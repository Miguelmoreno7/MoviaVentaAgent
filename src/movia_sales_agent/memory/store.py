from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional

from movia_sales_agent.config.settings import Settings


class MemoryStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._buffers: Dict[str, Deque[Dict[str, Any]]] = defaultdict(lambda: deque(maxlen=12))
        self._cache: Dict[str, Any] = {}
        self._redis = None
        if settings.redis_url:
            try:
                import redis

                self._redis = redis.from_url(settings.redis_url, decode_responses=True)
            except Exception:
                self._redis = None

    def _disable_redis(self) -> None:
        self._redis = None

    def add_recent(self, key: str, message: Dict[str, Any]) -> None:
        message = {**message, "ts": time.time()}
        if self._redis:
            redis_key = f"movia:recent:{key}"
            try:
                self._redis.lpush(redis_key, json.dumps(message, ensure_ascii=False))
                self._redis.ltrim(redis_key, 0, 11)
                self._redis.expire(redis_key, 60 * 60 * 24)
                return
            except Exception:
                self._disable_redis()
        self._buffers[key].append(message)

    def recent(self, key: str) -> List[Dict[str, Any]]:
        if self._redis:
            try:
                rows = self._redis.lrange(f"movia:recent:{key}", 0, 11)
                return [json.loads(row) for row in reversed(rows)]
            except Exception:
                self._disable_redis()
        return list(self._buffers[key])

    def get_cache(self, key: str) -> Optional[Any]:
        if self._redis:
            try:
                value = self._redis.get(f"movia:cache:{key}")
                return json.loads(value) if value else None
            except Exception:
                self._disable_redis()
        item = self._cache.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at < time.time():
            self._cache.pop(key, None)
            return None
        return value

    def set_cache(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        if self._redis:
            try:
                self._redis.setex(
                    f"movia:cache:{key}",
                    ttl_seconds,
                    json.dumps(value, ensure_ascii=False),
                )
                return
            except Exception:
                self._disable_redis()
        self._cache[key] = (time.time() + ttl_seconds, value)
