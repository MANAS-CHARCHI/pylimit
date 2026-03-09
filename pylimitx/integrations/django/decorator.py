import asyncio
import inspect
import functools

from django.http import JsonResponse

from pylimitx.core.limiter import RateLimiter
from pylimitx.exceptions   import RateLimitExceeded

def django_rate_limit(
    limit:           int,
    window:          int,
    algorithm:       str   = "sliding_window",
    bucket_capacity: int   = None,
    refill_rate:     float = None,
):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(request, *args, **kwargs):
            limiter = _extract_limiter(request)

            if limiter is None:
                return func(request, *args, **kwargs)

            identifier = _get_identifier(request)
            namespace  = _build_namespace(request)

            if inspect.iscoroutinefunction(func):
                return _async_wrapper(
                    func, request, args, kwargs,
                    limiter, identifier, namespace,
                    limit, window, algorithm,
                    bucket_capacity, refill_rate,
                )

            return _sync_wrapper(
                func, request, args, kwargs,
                limiter, identifier, namespace,
                limit, window, algorithm,
                bucket_capacity, refill_rate,
            )

        return wrapper
    return decorator

async def _async_wrapper(
    func, request, args, kwargs,
    limiter, identifier, namespace,
    limit, window, algorithm,
    bucket_capacity, refill_rate,
):
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
        response = await func(request, *args, **kwargs)
        _set_headers(response, result.remaining, limit)
        return response

    except RateLimitExceeded as e:
        return _build_429(e)
    
def _sync_wrapper(
    func, request, args, kwargs,
    limiter, identifier, namespace,
    limit, window, algorithm,
    bucket_capacity, refill_rate,
):
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
            result = loop.run_until_complete(
                limiter.check(
                    namespace        = namespace,
                    identifier       = identifier,
                    limit            = limit,
                    window           = window,
                    algorithm        = algorithm,
                    bucket_capacity  = bucket_capacity,
                    refill_rate      = refill_rate,
                )
            )
        else:
            # Create a fresh loop
            result = asyncio.run(
                limiter.check(
                    namespace        = namespace,
                    identifier       = identifier,
                    limit            = limit,
                    window           = window,
                    algorithm        = algorithm,
                    bucket_capacity  = bucket_capacity,
                    refill_rate      = refill_rate,
                )
            )
        
    except RateLimitExceeded as e:
        return _build_429(e)

    response = func(request, *args, **kwargs)
    _set_headers(response, result.remaining, limit)
    return response

def _extract_limiter(request) -> RateLimiter | None:
    return getattr(request, "pylimitx_limiter", None)

def _get_identifier(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")

def _build_namespace(request) -> str:
    method = request.method
    path   = request.path
    return f"{method}_{path}"

def _set_headers(response, remaining: int, limit: int) -> None:
    if remaining == -1:
        return
    response["X-RateLimit-Limit"]     = str(limit)
    response["X-RateLimit-Remaining"] = str(remaining)

def _build_429(exc: RateLimitExceeded) -> JsonResponse:
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