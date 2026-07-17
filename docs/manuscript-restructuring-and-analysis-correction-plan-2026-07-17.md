# Manuscript restructuring and analysis-correction plan

Status: planning document only. No further experiment execution or manuscript
promotion should occur until this structure is approved.

Primary manuscript: *Administered Menus and Hidden Clearing* (working title)

Target: ACM EC first; Management Science / M&SOM-style market-design or service
operations outlet as the journal path. The capacity mechanism remains a separate
theory paper.

## 1. Executive decision

The paper should stop trying to be a general empirical atlas of inference
markets. Its central question should be:

> When multiple providers sell execution of the same open-weight model under a
> common posted price surface, what economic service does an inference router
> add, and how can that service be measured?

The proposed answer is a two-layer market:

1. **Displayed layer:** providers and routers publish sticky, often common
   upstream token-price menus.
2. **Clearing layer:** the router privately applies eligibility, fallback,
   admission, and selection rules that determine whether and where a request is
   executed.

The paper's prospective headline should be:

> Posted provider-model prices are substantially standardized, but execution is
> not. A router manufactures a delivered service from revocable supplier offers;
> randomized policy variation decomposes that service into fallback option value
> and delegated-selection value.

This claim is not currently complete. H81 is still sample-gated, H93 is a
one-cross-section pilot, and H82 is descriptive. The restructure should be
implemented now at the level of argument and evidence assignment, but numerical
headline language must wait for the frozen gates.

## 2. What the reviews collectively say

Rounds 6--13 are remarkably consistent despite changes in title and analysis.

### 2.1 What reviewers believe is genuinely strong

- The market object is new and economically meaningful: provider-level execution
  for a fixed open-weight model, rather than model choice alone.
- The displayed-versus-deliverable distinction is sharp.
- The observability hierarchy correctly separates public prices, simulated
  routing, public enforcement aggregates, owned requests, and private logs.
- The fallback-versus-selection decomposition is a useful marketplace estimand.
- The randomized first-position designs, seed replay, compliance audits, masking,
  and immutable-prefix rules are unusually credible.
- H82 demonstrates a broad price-invariant operational margin, even though its
  pretrend prevents a causal enforcement interpretation.
- H84 is an informative rejection of a natural stale-cheap pickoff hypothesis.
- H92 is a correct and useful accounting correction: a pooled quantity-share
  elasticity near minus one is not by itself a revenue first-order condition.
- The new cross-router collector is remotely durable, and its initial 28/29
  exact-match result is a credible pilot fact.
- The manuscript is honest about missing cost, capacity, quality, and flow data.

### 2.2 What repeatedly causes rejection

1. The paper has no released, sufficiently supported primary randomized effect.
2. The mechanism proposed in theory is not the policy intervened on empirically.
3. Observational event studies have pretrends, backward-placebo signal, or
   endogenous treatment timing.
4. Millions of rows are being mistaken for calendar and event support.
5. External validity is narrow: one account, small prompts, repeated models, and
   one router dominate owned probes.
6. Posted-price matches do not establish identical contracts or realized fills.
7. Profit and global welfare require primitives the data do not contain.
8. Brown--MacKay-style reaction evidence lacks the focal slow-to-fast exposure.
9. The manuscript has become a catalog of bounded findings instead of one
   decisive economic argument.
10. Experiment gates have different histories and must not be silently pooled or
    revised after outcome exposure.

### 2.3 Root cause

The paper has been revised by accretion. Every reviewer objection produced
another analysis, theorem, comparator, or gate. This improved audit quality but
weakened the paper's center. The remedy is subtraction and hierarchy, not another
broad experiment family.

## 3. New paper architecture

### 3.1 One paper, one mechanism, three evidence layers

The empirical paper should make only one mechanism claim: **the router creates a
delivered product by clearing hidden execution state behind a public price
menu.** Three evidence layers support different parts of that claim:

