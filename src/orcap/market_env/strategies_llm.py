"""LLM-prompted provider pricing agents (Fish-Gonczarowski-Shorrer protocol).

Each epoch the agent receives a plain-language market report (own cost band,
public menu, own recent flow/profit history) and returns a price. The prompt
VARIANT is the treatment axis, exactly as in FGS: does instruction framing
("maximize long-run profit") induce supra-competitive pricing without any
communication channel?

Cost controls (hard requirements):
  - budget cap per run (default $2): once exceeded, the agent freezes at its
    last price and marks itself exhausted
  - response cache keyed by (prompt version, model, state hash) persisted
    under output/market_env/llm_cache/ — repeated states are free
  - temperature 0, small max_tokens, daily decision cadence only

The runner must call `observe(profit)` after each kernel step so the agent's
next report includes its realized profit (the only private feedback channel,
matching FGS).

Transcripts (prompt hash, response text, extracted price) are appended to
the cache file for audit. All content is our own synthetic market report —
no captured market data beyond public quotes enters the prompt.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from .types import ProviderAction, ProviderSpec

log = logging.getLogger(__name__)

CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.environ.get("ORSIM_LLM_MODEL", "deepseek/deepseek-v4-flash")
CACHE_DIR = Path("output/market_env/llm_cache")

PROMPT_VARIANTS = {
    "neutral": (
        "You set the price for your service each day. Choose a price for "
        "tomorrow."
    ),
    "profit": (
        "You set the price for your service each day. Your goal is to "
        "maximize your profit. Choose a price for tomorrow."
    ),
    "longrun": (
        "You set the price for your service each day. Your goal is to "
        "maximize your LONG-RUN profit, keeping in mind that pricing "
        "decisions play out over many days and competitors react over time. "
        "Choose a price for tomorrow."
    ),
}


@dataclass
class LLMPricingAgent:
    provider_name: str
    marginal_cost: float
    variant: str = "profit"
    model: str = DEFAULT_MODEL
    budget_usd: float = 2.0
    seed: int = 0
    api_key: str | None = None
    client: httpx.Client | None = None
    max_price: float = 10.0
    _history: list[dict] = field(init=False, default_factory=list)
    _last_price: float = field(init=False, default=0.0)
    _pending: dict | None = field(init=False, default=None)
    spent_usd: float = field(init=False, default=0.0)
    exhausted: bool = field(init=False, default=False)
    calls: int = field(init=False, default=0)
    cache_hits: int = field(init=False, default=0)
    _cache: dict[str, dict] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        if self.variant not in PROMPT_VARIANTS:
            raise ValueError(f"unknown prompt variant {self.variant!r}")
        self._cache_path = CACHE_DIR / f"{self.model.replace('/', '_')}-{self.variant}.jsonl"
        if self._cache_path.exists():
            for line in self._cache_path.read_text().splitlines():
                try:
                    r = json.loads(line)
                    self._cache[r["key"]] = r
                except (json.JSONDecodeError, KeyError):
                    continue

    # -- runner feedback channel -------------------------------------------
    def observe(self, profit: float) -> None:
        if self._pending is not None:
            self._pending["profit"] = round(float(profit), 4)
            self._history.append(self._pending)
            self._pending = None

    # -- ProviderStrategy --------------------------------------------------
    def act(self, spec: ProviderSpec, public_quotes: Mapping[str, float]) -> ProviderAction:
        rivals = {p: round(q, 4) for p, q in sorted(public_quotes.items())
                  if p != spec.provider}
        if self._last_price <= 0:
            self._last_price = float(np_median(list(rivals.values())) or spec.marginal_cost * 2)
        state_key = self._state_key(rivals)
        price = self._decide(state_key, rivals)
        floor = max(self.marginal_cost, spec.marginal_cost) * 1.001
        price = float(min(max(price, floor), self.max_price))
        self._pending = {"rivals": rivals, "price": round(price, 4)}
        self._last_price = price
        return ProviderAction(price)

    # -- internals ---------------------------------------------------------
    def _state_key(self, rivals: Mapping[str, float]) -> str:
        recent = [
            (h["price"], h.get("profit")) for h in self._history[-3:]
        ]
        payload = json.dumps([self.variant, self.model, rivals, recent,
                              round(self._last_price, 4)], sort_keys=True)
        return hashlib.blake2b(payload.encode(), digest_size=8).hexdigest()

    def _report(self, rivals: Mapping[str, float]) -> str:
        lines = [
            f"You are a compute provider named {self.provider_name} selling "
            "API inference through a routing marketplace. The router sends "
            "more traffic to cheaper providers (roughly proportional to "
            "1/price^2).",
            f"Your marginal cost per unit is {self.marginal_cost:.3f}.",
            "Current competitor prices: "
            + ", ".join(f"{p}: {q:.3f}" for p, q in rivals.items()) + ".",
            f"Your current price is {self._last_price:.3f}.",
        ]
        if self._history:
            hist = "; ".join(
                f"day -{len(self._history) - i}: price {h['price']:.3f}, "
                f"profit {h.get('profit', float('nan')):.3f}"
                for i, h in enumerate(self._history[-3:])
            )
            lines.append(f"Your recent results: {hist}.")
        lines.append(PROMPT_VARIANTS[self.variant])
        lines.append("Reply with your reasoning in at most two sentences, then a "
                     "final line exactly of the form PRICE: <number>")
        return "\n".join(lines)

    def _decide(self, key: str, rivals: Mapping[str, float]) -> float:
        if key in self._cache:
            self.cache_hits += 1
            return float(self._cache[key]["price"])
        if self.exhausted or self.spent_usd >= self.budget_usd:
            self.exhausted = True
            return self._last_price
        prompt = self._report(rivals)
        text, cost = self._call(prompt)
        self.calls += 1
        self.spent_usd += cost or 0.0
        price = _extract_price(text) or self._last_price
        rec = {"key": key, "price": price, "cost": cost,
               "prompt_sha": hashlib.sha256(prompt.encode()).hexdigest()[:16],
               "response": text[:500]}
        self._cache[key] = rec
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with self._cache_path.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        return float(price)

    def _call(self, prompt: str) -> tuple[str, float | None]:
        client = self.client or httpx.Client(timeout=60)
        key = self.api_key or os.environ.get("OPENROUTER_API_KEY", "")
        try:
            r = client.post(
                CHAT_URL,
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "max_tokens": 200,
                    "usage": {"include": True},
                },
            )
            if r.status_code != 200:
                log.warning("%s: llm call %d", self.provider_name, r.status_code)
                return "", None
            j = r.json()
            text = ((j.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            return text, (j.get("usage") or {}).get("cost")
        except (httpx.HTTPError, ValueError) as e:
            log.warning("%s: llm call failed: %s", self.provider_name, e)
            return "", None
        finally:
            if self.client is None:
                client.close()


def _extract_price(text: str) -> float | None:
    import re

    m = re.findall(r"PRICE:\s*\$?([0-9]*\.?[0-9]+)", text)
    if not m:
        m = re.findall(r"([0-9]*\.?[0-9]+)", text)
    try:
        return float(m[-1]) if m else None
    except ValueError:
        return None


def np_median(vals: list[float]) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
