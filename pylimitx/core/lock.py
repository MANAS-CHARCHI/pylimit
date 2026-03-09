import time
import uuid

from redis.asyncio import Redis

class RedisLock:
    def __init__(self, redis: Redis, ttl_ms: int = 50):
        self.redis  = redis
        self.ttl_ms = ttl_ms
    
    async def acquire(self, key: str) -> str | None:
        token = str(uuid.uuid4())
        acquired = await self.redis.set(
            key,
            token,
            px=self.ttl_ms,
            nx=True
        )
        if acquired:
            return token
        return None
    
    async def release(self, key: str, token: str) -> None:
        lua = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            return redis.call('DEL', KEYS[1])
        end
        return 0
        """
        await self.redis.eval(lua, 1, key, token)

    async def __aenter__(self):
        raise NotImplementedError(
            "Use acquire() and release() directly"
        )