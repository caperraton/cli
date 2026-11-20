import random
import threading
import time
from typing import Any, Dict, Optional
import requests


class ResilientHTTPClient:
    """Thread-safe HTTP client with rate-limit awareness and exponential backoff."""

    def __init__(
        self,
        headers: Optional[Dict[str, str]] = None,
        max_retries: int = 6,
        base_delay: float = 1.5,
        max_delay: float = 120.0,
        timeout: int = 30,
        verify_ssl: bool = True,
    ):
        self.session = requests.Session()
        if headers:
            self.session.headers.update(headers)
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self._rate_lock = threading.Lock()
        self._pause_until = 0.0

    def _wait_if_paused(self) -> None:
        now = time.time()
        if self._pause_until > now:
            time.sleep(self._pause_until - now)

    def _set_global_pause(self, seconds: float) -> None:
        with self._rate_lock:
            target = time.time() + max(1.0, seconds)
            if target > self._pause_until:
                self._pause_until = target

    def request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        allow_404: bool = False,
    ) -> Optional[requests.Response]:
        for attempt in range(self.max_retries + 1):
            self._wait_if_paused()
            try:
                resp = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt == self.max_retries:
                    raise RuntimeError(f"Network error for {url}: {exc}") from exc
                self._backoff(attempt, f"network error ({exc})")
                continue

            # Proactive rate-limit check (GitHub / GHES headers)
            rem = resp.headers.get("X-RateLimit-Remaining")
            reset = resp.headers.get("X-RateLimit-Reset")
            if rem is not None and rem.isdigit() and int(rem) <= 5 and reset:
                wait = max(1.0, float(reset) - time.time() + 2.0)
                self._set_global_pause(wait)

            if resp.status_code == 404 and allow_404:
                return None

            if 200 <= resp.status_code < 300:
                return resp

            # Handle Rate Limits (429 or GitHub 403 secondary/primary limit)
            is_rate_limit = resp.status_code == 429 or (
                resp.status_code == 403
                and "rate limit" in resp.text.lower()
            )
            if is_rate_limit:
                if attempt == self.max_retries:
                    resp.raise_for_status()
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait = float(retry_after) + random.uniform(0.5, 2.0)
                elif reset and reset.isdigit():
                    wait = max(1.0, float(reset) - time.time() + 2.0)
                else:
                    wait = min(
                        self.max_delay,
                        self.base_delay * (2**attempt) + random.uniform(0.5, 3.0),
                    )
                print(f"[rate-limit] {url} -> pausing {wait:.1f}s (attempt {attempt + 1})")
                self._set_global_pause(wait)
                continue

            # Handle transient 5xx errors
            if resp.status_code in (500, 502, 503, 504):
                if attempt == self.max_retries:
                    resp.raise_for_status()
                self._backoff(attempt, f"HTTP {resp.status_code}")
                continue

            # Non-retryable 4xx
            resp.raise_for_status()

        return None

    def _backoff(self, attempt: int, reason: str) -> None:
        delay = min(
            self.max_delay,
            self.base_delay * (2**attempt) + random.uniform(0.2, 1.5),
        )
        print(f"[backoff] {reason}; retrying in {delay:.1f}s (attempt {attempt + 1})")
        time.sleep(delay)