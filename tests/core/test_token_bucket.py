import pytest
import redis.asyncio as aioredis

from pylimitx.core.limiter import RateLimiter
from pylimitx.exceptions   import RateLimitExceeded


async def test_first_request_allowed(limiter):
    result = await limiter.check(
        namespace  = "global",
        identifier = "1.2.3.4",
        limit      = 5,
        window     = 60,
        algorithm  = "token_bucket",
    )
    assert result.allowed     == True
    assert result.remaining   == 4
    assert result.retry_after == -1


async def test_full_burst_allowed(limiter):
    for _ in range(5):
        result = await limiter.check(
            namespace  = "global",
            identifier = "1.2.3.4",
            limit      = 5,
            window     = 60,
            algorithm  = "token_bucket",
        )
        assert result.allowed == True


async def test_blocked_after_burst(limiter):
    for _ in range(5):
        await limiter.check(
            namespace  = "global",
            identifier = "1.2.3.4",
            limit      = 5,
            window     = 60,
            algorithm  = "token_bucket",
        )

    with pytest.raises(RateLimitExceeded) as exc:
        await limiter.check(
            namespace  = "global",
            identifier = "1.2.3.4",
            limit      = 5,
            window     = 60,
            algorithm  = "token_bucket",
        )

    assert exc.value.limit      == 5
    assert exc.value.remaining  == 0
    assert exc.value.retry_after > 0


async def test_tokens_refill_over_time(limiter):
    import asyncio

    for _ in range(5):
        await limiter.check(
            namespace  = "global",
            identifier = "1.2.3.4",
            limit      = 5,
            window     = 5,
            algorithm  = "token_bucket",
        )

    with pytest.raises(RateLimitExceeded):
        await limiter.check(
            namespace  = "global",
            identifier = "1.2.3.4",
            limit      = 5,
            window     = 5,
            algorithm  = "token_bucket",
        )

    await asyncio.sleep(2)

    result = await limiter.check(
        namespace  = "global",
        identifier = "1.2.3.4",
        limit      = 5,
        window     = 5,
        algorithm  = "token_bucket",
    )
    assert result.allowed == True


async def test_tokens_capped_at_capacity(limiter):
    import asyncio

    for _ in range(3):
        await limiter.check(
            namespace        = "global",
            identifier       = "1.2.3.4",
            limit            = 3,
            window           = 60,
            algorithm        = "token_bucket",
            bucket_capacity  = 3,
            refill_rate      = 10.0,
        )

    await asyncio.sleep(1)

    result = await limiter.check(
        namespace        = "global",
        identifier       = "1.2.3.4",
        limit            = 3,
        window           = 60,
        algorithm        = "token_bucket",
        bucket_capacity  = 3,
        refill_rate      = 10.0,
    )
    assert result.allowed   == True
    assert result.remaining == 2


async def test_explicit_bucket_capacity(limiter):
    result = await limiter.check(
        namespace        = "global",
        identifier       = "1.2.3.4",
        limit            = 10,
        window           = 60,
        algorithm        = "token_bucket",
        bucket_capacity  = 3,
        refill_rate      = 0.1,
    )
    assert result.allowed   == True
    assert result.remaining == 2


async def test_explicit_bucket_blocks_at_capacity(limiter):
    for _ in range(3):
        await limiter.check(
            namespace        = "global",
            identifier       = "1.2.3.4",
            limit            = 10,
            window           = 60,
            algorithm        = "token_bucket",
            bucket_capacity  = 3,
            refill_rate      = 0.1,
        )

    with pytest.raises(RateLimitExceeded):
        await limiter.check(
            namespace        = "global",
            identifier       = "1.2.3.4",
            limit            = 10,
            window           = 60,
            algorithm        = "token_bucket",
            bucket_capacity  = 3,
            refill_rate      = 0.1,
        )


async def test_different_ips_are_independent(limiter):
    for _ in range(5):
        await limiter.check(
            namespace  = "global",
            identifier = "1.2.3.4",
            limit      = 5,
            window     = 60,
            algorithm  = "token_bucket",
        )

    result = await limiter.check(
        namespace  = "global",
        identifier = "9.9.9.9",
        limit      = 5,
        window     = 60,
        algorithm  = "token_bucket",
    )
    assert result.allowed == True


async def test_redis_key_uses_tb_prefix(redis_client, limiter):
    await limiter.check(
        namespace  = "global",
        identifier = "1.2.3.4",
        limit      = 5,
        window     = 60,
        algorithm  = "token_bucket",
    )

    keys = await redis_client.keys("*")
    assert any(k.startswith("pylimitx:tb:") for k in keys)
    assert not any(k.startswith("pylimitx:lock:") for k in keys)


async def test_fail_open_when_redis_down():
    bad_redis = aioredis.from_url(
        "redis://localhost:9999",
        decode_responses       = True,
        socket_timeout         = 0.1,
        socket_connect_timeout = 0.1,
        retry_on_timeout       = False,
        retry_on_error         = [],
    )
    bad_limiter = RateLimiter(redis=bad_redis, fail_open=True)

    result = await bad_limiter.check(
        namespace  = "global",
        identifier = "1.2.3.4",
        limit      = 5,
        window     = 60,
        algorithm  = "token_bucket",
    )

    assert result.allowed   == True
    assert result.remaining == -1
    await bad_redis.aclose()