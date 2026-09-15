import logging
from typing import Optional
import redis.asyncio as aioredis
from app.config import settings

logger = logging.getLogger(__name__)

redis_pool: Optional[aioredis.Redis] = None


async def get_redis_client() -> aioredis.Redis:
    global redis_pool
    if redis_pool is None:
        redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
        )
    return redis_pool


async def close_redis():
    global redis_pool
    if redis_pool:
        await redis_pool.close()
        redis_pool = None


class IdempotencyLock:
    def __init__(self, redis: aioredis.Redis):
        self.redis = redis

    async def acquire(self, merchant_id: str, idempotency_key: str, request_hash: str, ttl_seconds: int = 60) -> bool:
        """
        Fast-path lock using Redis SET NX EX.
        Returns True if acquired (first request), False if already in-flight or held.
        """
        key = f"idem:{merchant_id}:{idempotency_key}"
        try:
            return bool(await self.redis.set(key, request_hash, nx=True, ex=ttl_seconds))
        except Exception as e:
            logger.warning(f"Redis idempotency lock failure: {e}. Falling back to durable DB lock.")
            return True  # Fallback to DB durable claim on Redis failure