| Layer | Evidence | Permitted conclusion |
|---|---|---|
| Public menus | H93/H94, H13, basic menu duration | Posted prices are largely upstream menus; cross-router wedges and update lags are measurable |
| Public operations | H82 and H84 | Eligibility/enforcement state moves while price is fixed; one stale-cheap mechanism is rejected |
| Owned randomization | H81 primary; H80 replication | Fallback and delegated selection causally affect the probed account's delivered outcome |

The public layers describe the market and motivate the experiment. The owned
randomization carries the causal headline. None is allowed to stand in for
market-wide flow or welfare.

### 3.2 Proposed contribution hierarchy

1. **Market definition.** Open-weight execution is a partially substitutable,
   perishable service supplied by multiple providers under a common model label.
   The router is a stochastic procurement intermediary, not merely a price
   comparison site.
2. **Identification result.** A default-versus-pinned comparison cannot separate
   fallback value from private selection. A three-policy experiment can.
3. **Primary experiment.** H81 estimates fallback option value and delegated-
   selection value on the eligible model-time population.
4. **Cross-layer measurement.** Public prices can remain identical while public
   enforcement and owned execution differ. This is the empirical definition of
   hidden clearing.
5. **Design implication.** Market quality should be measured using delivered
   generalized cost or execution-contingent prices, not token price alone.

Only items 1--2 are presently complete. Item 3 waits for its original frozen
gate. Item 4 is partly supported but requires the longitudinal cross-router
panel. Item 5 is a bounded implication, not a calibrated welfare conclusion.

### 3.3 Candidate title and abstract template

Preferred title:

> **Displayed Price, Hidden Clearing: Fallback and Selection in AI Inference
> Markets**

The final abstract should be 140--170 words and have exactly five moves:

1. Define the commodity and vertical stack.
2. State the displayed-price/hidden-clearing problem.
3. Describe the three evidence layers in one sentence.
4. Report no more than two numerical headline results: H81 and, if promoted,
   dynamic H93/H94.
5. State the design implication without claiming global welfare.

No price-atom, Brown--MacKay, revenue-stationarity, entry, MEV, retry, or broad
industry-comparison result belongs in the abstract.

## 4. Evidence triage

### 4.1 Keep in the main paper

| Evidence | Role | Condition |
|---|---|---|
| H81 fallback/selection randomization | Primary causal result | Release exactly the first frozen 40-per-arm balanced prefix; retain eligibility and compliance gates |
| H82 price-invariant enforcement events | Broad descriptive motivation | One figure; disclose all failed pretrends and do not call it causal substitution |
| H84 stale-cheap rejection | Mechanism falsification | Short subsection or combined with H82; retain backward placebo |
| H93/H94 cross-router pass-through | Market-layer result | Main result only after longitudinal gate; otherwise one institutional pilot paragraph |
| Observability hierarchy | Identification framework | Retain and simplify |
| Three-policy non-identification/decomposition proposition | Theory directly matched to experiment | Retain as the central formal result |
| Delivered-value frontier | Economic magnitude | User-side bounds only; no provider-cost or global-welfare label |

### 4.2 Move to appendix or online supplement

| Evidence | Reason |
|---|---|
| H80 four-arm crossover | Useful high-powered replication, but its 500-per-arm promotion history differs from H81 |
| Fixed-order pilot | Design motivation and failure disclosure only |
| Detailed H82 matching, leave-one-provider-out, accounting | Important robustness, too bulky for the main narrative |
| H83/H85/H88 prospective audits | Include only if a frozen result opens before submission; otherwise list in the data protocol, not as a contribution |
| Menu duration and repricing hazard | One descriptive table supports administered menus; full hazard models go online |
| Akash transparent comparator | External-validity appendix illustrating what public clearing reveals |
| Cross-router contract-field audit | Required robustness for H93/H94, likely appendix table |
| Reproducibility, source-health, and immutable-manifest details | Online appendix plus concise main-text paragraph |

### 4.3 Remove from this paper and preserve as companion work

