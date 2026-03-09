"""
Django decorator integration tests.

The decorator reads the limiter from request.pylimitx_limiter.
We inject it manually — the same way a real Django middleware would.
"""
import pytest
from django.http  import HttpResponse
from django.test  import RequestFactory

from pylimitx.core.limiter                    import RateLimiter
from pylimitx.integrations.django.decorator  import django_rate_limit

factory = RequestFactory()


def make_request(ip: str = "1.2.3.4", path: str = "/api/", method: str = "GET"):
    r = factory.generic(method, path)
    r.META["REMOTE_ADDR"] = ip
    return r


def inject_limiter(request, limiter: RateLimiter):
    request.pylimitx_limiter = limiter
    return request


# ── sync view ─────────────────────────────────────────────────────────────────

def test_sync_view_allowed(redis_client):
    limiter = RateLimiter(redis=redis_client)

    @django_rate_limit(limit=5, window=60)
    def view(request):
        return HttpResponse("ok")

    request = inject_limiter(make_request(), limiter)
    response = view(request)
    assert response.status_code == 200


def test_sync_view_blocked_at_limit(redis_client):
    limiter = RateLimiter(redis=redis_client)

    @django_rate_limit(limit=3, window=60)
    def view(request):
        return HttpResponse("ok")

    for _ in range(3):
        view(inject_limiter(make_request(ip="2.2.2.2"), limiter))

    response = view(inject_limiter(make_request(ip="2.2.2.2"), limiter))
    assert response.status_code == 429


def test_sync_view_429_has_retry_after(redis_client):
    limiter = RateLimiter(redis=redis_client)

    @django_rate_limit(limit=2, window=60)
    def view(request):
        return HttpResponse("ok")

    for _ in range(2):
        view(inject_limiter(make_request(ip="3.3.3.3"), limiter))

    response = view(inject_limiter(make_request(ip="3.3.3.3"), limiter))
    assert response.status_code == 429
    assert "Retry-After" in response
    assert int(response["Retry-After"]) > 0


def test_sync_view_no_limiter_passes_through(redis_client):
    """If limiter not injected, decorator is a no-op — view runs normally."""
    @django_rate_limit(limit=1, window=60)
    def view(request):
        return HttpResponse("ok")

    request = make_request()
    # pylimitx_limiter NOT set
    response = view(request)
    assert response.status_code == 200


def test_sync_different_ips_independent(redis_client):
    limiter = RateLimiter(redis=redis_client)

    @django_rate_limit(limit=2, window=60)
    def view(request):
        return HttpResponse("ok")

    for _ in range(2):
        view(inject_limiter(make_request(ip="4.4.4.4"), limiter))
    assert view(inject_limiter(make_request(ip="4.4.4.4"), limiter)).status_code == 429
    assert view(inject_limiter(make_request(ip="5.5.5.5"), limiter)).status_code == 200


# ── async view ────────────────────────────────────────────────────────────────

async def test_async_view_allowed(redis_client):
    limiter = RateLimiter(redis=redis_client)

    @django_rate_limit(limit=5, window=60)
    async def view(request):
        return HttpResponse("ok")

    request = inject_limiter(make_request(ip="6.6.6.6"), limiter)
    response = await view(request)
    assert response.status_code == 200


async def test_async_view_blocked(redis_client):
    limiter = RateLimiter(redis=redis_client)

    @django_rate_limit(limit=2, window=60)
    async def view(request):
        return HttpResponse("ok")

    for _ in range(2):
        await view(inject_limiter(make_request(ip="7.7.7.7"), limiter))

    response = await view(inject_limiter(make_request(ip="7.7.7.7"), limiter))
    assert response.status_code == 429


async def test_async_view_429_body(redis_client):
    import json
    limiter = RateLimiter(redis=redis_client)

    @django_rate_limit(limit=1, window=60)
    async def view(request):
        return HttpResponse("ok")

    await view(inject_limiter(make_request(ip="8.8.8.8"), limiter))
    response = await view(inject_limiter(make_request(ip="8.8.8.8"), limiter))
    assert response.status_code == 429
    body = json.loads(response.content)
    assert "retry_after" in body


async def test_async_view_headers(redis_client):
    limiter = RateLimiter(redis=redis_client)

    @django_rate_limit(limit=5, window=60)
    async def view(request):
        return HttpResponse("ok")

    response = await view(inject_limiter(make_request(ip="9.9.9.9"), limiter))
    assert response.status_code == 200
    assert "X-RateLimit-Limit"     in response
    assert "X-RateLimit-Remaining" in response
