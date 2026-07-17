# LaTeX manuscripts

## Current focal manuscript

The paper currently under empirical/reviewer revision is
[`inference-market-microstructure/main.tex`](inference-market-microstructure/main.tex).
Its checked-in, rendered artifact is
[`../output/pdf/inference-market-microstructure.pdf`](../output/pdf/inference-market-microstructure.pdf).

The July 17, 2026 revision:

- replaces the corrupted pricing-event ledger with the exact chronological
  reconstruction (3,219 of 3,219 completed-day events);
- updates the outcome-blind H81 and H95 collection counts and immutable data
  revision;
- freezes a leakage-resistant 15-day/15-day PM1 temporal validation with fixed
  ridge estimation and an events-per-parameter gate before its holdout exists;
- replaces H81's published Monte Carlo tail approximation with an exact
  fixed-count Fisher test and a fail-closed 100,000-draw implementation audit;
- hardens the still-blinded H95 replication with exact within-triplet Fisher
  inference, explicit structural and measurement missingness, provider-control
  coverage, time/whole-triplet transport gates, and a sequential-position
  interference diagnostic; and
- compresses the main empirical argument to 15 pages through the references,
  moving price-atom diagnostics and proofs to Appendix A without deleting them.

The latest adversarial assessment is
[`../docs/manuscript-review-round-22-2026-07-17.md`](../docs/manuscript-review-round-22-2026-07-17.md).
It treats the structural paper objection as resolved; the remaining promotion
gates are unreleased H81/H95 outcomes and the unopened 30-completed-day PM1
holdout.

This directory contains three non-concurrent manuscripts built from the reviewed
research drafts:

- `capacity-certified-routing/main.tex`: a theory-first EC/WINE-style paper.
- `routescope/main.tex`: a NeurIPS-style evaluation-methodology/protocol paper.
- `inference-market-microstructure/main.tex`: an empirical EC/IO/OR-style paper
  on administered provider menus, focal price anchors, and router-manufactured
  quote firmness.

They intentionally remain separate. The first proves restricted mechanism
results under explicit assumptions; the second specifies the empirical
calibration required to assess a real inference router. Neither source claims
that the public quote panel identifies realized routing.

## Build

From each manuscript directory:

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

The verified rendered PDFs are written to `output/pdf/` at the repository root:

- `output/pdf/capacity-certified-routing.pdf`
- `output/pdf/routescope.pdf`
- `output/pdf/inference-market-microstructure.pdf`

All three manuscripts share `../references.bib`. Run `latexmk -C` inside any
source directory to remove only LaTeX build intermediates; do not remove the
versioned PDF deliverables.

The theory manuscript's explicitly synthetic theorem illustration is generated
from the checked-in mechanism implementation:

```bash
PYTHONPATH=. .venv/bin/python \
  paper/capacity-certified-routing/figures/generate_synthetic_examples.py
```

It rewrites only the figure PDF/PNG/JSON next to the generator. These are
declared-primitive examples, not estimates from the public routing panel.
