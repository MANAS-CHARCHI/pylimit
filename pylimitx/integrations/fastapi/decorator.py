import functools

from fastapi          import Request
from fastapi.responses import JSONResponse

from pylimitx.core.limiter  import RateLimiter
from pylimitx.exceptions    import RateLimitExceeded

def rate_limit(
    limit:           int,
    window:          int,
    algorithm:       str   = "sliding_window",
    bucket_capacity: int   = None,
    refill_rate:     float = None,
):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            request  = _extract_request(*args, **kwargs)
            limiter  = _extract_limiter(request)
            if request is None or limiter is None:
                return await func(*args, **kwargs)
            
            identifier = _get_identifier(request)
            namespace  = _build_namespace(request)

            try:
                result = await limiter.check(
                    namespace        = namespace,
                    identifier       = identifier,
                    limit            = limit,
                    window           = window,
                    algorithm        = algorithm,
                    bucket_capacity  = bucket_capacity,
                    refill_rate      = refill_rate,
                )
                response = await func(*args, **kwargs)
                _set_headers(response, result.remaining, limit)
                return response
            except RateLimitExceeded as e:
                return _build_429(e)
        return wrapper
    return decorator

def _extract_request(*args, **kwargs) -> Request | None:
    for arg in args:
        if isinstance(arg, Request):
            return arg
    for val in kwargs.values():
        if isinstance(val, Request):
            return val
    return None

def _extract_limiter(request: Request) -> RateLimiter | None:
    if request is None:
        return None
    return getattr(request.app.state, "pylimitx_limiter", None)

def _get_identifier(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host

def _build_namespace(request: Request) -> str:
    method = request.method
    path   = request.url.path
    return f"{method}_{path}"

def _set_headers(response, remaining: int, limit: int) -> None:
    if remaining == -1:
        return
    if not hasattr(response, "headers"):
        return
    response.headers["X-RateLimit-Limit"]     = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)

def _build_429(exc: RateLimitExceeded) -> JSONResponse:
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