"""Eval probes: pinned quality fingerprints, graded benchmark items, shape routing.

Three arms, all motivated by the fact that ROUTING DEPENDS ON THE PROMPT
(eligibility filters on context/features, and possibly load):

  fingerprint arm   For each selected model, PIN each of up to 4 quoted
                    providers (only+order, no fallbacks) and run the
                    versioned deterministic battery at temperature 0.
                    Identical weights+samplers produce identical greedy
                    continuations, so cross-provider agreement of output
                    HASHES tests model equality (Gao et al. style) without
                    retaining any content. SENSITIVE but uncalibrated.
  graded arm        Known input/output benchmark items (MMLU + GSM8K test
                    samples, data-static/eval_items.jsonl, 500-item pool)
                    graded against ground truth. A rotating daily subset
                    (seeded by date) is drawn from the pool — the SAME
                    items for every provider that day, enabling paired
                    (McNemar) provider-vs-provider accuracy comparison —
                    and rotation defeats provider special-casing of famous
                    prompts. CALIBRATED but coarser: detects degradation
                    (quantization, truncation) as an accuracy gap.
  shape arm         Default-routed probes (no provider block) in two
                    shapes — short chat vs ~2k-token padded context —
                    to measure whether the default policy's selection
                    distribution shifts with workload shape.

Privacy: completions are hashed (sha256 of raw and of normalized text) and
discarded; graded rows additionally keep the extracted answer token (a
letter or number). All prompts are fixed public battery/benchmark items —
no user content exists anywhere in this path.

Cost bound: ~300 requests/day, dominated by 4-per-day GSM8K chains at
<=400 output tokens — a few cents per day.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import re
import time
import tomllib
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa

from .capture_api import write_partition
from .config import API_V1, BASE_URL, CURATED_DIR, dt_partition, run_timestamp

log = logging.getLogger(__name__)

BATTERY = Path(__file__).resolve().parents[2] / "config" / "eval_battery.toml"
ITEMS = Path(__file__).resolve().parents[2] / "data-static" / "eval_items.jsonl"
K_MMLU = int(os.environ.get("ORCAP_EVAL_K_MMLU", "16"))
K_GSM = int(os.environ.get("ORCAP_EVAL_K_GSM", "4"))
CHAT_URL = f"{BASE_URL}/api/v1/chat/completions"
RANKINGS_URL = f"{BASE_URL}/api/frontend/v1/rankings/models?view=week"
MODELS_URL = f"{BASE_URL}/api/v1/models"
N_MODELS = int(os.environ.get("ORCAP_EVAL_MODELS", "4"))
N_PROVIDERS = int(os.environ.get("ORCAP_EVAL_PROVIDERS", "4"))
PAD_TOKENS = 2000

def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        "HTTP-Referer": "https://github.com/pluriholonomic/ai-routing",
        "X-Title": "orcap eval probes",
    }


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def battery() -> dict[str, Any]:
    with BATTERY.open("rb") as f:
        return tomllib.load(f)


def pick_models(client: httpx.Client, n: int = N_MODELS) -> list[str]:
    from .capture_probes import hot_model_ids

    rankings = client.get(RANKINGS_URL).json()
    models = client.get(MODELS_URL).json()
    return hot_model_ids(rankings, models, n=n)


def quoted_providers(client: httpx.Client, model_id: str) -> list[dict[str, Any]]:
    try:
        r = client.get(f"{API_V1}/models/{model_id}/endpoints")
        if r.status_code != 200:
            return []
    except httpx.HTTPError:
        return []
    eps = []
    for ep in (r.json().get("data") or {}).get("endpoints") or []:
        name = ep.get("provider_name")
        try:
            price = float((ep.get("pricing") or {}).get("completion"))
        except (TypeError, ValueError):
            continue
        if name and price > 0:
            eps.append({"provider": name, "price": price})
    eps = sorted(eps, key=lambda e: e["price"])
    if len(eps) <= N_PROVIDERS:
        return eps
    # cheapest, second, median, most expensive — spread across the book
    mid = eps[len(eps) // 2]
    picks = [eps[0], eps[1], mid, eps[-1]]
    seen, out = set(), []
    for p in picks:
        if p["provider"] not in seen:
            seen.add(p["provider"])
            out.append(p)
    return out[:N_PROVIDERS]


def _chat(client: httpx.Client, model_id: str, prompt: str, max_tokens: int,
          provider: str | None = None) -> tuple[dict | None, int | None]:
    body: dict[str, Any] = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "usage": {"include": True},
    }
    if provider:
        body["provider"] = {"only": [provider], "order": [provider], "allow_fallbacks": False}
    status = None
    for attempt in range(3):
        try:
            r = client.post(CHAT_URL, headers=_headers(), json=body, timeout=90)
            status = r.status_code
            if status == 200:
                try:
                    return r.json(), status
                except ValueError:
                    # 200 with malformed body (keep-alive padding) — retry
                    pass
            elif status not in (429, 500, 502, 503):
                return None, status
        except httpx.HTTPError:
            status = None
        time.sleep(3 * (attempt + 1))
    return None, status


def fingerprint_rows(client: httpx.Client, model_id: str, run_ts: str, dt: str,
                     bat: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    eps = quoted_providers(client, model_id)
    # item-major order: consecutive requests hit DIFFERENT providers,
    # spacing out any one provider's per-key rate limit
    for p in bat["prompts"]:
        for ep in eps:
            resp, status = _chat(client, model_id, p["text"], p["max_tokens"], ep["provider"])
            text = ""
            usage = {}
            finish = None
            if resp:
                choice = (resp.get("choices") or [{}])[0]
                text = (choice.get("message") or {}).get("content") or ""
                finish = choice.get("finish_reason")
                usage = resp.get("usage") or {}
            rows.append({
                "run_ts": run_ts, "dt": dt,
                "battery": bat["version"], "prompt_id": p["id"],
                "model_id": model_id, "provider": ep["provider"],
                "quoted_price_completion": ep["price"],
                "http_status": status,
                "output_sha256": _sha(text) if text else None,
                "output_norm_sha256": _sha(_normalize(text)) if text else None,
                "output_len_chars": len(text),
                "finish_reason": finish,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "cost_usd": usage.get("cost"),
            })
    return rows


def daily_items(dt: str) -> list[dict[str, Any]]:
    """Rotating per-day subset: same items for every provider/model that day."""
    pool = [json.loads(line) for line in ITEMS.read_text().splitlines() if line.strip()]
    rng = random.Random(f"orcap-eval-{dt}")
    mmlu = [r for r in pool if r["source"] == "mmlu"]
    gsm = [r for r in pool if r["source"] == "gsm8k"]
    return rng.sample(mmlu, min(K_MMLU, len(mmlu))) + rng.sample(gsm, min(K_GSM, len(gsm)))


def extract_answer(text: str, grade: str) -> str | None:
    if grade == "letter":
        m = re.search(r"\b([ABCD])\b", text.strip().upper())
        return m.group(1) if m else None
    m = re.findall(r"####\s*(-?[\d,]+(?:\.\d+)?)", text)
    if not m:
        m = re.findall(r"(-?[\d,]+(?:\.\d+)?)", text)
    return m[-1].replace(",", "").rstrip(".") if m else None


def graded_rows(client: httpx.Client, model_id: str, run_ts: str, dt: str,
                items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    eps = quoted_providers(client, model_id)
    for it in items:
        for ep in eps:
            resp, status = _chat(client, model_id, it["prompt"], it["max_tokens"], ep["provider"])
            text = ""
            usage = {}
            finish = None
            if resp:
                choice = (resp.get("choices") or [{}])[0]
                text = (choice.get("message") or {}).get("content") or ""
                finish = choice.get("finish_reason")
                usage = resp.get("usage") or {}
            extracted = extract_answer(text, it["grade"]) if text else None
            rows.append({
                "run_ts": run_ts, "dt": dt,
                "item_id": it["item_id"], "source": it["source"],
                "model_id": model_id, "provider": ep["provider"],
                "quoted_price_completion": ep["price"],
                "http_status": status,
                "extracted_answer": extracted,
                "correct": (extracted == it["answer"]) if extracted is not None else None,
                "output_sha256": _sha(text) if text else None,
                "output_len_chars": len(text),
                "finish_reason": finish,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "cost_usd": usage.get("cost"),
            })
    return rows


def shape_rows(client: httpx.Client, model_id: str, run_ts: str, dt: str) -> list[dict[str, Any]]:
    pad = ("lorem ipsum dolor sit amet " * (PAD_TOKENS // 5)).strip()
    shapes = {
        "short": "Reply with the single word: pong",
        "padded_2k": pad + "\n\nAfter reading the filler above, reply with the single word: pong",
    }
    rows = []
    for shape, prompt in shapes.items():
        resp, status = _chat(client, model_id, prompt, 4)
        provider = (resp or {}).get("provider")
        rows.append({
            "run_ts": run_ts, "dt": dt, "model_id": model_id, "shape": shape,
            "http_status": status, "selected_provider": provider,
            "prompt_tokens": ((resp or {}).get("usage") or {}).get("prompt_tokens"),
        })
    return rows


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    bat = battery()
    run_ts, dt = run_timestamp(), dt_partition()
    items = daily_items(dt)
    fps: list[dict[str, Any]] = []
    grd: list[dict[str, Any]] = []
    shp: list[dict[str, Any]] = []
    with httpx.Client(timeout=90) as client:
        for model_id in pick_models(client):
            fps.extend(fingerprint_rows(client, model_id, run_ts, dt, bat))
            grd.extend(graded_rows(client, model_id, run_ts, dt, items))
            shp.extend(shape_rows(client, model_id, run_ts, dt))
    if fps:
        write_partition(pa.Table.from_pylist(fps), "eval_fingerprints", run_ts, dt, CURATED_DIR)
    if grd:
        write_partition(pa.Table.from_pylist(grd), "eval_graded", run_ts, dt, CURATED_DIR)
    if shp:
        write_partition(pa.Table.from_pylist(shp), "eval_shape_routing", run_ts, dt, CURATED_DIR)
    n_correct = sum(1 for r in grd if r["correct"])
    n_answered = sum(1 for r in grd if r["correct"] is not None)
    print(json.dumps({
        "fingerprints": len(fps),
        "fp_with_output": sum(1 for r in fps if r["output_sha256"]),
        "graded": len(grd), "graded_answered": n_answered, "graded_correct": n_correct,
        "shape_probes": len(shp),
        "est_cost_usd": round(float(sum((r.get("cost_usd") or 0) for r in fps + grd)), 4),
    }))


if __name__ == "__main__":
    main()
