# Writing-style assessment for the EC, ICML, and NeurIPS manuscripts

*Assessment date: 2026-07-18.  The purpose is to distinguish recurring features
of Tarun Chitra's published writing from a generic ``crypto-mechanism-design''
voice, then apply those features to the three venue manuscripts.*

## Bottom line

The original Markdown drafts did not consistently match the published corpus.
They captured three real habits -- cross-domain modeling, theorem-to-mechanism
translation, and an insistence on operational consequences -- but exaggerated
the surface voice.  In particular, repeated bold slogans, the long enumerative
abstracts, and lines such as ``one does not operate a power plant at
criticality'' or ``chosen by vibes'' read more like a synthetic imitation than
the papers themselves.

The corpus supports a quieter and more precise style:

1. establish the live mechanism and why it matters;
2. formulate the smallest model that exposes the design tradeoff;
3. state exact results in plain declarative sentences;
4. test or instantiate them on public, reconstructable data; and
5. end with an implementable design consequence and an explicit limitation.

The revised LaTeX manuscripts follow that sequence.  They preserve the
physics and market-microstructure connections only where those connections do
analytical work.

## Corpus and method

The assessment gives the most weight to solo and first-author papers, then uses
coauthored papers only for features that recur across author teams.  This is
important: a coauthored paper is evidence about a shared final text, not a
clean sample of one author's prose.

### High-weight samples

