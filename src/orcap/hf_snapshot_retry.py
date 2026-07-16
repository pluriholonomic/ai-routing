"""Retry Hugging Face snapshot hydration after transient CAS/Hub failures."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx
from huggingface_hub import snapshot_download as _snapshot_download
from huggingface_hub.errors import HfHubHTTPError

RETRYABLE_ERRORS = (HfHubHTTPError, httpx.TransportError, OSError)


def file_exists_retry(
    api: Any,
    *args: Any,
    attempts: int = 6,
    sleep: Callable[[float], None] = time.sleep,
    **kwargs: Any,
) -> bool:
    """Check Hub file existence without turning a transient timeout into absence.

    The memo workflow uses this check to decide whether it must hydrate a large
    legacy snapshot.  Exhausted retries therefore raise instead of returning
    ``False``: a network failure must not launch the expensive fallback path.
    """
    if attempts < 1:
        raise ValueError("attempts must be positive")

    for attempt in range(1, attempts + 1):
        try:
            return bool(api.file_exists(*args, **kwargs))
        except RETRYABLE_ERRORS as exc:
            if attempt == attempts:
                raise
            delay = min(2 ** (attempt - 1), 8)
            print(
                f"Hub file-existence attempt {attempt}/{attempts} failed "
                f"({type(exc).__name__}); retrying in {delay}s",
                flush=True,
            )
            sleep(delay)

    raise AssertionError("unreachable")


def snapshot_download_retry(
    *args: Any,
    attempts: int = 4,
    sleep: Callable[[float], None] = time.sleep,
    **kwargs: Any,
) -> str:
    """Download a snapshot, refreshing transient signed URLs between attempts.

    Completed files remain in the shared Hub cache, so a retry only has to
    recover missing objects. Error text is not logged here because Hub errors
    can contain long signed URLs.
    """
    if attempts < 1:
        raise ValueError("attempts must be positive")

    for attempt in range(1, attempts + 1):
        try:
            return _snapshot_download(*args, **kwargs)
        except RETRYABLE_ERRORS as exc:
            if attempt == attempts:
                raise
            delay = min(2 ** (attempt - 1), 8)
            print(
                f"Hub snapshot attempt {attempt}/{attempts} failed "
                f"({type(exc).__name__}); retrying in {delay}s",
                flush=True,
            )
            sleep(delay)

    raise AssertionError("unreachable")
