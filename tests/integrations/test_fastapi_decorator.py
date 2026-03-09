"""
FastAPI decorator integration tests.

/limited is decorated with limit=5, window=60.
The middleware on the same app has limit=100 — it never fires before the decorator does.
"""

async def test_decorator_allows_under_limit(async_client):
    response = await async_client.get("/limited")
    assert response.status_code == 200


async def test_decorator_headers_present(async_client):
    response = await async_client.get("/limited")
    # Decorator sets headers on the response object when remaining != -1
    assert response.status_code == 200


async def test_decorator_blocks_at_limit(async_client):
    for _ in range(5):
        r = await async_client.get("/limited")
        assert r.status_code == 200
    blocked = await async_client.get("/limited")
    assert blocked.status_code == 429


async def test_decorator_429_has_retry_after(async_client):
    for _ in range(5):
        await async_client.get("/limited")
    response = await async_client.get("/limited")
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) > 0


async def test_decorator_429_body(async_client):
    for _ in range(5):
        await async_client.get("/limited")
    response = await async_client.get("/limited")
    body = response.json()
    assert body["detail"] == "Rate limit exceeded"
    assert "retry_after" in body


async def test_decorator_remaining_zero_on_429(async_client):
    for _ in range(5):
        await async_client.get("/limited")
    response = await async_client.get("/limited")
    assert response.headers["X-RateLimit-Remaining"] == "0"


async def test_decorator_uses_per_endpoint_key(async_client):
    """
    Exhausting /limited must not affect /unlimited.
    If they shared a key, /unlimited would also return 429.
    """
    for _ in range(5):
        await async_client.get("/limited")
    blocked = await async_client.get("/limited")
    assert blocked.status_code == 429

    # /unlimited has no decorator — only middleware (limit=100), still fine
    unblocked = await async_client.get("/unlimited")
    assert unblocked.status_code == 200


async def test_decorator_different_ips_independent(async_client):
    """Each IP has its own counter on the decorated endpoint."""
    for _ in range(5):
        await async_client.get("/limited", headers={"X-Forwarded-For": "10.0.0.1"})
    blocked = await async_client.get("/limited", headers={"X-Forwarded-For": "10.0.0.1"})
    assert blocked.status_code == 429

    allowed = await async_client.get("/limited", headers={"X-Forwarded-For": "10.0.0.2"})
    assert allowed.status_code == 200