| Material | Destination |
|---|---|
| Price atoms, author anchors, grid nulls, matched-menu power | Separate pricing-microstructure paper if the 30-day replication is strong |
| BM1--BM5 Brown--MacKay program | Separate pricing-technology note; current focal mechanism is non-estimable |
| H91/H92 revenue stationarity and accounting identity | Short methodological note or appendix to a demand paper, not this manuscript |
| Full welfare planner and finite-entry theorem | Capacity-certified routing / theory companion |
| VCG, collateral, audit, and robust-capacity mechanism | Theory companion unless an actual commitment intervention is run |
| Retry feedback, conduct screens, Hawkes/Poisson--Dirichlet, broad MEV taxonomy | Research appendix or future paper |
| DeFi, FX, travel, ad-exchange, rideshare industry ranking | Related-work synthesis, at most one paragraph |

Removing material does not mean discarding code or results. It means refusing to
make one paper carry several incompatible novelty claims.

## 5. Proposed section-by-section rewrite

Target main-text length: 18--22 pages before references, with a long online
appendix.

### Section 1: Introduction (2.5 pages)

- Open with the partially substitutable provider-model commodity.
- Introduce harness, router, provider, and user in one compact paragraph.
- State the puzzle: common displayed prices coexist with hidden execution state.
- State the experiment and decomposition before descriptive facts.
- Give three contributions only: market object, identification/experiment, and
  market-design implication.
- End with the headline result table or a one-paragraph roadmap.

Delete the current seven-item contribution list.

### Section 2: Institutional setting and economic object (1.5 pages)

- Define one request, one model, provider menu, eligibility, fallback, and
  selected provider.
- Retain L0--L4 observability levels.
- Explain why the prompt is not split across suppliers and why no public
  pre-trade route exists.
- State the target population: eligible provider-model opportunities for the
  study account and workload.

### Section 3: Framework and estimands (2.5 pages)

Define three policies for a fixed public provider set:

- (C): public cheapest provider, no fallback;
- (F): public price order, fallback allowed;
- (D): delegated router selection and fallback.

For a bounded delivered-value outcome (Y), define

\[
\Delta_{fallback}=E[Y(F)-Y(C)],\qquad
\Delta_{selection}=E[Y(D)-Y(F)].
\]

Then

\[
E[Y(D)-Y(C)]=\Delta_{fallback}+\Delta_{selection}.
\]

The section should prove two compact results:

1. a two-arm (D) versus (C) experiment does not identify the two components;
2. random assignment among (C,F,D) identifies both finite-population policy
   effects for the eligible blocks.

Do not present generic Horvitz--Thompson algebra as novelty. The novelty is the
market-specific decomposition and treatment construction.

### Section 4: Data and experimental design (3 pages)

- Show the funnel from public model-time candidates to eligible blocks to valid
  randomized first-position attempts.
- Explain first-position identification under arbitrary later-position
  interference.
- Put assignment replay, treatment compliance, stopping rule, model support, and
  missingness before outcomes.
- Separate the H81 confirmatory gate from H80's later 500-per-arm replication
  gate.
- Describe H82/H84 and H93/H94 as supporting designs, not pooled samples.

### Section 5: Public menus and hidden operational state (2 pages)

- One compact administered-menu statistic: duration/change incidence.
- H82 event plot with the failed pretrend visually explicit.
- H84 stale-cheap rejection and backward placebo in the same table.
- Conclusion limited to: public operational state changes at fixed money prices,
  and stale cheapness does not explain the observed enforcement risk.

### Section 6: Randomized fallback and selection (4 pages)

- Open with support and gate audit.
- Report ITT success effects first.
- Report 429 rejection, selected provider, cost, and latency only under their
  prespecified missingness labels.
- Show model-stratified and time-stratified effects.
- Report exact/randomization inference, Newcombe intervals, and Holm adjustment.
- Show the accounting identity between the two components and total delegation.
- Translate success effects into a break-even delivered-value frontier, not
  global welfare.

If the H81 gate has not opened, this section remains a protocol and the paper is
not submitted as an empirical result paper.

### Section 7: Cross-router posted-price pass-through (2 pages, conditional)

Include only if the longitudinal gate opens. Report:

