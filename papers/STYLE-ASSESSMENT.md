# Style assessment: the three venue papers vs. Tarun Chitra's published voice

*2026-07-18. Grounded in a deep literature sweep of ten Chitra papers
(arXiv:1911.03380, 2012.08040, 2006.11156, 2003.10001, 2001.00919,
2207.11835, 2310.07865, 2403.02525, 2408.00928, plus Gauntlet/Medium
writing) and the local `tarun-writing-style` skill (2024–26 drafts). The
full researched profile is reproduced at the bottom of this file's commit
message trail; the 15-item fidelity checklist below is the scoring
instrument. Scores are AFTER the alignment pass applied to the LaTeX
versions; the pre-alignment score is in parentheses.*

## Key stylometric facts from the sweep

- Two eras: 2019–2023 (Angeris-era: convex-optimization skeleton,
  definition-driven, "Note that / In other words" dense) and 2024–2026
  (Pai-era: rhetorical-question framing, named dated incidents,
  "Our results suggest…" abstract closers). Current voice = late era
  over the early era's mathematical skeleton.
- Signature moves: question/pun titles ("Why Stake When You Can
  Borrow?", "The Specter (and Spectra) of MEV"); abstracts opening with
  a real-world scale fact, never "This paper introduces"; a mid-abstract
  question ("A natural question to ask is…"); flagged surprise with the
  reversal word *italicized*; italics-not-bold for emphasis; 6–10
  substantive footnotes (contract-level detail, TradFi analogies, casual
  physics erudition — quenched disorder, de Finetti); phase-transition /
  threshold result shapes; `\paragraph{}` intro beats ending in
  `\paragraph{Prior work.}`; every formal result followed by "In other
  words / This suggests that / This bound demonstrates that"; short
  "Conclusion" restating the economic upshot with one honest hedge
  ("at least at first glance").

## Scores (out of 15)

### EC — "The Router Is the Mechanism" : **14 (was 10)**

| # | Item | Verdict |
|---|------|---------|
| 1 | Title pattern | ✓ declarative-thesis + colon — his "Composability is the source…" register; not a question, but within corpus range |
| 2 | Abstract opens with scale fact | ✓ (added: trillions of tokens/month, ~90 providers) |
| 3 | Mid-abstract question / italicized surprise | ✓ ("A natural question to ask is: what market does this rule *buy*?"; "counterintuitively… *falls*") |
| 4 | "Our results suggest…" closer | ✓ (added) |
| 5 | Intro `\paragraph{}` beats + Prior work | ✓ (added: Routing marketplaces / What the data forces / Temperature, not taste / Prior work / Contributions) |
| 6 | Named naive model + gap | ✓ (structural-IO footnote; Calvano/JRW/Demirer gaps stated flatly) |
| 7 | Contributions with §/Thm pointers | ✓ |
| 8 | Post-theorem glosses | ✓ (added "In other words…", "This bound demonstrates…") |
| 9 | Threshold/phase-transition shapes | ✓✓ (critical line; deterrence threshold; resilience threshold ρ≈5%) |
| 10 | House notation | ◐ (a, θ, δ† — coherent, but not his Δ/Λ/γ-fee conventions; deliberate, since the deployed rule's notation leads) |
| 11 | ≥6 substantive footnotes | ✓ (7: curvature-by-vibes, structural-IO, last-look, PFOF, probe-protocol minimalism, quenched disorder, power-plant quip) |
| 12 | Named systems + numbers recur | ✓ (OpenRouter, vast.ai H100 book, 3.9%/23.3%, 41c) |
| 13 | Appendix proofs + late validation | ✓ |
| 14 | Tone audit (natural / Note that / italics / hedges) | ✓ ("A natural question…", italics on reversals, "at least at first glance" in the conclusion) |
| 15 | Short Conclusion, upshot + one hedge | ✓ (added) |

Residual gap: item 10 — adopting his Δ/Λ trade notation would be
affectation here; the mechanism's own published symbols should lead.

### NeurIPS — "The Price of Softmax" : **12 (was 9)**

Hits: pun title in his register (Price-of-Anarchy echo); scale-fact
opening + "natural question" (added); italicized-surprise finding (3)
(added); "Our results suggest…" closer (added); named systems with
numbers; phase-transition shape; theory-gloss discipline. Misses:
footnote density (venue format compresses his footnote culture — 3
substantive vs his 6–10); no `\paragraph{Prior work.}` beat (related
work is a numbered section per venue norm); notation item as above.
These are venue-constraint costs, not drift: the framing choices (the
opening line, the inverted question "what do learners converge to in the
market actually deployed") are recognizably his.

### ICML — "Phase Transitions in Routing Games" : **11 (was 8)**

Hits after alignment: scale-fact opening; "Our results suggest…" closer
with a bounded non-obvious takeaway; phase-transition headline (his
favorite result shape — cf. "a formal proof of a phase transition
between equilibria", arXiv:2001.00919); honest-hedge calibration.
Misses: fewest footnotes and analogies of the three (the sober ICML
register mutes the microstructure asides that anchor his voice); title
is descriptive-with-colon rather than question/pun; the QRE connection
is exactly where his style would drop a casual McKelvey–Palfrey aside
and the current text under-plays it. Recommendation if this paper is
revised toward resubmission anyway (per its review): retitle in question
form — e.g., "Can Learners Find the Ceiling?" — and let the erudition
footnotes back in; the venue tolerates more voice than the draft uses.

## Overall

The trilogy now reads late-era Chitra: physics framing that is
load-bearing, microstructure analogies doing argumentative work,
assertive theses with explicit scope fences, and results stated as
design levers with recommended parameter values. The EC flagship is the
closest match (14/15); the conference-format papers pay a deliberate
venue tax on footnote culture. All three LaTeX files compile clean
(pdflatex, TeX Live 2025; EC on acmart, NeurIPS/ICML on article-class
approximations with a comment marking where the official style files
drop in).
