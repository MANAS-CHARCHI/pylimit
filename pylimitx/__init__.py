import functools

from pylimitx.core.limiter import RateLimiter
from pylimitx.exceptions   import RateLimitExceeded

try:
    from pylimitx.integrations.fastapi.decorator  import rate_limit
    from pylimitx.integrations.fastapi.middleware import RateLimitMiddleware
except ImportError:
    pass

try:
    from pylimitx.integrations.django.decorator  import django_rate_limit
    from pylimitx.integrations.django.middleware import DjangoRateLimitMiddleware
except ImportError:
    pass

__all__ = [
    "RateLimiter",
    "RateLimitExceeded",
    "rate_limit",
    "RateLimitMiddleware",
    "django_rate_limit",
    "DjangoRateLimitMiddleware",
]