- same-provider/model price equality by router pair;
- exact component-price transitions;
- one-to-one matched common shocks and interval-censored lead times;
- duration and resolution of material wedges;
- circular-time-shift placebo and negative-control matches;
- contract-field conflicts and unknown terms;
- whether a price transition changes the simulated cheapest-provider set.

If the gate does not open, replace this section with one paragraph and move the
28/29 pilot to the appendix. Exact equality alone is not a competitive-convergence
result because shared upstream price books are the natural null.

### Section 8: Market-design implications (1.5 pages)

- Define delivered generalized cost using money cost, failure, and delay.
- Explain that routers compete on clearing quality even when retail menus pass
  through upstream prices.
- Discuss execution-contingent prices, explicit fallback prices, and auditable
  provider-level fill rates.
- State that capacity certificates are a companion design proposal.
- Remove the global planner, free-entry calibration language, and any implication
  that the experiment validates VCG/collateral/audit mechanisms.

### Section 9: Related work and limitations (1.5 pages)

Organize around four literatures only:

1. stochastic procurement and dealer/RFQ markets;
2. platform fallback, matching, and marketplace experiments;
3. service reliability and hidden inventory;
4. model routing versus provider routing.

DeFi is a contrast, not the organizing analogy. Brown--MacKay appears as pricing-
technology motivation, not as a result the paper claims to replicate.

## 6. Analysis correction plan

### Workstream A: freeze and governance audit

Before viewing or changing any additional outcome estimate:

1. Inventory every experiment ID, preregistration timestamp, gate version, and
   first analyst-visible outcome timestamp.
2. Produce a machine-readable gate genealogy. H81's 40-per-arm gate and H80's
   later 500-per-arm gate must remain separate.
3. Resolve which dataset revision is authoritative; local summaries showing zero
   randomized blocks cannot be used as current status without a fresh remote
   pull.
4. Freeze the rewrite's discovery/confirmatory labels in one table.
5. Create a paper-only manifest containing exactly the inputs used by the new
   main results.
6. Prohibit new hypotheses from entering the main paper after this freeze.

Deliverables:

- `analysis/paper_gate_genealogy.parquet`
- `analysis/paper_evidence_assignment.parquet`
- `analysis/paper_release_manifest.json`
- a one-page incident/amendment ledger

### Workstream B: H81 as the primary causal experiment

#### Population and assignment

- Unit: eligible model-time block with at least two positive-price displayed
  providers and valid policy construction.
- Arms: (C,F,D) exactly as defined above.
- Estimand: finite-population first-position ITT on the earliest balanced prefix.
- Primary outcome: request success, with all failures retained.
- Primary family: fallback and hidden-selection contrasts; Holm correction.
- Secondary identity: total delegation equals the sum of the two components.

#### Mandatory pre-outcome diagnostics

- assignment seed replay and intended first-position probability;
- treatment metadata and pinned-provider compliance;
- zero cross-study overlap;
- candidate funnel, eligibility exclusions, and zero-attempt runs;
- model/provider concentration and effective support;
- hourly and calendar coverage;
- accounting, selected-provider, and latency missingness by arm.

#### Inference

- exact or Monte Carlo randomization p-values using logged assignment sets;
- Newcombe confidence intervals for success-rate contrasts;
- Horvitz--Thompson point estimates and model-stratified estimates;
- cluster/bootstrap sensitivity by model and collection day;
- leave-one-model-out estimates;
- worst-case bounded secondary outcomes without conditioning on success.

#### Gate policy

- Release the original H81 first balanced 40-per-arm prefix regardless of sign.
- Treat it as the confirmatory cut because that rule predates the outcome.
- Continue collection only as a separately labeled replication/power extension.
- Do not rewrite the 40-per-arm result using the later sample.
- If publication precision is inadequate, preregister an independent replication
  target before inspecting post-prefix outcomes.

### Workstream C: H80 as replication, not a competing primary

- Preserve the first 40-per-arm readout as an explicitly interim diagnostic.
- Preserve the reviewed 500-per-arm promotion rule.
- Use H80 to test whether default-versus-pinned total value replicates under four
  provider-order arms.
