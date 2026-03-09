# Pylimitx - Distributed Rate Limiting for Python

A distributed rate-limiting solution for **FastAPI** and **Django** applications.

## Features

- Multiple Algorithms: Sliding Window (accurate) and Token Bucket (burst-friendly)
- FastAPI Support: Middleware and decorators for FastAPI
- Django Support: Middleware and decorators for Django
- Distributed: Redis-backed, scales horizontally
- Reliable: Circuit breaker pattern, fail-open safety
- Simple: Easy to integrate, minimal configuration
- Fast: Uses Python and Lua scripts for atomic operations with minimal round-trips to Redis.

---

## Installation

### FastAPI

```bash
pip install pylimitx[fastapi]
```

### Django

```bash
pip install pylimitx[django]
```

---

## IMPORTANT: Redis Setup (Required for Both FastAPI and Django)

Rate limiting requires a running Redis server. Set it up first:

### 1. Start Redis

```bash
# Using Docker (Recommended)
docker run -d -p 6379:6379 redis:latest

# Or install locally
brew install redis
redis-server
```

### 2. Verify Redis is Running

```bash
redis-cli ping
# Should return: PONG
```

### 3. Configure Redis URL in Your App

The default Redis URL is: `redis://localhost:6379`

If using a different URL, update it when initializing Pylimitx (see examples below).

---

## FastAPI Usage

### IMPORTANT: Middleware Must Be Added FIRST

Middleware MUST be added before route handlers are defined, so it checks requests BEFORE your backend logic runs. If a request exceeds the rate limit, it returns 429 immediately without executing your route.

### Step 1: Initialize Redis and RateLimiter

```python
from fastapi import FastAPI
from redis.asyncio import Redis
from pylimitx import RateLimiter, RateLimitMiddleware, rate_limit

app = FastAPI()

# Create Redis connection
redis = Redis.from_url("redis://localhost:6379", decode_responses=True)

# Create rate limiter instance (for decorators)
limiter = RateLimiter(redis=redis)
app.state.pylimitx_limiter = limiter
```

### Step 2: Add Global Middleware (MUST BE FIRST in middleware stack)

```python
# Add middleware BEFORE defining routes
# This ensures ALL requests are checked for rate limits FIRST
app.add_middleware(
    RateLimitMiddleware,
    redis_url="redis://localhost:6379",
    limit=100,        # 100 requests allowed
    window=60,        # per 60 seconds
)

# Now define your routes AFTER adding middleware
```

### Step 3: Optional - Add Per-Route Rate Limiting

```python
from pylimitx import rate_limit

@app.get("/api/search")
@rate_limit(limit=10, window=60)  # Override global limit for this route
async def search(q: str):
    return {"results": "..."}
```

### Complete FastAPI Example

```python
from fastapi import FastAPI, UploadFile
from redis.asyncio import Redis
from pylimitx import RateLimiter, RateLimitMiddleware, rate_limit

app = FastAPI()

# Step 1: Redis setup
redis = Redis.from_url("redis://localhost:6379", decode_responses=True)
app.state.pylimitx_limiter = RateLimiter(redis=redis)

# Step 2: Add middleware FIRST (before any routes)
app.add_middleware(
    RateLimitMiddleware,
    redis_url="redis://localhost:6379",
    limit=100,
    window=60,
)

# Step 3: NOW define your routes (they are protected by middleware)
@app.get("/api/search")
@rate_limit(limit=10, window=60)  # Different limit for this endpoint
async def search(q: str):
    return {"results": "..."}

@app.post("/api/upload")
async def upload(file: UploadFile):
    # Uses global middleware limit (100/60)
    return {"uploaded": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## Django Usage

### IMPORTANT: Middleware Must Be Placed Early in MIDDLEWARE List

Middleware checks requests BEFORE your views run. Place it HIGH in the MIDDLEWARE list so requests are checked FIRST. If a request exceeds the rate limit, it returns 429 immediately without calling your view.

### Step 1: Configure Redis in settings.py (BEFORE middleware)

```python
# settings.py

# Configure rate limiting
RATE_LIMIT_CONFIG = {
    'REDIS_URL': 'redis://localhost:6379',  # Must run Redis before using
    'LIMIT': 100,        # Default: 100 requests
    'WINDOW': 60,        # Default: per 60 seconds
}
```

### Step 2: Option A - Use Decorators (Per-View Rate Limiting)

```python
from django.http import HttpResponse
from pylimitx import django_rate_limit

@django_rate_limit(limit=20, window=60)
def search_view(request):
    # Only allows 20 requests per 60 seconds to this view
    return HttpResponse("Search results")

# Class-based view
from django.views import View

class ExportView(View):
    @django_rate_limit(limit=5, window=3600)
    def post(self, request):
        # Only allows 5 requests per hour to this endpoint
        return HttpResponse("Exporting...")
