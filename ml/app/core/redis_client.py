from redis.asyncio import Redis

from app.core.config import Settings, get_settings


def get_redis(settings: Settings | None = None) -> Redis:
    """Returns an async Redis client. Caller is responsible for closing it."""
    s = settings or get_settings()
    return Redis.from_url(s.redis_url, decode_responses=True)