- Never pool H80 and H81 because candidate support and policies differ.
- Cross-study agreement is validation; disagreement triggers a support/estimand
  decomposition, not an average treatment effect.

### Workstream D: public operational mechanism

H82 and H84 should be reanalyzed only under their frozen specifications.

- H82 remains descriptive because all three pretrend tests fail.
- Display raw-count accounting so rival recovery and router exit are visible.
- Do not call the event a capacity shock; call it a public enforcement onset.
- H84 remains a rejection of the stale-cheap pickoff prediction.
- Report the backward placebo beside the forward estimate.
- Use H83/H85 only if their prospective first cuts open; otherwise exclude their
  outcomes from the paper.

The purpose of this workstream is not to manufacture a causal public event study.
It establishes why the L3 randomization is necessary.

### Workstream E: longitudinal cross-router pass-through

The current H93 result is a pilot. The proposed dynamic design should be frozen
before the first longitudinal price event is analyzed.

#### Primary objects

- Exact provider-model commodity using fail-closed model matching and punctuation-
  only provider normalization.
- Component-price transition between consecutive successful captures; no
  disappear/reappear event.
- One-to-one common shock: same new input/output vector within 90 minutes.
- Interval-censored lead time and router-pair leadership.
- Material workload wedge above 1%, with left/right censoring.

#### Falsification

- within-router circular capture-time shifts;
- same-model/different-provider target-price coincidences;
- same-provider/different-model coincidences;
- noncompetitive-model and closed-weight negative controls;
- batch-refresh indicators and UTC-hour fixed effects;
- familywise Holm correction across router pairs.

#### Contract audit

Compare all available context, output limit, tool, vision, caching, reasoning,
structured-output, mode, and status fields. Explicitly mark region, SLA, rate
limit, capacity, fallback, billing, and caching terms as unobserved. A pair with
conflicting or unknown material terms is a different-product comparison, not a
clean price wedge.

#### Promotion branches

- **Dynamic pass-through gate:** at least seven days, 48 snapshots per router, 30
  transitions, 15 matched common shocks, and 10 independent provider-models.
- **Allocation consequence gate:** separately require 15 transition-linked
  simulated cheapest-provider switches.
- **Realized-routing gate:** separately require owned attempts with selected
  provider, fallback, realized cost, latency, and success.

Do not require the allocation gate to describe pass-through synchronization; do
not use a simulated switch to claim realized demand reallocation.

### Workstream F: economic magnitude without global welfare

For a user value of completion (v), delay cost (d), and observed spend (c),
construct the policy value

\[
U_k(v,d)=v\Pr(\text{success}\mid k)-E[c\mid k]
-dE[\text{latency or timeout loss}\mid k].
\]

Report:

- break-even completion value for each policy contrast;
- success-only latency as a selected secondary statistic;
- timeout-inclusive upper/lower latency-loss bounds;
- spend bounds under missing accounting;
- sensitivity over transparent (v) and (d) grids.

Label this **user-side delivered-value analysis**. It is not consumer surplus,
provider profit, router profit, or global welfare. Global welfare requires
provider marginal cost, displacement, quality, take rates, and capacity response
and belongs in future partner-data work.

### Workstream G: transport and heterogeneity

- Report model-specific effects and leave-one-model-out estimates.
- Partition by public provider count, price dispersion, model popularity, and
  time of day using only prespecified bins.
- Show the eligibility funnel over time and adjacent-set Jaccard similarity.
- Distinguish finite-study-population validity from market-wide transport.
- Add at least one different prompt-length/workload stratum only as a separately
  randomized replication, not an unregistered pooled covariate search.
- If multiple accounts or regions become available, treat each as a site and
  report site-specific estimates before any hierarchical pooling.

## 7. Theory correction plan

### 7.1 Retain only theory matched to measured treatments

Keep:

