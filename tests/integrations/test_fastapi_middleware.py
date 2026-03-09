"""
FastAPI middleware integration tests.

The middleware is configured with limit=100, window=60.
These tests hit /unlimited (no decorator) so only the middleware check runs.
"""
import pytest


# ── allowed requests ──────────────────────────────────────────────────────────

async def test_request_allowed_under_limit(async_client):
    response = await async_client.get("/unlimited")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


async def test_response_headers_present_on_allowed(async_client):
    response = await async_client.get("/unlimited")
    assert "X-RateLimit-Limit"     in response.headers
    assert "X-RateLimit-Remaining" in response.headers


async def test_limit_header_matches_config(async_client):
    response = await async_client.get("/unlimited")
    assert response.headers["X-RateLimit-Limit"] == "100"


async def test_remaining_decrements_on_each_request(async_client):
    r1 = await async_client.get("/unlimited")
    r2 = await async_client.get("/unlimited")
    remaining_1 = int(r1.headers["X-RateLimit-Remaining"])
    remaining_2 = int(r2.headers["X-RateLimit-Remaining"])
    assert remaining_2 == remaining_1 - 1


async def test_retry_after_absent_on_allowed(async_client):
    response = await async_client.get("/unlimited")
    assert "Retry-After" not in response.headers


# ── blocked requests ──────────────────────────────────────────────────────────

@pytest.fixture
async def tight_client(redis_client):
    """Separate app with limit=3 so we can exhaust it cheaply."""
    from fastapi import FastAPI
    from httpx   import AsyncClient, ASGITransport
    from pylimitx.integrations.fastapi.middleware import RateLimitMiddleware

    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        redis_url = "redis://localhost:6379",
        limit     = 3,
        window    = 60,
    )

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    async with AsyncClient(
        transport = ASGITransport(app=app),
        base_url  = "http://test",
    ) as client:
        yield client


async def test_request_blocked_when_limit_exceeded(tight_client):
    for _ in range(3):
        await tight_client.get("/ping")
    response = await tight_client.get("/ping")
    assert response.status_code == 429


async def test_429_body_contains_detail(tight_client):
    for _ in range(3):
        await tight_client.get("/ping")
    response = await tight_client.get("/ping")
    body = response.json()
    assert "detail" in body
    assert "retry_after" in body


async def test_retry_after_header_on_429(tight_client):
    for _ in range(3):
        await tight_client.get("/ping")
    response = await tight_client.get("/ping")
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) > 0


async def test_remaining_is_zero_on_429(tight_client):
    for _ in range(3):
        await tight_client.get("/ping")
    response = await tight_client.get("/ping")
    assert response.headers["X-RateLimit-Remaining"] == "0"


async def test_different_ips_have_independent_counters(redis_client):
    """IP 1.1.1.1 exhausted should not affect IP 2.2.2.2."""
    from fastapi import FastAPI
    from httpx   import AsyncClient, ASGITransport
    from pylimitx.integrations.fastapi.middleware import RateLimitMiddleware

    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        redis_url = "redis://localhost:6379",
        limit     = 2,
        window    = 60,
    )

    @app.get("/check")
    async def check():
        return {"ok": True}

    async with AsyncClient(
        transport = ASGITransport(app=app),
        base_url  = "http://test",
    ) as client:
        for _ in range(2):
            await client.get("/check", headers={"X-Forwarded-For": "1.1.1.1"})
        blocked = await client.get("/check", headers={"X-Forwarded-For": "1.1.1.1"})
        assert blocked.status_code == 429

        allowed = await client.get("/check", headers={"X-Forwarded-For": "2.2.2.2"})
        assert allowed.status_code == 200
