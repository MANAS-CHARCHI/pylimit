import time
import logging

logger = logging.getLogger(__name__)

class CircuitBreaker:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int   = 3,
        recovery_timeout:  int   = 30,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = self.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
    
    async def call(self, func):
        if self.state == self.OPEN:
            if self._recovery_timeout_passed():
                self._transition(self.HALF_OPEN)
            else:
                return None

        try:
            result = await func()
            self._on_success()
            return result

        except Exception as e:
            self._on_failure(e)
            return None
    
    def _recovery_timeout_passed(self) -> bool:
        if self.last_failure_time is None:
            return True
        return time.time() - self.last_failure_time >= self.recovery_timeout

    def _on_success(self) -> None:
        self.failure_count = 0
        self.state         = self.CLOSED
    
    def _on_failure(self, error: Exception) -> None:
        self.failure_count    += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self._transition(self.OPEN)

        logger.warning(
            "pylimitx.redis_failure",
            extra={
                "error":         str(error),
                "failure_count": self.failure_count,
                "circuit_state": self.state,
            }
        )

    def _transition(self, new_state: str) -> None:
        logger.warning(
            "pylimitx.circuit_transition",
            extra={
                "from": self.state,
                "to":   new_state,
            }
        )
        self.state = new_state

    @property
    def is_open(self) -> bool:
        return self.state == self.OPEN

    @property
    def is_closed(self) -> bool:
        return self.state == self.CLOSED

    @property
    def is_half_open(self) -> bool:
        return self.state == self.HALF_OPEN