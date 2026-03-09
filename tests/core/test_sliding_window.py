import pytest
from pylimitx.exceptions import RateLimitExceeded
from pylimitx.core.limiter import RateLimiter

async def test_first_request_allowed(limiter):
    result = await limiter.check(
        namespace  = "global",
        identifier = "1.2.3.4",
        limit      = 3,
        window     = 60,
    )
    assert result.allowed     == True
    assert result.remaining   == 2
    assert result.retry_after == -1


async def test_requests_count_down(limiter):
    for expected_remaining in [2, 1, 0]:
        result = await limiter.check(
            namespace  = "global",
            identifier = "1.2.3.4",
            limit      = 3,
            window     = 60,
        )
        assert result.remaining == expected_remaining


async def test_blocked_at_limit(limiter):
    for _ in range(3):
        await limiter.check(
            namespace  = "global",
            identifier = "1.2.3.4",
            limit      = 3,
            window     = 60,
        )

    with pytest.raises(RateLimitExceeded) as exc:
        await limiter.check(
            namespace  = "global",
            identifier = "1.2.3.4",
            limit      = 3,
            window     = 60,
        )

    assert exc.value.limit       == 3
    assert exc.value.remaining   == 0
    assert exc.value.retry_after  > 0


async def test_different_ips_are_independent(limiter):
    for _ in range(3):
        await limiter.check(
            namespace  = "global",
            identifier = "1.2.3.4",
            limit      = 3,
            window     = 60,
        )

    result = await limiter.check(
        namespace  = "global",
        identifier = "9.9.9.9",
        limit      = 3,
        window     = 60,
    )
    assert result.allowed == True


async def test_different_namespaces_are_independent(limiter):
    for _ in range(3):
        await limiter.check(
            namespace  = "POST_/login",
            identifier = "1.2.3.4",
            limit      = 3,
            window     = 60,
        )

    result = await limiter.check(
        namespace  = "POST_/register",
        identifier = "1.2.3.4",
        limit      = 3,
        window     = 60,
    )
    assert result.allowed == True


async def test_window_slides_old_requests_expire(limiter):
    import time

    # exhaust the limit
    for _ in range(3):
        await limiter.check(
            namespace  = "global",
            identifier = "1.2.3.4",
            limit      = 3,
            window     = 2,   # 2 second window so test runs fast
        )

    with pytest.raises(RateLimitExceeded):
        await limiter.check(
            namespace  = "global",
            identifier = "1.2.3.4",
            limit      = 3,
            window     = 2,
        )

    # wait for window to pass
    import asyncio
    await asyncio.sleep(3)

    result = await limiter.check(
        namespace  = "global",
        identifier = "1.2.3.4",
        limit      = 3,
        window     = 2,
    )
    assert result.allowed == True


async def test_redis_key_uses_pylimitx_prefix(redis_client, limiter):
    await limiter.check(
        namespace  = "global",
        identifier = "1.2.3.4",
        limit      = 3,
        window     = 60,
    )

    keys = await redis_client.keys("*")
    assert any(k.startswith("pylimitx:") for k in keys)
    assert not any(k.startswith("rl:") for k in keys)


async def test_fail_open_when_redis_down(redis_client):
    import redis.asyncio as aioredis

    bad_redis = aioredis.from_url(
        "redis://localhost:9999",
        decode_responses   = True,
        socket_timeout     = 0.1,
        socket_connect_timeout = 0.1,
    )
    bad_limiter = RateLimiter(redis=bad_redis, fail_open=True)

    result = await bad_limiter.check(
        namespace  = "global",
        identifier = "1.2.3.4",
        limit      = 3,
        window     = 60,
    )

    assert result.allowed    == True
    assert result.remaining  == -1
    await bad_redis.aclose()


