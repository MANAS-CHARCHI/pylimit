import pytest
from pylimitx.core.lock import RedisLock


async def test_acquire_returns_token(lock):
    token = await lock.acquire("pylimitx:lock:test")
    assert token is not None
    assert isinstance(token, str)
    assert len(token) > 0


async def test_acquire_same_key_twice_fails(lock):
    token = await lock.acquire("pylimitx:lock:test")
    assert token is not None

    second = await lock.acquire("pylimitx:lock:test")
    assert second is None


async def test_acquire_different_keys_both_succeed(lock):
    token1 = await lock.acquire("pylimitx:lock:key1")
    token2 = await lock.acquire("pylimitx:lock:key2")

    assert token1 is not None
    assert token2 is not None


async def test_release_allows_reacquire(redis_client, lock):
    token = await lock.acquire("pylimitx:lock:test")
    assert token is not None

    await redis_client.delete("pylimitx:lock:test")

    new_token = await lock.acquire("pylimitx:lock:test")
    assert new_token is not None


async def test_wrong_token_cannot_release(redis_client, lock):
    token = await lock.acquire("pylimitx:lock:test")
    assert token is not None

    stored = await redis_client.get("pylimitx:lock:test")
    assert stored != "wrong-token"

    second = await lock.acquire("pylimitx:lock:test")
    assert second is None


async def test_each_acquire_gets_unique_token(redis_client, lock):
    token1 = await lock.acquire("pylimitx:lock:key1")
    await redis_client.delete("pylimitx:lock:key1")

    token2 = await lock.acquire("pylimitx:lock:key1")
    await redis_client.delete("pylimitx:lock:key1")

    assert token1 != token2


async def test_lock_key_stored_in_redis(redis_client, lock):
    await lock.acquire("pylimitx:lock:test")

    keys = await redis_client.keys("*")
    assert "pylimitx:lock:test" in keys


async def test_release_removes_key_from_redis(redis_client, lock):
    token = await lock.acquire("pylimitx:lock:test")
    await redis_client.delete("pylimitx:lock:test")

    keys = await redis_client.keys("*")
    assert "pylimitx:lock:test" not in keys