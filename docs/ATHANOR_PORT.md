# Athanor in the colony (ported from Athanor 3.0.0)

ATHANOR is James Jackson's work (github.com/jacksonjp0311-gif/Athanor). This port follows
Athanor 3.0.0 (merged 2026-10-17). Its math is used unchanged: ΔΦ is the L2 distance between
consecutive states, C = 1/(1+|ΔΦ|), H7 is the fraction of steps with C ≥ τ, and the verdict is
APPROVE if H7 ≥ τ, REFINE if H7 ≥ 0.50, REJECT otherwise.

The colony's existing residual governor (`colony/athanor_coherence.py`, τ 0.70, inform-only) is
unchanged. The new gate is `colony/trust/athanor_gate.py`. It judges each lemma-desk self-edit.

| Piece | Athanor source | Colony code | What it does |
|---|---|---|---|
| Adapter API shape | 3.0 `governor.py` `Governor(probe, scale, check).judge(cur, cand, tolerance)` | `athanor_coherence.Governor` | Pure-Python port, checked against Athanor 3.0 itself when it is installed. Per probe, drift = abs(new − cur) / (scale · tolerance), and a crash or non-finite value counts as 1000. The validity check runs first. |
| Validity pre-gate | 2.5 `core/validity.py` | `validity_check`, `snapshot_validity` | Every value the bench reports after a change must be numeric and finite, with no bench error. A failure is a hard REJECT. |
| Worker memory cap | 3.0 `WORKER_MEMORY_LIMIT_GB = 2` | `athanor_gate.guarded_run` | Before the in-process bench, the candidate lemma impl runs in a child process under a 2 GB address-space cap and a 120 s limit. A runaway allocation then becomes a `MemoryError`, and a runaway loop becomes a timeout. Either way it fails validity. |
| Conservative adaptive tolerance | 2.5 `TUNED_ADAPTIVE_CONSERVATIVE`, registry `selfmod/adaptive@1.1.0` | `drift_tolerance`, `scheduled_tolerance` | τ 0.75, γ 6, p 3, best-so-far basis, cap 6, floor 0.7, half-life 50. The 2.6 TSP retune `tsp/adaptive@1.1.0` (τ 0.78, no decay) and the colony's fixed τ 0.70 are reported alongside it. |
| Eval-gated promotion | 2.7 `evals/promotion.py` (3.0 seed policy) | `colony/trust/athanor_promotion.py` | Another profile can replace the gate's profile only if (1) every captured bug2eval case's regression test still passes with it active, and (2) the Athanor rule APPROVEs its behaviour against the incumbent on a fresh block of recorded desk changes. A block is never reused. Report-only: nothing reads the result. |

Probes for a desk change: every bench check (1 pass / 0 fail) plus the speed-neutral lemma score
divided by κ = 0.10. A check the change adds counts as no drift if it passes; a lost check
counts as drift 1. The tolerance error is e = 1 − lemma score before the change, and t is the
number of assessed changes. All of these were chosen before any run and were not tuned.

Not ported: the 3.0 size-scaled validity inputs (`probe_scaling`). Colony checks run on fixed
ranges with no size parameter, and the Oracle already re-runs hard checks on a shifted held-out
window. Also not ported: the 2.8 AgentSearch evidence layer, because the colony already has its
own novelty shadow.

## The switch

One env var, `COLONY_ATHANOR_GATE`:

- `shadow` (default): assess and log to `society/systems/athanor_gate.json`. Never changes a
  keep/revert, score, P value, Oracle verdict, authorization or the 0.70 gate.
- `off`: no assessment, no child process, no log.

The gate sits in the lemma desk after the Oracle and the promotion check, so it never touches
the Oracle. It is monotone: it can only turn a keep into a revert, never the other way.

## What it cannot do

Athanor's own card says it plainly. H7 bounds the fraction of probes with large drift. It is not
a correctness proof, and it cannot see failures outside the inputs it checks.
