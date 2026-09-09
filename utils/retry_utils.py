import time
import random
import functools
import logging
from utils.db_utils import check_api_quota, increment_api_quota, QuotaExceededError

logger = logging.getLogger("NarrateLoop.Retry")

NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404, 405, 422}
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

def is_transient_error(exception):
    """Determines whether an exception is transient (network/timeout/rate limit) or permanent."""
    if isinstance(exception, QuotaExceededError):
        return False

    # Check for HTTP status codes on response objects
    status_code = getattr(exception, "status_code", None)
    if status_code is None and hasattr(exception, "response") and exception.response is not None:
        status_code = getattr(exception.response, "status_code", None)
        
    if status_code is not None:
        if status_code in NON_RETRYABLE_STATUS_CODES:
            return False
        if status_code in RETRYABLE_STATUS_CODES:
            return True

    msg = str(exception).lower()
    if any(k in msg for k in ["rate limit", "429", "timeout", "timed out", "connection reset", "connection refused", "temporary", "503", "502", "504"]):
        return True
        
    if any(k in msg for k in ["invalid credentials", "permission denied", "unauthorized", "quota exceeded", "not found"]):
        return False

    # Default to transient for generic network exceptions
    exc_type = type(exception).__name__
    if any(k in exc_type for k in ["Timeout", "ConnectionError", "NetworkError", "TransportError"]):
        return True

    return False

def retry_with_backoff(max_retries=3, initial_delay=2.0, backoff_factor=2.0, jitter=True, api_type=None):
    """
    Reusable decorator for resilient API calls with exponential backoff and quota tracking.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if api_type:
                check_api_quota(api_type)

            attempts = 0
            delay = initial_delay

            while True:
                try:
                    result = func(*args, **kwargs)
                    if api_type:
                        increment_api_quota(api_type, success=True)
                    return result
                except Exception as e:
                    attempts += 1
                    is_rate_limit = "429" in str(e) or "rate limit" in str(e).lower()
                    
                    if api_type:
                        increment_api_quota(api_type, success=False, is_rate_limit=is_rate_limit)

                    if not is_transient_error(e) or attempts > max_retries:
                        print(f"[API Error] {func.__name__} failed permanently or exhausted {max_retries} retries: {e}")
                        raise

                    actual_delay = delay + (random.uniform(0.1, 0.8) if jitter else 0.0)
                    print(f"[API Retry {attempts}/{max_retries}] {func.__name__} failed ({e}). Retrying in {actual_delay:.2f}s...")
                    time.sleep(actual_delay)
                    delay *= backoff_factor

        return wrapper
    return decorator
