"""
Django middleware integration tests.

The middleware is instantiated directly (not via MIDDLEWARE setting) so we
can control limit / window per test without touching settings.

Pattern:
    middleware = DjangoRateLimitMiddleware(view_fn, redis_url=..., limit=N, window=60)
    response   = middleware(request)          ← sync path
"""
import pytest
from django.http           import HttpResponse
from django.test           import RequestFactory

from pylimitx.integrations.django.middleware import DjangoRateLimitMiddleware

REDIS_URL = "redis://localhost:6379"
factory   = RequestFactory()


def make_middleware(limit: int, window: int = 60):
    """Return a configured middleware wrapping a trivial sync view."""
    def view(request):
        return HttpResponse("ok", status=200)

    return DjangoRateLimitMiddleware(
        view,
        redis_url = REDIS_URL,
        limit     = limit,
        window    = window,
    )


# ── allowed ───────────────────────────────────────────────────────────────────

def test_request_allowed_under_limit(redis_client):
    mw      = make_middleware(limit=10)
    request = factory.get("/test/")
    request.META["REMOTE_ADDR"] = "1.2.3.4"
    response = mw(request)
    assert response.status_code == 200


def test_rate_limit_headers_on_allowed(redis_client):
    mw      = make_middleware(limit=10)
    request = factory.get("/test/")
    request.META["REMOTE_ADDR"] = "1.2.3.4"
    response = mw(request)
    assert "X-RateLimit-Limit"     in response
    assert "X-RateLimit-Remaining" in response


def test_limit_header_value(redis_client):
    mw      = make_middleware(limit=10)
    request = factory.get("/test/")
    request.META["REMOTE_ADDR"] = "1.2.3.4"
    response = mw(request)
    assert response["X-RateLimit-Limit"] == "10"


def test_remaining_decrements(redis_client):
    mw = make_middleware(limit=10)

    def req():
        r = factory.get("/test/")
        r.META["REMOTE_ADDR"] = "1.2.3.4"
        return mw(r)

    r1 = req()
    r2 = req()
    assert int(r2["X-RateLimit-Remaining"]) == int(r1["X-RateLimit-Remaining"]) - 1


# ── blocked ───────────────────────────────────────────────────────────────────

def test_request_blocked_at_limit(redis_client):
    mw = make_middleware(limit=3)

    for _ in range(3):
        r = factory.get("/test/")
        r.META["REMOTE_ADDR"] = "5.5.5.5"
        mw(r)

    r = factory.get("/test/")
    r.META["REMOTE_ADDR"] = "5.5.5.5"
    response = mw(r)
    assert response.status_code == 429


def test_retry_after_header_on_429(redis_client):
    mw = make_middleware(limit=2)

    for _ in range(2):
        r = factory.get("/test/")
        r.META["REMOTE_ADDR"] = "6.6.6.6"
        mw(r)

    r = factory.get("/test/")
    r.META["REMOTE_ADDR"] = "6.6.6.6"
    response = mw(r)
    assert response.status_code == 429
    assert "Retry-After" in response
    assert int(response["Retry-After"]) > 0


def test_remaining_zero_on_429(redis_client):
    mw = make_middleware(limit=2)

    for _ in range(2):
        r = factory.get("/test/")
        r.META["REMOTE_ADDR"] = "7.7.7.7"
        mw(r)

    r = factory.get("/test/")
    r.META["REMOTE_ADDR"] = "7.7.7.7"
    response = mw(r)
    assert response["X-RateLimit-Remaining"] == "0"


def test_different_ips_independent(redis_client):
    mw = make_middleware(limit=2)

    for _ in range(2):
        r = factory.get("/test/")
        r.META["REMOTE_ADDR"] = "8.8.8.8"
        mw(r)

    blocked_req = factory.get("/test/")
    blocked_req.META["REMOTE_ADDR"] = "8.8.8.8"
    assert mw(blocked_req).status_code == 429

    allowed_req = factory.get("/test/")
    allowed_req.META["REMOTE_ADDR"] = "9.9.9.9"
    assert mw(allowed_req).status_code == 200


# ── async view ────────────────────────────────────────────────────────────────

async def test_async_view_allowed(redis_client):
    """Middleware detects async get_response and uses __acall__."""
    from django.http import HttpResponse

    async def async_view(request):
        return HttpResponse("async ok", status=200)

    mw = DjangoRateLimitMiddleware(
        async_view,
        redis_url = REDIS_URL,
        limit     = 10,
        window    = 60,
    )
    r = factory.get("/async/")
    r.META["REMOTE_ADDR"] = "3.3.3.3"
    response = await mw(r)
    assert response.status_code == 200


async def test_async_view_blocked(redis_client):
    from django.http import HttpResponse

    async def async_view(request):
        return HttpResponse("async ok", status=200)

    mw = DjangoRateLimitMiddleware(
        async_view,
        redis_url = REDIS_URL,
        limit     = 2,
        window    = 60,
    )

    for _ in range(2):
        r = factory.get("/async/")
        r.META["REMOTE_ADDR"] = "4.4.4.4"
        await mw(r)

    r = factory.get("/async/")
    r.META["REMOTE_ADDR"] = "4.4.4.4"
    response = await mw(r)
    assert response.status_code == 429
