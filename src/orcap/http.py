"""Async HTTP helpers: shared client, polite rate limiting, retries, raw-layer writer."""

import asyncio
import gzip
import json
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import MAX_CONCURRENCY, REQUESTS_PER_SECOND, USER_AGENT


class RateLimiter:
    """Simple token-interval limiter: at most `rps` request starts per second."""

    def __init__(self, rps: float):
        self._interval = 1.0 / rps
        self._next_at = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = self._next_at - now
            self._next_at = max(now, self._next_at) + self._interval
        if delay > 0:
            await asyncio.sleep(delay)


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
        limits=httpx.Limits(max_connections=MAX_CONCURRENCY),
    )


class Fetcher:
    """Rate-limited, retrying GET that records every response for the raw layer."""

    def __init__(self, client: httpx.AsyncClient, rps: float | None = None):
        self.client = client
        self.limiter = RateLimiter(rps or REQUESTS_PER_SECOND)
        self.records: list[dict[str, Any]] = []

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        wait=wait_exponential(multiplier=1, max=30),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    async def _get(self, url: str, headers: Mapping[str, str] | None = None) -> httpx.Response:
        await self.limiter.wait()
        resp = await self.client.get(url, headers=headers)
        if resp.status_code in (429, 500, 502, 503, 504):
            resp.raise_for_status()
        return resp

    async def get_json(self, url: str, headers: Mapping[str, str] | None = None) -> Any | None:
        """GET a JSON document; returns None (and records the failure) on hard errors."""
        fetched_at = datetime.now(UTC).isoformat()
        try:
            resp = await self._get(url, headers=headers)
        except httpx.HTTPError as exc:
            self.records.append(
                {"fetched_at": fetched_at, "url": url, "status": None, "error": str(exc)}
            )
            return None
        try:
            body = resp.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            # e.g. Wayback id_ snapshots can be raw gzip bytes without headers
            try:
                body = json.loads(gzip.decompress(resp.content))
            except Exception:
                body = None
        if body is None:
            try:
                fallback = resp.text[:200_000]
            except UnicodeDecodeError:
                fallback = f"<binary {len(resp.content)} bytes>"
        self.records.append(
            {
                "fetched_at": fetched_at,
                "url": url,
                "status": resp.status_code,
                "body": body if body is not None else fallback,
            }
        )
        return body if resp.status_code == 200 else None

    async def get_text(self, url: str, headers: Mapping[str, str] | None = None) -> str | None:
        """GET a text document while retaining the verbatim response in the raw layer."""
        fetched_at = datetime.now(UTC).isoformat()
        try:
            resp = await self._get(url, headers=headers)
            body = resp.text
        except (httpx.HTTPError, UnicodeDecodeError) as exc:
            self.records.append(
                {"fetched_at": fetched_at, "url": url, "status": None, "error": str(exc)}
            )
            return None
        self.records.append(
            {"fetched_at": fetched_at, "url": url, "status": resp.status_code, "body": body}
        )
        return body if resp.status_code == 200 else None

    async def post_json(
        self,
        url: str,
        payload: Any,
        headers: Mapping[str, str] | None = None,
        *,
        record_url: str | None = None,
    ) -> Any | None:
        """POST JSON while preserving raw evidence without persisting credentials.

        Some API credentials are embedded in a provider URL rather than a
        header (for example a Graph gateway key or managed JSON-RPC URL).
        Callers can keep the real request URL private while storing a stable,
        redacted provenance label in the raw layer.
        """
        fetched_at = datetime.now(UTC).isoformat()
        try:
            await self.limiter.wait()
            resp = await self.client.post(url, json=payload, headers=headers)
            if resp.status_code in (429, 500, 502, 503, 504):
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            self.records.append(
                {"fetched_at": fetched_at, "url": url, "status": None, "error": str(exc)}
            )
            return None
        try:
            body = resp.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            try:
                body = json.loads(gzip.decompress(resp.content))
            except Exception:
                try:
                    body = resp.text[:200_000]
                except UnicodeDecodeError:
                    body = f"<binary {len(resp.content)} bytes>"
        self.records.append(
            {
                "fetched_at": fetched_at,
                "url": record_url or url,
                "method": "POST",
                "request_json": payload,
                "status": resp.status_code,
                "body": body,
            }
        )
        return body if resp.status_code == 200 else None


def write_raw(
    records: list[dict[str, Any]], source: str, raw_dir: Path, run_ts: str, dt: str
) -> Path:
    """Persist verbatim responses as raw/{source}/dt=YYYY-MM-DD/{run_ts}.jsonl.gz."""
    out_dir = raw_dir / source / f"dt={dt}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{run_ts}.jsonl.gz"
    with gzip.open(out, "wt", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")
    return out
