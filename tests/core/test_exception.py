from pylimitx.exceptions import RateLimitExceeded

def test_rate_limit_exceeded_carries_metadata():
    exc=RateLimitExceeded(limit=10, remaining=5, retry_after=60)
    assert exc.limit==10
    assert exc.remaining==5
    assert exc.retry_after==60

def test_rate_limit_exceeded_is_exception():
    exc = RateLimitExceeded(limit=10, remaining=0, retry_after=5)
    assert isinstance(exc, Exception)

def test_rate_limit_exceeded_can_be_raised_and_caught():
    try:
        raise RateLimitExceeded(limit=10, remaining=0, retry_after=5)
    except RateLimitExceeded as exc:
        assert exc.limit==10