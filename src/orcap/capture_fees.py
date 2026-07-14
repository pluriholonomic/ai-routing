"""Daily fee/pricing-page watcher.

Snapshots the fee pages registered in config/fee_pages.toml: raw HTML to
raw/, one curated row per page per run with a content hash and every
percentage token in context. The content-hash delta across days is the
CBH-17 (waterbed) event trigger and the O1/R1 fee-migration feed — parsing
is best-effort, the archived HTML is the source of truth.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import re
import tomllib
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa

from .capture_api import write_partition
from .config import CURATED_DIR, RAW_DIR, dt_partition, run_timestamp

log = logging.getLogger(__name__)

REGISTRY = Path(__file__).resolve().parents[2] / "config" / "fee_pages.toml"
PCT_RE = re.compile(r"(\d{1,2}(?:\.\d{1,2})?)\s?%")
UA = {"User-Agent": "Mozilla/5.0 (orcap fee watcher; research; contact via repo)"}


def pct_tokens(text: str, max_tokens: int = 40) -> list[dict[str, Any]]:
    """Every percentage in the page with 40 chars of context either side."""
    out = []
    for m in PCT_RE.finditer(text):
        ctx = text[max(0, m.start() - 40) : m.end() + 40].replace("\n", " ")
        out.append({"value": float(m.group(1)), "context": ctx})
        if len(out) >= max_tokens:
            break
    return out


def capture(
    registry: Path = REGISTRY,
    curated_dir: Path = CURATED_DIR,
    raw_dir: Path = RAW_DIR,
) -> dict[str, Any]:
    with registry.open("rb") as f:
        pages = tomllib.load(f)["pages"]
    run_ts, dt = run_timestamp(), dt_partition()
    rows = []
    with httpx.Client(timeout=30, follow_redirects=True, headers=UA) as client:
        for p in pages:
            status, sha, tokens = None, None, []
            try:
                r = client.get(p["url"])
                status = r.status_code
                if r.status_code == 200:
                    body = r.text
                    sha = hashlib.sha256(body.encode()).hexdigest()
                    # strip tags crudely for context extraction
                    text = re.sub(r"<[^>]+>", " ", body)
                    tokens = pct_tokens(text)
                    out = raw_dir / "fee_pages" / f"dt={dt}"
                    out.mkdir(parents=True, exist_ok=True)
                    (out / f"{p['name']}-{run_ts}.html.gz").write_bytes(
                        gzip.compress(body.encode())
                    )
            except httpx.HTTPError as exc:
                log.warning("fee page %s failed: %s", p["name"], exc)
            rows.append(
                {
                    "run_ts": run_ts,
                    "dt": dt,
                    "name": p["name"],
                    "url": p["url"],
                    "page_kind": p["kind"],
                    "http_status": status,
                    "content_sha256": sha,
                    "pct_tokens_json": json.dumps(tokens, separators=(",", ":")),
                }
            )
    write_partition(pa.Table.from_pylist(rows), "fee_pages", run_ts, dt, curated_dir)
    ok = sum(1 for r in rows if r["http_status"] == 200)
    log.info("fee watcher: %d/%d pages captured", ok, len(rows))
    return {"pages": len(rows), "ok": ok}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    print(json.dumps(capture()))


if __name__ == "__main__":
    main()
