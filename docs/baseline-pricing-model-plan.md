# A baseline pricing model and the nested alternatives: pre-registered plan

Registered 2026-07-15, after a three-agent literature sweep (sticky-price
econometrics; collusion detection; congestion/peak-load estimation — full
reports in session transcripts). Purpose: replace one-off tests with ONE
baseline statistical model of price setting, against which congestion-pricing
and cooperative-pricing alternatives are nested and compared by likelihood,
out-of-sample prediction, and pre-registered sufficient statistics.

Module namespace: `pm*` (pricing model), collision-free.

## Why not GARCH as THE baseline

Posted quotes are sticky and lumpy (2.8%/day repricing, 25% median jumps):
returns-based GARCH is misspecified for them. The correct baseline for the
quote panel is a **marked point process** — a repricing hazard plus a
jump-size (mark) distribution. GARCH-family models are the right baseline for
the two genuinely continuous series (transacted effective-price index; GPU
rental spot). Hence three tracks.

## Track A — posted quotes: hazard + marks (the core)

**A1. Baseline engine (pm1): discrete-time competing-risks hazard**, cloglog
link (grouped Cox), daily bins, events = {increase, decrease}, delisting a
competing risk, unit = provider x model endpoint, open spells right-censored:

  h_imt = 1 - exp(-exp( a(tau) + b'x_imt + g'gap_imt + d'R_imt + s(cal) + u_im ))

- a(tau): piecewise-constant spell-age baseline on log-spaced bins.
  **Calvo test: a flat.** (Cavallo 2018: clean scraped data yields
  hump-shaped hazards; declining hazards are a heterogeneity artifact —
  frailty/unit effects u_im are mandatory.)
- gap: (i) own price vs rival median on the model (Campbell-Eden), (ii) own
  price vs GPU-cost-implied target (Davis-Hamilton); |gap| and sign entered
  separately. **Menu-cost/state-dependence test: g>0 on |gap|.**
- x: congestion covariates — utilization, p95 latency, 429 incidence (levels
  + 7d changes), GPU spot change. **Congestion-pricing test: b != 0 with
  sign asymmetry (up-hazard loads on utilization). Clean exclusion: under
  cost-based pricing, congestion matters only through the cost gap — test
  b=0 | g free.**
- R: rival-move marks — trailing counts of rival repricings by sign, leader
  indicator. **Strategic test: d != 0, asymmetric.**
- Nesting ladder, LR at each rung: (1) Calvo -> (2) +seasonality/duration ->
  (3) +state dependence -> (4) +congestion -> (5) +strategic.

**A2. Mark equation (pm2):** distribution of Delta-p given repricing, on the
same covariates; ACM-style ordered layer on the (coarse, round-number-
attracted) price grid. Calvo: size independent of age and gap. Menu cost:
Delta-p ~ -gap (reset to target).

**A3. Sufficient statistics (pm2 reports):** Kurtosis of nonzero log price
changes and frequency N — the Alvarez-Le Bihan-Lippi index (Kur=6 Calvo,
Kur=1 Golosov-Lucas menu cost); the small-change hole (share |dp|<5%);
E[|dp| | age] slope. Our exact quotes make these unusually clean
(no time-averaging bias per EJRS 2014).

**A4. Contagion validator (pm3): multivariate Hawkes per model**, providers
as components, kernels = sums of 2-3 exponentials (hours/days/weeks).
Guardrails (Filimonov-Sornette): deterministic time-varying baseline and the
common GPU-cost covariate FIRST, multi-start MLE, time-rescaling KS
residuals — else cross-excitation and criticality are spurious. Tests:
phi_jk=0 (no strategic contagion); kernel asymmetry = leadership.

**Comparison metrics for Track A:** LR/AIC along the ladder; out-of-sample
hazard AUC benchmarked against H18's ML ceiling (0.87); time-rescaling KS.

## Track B — continuous series: GARCH family with congestion alternatives

**B1 (pm4). Effective-price daily index** (n ~ 90-300 for a while):
- Baseline: ARMA(1,1) + day-of-week; GARCH(1,1)-t with variance targeting
  (2 free vol params); EWMA(0.94) as the zero-parameter benchmark; EGARCH/GJR
  only if the Engle-Ng sign-bias test rejects. HAR-RV once intraday
  effective prices support realized variance (handles Hurst 0.84 with 3 OLS
  params; FIGARCH and MS-GARCH are ruled out at this n — MS-GARCH needs
  ~1500 obs).
- Congestion alternative (Barlow/Kanamura-Ohashi reduced form + TARX):
  log P_t = phi log P_{t-1} + b1 u_t + b2 (u_t - u_bar)_+ + lambda log G_t + e.
  **Congestion priced: b2 > 0 (hockey-stick curvature) or a threshold regime
  in u with larger loading.** Instrument u with rival outages (lab_incidents)
  and model-launch events.
- First: Oaxaca decomposition of Var(dlog P_eff) into posted-repricing vs
  routing/composition components (assumption-free headline).

**B2 (pm4). GPU spot:** administered-vs-market diagnostics first (our CBH-6
battery — the AWS precedent says compute "spot" can be an administered
signal); then AR(1)/HAR + GARCH(1,1)-t VT residuals, jump dummies; ARDL
bounds test for long-run G -> P_eff pass-through (valid at small n), with
the error-correction speed sizing the cost channel that Track A's congestion
coefficients are judged against. Bessembinder-Lemmon premium via two-step
regression, not GARCH-M (weakly identified at this n).

## Track C — cooperative pricing: the nested ladder

Estimated on Track A residual structure + margin proxies. Rungs, each
nesting the last:

- **C0 competitive baseline:** repricing residuals cross-sectionally
  independent (Bajari-Ye conditional independence) and exchangeable
  (symmetric response to rivals); gap-to-cheapest density smooth through
  zero (Chassang et al. missing-mass logic); ties transient, broken
  downward, sitting near the cost floor.
- **C1 parallelism/focal pricing:** leadership concentration (Lewis),
  focal-point mass — SPECIFICALLY whether exact ties sit at the model
  author's first-party API price (the Knittel-Stango nonbinding focal
  point) or at round numbers vs cost-driven values; ties formed by UPWARD
  moves; dispersion collapse (Abrantes-Metz CV screen; benchmark: perch
  cartel collapse moved CV +332%). Brown-MacKay commitment is the
  non-collusive sub-case; separators: fastest repricer is cheapest and
  never leads raises; reaction functions memoryless in current rival
  prices; NO reversion against a persisting cut.
- **C2 Edgeworth cycling (Maskin-Tirole):** Noel MS on delta-p with
  undercut/relent regimes and margin-dependent transitions; Lewis
  mean-median asymmetry; Musolff resetting = 24h spectral peak in
  unilateral raises at low-traffic hours. Pre-register the detector suite
  (Holt-Igami-Scheidegger: conclusions flip with detector choice).
- **C3 trigger-strategy collusion (Green-Porter/Porter/Ellison):** 2-regime
  MS on margin LEVELS with transition covariates; war onset loads on
  monitoring noise (share innovations, rival-deviation flags) not cost;
  reversion to the prior elevated level while fundamentals unchanged;
  dampened cost pass-through in the cooperative regime; Assad both-adopt
  overlay (all statistics computed separately for algo-algo / mixed /
  neither cheapest pairs — anomalies should concentrate in algo-algo).

**Critical reclassification of the existing punish-and-revert result
(pm6, run immediately):** our 95 typed events are cuts followed by rival
cuts then rival re-raises. The ladder distinguishes three stories by sign
and persistence, which CBH-4 did not: (i) Byrne-de Roos failed-leadership
= RAISE then revert when unfollowed (initiation, not punishment); (ii)
Green-Porter punishment = cut met by overshoot-then-reversion WHILE the
initiator's cut persists; (iii) Brown-MacKay = cut met by re-optimization
to a permanently lower level (no reversion unless initiator reverts).
Classify every event by initiator sign, follower sign, whether the
initiator's move persisted through the follower's reversion, initiator
volume (low-volume initiators = costless ATPCO-style signaling), and
algo/non-algo pair type.

## Modules and sequencing

| Module | Content | When |
|---|---|---|
| pm1 | hazard baseline + ladder rungs 1-5 | now (10-day panel; underpowered rungs report gates) |
| pm2 | marks + sufficient statistics (Kur, N, small-change hole) | now |
| pm5 | tie microstructure: gap-density atom, tie-formation direction, focality vs first-party price, tie-break hazards | now — highest immediate value |
| pm6 | signed-IRF event reclassification (persistence, initiator sign/volume, pair type) | now |
| pm3 | multivariate Hawkes with guardrails | ~6 weeks of events |
| pm4 | index GARCH/HAR + TARX congestion; GPU ARDL | ~90 daily obs (self-activating) |
| pm7 | variance screens + structural breaks (Bai-Perron on mean/CV/tie-share) | ~2-3 months |
| pm8 | MS regime models (Noel delta-p; Porter/Ellison margins) | 6-12 months, localized first by pm5-pm7 |

Scorecard integration: pm outputs feed the CBH scorecard rows Q1/Q2 and the
reaction-dynamics watch; the ladder verdict (highest non-rejected rung per
model-market) becomes a memo panel.

## Honesty constraints

- Margin proxies are ordering-informative only (single-stream cost bound).
- The Hawkes/strategic layer is uninterpretable without the common-cost
  baseline; report phi_jk only with time-rescaling diagnostics attached.
- Simultaneity: utilization responds to price via routing; hazard congestion
  coefficients get the rival-outage/model-launch instruments before any
  causal congestion-pricing claim.
- All detector choices pre-registered here; deviations require a dated
  addendum, never edits.