```

### Step 2: Option B - Use Global Middleware (All Endpoints)

```python
# settings.py

# Add middleware EARLY in the list (before other middleware that processes requests)
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # Place rate limiting middleware EARLY, BEFORE processing middleware
    'pylimitx.integrations.django.middleware.DjangoRateLimitMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

RATE_LIMIT_CONFIG = {
    'REDIS_URL': 'redis://localhost:6379',
    'LIMIT': 100,
    'WINDOW': 60,
}

# Now ALL endpoints are rate limited to 100 requests per 60 seconds
# No changes needed in your views
```

### Complete Django Example

```python
# settings.py
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # Place rate limiting early - BEFORE processing middleware
    'pylimitx.integrations.django.middleware.DjangoRateLimitMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

RATE_LIMIT_CONFIG = {
    'REDIS_URL': 'redis://localhost:6379',
    'LIMIT': 100,
    'WINDOW': 60,
}

# urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('search/', views.search_view),
    path('export/', views.ExportView.as_view()),
]

# views.py
from django.http import HttpResponse
from django.views import View
from pylimitx import django_rate_limit

# Per-view limit (overrides middleware limit)
@django_rate_limit(limit=20, window=60)
def search_view(request):
    return HttpResponse("Search results")

# Class-based view with decorator
class ExportView(View):
    @django_rate_limit(limit=5, window=3600)
    def post(self, request):
        return HttpResponse("Exporting...")
```

---

## Rate Limiting Algorithms

### Sliding Window (Default - Most Accurate)

Tracks exact request timestamps. Best for strict API limits.

```python
# FastAPI
@rate_limit(limit=10, window=60, algorithm="sliding_window")
async def endpoint():
    pass

# Django
RATE_LIMIT_CONFIG = {
    'LIMIT': 10,
    'WINDOW': 60,
    'ALGORITHM': 'sliding_window',  # Default
}
```

### Token Bucket (Burst Support)

Allows users to burst requests up to bucket_capacity, then rate limits to the specified limit/window.

IMPORTANT: If you do NOT provide bucket_capacity and refill_rate:

- bucket_capacity defaults to limit value
- refill_rate defaults to limit/window (steady rate)
- Result: Works like sliding window with no burst allowed

```python
# Example 1: With burst support
# FastAPI
@rate_limit(
    limit=10,
    window=60,
    algorithm="token_bucket",
    bucket_capacity=30,    # Can burst up to 30 requests
    refill_rate=10/60,     # Then refill at 10 per minute
)
async def upload(file):
    # Users can upload 30 files instantly, then limited to 10/min
    pass

# Django
RATE_LIMIT_CONFIG = {
    'LIMIT': 10,
    'WINDOW': 60,
    'ALGORITHM': 'token_bucket',
    'BUCKET_CAPACITY': 30,     # Burst size
    'REFILL_RATE': 10/60,      # Refill rate (requests per second)
}
```

```python
# Example 2: Without burst (defaults used)
# FastAPI
@rate_limit(
    limit=10,
    window=60,
    algorithm="token_bucket",
    # bucket_capacity NOT provided -> defaults to 10
    # refill_rate NOT provided -> defaults to 10/60 (0.167 per second)
)
async def endpoint():
    # Same as sliding_window above - no burst, just rate limiting
    pass

# Django
RATE_LIMIT_CONFIG = {
    'LIMIT': 10,
    'WINDOW': 60,
    'ALGORITHM': 'token_bucket',
    # BUCKET_CAPACITY NOT provided -> defaults to LIMIT (10)
    # REFILL_RATE NOT provided -> defaults to LIMIT/WINDOW
    # Result: Works like sliding_window with no burst
}
```

### Understanding Parameters

- **limit**: Maximum requests allowed (e.g., 10)
- **window**: Time window in seconds (e.g., 60 for per minute)
- **algorithm**: Either "sliding_window" or "token_bucket"
- **bucket_capacity** (token_bucket only): Max burst size. If not provided, defaults to limit
- **refill_rate** (token_bucket only): How many requests refill per second. If not provided, defaults to limit/window

---

## Response Headers

When a request is blocked (HTTP 429):

```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
Retry-After: 45
```

When a request is allowed:

```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 3
```

---

## Troubleshooting

### Redis Connection Error

Error: "ConnectionError: Error 111 connecting to localhost:6379"

Solution:

```bash
# Make sure Redis is running
redis-cli ping
# Should return: PONG

