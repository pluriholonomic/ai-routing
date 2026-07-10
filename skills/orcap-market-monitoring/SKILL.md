---
name: orcap-market-monitoring
description: Operate, extend, and diagnose the ORCAP OpenRouter, GPU, and comparative-market data monitor. Use when changing collectors or GitHub workflows, investigating stale or missing data, adding a source, validating raw-to-curated lineage, running source-health checks, or preventing a degraded monitor from publishing as healthy.
---

# ORCAP Market Monitoring

Operate this repository as an evidence-preserving monitor. Treat the private
Hugging Face dataset as authoritative and local `data/` as staging.

## Start with health and ownership

1. Read `docs/repo-guide.md` and `config/sources.toml`.
2. Identify the collector, source key, output table, and owning workflow.
3. Run `uv run orcap quality --profile <profile>` before diagnosing market
   behavior. A red source state is a monitoring incident, not evidence of a
   quiet market.
4. Inspect raw JSONL.gz before a normalized parquet table. Preserve raw
   payloads and source-run records for every collector attempt.

## Change a collector safely

1. Write a source contract using `references/monitor-contract.md`.
2. Keep source identity, observed timestamp/block, schema version, and raw
   payload linkage in the normalized rows.
3. Record `success`, `degraded`, `failed`, or `skipped` with
   `write_source_run`; never represent a missing credential as zero activity.
4. Add parser, schema, and failure-mode tests. Use a temporary
   `ORCAP_DATA_DIR` for live smoke tests.
5. Add the source to `config/sources.toml`, choose its required/optional
   semantics, then add the matching quality command to its workflow.

## Publish safely

- Run `uv run pytest -q` and `uv run ruff check .`.
- Keep `orcap analyze` strict. Use `--allow-partial` only for deliberate
  exploratory work and do not publish its result as a healthy memo.
- Require a green required-source profile before a clean memo publication.
- Surface optional-source failures as degraded in the source ledger and memo.

## Do not

- Put API keys in source, raw payloads, analysis outputs, or git history.
- Use a dashboard aggregate as the only evidence for a microstructure claim.
- Repair a source by overwriting historical raw data or suppressing an error.
