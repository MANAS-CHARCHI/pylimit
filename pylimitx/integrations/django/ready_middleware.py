"""
Ready-to-use Django middleware that reads configuration from settings.

Usage:
1. Add to MIDDLEWARE in settings.py:
   MIDDLEWARE = [
       'myapp.middleware.RateLimitMiddleware',  # or wherever you copy this
   ]

2. Configure in settings.py:
   RATE_LIMIT_CONFIG = {
       'REDIS_URL': 'redis://localhost:6379',
       'LIMIT': 100,
       'WINDOW': 60,
   }

That's it! No additional setup needed.
"""

from django.conf import settings
from pylimitx.integrations.django.middleware import DjangoRateLimitMiddleware as BaseMiddleware


class RateLimitMiddleware(BaseMiddleware):
    """
    Django middleware that automatically reads rate limit config from settings.
    
    Just add to MIDDLEWARE and configure RATE_LIMIT_CONFIG in settings.
    """
    
    def __init__(self, get_response):
        config = getattr(settings, 'RATE_LIMIT_CONFIG', {})
        
        super().__init__(
            get_response,
            redis_url=config.get('REDIS_URL', 'redis://localhost:6379'),
            limit=config.get('LIMIT', 100),
            window=config.get('WINDOW', 60),
            algorithm=config.get('ALGORITHM', 'sliding_window'),
            bucket_capacity=config.get('BUCKET_CAPACITY'),
            refill_rate=config.get('REFILL_RATE'),
            fail_open=config.get('FAIL_OPEN', True),
            failure_threshold=config.get('FAILURE_THRESHOLD', 3),
            recovery_timeout=config.get('RECOVERY_TIMEOUT', 30),
        )
