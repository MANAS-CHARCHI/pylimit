class RateLimitExceeded(Exception):
    def __init__(self, limit: int, remaining: int, retry_after: int):
        self.limit=limit                # limit for this endpoint or global
        self.remaining=remaining        # How many requests are left in the current window
        self.retry_after=retry_after    # Seconds until the window resets and the client can try again