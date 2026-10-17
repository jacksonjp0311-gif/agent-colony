# Athanor v2.5–v2.7 in the colony

ATHANOR is James Jackson's work (github.com/jacksonjp0311-gif/Athanor). Its math is used here
unchanged: ΔΦ is the L2 distance between consecutive states, C = 1/(1+|ΔΦ|), H7 is the fraction
of steps with C ≥ τ, and the verdict is APPROVE if H7 ≥ τ, REFINE if H7 ≥ 0.50, REJECT otherwise.

The colony's existing governor (`colony/athanor_coherence.py`, residual trajectories, τ 0.70) is
unchanged. These pieces were added on top of it, one commit each:

| Piece | Athanor source | Colony code | What it does |
|---|---|---|---|
| Validity pre-gate | 2.5 `core/validity.py` | `validity_check`, `snapshot_validity` | Every value the bench reports after a desk change (score, seconds, each check) must be numeric and finite, with no bench error. A failure is a hard REJECT before the coherence gate. |
| Conservative adaptive tolerance | 2.5 `TUNED_ADAPTIVE_CONSERVATIVE`, registry `selfmod/adaptive@1.1.0` | `drift_tolerance`, `scheduled_tolerance`, `edit_trajectory`, `colony/trust/athanor_v27.py` | Each desk change becomes Athanor's self-edit trajectory over the bench checks plus the score, with drift divided by an adaptive tolerance (τ 0.75, γ 6, p 3, best-so-far basis, cap 6, floor 0.7, half-life 50). The 2.6 TSP retune (τ 0.78, no decay) and the colony's fixed τ 0.70 are reported alongside. |
| Eval-gated promotion | 2.7 `evals/promotion.py` | `colony/trust/athanor_promotion.py` | A different profile is only a candidate. It is promoted only if every captured bug2eval case's regression test still passes with it active and the Athanor rule APPROVEs its behaviour against the incumbent on the recorded desk changes. Report-only: nothing reads the result. |

Colony-specific choices (fixed before any run, not tuned): score probe scale κ = 0.10 (Athanor's
TSP choice); a newly added passing check counts as no behaviour drift; tolerance error
e = 1 − lemma score before the change; t counts assessed changes; w_s = 0.5.

## The switch

One env var, `COLONY_ATHANOR_GATE`:

- `shadow` (default): assess and log to `society/systems/athanor_v27.json`. Never changes a
  keep/revert, score, P value, Oracle verdict, authorization or the 0.70 gate.
- `off`: no assessment and no log.

The gate sits in the lemma desk after the Oracle and the promotion check, so it never touches
the Oracle. It is monotone: it can only turn a keep into a revert, never the other way.

## What it cannot do

Athanor's own card says it plainly: H7 bounds the fraction of probes with large drift; it is not
a correctness proof, and it cannot see failures outside the inputs it checks.
