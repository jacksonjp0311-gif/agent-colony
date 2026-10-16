# Pre-registration — holdout_v2 (frozen 2026-10-16, before any run on it)

Committed before any colony run touches `evaluation/pools/holdout_v2`. `evaluation/MANIFEST.sha256`
pins `build_pools_v2.py`, `evaluator_v2.py` and both pool files; the harness refuses to run on a mismatch.
Protocol is the 2026-10-11 trust-loop protocol (`evaluation/PREREGISTRATION.md`) unchanged except where noted.

## Why a v2
holdout_v1 was exposed once (2026-10-11) and is retired for capability claims. Since then the colony
reached novelty ≈ 0.80 (fitness ≈ 0.86) through self-authored checks, feed-driven checks and
frontier ranges. Question: is that a **capability gain** on unfamiliar tasks, or **coverage** only?

## Pool
12 external candidates, families absent from dev, holdout_v1, the lemma catalog and the colony's
authored checks (see `NOVELTY_AUDIT.txt`): 6 sound (partitions, Fibonacci-binomial, divisor count,
sigma multiplicativity, four squares, Fermat's little theorem), 4 unsound (Fermat numbers prime,
three squares, sigma(n) < 3n, Pell 991 — escape by design, 29-digit witness), 2 trivial.
Isolation: identical to v1 (throwaway `/tmp/trust_ws` copies without `evaluation/`, `evidence/`, `.git`);
plus an AST test that `colony/` never names `holdout_v2`/`pool_v*` and a test that no `pool_v*` name
appears in `colony/`, `society/` or `data/`.

## Arms (5 seeds 11/23/37/41/53, 14 desk cycles each)
- HEAD code (main after this commit): L1C1, L0C1, L1C0, L0C0.
- BASE code = `893045a` (end of the 2026-10-11 trust loop, before the novelty rise): same 4 arms,
  same exposure (`--baseline-ref 893045a`).
- Stripped baseline (bench-only keep rule) on holdout_v2.
- Planted faults: `scripts/trust_faults.py` re-run on HEAD.

## Pass rules (decided now, before results)
1. **Learning helps (capability)** iff HEAD L1C1 − L0C1 mean verified > 0 with sign-flip p ≤ 0.10
   AND harmful(L1C1) ≤ harmful(L0C1).
2. **Challenger helps** iff harmful(HEAD L1C1) < harmful(HEAD L1C0); false rejects (useful
   candidates blocked) reported alongside.
3. **The week's evolution (novelty 0.80) is a capability gain** iff HEAD L1C1 − BASE L1C1 mean
   verified > 0 with sign-flip p ≤ 0.10 AND harmful(HEAD L1C1) ≤ harmful(BASE L1C1).
   If it fails but HEAD keeps more *non-pool* checks (its own authored checks) → **coverage only**.
   If both are equal → **no measurable gain**. If verified falls or harmful rises with p ≤ 0.10 → **regression**.
4. **Faults**: no regression vs 2026-10-11 (13/14 caught); every fault caught then must still be caught.
Verdict labels: VERIFIED CAPABILITY GAIN (rule 3 holds) / COVERAGE ONLY / NO MEASURABLE GAIN / REGRESSION.
Exposure is logged in `evaluation/EXPOSURES.jsonl`; this is the single holdout_v2 exposure.
n = 5 pairs → smallest attainable two-sided p is 0.0625. Small sample; null results will be reported as null.
