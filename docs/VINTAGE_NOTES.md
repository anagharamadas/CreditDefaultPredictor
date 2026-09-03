# Vintage composition — interpretation notes

Figure: `figures/vintage_composition.png` (regenerate with
`scripts/vintage_composition.py`). This is the R1 detection artifact the risk
register requires **before any modelling**. Read top to bottom.

## Panel 1 — originations per month

Volume grows ~1000× from 2007 (hundreds/month) to 2015–2018 (30–60k/month), with
visible policy-era turbulence in 2015–2016 (the sawtooth). Two consequences:
early vintages are too thin to estimate monthly rates precisely (the noisy left
edge of panels 2–3), and any pooled statistic is dominated by 2015+ loans.

## Panel 2 — resolution rate (the censoring picture)

The clean staircase confirms the maturity arithmetic used in Charter §3.3:

- **36-month loans issued through 2015 are ≥99.9% resolved** — the training window
  (2013–2015, 36-month) has effectively zero censoring. This is measured
  justification, not assumption.
- 60-month resolution starts collapsing with 2014 vintages (82.9% → 67.1% by
  2015) — measured proof that 60-month loans cannot honestly sit in this training
  window; they are v1-excluded, revisited only under a survival framing.
- In the replay window resolution falls from 71.8% (2016, 36-mo) to 12.0% (2018) —
  the label-lag reality P10's monitoring must be built around.

## Panel 3 — default rate among resolved (the drift-and-artifact picture)

Three regimes:

1. **2007–2012 (noisy, thin)**: crisis-era rates visible but on tiny volumes.
2. **2013–2016 (the real signal)**: 36-month default rate climbs steadily
   ~12% → ~20%, and 60-month from ~25% → ~36%. This is the genuine drift the
   replay will surface — borrower-mix and policy change, not an artifact.
3. **2017–2018 (the trap)**: rates *appear* to fall (36-mo: 20.0% → 13.2%). This
   is **not** improving credit quality — it is the snapshot boundary. Only
   fast-resolving loans from these vintages have outcomes, and early charge-off
   is over-represented first, early payoff catches up differently; the mix of
   "resolved" is not the mix of "originated". Any replay metric on these months
   mixes real drift with label immaturity and must be reported under the
   label-lag framework (Charter §8.1).

## Decisions this evidence supports

| Decision | Evidence |
|---|---|
| Train on 36-month 2013–2015 (Charter §3.3) | Panel 2: ≥99.9% resolved; Panel 3: stable-regime signal |
| Exclude 60-month from v1 | Panel 2 collapse from 2014; Panel 3: ~2× default level would corrupt a mixed label |
| Replay 2016–2018 with explicit label-lag handling | Panels 2–3: degradation there is real drift × immaturity, separable only if modelled |
| Report drift vs artifact separately in P10 | Panel 3 regime 3 |
