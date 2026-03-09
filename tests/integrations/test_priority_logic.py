"""
Priority logic tests.

Rule: the stricter limit always wins.

App config:
  Middleware  →  limit=100, window=60  (global)
  /limited    →  limit=5,   window=60  (decorator, stricter)
  /unlimited  →  no decorator

Expected:
  - /limited is blocked after 5 requests by the decorator, not at 100
  - /unlimited is blocked only after 100 requests by middleware
  - Exhausting /limited does NOT exhaust /unlimited (independent keys)
"""

async def test_decorator_fires_before_middleware_limit(async_client):
    """Decorator limit (5) kicks in long before middleware limit (100)."""
    for i in range(5):
        r = await async_client.get("/limited")
        assert r.status_code == 200, f"Request {i+1} should be allowed"

    blocked = await async_client.get("/limited")
    assert blocked.status_code == 429


async def test_middleware_still_runs_on_unlimited_route(async_client):
    """Without a decorator, the middleware is the only gate."""
    response = await async_client.get("/unlimited")
    assert response.status_code == 200
    assert "X-RateLimit-Limit" in response.headers


async def test_exhausting_one_endpoint_does_not_block_another(async_client):
    """Independent Redis keys — /limited blocked ≠ /unlimited blocked."""
    for _ in range(5):
        await async_client.get("/limited")
    assert (await async_client.get("/limited")).status_code == 429
    assert (await async_client.get("/unlimited")).status_code == 200


async def test_decorator_limit_header_reflects_decorator_not_middleware(async_client):
    """
    On /limited the X-RateLimit-Limit should come from the decorator (5),
    not from the middleware (100).
    The last response to be modified wins — decorator wraps the response
    returned by the handler, middleware wraps the full response.
    Either way the 429 from the decorator carries limit=5.
    """
    for _ in range(5):
        await async_client.get("/limited")
    response = await async_client.get("/limited")
    assert response.status_code == 429
    assert response.headers["X-RateLimit-Limit"] == "5"


async def test_middleware_blocks_after_global_limit(redis_client):
    """
    App with middleware=3, decorator=10 — middleware fires first.
    This is the reverse priority case: global is stricter than endpoint.
    """
    from fastapi import FastAPI, Request
    from httpx   import AsyncClient, ASGITransport
    from pylimitx.core.limiter import RateLimiter
    from pylimitx.integrations.fastapi.middleware import RateLimitMiddleware
    from pylimitx.integrations.fastapi.decorator  import rate_limit

    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        redis_url = "redis://localhost:6379",
        limit     = 3,
        window    = 60,
    )
    app.state.pylimitx_limiter = RateLimiter(redis=redis_client)

    @app.get("/loose")
    @rate_limit(limit=10, window=60)
    async def loose(request: Request):
        return {"ok": True}

    async with AsyncClient(
        transport = ASGITransport(app=app),
        base_url  = "http://test",
    ) as client:
        for _ in range(3):
            r = await client.get("/loose")
            assert r.status_code == 200
        blocked = await client.get("/loose")
        assert blocked.status_code == 429
