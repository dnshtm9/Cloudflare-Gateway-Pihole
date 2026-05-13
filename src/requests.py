import json
import time
import random
from functools import wraps
from typing import Optional, Tuple
from src import info, silent_error, error, CF_IDENTIFIER, CF_API_TOKEN
from src.http_client import request as http_request, HttpClientError, HttpRedirectError

# Custom Exceptions
class HTTPException(Exception):
    pass

class RateLimitException(HTTPException):
    pass

# Cloudflare Gateway Request Function
def cloudflare_gateway_request(
    method: str, endpoint: str,
    body: Optional[str] = None,
    timeout: int = 10
) -> Tuple[int, dict]:
    headers = {
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json",
        "Accept-Encoding": "gzip, deflate"
    }

    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_IDENTIFIER}/gateway{endpoint}"
    
    try:
        # Use the new secure client
        status, _, data_str = http_request(
            method, url,
            body=body.encode('utf-8') if body else None,
            headers=headers,
            timeout=timeout
        )

        # Handle HTTP error status codes
        if status >= 400:
            error_message = (
                f"Request failed: {status}, "
                f"Body: {data_str} "
                f"for URL: {url}"
            )
            if status == 429:
                silent_error(error_message)
                raise RateLimitException(error_message)
            elif status in [400, 403, 404]:
                error(error_message)
            else:
                silent_error(error_message)
            raise HTTPException(error_message)

        return status, json.loads(data_str)

    except HttpClientError as e:
        # Network or Client Error
        error_message = f"Network error occurred: {e}"
        silent_error(error_message)
        raise HTTPException(error_message)
    except json.JSONDecodeError:
        # JSON Error
        error_message = "Failed to decode JSON response"
        silent_error(error_message)
        raise HTTPException(error_message)

# Retry conditions and strategies
def stop_after_custom_attempts(attempt_number):
    return attempt_number >= 5

def stop_never(attempt_number):
    return False

def wait_random_exponential(attempt_number, multiplier=1, max_wait=10):
    return min(multiplier * (2 ** random.uniform(0, attempt_number - 1)), max_wait)

def retry_if_exception_type(exceptions):
    return lambda e: isinstance(e, exceptions)

# Retry Decorator
def retry(stop=None, wait=None, retry=None, after=None, before_sleep=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt_number = 0
            first_rate_limit_encountered = False  # Cờ để theo dõi lần đầu gặp 429
            while True:
                try:
                    attempt_number += 1
                    return func(*args, **kwargs)
                except RateLimitException as e:
                    if not first_rate_limit_encountered:
                        # First time meeting 429, delay 2 minutes
                        first_rate_limit_encountered = True
                        wait_time = 120
                        info(f"Meet rate limit from Cloudflare. Sleeping for {wait_time} seconds.")
                        time.sleep(wait_time)
                    else:
                        # Subsequent 429 encounters follow the old retry logic
                        if stop and stop(e, attempt_number):
                            raise
                        if before_sleep:
                            before_sleep({'attempt_number': attempt_number})
                        wait_time = wait(attempt_number) if wait else 1
                        time.sleep(wait_time)
                except Exception as e:
                    if retry and not retry(e):
                        raise
                    if after:
                        after({'attempt_number': attempt_number, 'outcome': e})
                    if stop and stop(e, attempt_number):
                        raise
                    if before_sleep:
                        before_sleep({'attempt_number': attempt_number})
                    wait_time = wait(attempt_number) if wait else 1
                    time.sleep(wait_time)
        return wrapper
    return decorator

# Custom stop condition that handles RateLimitException and other exceptions separately
def custom_stop_condition(exception, attempt_number):
    if isinstance(exception, RateLimitException):
        return False
    return stop_after_custom_attempts(attempt_number)

# Retry configuration:
retry_config = {
    'stop': custom_stop_condition,
    'wait': lambda attempt_number: wait_random_exponential(
        attempt_number, multiplier=1, max_wait=10
    ),
    'retry': retry_if_exception_type((HTTPException,)),
    'before_sleep': lambda retry_state: info(
        f"Sleeping before next retry ({retry_state['attempt_number']})"
    )
}

# Rate Limiter Class
class RateLimiter:
    def __init__(self, interval: float = 1):
        self.interval = interval
        self.timestamp = time.time()

    def wait_for_next_request(self):
        now = time.time()
        elapsed = now - self.timestamp
        sleep_time = max(0, self.interval - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)
        self.timestamp = time.time()

# Rate Limited Request Decorator
def rate_limited_request(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        rate_limiter = RateLimiter()
        rate_limiter.wait_for_next_request()
        return func(*args, **kwargs)
    return wrapper
