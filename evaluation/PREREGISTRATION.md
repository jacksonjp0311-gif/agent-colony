# Pre-registration — trust-loop experiments (frozen 2026-10-11, before any run)

Written and committed before any ablation, stripped-baseline, adversarial or holdout run.
`MANIFEST.sha256` pins evaluator + pools; the harness refuses to run on a mismatch.

## Task (what "capability" means here, narrowly)
The colony's conjecture desk is given a pool of 12 external candidate hard checks it has never
seen (disabled catalog entries). Within a fixed budget of 14 desk cycles it must decide which
to enable (keep). An independent evaluator (extended ranges + known counterexample witnesses,
separate code) judges each kept candidate:
- **verified result** = kept and truly sound and non-trivial;
- **harmful keep** = kept but false (has a counterexample);
- **coverage-only keep** = kept, true but trivial.

## Pools
- `dev` (12: 5 sound, 5 unsound incl. 1 escape-by-design, 2 trivial) — used while building and
  for the bounded spark; may be run many times.
- `holdout_v1` (12: 6 sound, 4 unsound incl. 1 escape-by-design, 2 trivial) — evaluated ONCE on
  the final frozen code. Every exposure is logged in `EXPOSURES.jsonl`; any second run is a
  re-exposure and must be reported as reused data.

## Arms (matched: same starting state = this branch's repo copy, same pool, same 5 seeds
11/23/37/41/53 controlling pick order + Challenger sampling, same 14-cycle budget)
- L1C1 full colony; L0C1 learning off; L1C0 Challenger off; L0C0 both off.
- Stripped baseline: bench-only keep rule (enable alone, keep iff in-window bench green).

## Primary metrics and promotion criteria
1. Learning helps (capability claim) iff, on holdout_v1, L1C1 − L0C1 mean verified results > 0
   with sign-flip p ≤ 0.10 over the 5 paired seeds, AND harmful keeps of L1C1 ≤ L0C1.
   (5 pairs: the smallest attainable two-sided p is 0.0625. This is a small sample.)
2. Challenger helps iff L1C1 harmful keeps < L1C0 harmful keeps on holdout_v1, reported with
   useful candidates it wrongly blocked (false rejects).
3. A bounded-spark mutation is retained only if on `dev` it improves its declared metric
   without increasing harmful keeps or false rejects, all mandatory gates pass, and (for a
   capability claim) it is confirmed on the single holdout exposure.
Secondary: repeated failures, distinct candidates tried, wall seconds, Oracle/Challenger calls,
cycles and seconds per verified result.

## Verdict rules
VERIFIED IMPROVEMENT only if criterion 1 or a spark capability claim holds on holdout_v1.
VERIFIED COVERAGE IMPROVEMENT if gates/coverage improve with correctness intact but no
capability criterion holds. NO MEASURABLE GAIN / HOLD / REGRESSION otherwise.
