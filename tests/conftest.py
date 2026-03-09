import pytest
import redis.asyncio as aioredis

from fastapi import FastAPI, Request
from httpx  import AsyncClient, ASGITransport

from pylimitx.core.limiter         import RateLimiter
from pylimitx.core.circuit_breaker import CircuitBreaker
from pylimitx.core.lock            import RedisLock
from pylimitx.integrations.fastapi.middleware import RateLimitMiddleware
from pylimitx.integrations.fastapi.decorator  import rate_limit

REDIS_URL = "redis://localhost:6379"


@pytest.fixture
async def redis_client():
    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    await client.flushdb()
    yield client
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

#--- FastAPI test app-----------------------

@pytest.fixture
async def fastapi_app(redis_client):
    """
    Middleware:   global limit = 100 / 60 s
    /limited   → decorator limit = 5 / 60 s
    /unlimited → no decorator, only middleware applies
    """
    app = FastAPI()

    app.add_middleware(
        RateLimitMiddleware,
        redis_url = REDIS_URL,
        limit     = 100,
        window    = 60,
    )

    # Decorator reads limiter from app.state
    app.state.pylimitx_limiter = RateLimiter(redis=redis_client)

    @app.get("/limited")
    @rate_limit(limit=5, window=60)
    async def limited_route(request: Request):
        return {"ok": True}

    @app.get("/unlimited")
    async def unlimited_route():
        return {"ok": True}

    return app

@pytest.fixture
async def async_client(fastapi_app):
    async with AsyncClient(
        transport = ASGITransport(app=fastapi_app),
        base_url  = "http://test",
    ) as client:
        yield client