# If not running, start Redis
redis-server  # or docker run -d -p 6379:6379 redis:latest
```

### Circuit Breaker Open

If you see many "pylimitx.redis_failure" messages, your Redis is down or disconnected.

What happens:

1. Rate limiter fails to connect to Redis
2. After 3 failures, circuit breaker opens
3. All requests allowed (fail-open safety)
4. Rate limiter retries connection after 30 seconds

Solution: Get Redis running again.

---

## Configuration Reference

### RATE_LIMIT_CONFIG (Django only)

```python
RATE_LIMIT_CONFIG = {
    'REDIS_URL': 'redis://localhost:6379',      # Redis connection
    'LIMIT': 100,                               # Max requests
    'WINDOW': 60,                               # Time window (seconds)
    'ALGORITHM': 'sliding_window',              # Or 'token_bucket'
    'BUCKET_CAPACITY': 200,                     # Token bucket only
    'REFILL_RATE': 100/60,                      # Token bucket only
    'FAIL_OPEN': True,                          # Allow traffic if Redis down
    'FAILURE_THRESHOLD': 3,                     # Failures before circuit opens
    'RECOVERY_TIMEOUT': 30,                     # Seconds before retry
}
```

### Rate Limiter Options (FastAPI)

```python
app.state.pylimitx_limiter = RateLimiter(
    redis=redis,
    fail_open=True,                 # Allow traffic if Redis down
    failure_threshold=3,            # Failures before circuit opens
    recovery_timeout=30,            # Seconds before retry
)

# Middleware options
app.add_middleware(
    RateLimitMiddleware,
    redis_url="redis://localhost:6379",
    limit=100,
    window=60,
    algorithm="sliding_window",
    bucket_capacity=None,           # Token bucket only
    refill_rate=None,               # Token bucket only
    fail_open=True,
    failure_threshold=3,
    recovery_timeout=30,
)

# Decorator options
@rate_limit(
    limit=10,
    window=60,
    algorithm="sliding_window",
    bucket_capacity=None,
    refill_rate=None,
)
```

---

## Key Concepts

Namespace: "global", "GET\_/api/search"
Identifier: IP address, API key, user ID
Window: 60 (per minute), 3600 (per hour)
Limit: Max requests in window

---

## Contributing

Want to contribute? You can:

1. Fork the repo: https://github.com/MANAS-CHARCHI/pylimit
2. Use it for yourself and share feedback
3. Contribute improvements via pull requests
4. Report issues on GitHub

---

## License

MIT License

### Step 1: Initialize Redis and RateLimiter

```python
from fastapi import FastAPI
from redis.asyncio import Redis
from pylimitx import RateLimiter

app = FastAPI()

# Create Redis connection
redis = Redis.from_url("redis://localhost:6379", decode_responses=True)

# Create rate limiter instance
limiter = RateLimiter(redis=redis)

# Store in app state (needed for decorators)
app.state.pylimitx_limiter = limiter
```

### Step 2: Add Global Middleware (Optional)

```python
from pylimitx import RateLimitMiddleware

# Add before app initialization or after
app.add_middleware(
    RateLimitMiddleware,
    redis_url="redis://localhost:6379",
    limit=100,        # 100 requests
    window=60,        # per 60 seconds
)
```

### Step 3: Use Decorators (Optional)

```python
from pylimitx import rate_limit

@app.get("/api/search")
@rate_limit(limit=10, window=60)  # 10 requests per 60 seconds
async def search(q: str):
    return {"results": "..."}

@app.post("/api/upload")
@rate_limit(limit=5, window=60, algorithm="token_bucket", bucket_capacity=15)
async def upload(file: UploadFile):
    return {"uploaded": True}
```

### Complete FastAPI Example

```python
from fastapi import FastAPI, UploadFile
from redis.asyncio import Redis
from pylimitx import RateLimiter, RateLimitMiddleware, rate_limit

app = FastAPI()

# Redis setup
redis = Redis.from_url("redis://localhost:6379", decode_responses=True)
app.state.pylimitx_limiter = RateLimiter(redis=redis)

# Add global rate limiting (optional)
app.add_middleware(
    RateLimitMiddleware,
    redis_url="redis://localhost:6379",
    limit=100,
    window=60,
)

# Per-route rate limiting
@app.get("/api/search")
@rate_limit(limit=10, window=60)
async def search(q: str):
    return {"results": "..."}