- public-price versus hidden-eligibility distinction;
- two-arm non-identification;
- three-policy fallback/selection decomposition;
- a delivered-generalized-cost scoring benchmark;
- observational equivalence between firm suppliers and revocable suppliers plus
  successful fallback at the aggregate service level.

Move out:

- capacity-water-fill implementation;
- robust LP dominance;
- VCG transfers and audit scoring;
- collateral and liability design;
- finite-entry proposition and welfare-count comparison;
- any theorem requiring certified capacity not used by an empirical arm.

### 7.2 Add one sharper, paper-specific proposition

Develop a minimal stochastic-procurement model in which providers post a common
menu but have private deliverability states. Prove that:

1. platform-level completion probability can rise strictly through fallback even
   when no supplier quote becomes firmer;
2. posted-price equality across routers does not imply equality of delivered
   generalized price when their information or fallback policies differ; and
3. price-only best execution is optimal only if eligibility, failure loss,
   latency, and quality are equal or contractibly priced.

Each primitive must map to an observed or explicitly missing field. The result
should explain the experiment; it should not introduce an untested institution.

## 8. Figure and table plan

### Main figures

1. **Market stack and observability:** user/harness to router to providers, with
   L0--L4 evidence attached.
2. **Displayed price versus operational state:** fixed-price H82 event path with
   pretrend and raw flow accounting.
3. **Experimental decomposition:** policies (C,F,D), randomized first position,
   and the two identified contrasts.
4. **Primary causal effects:** forest plot with success ITTs, confidence
   intervals, Holm p-values, and model heterogeneity.
5. **Cross-router dynamics:** matched transitions, lead-lag, and wedge duration;
   include only if promoted.
6. **Delivered-value frontier:** break-even value/latency grid with missingness
   bounds.

### Main tables

1. Data sources, observability level, span, and permitted claim.
2. H81 funnel, assignment, compliance, support, and missingness.
3. H81 primary contrasts and decomposition identity.
4. H82/H84 descriptive and falsification results.
5. H93/H94 pass-through and contract audit, conditional on promotion.

Every main experiment gets a visual. Gate-closed experiments get support plots,
not outcome plots.

## 9. Reproducibility and artifact plan

1. Create a clean paper build entry point that runs only the evidence retained in
   the manuscript.
2. Pin one immutable dataset revision before the first query.
3. Record code commit, dataset revision, environment lock hash, source-health
   ledger, and every output hash.
4. Separate outcome-free support artifacts from outcome-bearing tables.
5. Make each figure read a frozen estimate table, not a live analyzer.
6. Add a claim-to-artifact manifest mapping every abstract/conclusion number to
   one JSON field and one table row.
7. Reproduce the paper in a clean worktree and remote CI job.
8. Archive the exact first qualifying prefix, even if a later sample is larger.
9. Publish negative and null gated results under the same release rules.

## 10. Decision tree

### Branch A: H81 is precise and economically material

- Promote H81 as the headline.
- Use H82/H84 to show the public operational mechanism.
- Use H93/H94 as a second result only if its dynamic gate opens.
- Submit the focused empirical paper after a clean frozen replay.

### Branch B: H81 is a precise null

- If intervals rule out an economically meaningful fallback or selection effect,
  make the negative result the headline: hidden public state does not create
  measurable router value for the eligible workload despite descriptive public
  enforcement variation.
- Retain the same design and do not search for a favorable subgroup.

### Branch C: H81 is imprecise

- Do not submit the empirical paper.
- Freeze and report the first cut, preregister a genuinely independent replication
  based on precision rather than sign, and wait.
- Submit the theory companion separately if it stands on its own.

### Branch D: cross-router transitions remain rare

- Treat rarity itself as evidence of administered upstream menus only after
  sufficient calendar coverage.
- Demote the 28/29 cross-section to institutional description.
- Do not claim convergence, leadership, or strategic response.

### Branch E: contract terms conflict

- Reclassify matched rows as differentiated products.
- Analyze price plus observed contract bundle rather than a law of one price.
- The resulting contribution becomes router packaging, not pass-through.

## 11. Reviewer-objection closure matrix

