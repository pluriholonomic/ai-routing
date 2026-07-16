# LaTeX manuscripts

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

Both manuscripts share `../references.bib`. Run `latexmk -C` inside either
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
