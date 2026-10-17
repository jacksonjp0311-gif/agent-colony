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
- `live`: the same assessment, and it gates. A keep goes through only on APPROVE. If the
  memory-capped run fails, the candidate never runs in-process and the change is reverted.
  Assessment errors fail closed.
- `off`: no assessment, no child process, no log.

The evolve workflow sets `COLONY_ATHANOR_GATE: live` on its evolve step. To turn it off, change
that one line to `shadow` (report-only) or `off`. Tests prove that either value restores the
old keep/revert behaviour.

The gate sits in the lemma desk after the Oracle and the promotion check, so it never touches
the Oracle. It is monotone: it can only turn a keep into a revert, never the other way.

## What it cannot do

Athanor's own card says it plainly. H7 bounds the fraction of probes with large drift. It is not
a correctness proof, and it cannot see failures outside the inputs it checks.

## What the gate measures: legacy vs state probe

`COLONY_ATHANOR_PROBE=legacy|state` (default `legacy`) picks which probe's verdict counts. Both are
always computed and logged side by side in `society/systems/athanor_gate.json`
(`legacy_verdict`, `state_verdict`, `state_dphi`, `state_drift_raw`, `would_block_by_probe`).

- `legacy`: pass bit of every check present before and after, plus score/0.1. A desk keep adds one
  passing check with the score flat, so dPhi = 0 every time; on replayed history it also approves
  every perturbation control (it dilutes them over ~165 probes).
- `state` (`colony/trust/athanor_probe.py`): ten blocks of the colony's state before vs after
  (check pass bits per family with absent = 0.5, coverage, score components, tier ok bits, runtime,
  AST structural distance, textbook share of enabled checks, Oracle pass rate over the last 20
  verdicts). One probe per block; dPhi = L2 distance per block / calibrated scale; C, H7 and the
  verdict rule are Athanor's, unchanged. Scales: `colony/trust/athanor_probe_calibration.json`,
  calibrated on historical desk changes (tuning split) and evaluated on held-out ones, see
  `docs/ATHANOR_PROBE_TUNING_LOG.md`. Reproduce: `python evals/athanor_probe/replay.py &&
  python evals/athanor_probe/calibrate.py`.

The gate stays downgrade-only (a keep can become a revert, never the reverse) and never touches the
Oracle, P, authorization, the 0.70 authorize gate, charter, TributeKeeper or Ceiling.
Flag-off: set `COLONY_ATHANOR_PROBE: legacy` (or remove it) in `.github/workflows/colony-evolve.yml`.

## Per-area hard veto (beside the verdict)

`COLONY_ATHANOR_VETO=off|shadow|live` (code default `shadow`). H7 is the share of areas within the
line, so one wildly alarming area (score inflation, a 5x slowdown, checks swapped at equal count)
can never change the verdict by itself. The veto is an extra check next to Athanor's verdict, like
the validity pre-gate: if one integrity area (`VETO_AREAS`: check bits, coverage, score, tier ok,
runtime, AST structure) moves past its calibrated limit, a keep becomes a revert (live only, and
only with `COLONY_ATHANOR_PROBE=state`). Runtime also needs a >= 0.5 s absolute slow-down so CI
timing noise cannot trigger it. Athanor's dPhi, C, H7 and verdict are unchanged and logged as is;
the veto is logged separately (`veto`, `would_veto`, `block_reason`). Calibration: the `veto`
section of `colony/trust/athanor_probe_calibration.json` and `docs/ATHANOR_PROBE_TUNING_LOG.md`.

## Hunt guidance (COLONY_HUNT=live|shadow|off)

`colony/hunt.py`. In `live` (workflow default) the hunt rules steer the colony's own exploration:
desk candidate order (`exploration_budget.pick_mutation_order`), authoring candidate order
(`authoring.author_checks`) and the keep reward (`exploration_budget.record_outcome`, 1.25 flat →
1 + 0.25·v). v = K/(s+K) for authored claims (s = Oracle-passed family members, K calibrated, see
`docs/HUNT_TUNING_LOG.md`), min(1, n/2) for building blocks chained by n Oracle-passed authored
claims, 0 for a bare enable. Order/reward only: nothing is removed or killed; the Oracle, P, the
0.70 authorize bar and desk decisions are unchanged (P_shadow stays beside P on the shortlist).
Anti-freeze: strength halves when >½ of the last 6 desk results were idle (¼ when all were).
`shadow` (code default) = old behaviour; `off` also stops the hunt shadow report.
Revert: set `COLONY_HUNT: shadow` in `.github/workflows/colony-evolve.yml`, or revert the commit.
