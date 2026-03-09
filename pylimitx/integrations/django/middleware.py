import asyncio, inspect

from django.http            import JsonResponse
from django.conf            import settings
from django.utils.decorators import sync_and_async_middleware

from redis.asyncio import Redis

from pylimitx.core.limiter import RateLimiter
from pylimitx.exceptions   import RateLimitExceeded

class DjangoRateLimitMiddleware:
    def __init__(
            self, 
            get_response, 
            redis_url: str = None, 
            limit: int = None, 
            window: int = None,
            algorithm: str = "sliding_window", 
            bucket_capacity: int = None,
            refill_rate: float = None, 
            fail_open: bool = True,
            failure_threshold: int = 3, 
            recovery_timeout: int = 30
    ):
        # Read from Django settings if not provided
        config = getattr(settings, 'RATE_LIMIT_CONFIG', {})
        redis_url = redis_url or config.get('REDIS_URL', 'redis://localhost:6379')
        limit = limit or config.get('LIMIT', 100)
        window = window or config.get('WINDOW', 60)
        
        self.get_response    = get_response
        self.limit           = limit
        self.window          = window
        self.algorithm       = algorithm
        self.bucket_capacity = bucket_capacity
        self.refill_rate     = refill_rate
        self.async_capable   = inspect.iscoroutinefunction(get_response)
        redis          = Redis.from_url(redis_url, decode_responses=True)
        self.limiter   = RateLimiter(
            redis             = redis,
            fail_open         = fail_open,
            failure_threshold = failure_threshold,
            recovery_timeout  = recovery_timeout,
        )
    
    def __call__(self, request):
        if self.async_capable:
            return self.__acall__(request)
        return self._sync_call(request)

    def _sync_call(self, request):
        try:
            # Try to use the existing event loop from pytest-asyncio if available
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = None
            
            if loop and loop.is_closed():
                loop = None
            
            if loop:
                # Reuse the existing loop
                result = loop.run_until_complete(self._check(request))
            else:
                # Create a fresh loop with asyncio.run
                result = asyncio.run(self._check(request))
        except Exception:
            # If event loop management fails, handle gracefully
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(self._check(request))
            finally:
                loop.close()
                asyncio.set_event_loop(None)

        if isinstance(result, JsonResponse):
            return result

        response = self.get_response(request)
        self._set_headers(response, result.remaining)
        return response
    
    async def __acall__(self, request):
        result = await self._check(request)

        if isinstance(result, JsonResponse):
            return result

        response = await self.get_response(request)
        self._set_headers(response, result.remaining)
        return response
    
    async def _check(self, request):
        identifier = self._get_identifier(request)

        try:
            return await self.limiter.check(
                namespace        = "global",
                identifier       = identifier,
                limit            = self.limit,
                window           = self.window,
                algorithm        = self.algorithm,
                bucket_capacity  = self.bucket_capacity,
                refill_rate      = self.refill_rate,
            )
        except RateLimitExceeded as e:
            return self._build_429(e)
        
    def _get_identifier(self, request) -> str:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")

    def _set_headers(self, response, remaining: int) -> None:
        if remaining == -1:
            return
        response["X-RateLimit-Limit"]     = str(self.limit)
        response["X-RateLimit-Remaining"] = str(remaining)

    def _build_429(self, exc: RateLimitExceeded) -> JsonResponse:
        response = JsonResponse(
            {
                "detail":      "Rate limit exceeded",
                "retry_after": exc.retry_after,
            },
            status = 429,
        )
        response["X-RateLimit-Limit"]     = str(exc.limit)
        response["X-RateLimit-Remaining"] = "0"
        response["Retry-After"]           = str(exc.retry_after)
        return response