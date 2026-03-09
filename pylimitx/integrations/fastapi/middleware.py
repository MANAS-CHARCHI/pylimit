from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests        import Request
from starlette.responses       import JSONResponse

from redis.asyncio import Redis

from pylimitx.core.limiter  import RateLimiter
from pylimitx.exceptions    import RateLimitExceeded

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        redis_url:         str,
        limit:             int,
        window:            int,
        algorithm:         str   = "sliding_window",
        bucket_capacity:   int   = None,
        refill_rate:       float = None,
        fail_open:         bool  = True,
        failure_threshold: int   = 3,
        recovery_timeout:  int   = 30,
    ):
        super().__init__(app)
        self.limit     = limit
        self.window    = window
        self.algorithm = algorithm
        self.bucket_capacity = bucket_capacity
        self.refill_rate     = refill_rate
        redis          = Redis.from_url(redis_url, decode_responses=True)
        self.limiter   = RateLimiter(
            redis             = redis,
            fail_open         = fail_open,
            failure_threshold = failure_threshold,
            recovery_timeout  = recovery_timeout,
        )

    async def dispatch(self, request: Request, call_next):
        identifier = self._get_identifier(request)
        try:
            result = await self.limiter.check(
                namespace        = "global",
                identifier       = identifier,
                limit            = self.limit,
                window           = self.window,
                algorithm        = self.algorithm,
                bucket_capacity  = self.bucket_capacity,
                refill_rate      = self.refill_rate,
            )
            response = await call_next(request)
            self._set_headers(response, result.remaining)
            return response
        except RateLimitExceeded as e:
            return self._build_429(e)
    
    def _get_identifier(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host
    
    def _set_headers(self, response, remaining: int) -> None:
        if remaining == -1:
            return
        response.headers["X-RateLimit-Limit"]     = str(self.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
    
    def _build_429(self, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code = 429,
            content     = {
                "detail":      "Rate limit exceeded",
                "retry_after": exc.retry_after,
            },
            headers = {
                "X-RateLimit-Limit":     str(exc.limit),
                "X-RateLimit-Remaining": "0",
                "Retry-After":           str(exc.retry_after),
            }
        )