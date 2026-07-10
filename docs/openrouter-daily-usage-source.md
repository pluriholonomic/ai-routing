# OpenRouter daily aggregate model-usage source

`openrouter_rankings_daily` is an opt-in capture of OpenRouter's documented
authenticated daily rankings API:

```text
GET https://openrouter.ai/api/v1/datasets/rankings-daily
```

The endpoint supplies up to the 50 public models with the most total token
usage per UTC day and exactly one source-defined `other` aggregate. The API
reports total tokens as prompt plus completion tokens under OpenRouter's
upstream tokenizer accounting. It can request a bounded historical interval
from 2025-01-01 onward; see the [OpenRouter API reference](https://openrouter.ai/docs/api/api-reference/datasets/get-rankings-daily).

## Capture

Set a credential only in the job environment, then run the explicit collector:

```bash
export ORCAP_OPENROUTER_DATASET_API_KEY='...'
uv run orcap capture-openrouter-usage --start-date 2026-06-10 --end-date 2026-07-09
```

If the credential is absent, the command writes an immutable `skipped`
source-run record and makes no network request. Authentication is passed in an
HTTP header and is not retained in raw capture files. This collector does not
send any inference requests, prompts, or user data.

The raw response is retained under `raw/openrouter_datasets/`; normalized rows
are written to `curated/openrouter_rankings_daily/`. The parser rejects an
invalid metadata range, duplicate model-day rows, missing/duplicate `other`
rows, empty days, and more than 50 named models per day.

## Analysis and claim boundary

Run:

```bash
uv run orcap analyze --hypothesis h64 --out analysis
```

H64 retains the latest captured revision per `(source_date, model_permaslug)`
and reports daily total tokens, top-50 versus `other` shares, and top-model
concentration. It requires 30 consecutive complete source days (50 named
models plus `other`) before labeling the aggregate demand time series ready.

This is model-level aggregate demand concentration within OpenRouter's own
reported accounting. It is not provider routing or allocation, individual
requests, prompts, completions, user behavior, price elasticity, latency,
revenue, quality, or cross-provider token-equivalent usage. It should not be
used to infer a provider's routed share or market-clearing volume.

The source is intentionally not in a scheduled profile. Enabling recurring
collection or publishing its captured rows requires an explicit operational
decision about the API credential and publication scope.
