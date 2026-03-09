import time
import uuid
import asyncio
from pathlib import Path
from typing import NamedTuple

from redis.asyncio import Redis

from pylimitx.core.circuit_breaker  import CircuitBreaker
from pylimitx.core.lock             import RedisLock
from pylimitx.exceptions            import RateLimitExceeded

class LimitResult(NamedTuple):
    allowed:     bool
    remaining:   int
    retry_after: int

class RateLimiter:
    def __init__(
        self,
        redis:                   Redis,
        fail_open:               bool  = True,
        failure_threshold:       int   = 3,
        recovery_timeout:        int   = 30,
    ):
        self.redis           = redis
        self.fail_open       = fail_open
        self.circuit_breaker = CircuitBreaker(
            failure_threshold = failure_threshold,
            recovery_timeout  = recovery_timeout,
        )
        self.lock            = RedisLock(redis)
        self._sliding_window = self._load_script("sliding_window.lua")
        self._token_bucket   = self._load_script("token_bucket.lua")
    
    def _load_script(self, filename: str) -> str:
        path = Path(__file__).parent.parent / "algorithms" / filename
        return path.read_text()
    
    def _build_key(self, algorithm: str, namespace: str, identifier: str) -> str:
        if algorithm == "token_bucket":
            return f"pylimitx:tb:{namespace}:{identifier}"
        return f"pylimitx:{namespace}:{identifier}"

    def _build_lock_key(self, namespace: str, identifier: str) -> str:
        return f"pylimitx:lock:{namespace}:{identifier}"
    
    async def check(
        self,
        namespace:      str,
        identifier:     str,
        limit:          int,
        window:         int,
        algorithm:      str   = "sliding_window",
        bucket_capacity: int  = None,
        refill_rate:    float = None,
    ) -> LimitResult:
        if algorithm == "token_bucket":
            return await self._check_token_bucket(
                namespace       = namespace,
                identifier      = identifier,
                capacity        = bucket_capacity or limit,
                refill_rate     = refill_rate or (limit / window),
            )

        return await self._check_sliding_window(
            namespace   = namespace,
            identifier  = identifier,
            limit       = limit,
            window      = window,
        )
    
    async def _check_sliding_window(
        self,
        namespace:  str,
        identifier: str,
        limit:      int,
        window:     int,
    ) -> LimitResult:
        key        = self._build_key("sliding_window", namespace, identifier)
        now_ms     = int(time.time() * 1000)
        request_id = str(uuid.uuid4())

        async def redis_call():
            return await self.redis.eval(
                self._sliding_window,
                1,
                key,
                limit,
                window,
                now_ms,
                request_id,
            )

        result = await self.circuit_breaker.call(redis_call)

        if result is None:
            return self._fail_open_result()

        allowed, remaining, retry_after = result

        if not allowed:
            retry_after_sec = max(1, int(retry_after / 1000))
            raise RateLimitExceeded(
                limit       = limit,
                remaining   = 0,
                retry_after = retry_after_sec,
            )

        return LimitResult(
            allowed     = True,
            remaining   = int(remaining),
            retry_after = -1,
        )
    
    async def _check_token_bucket(
        self,
        namespace:   str,
        identifier:  str,
        capacity:    int,
        refill_rate: float,
    ) -> LimitResult:

        key      = self._build_key("token_bucket", namespace, identifier)
        lock_key = self._build_lock_key(namespace, identifier)
        now_sec  = int(time.time())

        # acquire lock — both attempts wrapped in try/except
        try:
            token = await self.lock.acquire(lock_key)
            if token is None:
                await asyncio.sleep(0.01)
                token = await self.lock.acquire(lock_key)
        except Exception:
            return self._fail_open_result()

        # lock not acquired — fail open
        if token is None:
            return self._fail_open_result()

        # run token bucket with lock held
        try:
            async def redis_call():
                return await self.redis.eval(
                    self._token_bucket,
                    1,
                    key,
                    capacity,
                    refill_rate,
                    now_sec,
                )

            result = await self.circuit_breaker.call(redis_call)

            if result is None:
                return self._fail_open_result()

            allowed, remaining, retry_after = result

            if not allowed:
                raise RateLimitExceeded(
                    limit       = capacity,
                    remaining   = 0,
                    retry_after = int(retry_after),
                )

            return LimitResult(
                allowed     = True,
                remaining   = int(remaining),
                retry_after = -1,
            )

        except RateLimitExceeded:
            raise

        except Exception:
            return self._fail_open_result()

        finally:
            try:
                await self.lock.release(lock_key, token)
            except Exception:
                pass


    def _fail_open_result(self) -> LimitResult:
        if self.fail_open:
            return LimitResult(allowed=True, remaining=-1, retry_after=-1)
        raise RateLimitExceeded(limit=0, remaining=0, retry_after=60)