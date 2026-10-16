# holdout_v2 — 2026-10-16 (agent-colony)

Question: the colony's novelty rose to ≈0.80 since 2026-10-11. Does that show up as a **capability
gain** on problems it has never seen, or only as **coverage**? Pass rules were written and committed
(`PREREGISTRATION.md`, commit a4643b0) before any run. Single exposure, logged in `evaluation/EXPOSURES.jsonl`.

## Verdict: **NO MEASURABLE GAIN** (capability) — the novelty rise is **coverage only**

- HEAD (main, novelty 0.80) and BASE `893045a` (end of the 10-11 trust loop, before the novelty rise)
  produced **identical** results on every arm, every seed: same verified, harmful, repeated failures,
  candidates tried. Paired diffs are 0 on all 5 seeds (p = 1.0). Rule 3 → no measurable gain.
- Both versions also keep the same 7 non-pool checks per run (their own authored checks) — that is
  coverage, and it is not larger on HEAD within this 14-cycle budget.

## Results (12 unseen candidates: 6 sound, 4 unsound incl. 1 escape-by-design, 2 trivial; 14 cycles, seeds 11/23/37/41/53)

| arm | verified per seed | harmful per seed | repeated failures (mean) | distinct tried |
|---|---|---|---|---|
| L1C1 full (HEAD) | 5,3,4,3,5 (mean 4.0) | 0,1,0,1,0 (0.4) | 0.0 | 7.0 |
| L0C1 learning off | 3,0,1,2,2 (1.6) | 0,0,0,1,0 (0.2) | 4.0 | 3.0 |
| L1C0 Challenger off | 5,3,4,3,5 (4.0) | 0,1,0,1,0 (0.4) | 0.0 | 7.0 |
| L0C0 | 3,0,1,2,2 (1.6) | 0,0,0,1,0 (0.2) | 4.0 | 3.0 |
| BASE_* (893045a), all 4 arms | identical to the HEAD row of the same arm | | | |
| stripped (bench-only keep) | 6 | 4 | — | 12 |

## Pre-registered rules

| # | Rule | Outcome |
|---|---|---|
| 1 | Learning helps: verified L1C1−L0C1 > 0, p ≤ 0.10, AND harmful(L1C1) ≤ harmful(L0C1) | verified +2.4 [2,3,3,1,3], p = 0.0625 ✔; harmful 0.4 vs 0.2 ✘ → **not met** (same mixed pattern as v1) |
| 2 | Challenger helps: harmful(L1C1) < harmful(L1C0) | 0.4 vs 0.4 → **not met**. Challenger blocked the trivial `v11` (4/5 seeds) and the three in-window-false claims before the Oracle; 0 useful candidates wrongly blocked. Value = triviality filtering + earlier rejection, not fewer harmful keeps |
| 3 | Week's evolution is a capability gain: HEAD L1C1 − BASE L1C1 verified > 0, p ≤ 0.10 | diffs 0,0,0,0,0 → **NO MEASURABLE GAIN** |
| 4 | Faults: no regression vs 13/14 | **13/14, same faults caught** (`adversarial_faults.json`) ✔ |

## Honest reading
- **Capability: none measured.** The changes since 10-11 (authored checks, feeds, frontier, authorizations,
  novelty 0.80) did not change how the desk handles unfamiliar candidates at all.
- **Learning on/off:** the effect replicates on fresh problems: +2.4 verified per 14 cycles by not retrying
  failed candidates. But it again keeps more harmful claims (the Pell-991 escape: false only at a 29-digit y,
  invisible to every in-loop check), so the pre-registered criterion fails. Within-run memory, not transfer.
- **Escape:** `pool_v10_pell991_no_solution` was kept in 2/5 full-colony runs on both HEAD and BASE.
  No in-loop layer catches a claim whose first counterexample is astronomically far out; only the
  out-of-loop evaluator does. This is the colony's real blind spot.
- **Coverage gains** (labelled separately): more authored checks, feed checks, longer frontier ranges —
  real, but they are coverage, not capability.
- n = 5 paired seeds; smallest attainable p = 0.0625. Small sample.

## Files
`PREREGISTRATION.md`, `NOVELTY_AUDIT.txt`, `holdout_v2.json` (all runs), `stripped_holdout_v2.json`,
`adversarial_faults.json`. Pool + evaluator: `evaluation/pools/holdout_v2/`, `evaluation/evaluator_v2.py`,
`evaluation/build_pools_v2.py` (hash-locked in `evaluation/MANIFEST.sha256`).
Reproduce: `PYTHONPATH=. python3 scripts/trust_experiments.py holdout --pool holdout_v2 --baseline-ref 893045a`
(will be logged as a re-exposure).
holdout_v2 is now **exposed**; future capability claims need holdout_v3.