- Tarun Chitra, [Competitive Equilibria between Staking and On-Chain
  Lending](https://arxiv.org/abs/2001.00919) (solo, 2020).
- Tarun Chitra, [Autodeleveraging: Impossibilities and
  Optimization](https://arxiv.org/abs/2512.01112) (solo, 2025/2026).
- Tarun Chitra et al., [Autodeleveraging as Online
  Learning](https://arxiv.org/abs/2602.15182) (first author, 2026).
- Tarun Chitra, Kshitij Kulkarni, and Karthik Srinivasan, [Optimal Routing in
  the Presence of Hooks](https://arxiv.org/abs/2502.02059) (first author,
  2025).
- Tarun Chitra, Matheus Ferreira, and Kshitij Kulkarni, [Credible, Optimal
  Auctions via Blockchains](https://eprint.iacr.org/2023/114.pdf) (first
  author, 2023).

### Cross-check samples

- Guillermo Angeris and Tarun Chitra, [Improved Price Oracles: Constant
  Function Market Makers](https://arxiv.org/abs/2003.10001).
- Guillermo Angeris, Alex Evans, and Tarun Chitra, [When Does the Tail Wag the
  Dog? Curvature and Market Making](https://arxiv.org/abs/2012.08040).
- Kshitij Kulkarni, Theo Diamandis, and Tarun Chitra, [Towards a Theory of
  Maximal Extractable Value I](https://arxiv.org/abs/2207.11835).
- Guillermo Angeris et al., [The Geometry of Constant Function Market
  Makers](https://arxiv.org/abs/2308.08066).
- Guillermo Angeris et al., [Optimal Routing for Constant Function Market
  Makers](https://arxiv.org/abs/2204.05238).
- Theo Diamandis, Max Resnick, Tarun Chitra, and Guillermo Angeris, [An
  Efficient Algorithm for Optimal Routing Through Constant Function Market
  Makers](https://arxiv.org/abs/2302.04938).
- Guillermo Angeris, Tarun Chitra, Theo Diamandis, and Kshitij Kulkarni, [The
  Specter (and Spectra) of Miner Extractable
  Value](https://arxiv.org/abs/2310.07865).
- Theo Diamandis et al., [Designing Multidimensional Blockchain Fee
  Markets](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.AFT.2023.4).

The search also used the [DBLP author record](https://dblp.org/pid/239/5999)
to reduce selection bias toward only the well-known CFMM papers.  The local
analysis corpus contains page-layout text extracted from the primary PDFs; no
secondary summary was used to infer prose style.

As a small quantitative cross-check, ten corpus papers repeatedly use direct
research verbs such as ``we show,'' ``we consider,'' and ``in this paper.''
Across the same files, explicit uses of ``practitioner'' are rare.  The applied
orientation is conveyed through the problem formulation and final mechanism,
not through repeatedly labeling a paragraph as practical.

## Recurring style features

### 1. The opening starts with a mechanism, not a metaphor

The staking paper begins from the cost of Sybil resistance; the ADL papers
begin from a venue's residual-loss mechanism; the routing papers begin from a
user order over a network of CFMMs.  The prose usually explains what the system
does before saying what mathematical object it resembles.

**Implication for this trilogy:** explain open weights, providers, and router
dispatch before introducing Gibbs measures.  ``The exponent is inverse
temperature'' is useful after the allocation rule is defined; it is weak as a
standalone opening flourish.

### 2. Cross-domain analogies transfer a model

The strongest analogies map an operational object onto a mathematical one:
staking versus lending becomes a portfolio-allocation phase transition;
curvature becomes price sensitivity; routing becomes convex optimization; ADL
becomes online learning.  The analogy earns space by yielding a theorem,
algorithm, or measurement.

**Implication:** retain the Gibbs and AMM-curvature connections because they
identify the exponent's role.  Retain last look only to explain the direction
of quote response.  Remove analogies that merely add attitude.

### 3. Natural questions organize long introductions

The papers often move from system description to one or more natural
questions, then to ``In this paper, we...''.  The questions are concrete:
optimal routing, solvency under repeated ADL, or whether lending can reduce
staking security.  They do not arrive as a long contributions inventory in the
abstract.

**Implication:** abstracts should contain the object, method, principal result,
and scope in roughly five sentences.  Detailed contribution numbering belongs
in the introduction.

### 4. Definitions precede interpretation

Technical sections define the state, strategy, utility, or feasible trade
before offering broad economic language.  The strongest papers use short
micro-headings (for example, ``Network trade vector'' or ``Autodeleveraging'')
to keep a dense construction navigable.

**Implication:** each manuscript now defines route share and profit before
using ``critical line,'' ``markup floor,'' or ``delayed credit.''  The EC paper
uses theorem--interpretation--design blocks; the ML papers use
environment--gate--result--limitation blocks.

### 5. Claims are declarative but bounded

The corpus is willing to say ``we show'' frequently, but the object of the verb
is normally exact: a convex formulation, an impossibility theorem, a regret
bound, or a replay estimate.  Applied papers distinguish ex ante and ex post
benchmarks, public observability, and assumptions needed for reconstruction.

**Implication:** the LaTeX versions distinguish:

- exact static theorems from elastic-demand sensitivities;
- an owned-probe conditional ratio from identification of a proprietary
  routing penalty;
- simulated mechanism counterfactuals from live-router causality; and
- emergent coordination in a learning environment from provider conduct.

### 6. Numerical examples close the loop

The papers do not stop at existence or asymptotics.  They provide a route
solver, a realistic CFMM network, an event reconstruction, or an implementable
controller.  Numbers are most persuasive when tied to a benchmark or bound.

**Implication:** the manuscripts keep the critical-line calibration, delayed-
credit boundary, welfare frontier, and verified-quality threshold.  They avoid
turning every number into a headline.

### 7. The prose is technical, not theatrical

There is personality in titles (``tail wag the dog,'' ``specter and spectra'')
and in the choice of examples.  The body, however, mostly uses conventional
technical prose.  Opinionated footnotes are not common enough in the corpus to
be treated as a signature requirement.

**Implication:** one memorable title or analogy is enough.  Repeated bold
declarations, all-caps emphasis, and adversarial asides create the ``AI slop''
effect because they simulate confidence without improving identification.

## Venue-by-venue assessment

### ACM EC: `The Router Is the Mechanism`

**Original fidelity: medium.**  The model-to-design arc and the platform
incentive conflict are strongly aligned with the corpus.  The abstract was too
long, the introduction overused the physics frame, and some lines assigned
more intent than the evidence can support.

**Revision:** the LaTeX version starts from the intermediary's allocation
problem; states the exact equilibrium and delayed-credit results as formal
objects; treats the history multiplier as a reduced-form counterfactual; keeps
the two-type welfare table; and ends with implementable mechanism choices.
This is the closest of the three to the solo ADL paper's
impossibility--optimization--replay structure.

**Remaining paper-level issue:** the central empirical steering input still
needs the immutable probe result and claim boundary used by the focal empirical
paper.  Typesetting cannot repair an identification gap.

### ICML: `Phase Transitions in Price-Weighted Routing Games`

**Original fidelity: superficially restrained, structurally incomplete.**  Its
tone was closer to the corpus than the EC draft, but it promised a learning-
dynamics result without a learning-dynamics theorem or algorithmic sweep.  The
review correctly identified that mismatch.

**Revision:** the LaTeX version makes the exact stage-game result formal,
derives the $O(p^{-1})$ vanishing drift on the critical line, and calls the
smooth learned branch an empirical regularity.  It explicitly states the next
theorem target: a stochastic-approximation result linking drift, exploration,
and grid scale.

**Remaining paper-level issue:** this is still a major-revision ICML paper.
The PPO/actor-critic baseline, exploration and grid sweeps, and formal dynamics
result have not been generated by conversion.  The manuscript now says that
plainly instead of writing around it.

### NeurIPS: `The Price of Softmax`

**Original fidelity: medium-low at sentence level, high at conceptual level.**
The benchmark idea, validation gate, and mechanism comparisons fit the corpus.
The abstract was an overpacked list of claims, and bold slogan blocks made the
paper sound more certain than its seed counts and single-algorithm design.

**Revision:** the LaTeX version gives the environment and its gate first,
separates analytical oracles from learning results, includes compact result
tables, softens the quality result to directional evidence, and adds a concrete
broader-impact discussion.  The official 2026 checklist is filled honestly;
the current ``No'' answers on uniform significance reporting, compute
accounting, and consolidated licenses are retained as work items rather than
papered over.

**Remaining paper-level issue:** the review's policy-gradient request and
uniform uncertainty reporting remain open.  The environment also needs a
submission-quality minimal example and API documentation if the artifact is a
headline contribution.

## Editing rules to use going forward

Use these as a practical house style for the trilogy:

1. **One abstract arc.** Mechanism, question, method, main result, scope.  Five
   or six sentences; no numbered result dump.
2. **One load-bearing analogy per section.** If removing it does not change the
   model or prediction, remove it.
3. **Define before naming.** Write the allocation or objective before calling
   it Gibbs, critical, collusive, or adverse selection.
4. **Use ``we show'' only with an object.** Prefer ``we show that the Lerner
   index exceeds $1/a$'' to ``we show a striking market failure.''
5. **Pair every counterfactual with its estimand boundary.** Say which input is
   measured, which is calibrated, and which remains latent.
6. **Let tables carry numbers.** Main text should explain sign, mechanism, and
   benchmark instead of repeating every cell.
7. **End sections with design consequences.** State what a router, provider, or
   researcher would change and which tradeoff remains.
8. **Prefer exact nouns to emphasis.** ``Owned-probe conditional ratio'' is
   stronger than bold ``measured penalty.''
9. **Keep negative results.** Failed transport, nonmonotone quality response,
   and the missing dynamics theorem improve credibility when clearly scoped.
10. **Do not imitate the reviews' style diagnosis.** The earlier reviews called
    opinionated footnotes a signature trait, but the publication corpus does
    not support making them a template requirement.

## Conversion outputs

- EC: `paper/ec-router-mechanism/main.tex`
- ICML: `paper/icml-routing-games/main.tex`
- NeurIPS: `paper/neurips-price-softmax/main.tex`
- Shared bibliography: `paper/venue-trilogy-references.bib`

The projects use the current venue formats: `acmart` for ACM EC, the official
ICML 2026 style, and the official NeurIPS 2026 style and checklist.  Venue
formatting is distinct from substantive readiness: a compiling PDF is not an
acceptance claim.