@app.post("/api/upload")
@rate_limit(limit=5, window=60, algorithm="token_bucket", bucket_capacity=15)
async def upload(file: UploadFile):
    return {"uploaded": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## Django Usage

### Step 1: Configure Redis in settings.py

```python
# settings.py
RATE_LIMIT_CONFIG = {
    'REDIS_URL': 'redis://localhost:6379',  # ← Must run Redis before using
    'LIMIT': 100,        # Default: 100 requests
    'WINDOW': 60,        # Default: per 60 seconds
}
```

### Step 2: Option A - Use Decorators (Per-View)

```python
from django.http import HttpResponse
from pylimitx import django_rate_limit

@django_rate_limit(limit=20, window=60)
def search_view(request):
    return HttpResponse("Search results")

# Class-based view
from django.views import View

class ExportView(View):
    @django_rate_limit(limit=5, window=3600)
    def post(self, request):
        return HttpResponse("Exporting...")
```

### Step 2: Option B - Use Global Middleware (All Endpoints)

```python
# settings.py
MIDDLEWARE = [
    # ... your other middleware ...
    'pylimitx.integrations.django.middleware.DjangoRateLimitMiddleware',
]

# Configure rate limits
RATE_LIMIT_CONFIG = {
    'REDIS_URL': 'redis://localhost:6379',
    'LIMIT': 100,
    'WINDOW': 60,
}
```

Now ALL endpoints are rate limited with 100 requests per 60 seconds.

### Complete Django Example

```python
# settings.py
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    # Add rate limiting middleware
    'pylimitx.integrations.django.middleware.DjangoRateLimitMiddleware',
]

RATE_LIMIT_CONFIG = {
    'REDIS_URL': 'redis://localhost:6379',
    'LIMIT': 100,
    'WINDOW': 60,
}

# views.py
from django.http import HttpResponse
from django.views import View
from pylimitx import django_rate_limit

# Per-view rate limiting (overrides middleware limit)
@django_rate_limit(limit=20, window=60)
def search_view(request):
    return HttpResponse("Search results")

# Class-based view
class ExportView(View):
    @django_rate_limit(limit=5, window=3600)
    def post(self, request):
        return HttpResponse("Exporting...")
```

---

## ⚙️ Advanced Configuration

### Token Bucket (Burst Support)

```python
# FastAPI
@rate_limit(
    limit=10,
    window=60,
    algorithm="token_bucket",
    bucket_capacity=30,    # Max burst
    refill_rate=10/60,     # Refill rate
)
async def endpoint():
    pass

# Django (in RATE_LIMIT_CONFIG)
RATE_LIMIT_CONFIG = {
    'REDIS_URL': 'redis://localhost:6379',
    'LIMIT': 10,
    'WINDOW': 60,
    'ALGORITHM': 'token_bucket',
    'BUCKET_CAPACITY': 30,
    'REFILL_RATE': 10/60,
}
```

### Sliding Window (Default, Most Accurate)

```python
# FastAPI
@rate_limit(limit=10, window=60, algorithm="sliding_window")
async def endpoint():
    pass

# Django (in RATE_LIMIT_CONFIG)
RATE_LIMIT_CONFIG = {
    'REDIS_URL': 'redis://localhost:6379',
    'LIMIT': 10,
    'WINDOW': 60,
    'ALGORITHM': 'sliding_window',
}
```

### Fail-Open Safety

If Redis goes down, pylimitx allows ALL requests (fail-open). When Redis is back, rate limiting resumes.

```python
RATE_LIMIT_CONFIG = {
    'REDIS_URL': 'redis://localhost:6379',
    'LIMIT': 100,
    'WINDOW': 60,
    'FAIL_OPEN': True,              # Allow traffic if Redis is down
    'FAILURE_THRESHOLD': 3,         # Open circuit after 3 failures
    'RECOVERY_TIMEOUT': 30,         # Try reconnecting after 30 seconds
}
```

---

## Response Headers

When a request is blocked (HTTP 429):

```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
Retry-After: 45
```

When a request is allowed:

```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 3
```

---

## Troubleshooting

### Redis Connection Error

```
Error: ConnectionError: Error 111 connecting to localhost:6379
```

**Solution:**

```bash
# Make sure Redis is running
redis-cli ping
# Should return: PONG

# If not running, start Redis
redis-server  # or docker run -d -p 6379:6379 redis:latest
```

### Circuit Breaker Open

If you see many "pylimitx.redis_failure" messages, your Redis is down or disconnected.

**What happens:**

1. Rate limiter fails to connect to Redis
2. After 3 failures, circuit breaker opens
3. All requests allowed (fail-open safety)
4. Rate limiter retries connection after 30 seconds

**Solution:** Get Redis running again.

---

## Key Concepts

| Concept        | Example                          |
| -------------- | -------------------------------- |
| **Namespace**  | `"global"`, `"GET_/api/search"`  |
| **Identifier** | IP address, API key, user ID     |
| **Window**     | 60 (per minute), 3600 (per hour) |
| **Limit**      | Max requests in window           |

---

## Contributing

Want to contribute? You can:

1. Fork the repo: https://github.com/MANAS-CHARCHI/pylimit
2. Use it for yourself and share feedback
3. Contribute improvements via pull requests
4. Report issues on GitHub

---

## License

MIT License

Created with love for development and scalable systems 💙