| Reviewer objection | Required correction | Closure evidence |
|---|---|---|
| No released causal result | H81 frozen first cut | Balanced prefix, assignment replay, primary table |
| Theory/experiment mismatch | Keep only fallback/selection theory | Every theorem primitive mapped to an arm or measured variable |
| Public pretrends | Descriptive label and visible placebo | Main figure includes preperiod; no causal language |
| Short panel | Calendar/event gates | Frozen support ledger, not row count |
| Narrow external support | Funnel and heterogeneity | Model/site/time support tables |
| Static cross-router equality | Dynamic events and natural null | Lead-lag, wedge spells, circular-shift placebo |
| Nonidentical contracts | Contract audit | Conflict/unknown-term table |
| No realized routing | Owned-request validation | Selected provider, fallback, cost, latency, outcome |
| Welfare unidentified | User-side value frontier only | No global-welfare number in abstract or conclusion |
| Too many results | Evidence triage and page budget | Three contributions, one causal headline |
| Gate drift | Gate genealogy | Timestamped immutable amendment ledger |
| Reproducibility not power | Separate engineering and inference claims | Clean remote replay plus independent support gates |

## 12. Execution phases after approval

### Phase 0: paper freeze and branch hygiene

- Preserve the current PDF and artifacts as the pre-restructure baseline.
- Create a dedicated paper-restructure branch/worktree.
- Classify all current dirty files as user work, generated output, or paper input.
- Do not bulk-commit the present dirty tree.

### Phase 1: evidence and gate audit

- Pull the authoritative remote dataset.
- Generate gate genealogy, evidence assignment, and claim manifest.
- Reconcile local/remote H80 and H81 summaries.
- Produce a reviewer-facing audit memo before opening any newly eligible outcome.

### Phase 2: skeleton rewrite

- Replace the seven-contribution introduction with the three-contribution
  structure.
- Move companion material out before updating results.
- Write framework, estimands, and section placeholders with no promoted numbers.
- Enforce the page budget.

### Phase 3: frozen empirical releases

- Release H81 only if its original gate opens.
- Release H80 only at its reviewed 500-per-arm gate.
- Evaluate H93/H94 only under the prospectively approved dynamic design.
- Preserve H82/H84 specifications without retrospective variants.

### Phase 4: economic synthesis

- Estimate user-side value frontiers and bounds.
- Link public menu, public enforcement, and owned policy results without pooling
  their estimands.
- Add the stochastic-procurement proposition and remove untested mechanism theory.

### Phase 5: artifact freeze and red-team review

- Run the paper from a clean immutable revision.
- Audit every numerical claim against the claim manifest.
- Conduct separate EC, empirical IO, and OR mock reviews.
- Require all three reviewers to agree that the causal headline is supported,
  the theory matches the treatment, and no main claim depends on a closed gate.

## 13. Submission gates

The empirical manuscript is submission-ready only if all are true:

1. One primary randomized result is released at its original prospective gate.
2. Its confidence interval is informative, whether the point estimate is positive
   or null.
3. Assignment, compliance, funnel, support, and missingness audits pass.
4. At least one broad public result establishes the market mechanism without
   causal overclaiming.
5. Any cross-router headline has longitudinal events, natural-null falsification,
   and contract audit.
6. Main theory corresponds directly to measured treatments.
7. Global welfare, provider profit, collusion, and literal front-running claims
   are absent unless new identifying data are obtained.
8. The paper has no more than three stated contributions.
9. Every number is reproduced from one immutable revision in clean local and
   remote builds.
10. A fresh mock reviewer recommends accept or weak accept for the empirical
    contribution itself, not merely for the protocol or theory companion.

## 14. Immediate next decision

No more analyses should be added before choosing this structure. The next action
after approval is Phase 1—the evidence/gate audit—not another hypothesis test.

The H94 configuration, preregistration, and analyzer currently present as
uncommitted local work should be treated as a **draft design**, not as an executed
or outcome-reviewed experiment, until this plan is approved and its gate history
is entered in the governance ledger.

