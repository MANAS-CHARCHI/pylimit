import pytest
from pylimitx.core.circuit_breaker import CircuitBreaker


async def test_starts_closed(circuit_breaker):
    assert circuit_breaker.is_closed
    assert not circuit_breaker.is_open
    assert not circuit_breaker.is_half_open


async def test_successful_call_returns_result(circuit_breaker):
    async def redis_call():
        return "ok"

    result = await circuit_breaker.call(redis_call)
    assert result == "ok"


async def test_successful_call_stays_closed(circuit_breaker):
    async def redis_call():
        return "ok"

    await circuit_breaker.call(redis_call)
    assert circuit_breaker.is_closed


async def test_single_failure_stays_closed(circuit_breaker):
    async def failing_call():
        raise ConnectionError("redis down")

    await circuit_breaker.call(failing_call)
    assert circuit_breaker.is_closed
    assert circuit_breaker.failure_count == 1


async def test_failure_returns_none(circuit_breaker):
    async def failing_call():
        raise ConnectionError("redis down")

    result = await circuit_breaker.call(failing_call)
    assert result is None


async def test_trips_open_after_threshold(circuit_breaker):
    async def failing_call():
        raise ConnectionError("redis down")

    for _ in range(3):
        await circuit_breaker.call(failing_call)

    assert circuit_breaker.is_open
    assert not circuit_breaker.is_closed


async def test_open_circuit_skips_redis(circuit_breaker):
    called = {"count": 0}

    async def failing_call():
        called["count"] += 1
        raise ConnectionError("redis down")

    for _ in range(3):
        await circuit_breaker.call(failing_call)

    await circuit_breaker.call(failing_call)
    assert called["count"] == 3


async def test_open_circuit_returns_none(circuit_breaker):
    async def failing_call():
        raise ConnectionError("redis down")

    for _ in range(3):
        await circuit_breaker.call(failing_call)

    result = await circuit_breaker.call(failing_call)
    assert result is None


async def test_success_resets_failure_count(circuit_breaker):
    async def failing_call():
        raise ConnectionError("redis down")

    async def success_call():
        return "ok"

    await circuit_breaker.call(failing_call)
    await circuit_breaker.call(failing_call)
    assert circuit_breaker.failure_count == 2

    await circuit_breaker.call(success_call)
    assert circuit_breaker.failure_count == 0
    assert circuit_breaker.is_closed


async def test_recovery_after_timeout(circuit_breaker):
    import time

    async def failing_call():
        raise ConnectionError("redis down")

    async def success_call():
        return "ok"

    for _ in range(3):
        await circuit_breaker.call(failing_call)

    assert circuit_breaker.is_open

    circuit_breaker.last_failure_time = time.time() - 31

    result = await circuit_breaker.call(success_call)
    assert result   == "ok"
    assert circuit_breaker.is_closed


async def test_half_open_failure_goes_back_to_open(circuit_breaker):
    import time

    async def failing_call():
        raise ConnectionError("redis down")

    for _ in range(3):
        await circuit_breaker.call(failing_call)

    circuit_breaker.last_failure_time = time.time() - 31

    await circuit_breaker.call(failing_call)
    assert circuit_breaker.is_open


async def test_consecutive_failures_required(circuit_breaker):
    async def failing_call():
        raise ConnectionError("redis down")

    async def success_call():
        return "ok"

    await circuit_breaker.call(failing_call)
    await circuit_breaker.call(failing_call)
    await circuit_breaker.call(success_call)

    assert circuit_breaker.is_closed

    await circuit_breaker.call(failing_call)
    await circuit_breaker.call(failing_call)
    await circuit_breaker.call(failing_call)

    assert circuit_breaker.is_open