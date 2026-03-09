import pytest
import redis.asyncio as aioredis

from pylimitx.core.limiter         import RateLimiter
from pylimitx.core.circuit_breaker import CircuitBreaker
from pylimitx.core.lock            import RedisLock

REDIS_URL = "redis://localhost:6379"


@pytest.fixture
async def redis_client():
    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture
async def limiter(redis_client):
    return RateLimiter(redis=redis_client)


@pytest.fixture
def circuit_breaker():
    return CircuitBreaker(failure_threshold=3, recovery_timeout=30)


@pytest.fixture
async def lock(redis_client):
    return RedisLock(redis=redis_client)