# H₇ Residual Diagnosis

**When:** 2026-09-27 08:09 AM ET (`2026-09-27T12:09:58Z`)
**Mile:** `h7-diagnosis` — diagnostics / report ONLY
**Scope:** no behavior scripting · no durable-accept double-gate · Athanor stays inform-only

## Snapshot

| Field | Value |
|---|---|
| Verdict | `REFINE` |
| H₇ (horizon) | `0.5384615384615384` |
| H₇ weighted | `0.8462469543977093` |
| H₇ cusp | `0.7777777777777778` |
| κ bound (C̄²) | `0.606478884669746` |
| C̄ / C σ | `0.7787675421264975` / `0.2292395603699158` |
| ΔΦ μ / σ | `0.419959453029457` / `0.46667371617120834` |
| Threshold / floor | `0.7` / `0.5` |
| Agents | `14` |

## Distribution (APPROVE / REFINE / REJECT)

- State counters: `{'APPROVE': 3, 'REFINE': 23, 'REJECT': 0}` (REFINE share ≈ `0.8846`)
- Log counters: `{'APPROVE': 3, 'REFINE': 23, 'REJECT': 0}`

## H₇ history

- n=`26` mean=`0.5917159763313609` std=`0.1474548614719185` min=`0.5384615384615384` max=`1.0`
- last5=`[0.5384615384615384, 0.5384615384615384, 0.5384615384615384, 0.5384615384615384, 0.5384615384615384]`

## Cusp vs weighted

- horizon=`0.5384615384615384` weighted=`0.8462469543977093` cusp=`0.7777777777777778`
- gap weighted−horizon=`0.307785`
- gap cusp−horizon=`0.239316`
- Reading: Weighted mean looks healthy while horizon fraction stays REFINE — APPROVE needs more steps with C≥0.70, not just a higher average C.

## κ bound

- κ=`0.606478884669746` via `kappa = C_mean^2 (omega Lipschitz)` with C̄=`0.7787675421264975`
- Below APPROVE threshold: `True`

## Agent residual variance

- n_agents=`14` roles=`['builder', 'courier', 'geometer', 'herald', 'improver', 'legislator', 'memory_weaver', 'oracle_scribe', 'pathfinder', 'scribe', 'spark', 'stem_checker', 'surveyor', 'tribute_keeper']`
- error_gradient=`{'mean': 0.00825714285714283, 'std': 0.02580940344375377, 'min': 0.0, 'max': 0.10129999999999997}`
- arousal=`{'mean': 0.4934142857142857, 'std': 0.15584074108407164, 'min': 0.3, 'max': 1.0}`
- attention=`{'mean': 0.5508371428571428, 'std': 0.04441959275374058}`
- confidence0=`{'mean': 0.7774057142857143, 'std': 0.1132504086220497}`
- activation_mean=`{'mean': 0.43687642857142855, 'std': 0.13752922606185738}`
- pairwise_l2=`{'mean': 0.36598354755316964, 'std': 0.4628987447697475, 'min': 0.0, 'max': 1.2768871335008432, 'n_pairs': 91}`

## Why REFINE (~0.54)

- **refine_band:** H7=0.5385 sits in REFINE band [0.5, 0.7). Fraction of C_i ≥ 0.70 is only ~half the trajectory steps.
- **weighted_vs_horizon_gap:** Weighted coherence mean (0.8462) >> horizon H7 (0.5385). Many steps are moderately coherent, but not enough clear the 0.70 threshold for the horizon fraction — weighted metric masks the cusp shortfall.
- **cusp_survival_lift:** Cusp-limited H7 (0.7778) > raw H7 (0.5385) after dropping C<0.50. Low-coherence outlier steps dilute the horizon; surviving mass is healthier.
- **agent_residual_variance:** Agent residual pairwise L2 mean=0.36598354755316964 std=0.4628987447697475. Heterogeneous activation/arousal/error across roles → larger ΔΦ → lower C on more trajectory edges → H7 stuck below APPROVE threshold.
- **kappa_bound_below_threshold:** κ=ω Lipschitz bound (C_mean²)=0.6065 < H7 threshold 0.7. Mean coherence squared cannot underwrite APPROVE-level horizon stability.
- **dphi_dispersion:** ΔΦ std=0.4667 (mean=0.4200) — drift is bursty across the peer residual field, so C oscillates and H7 fraction stays mid-band.

## Recommendation (city-free)

Report only. City may later reduce residual heterogeneity (attention/arousal spread) or tolerate REFINE as honest plateau signal. Do NOT double-gate durable accept. Do NOT script behavior from this report. Human authorize ceiling untouched.

## Non-claims

- not_AGI, not_consciousness, not_Millennium, diagnostics_only

_We light the spark and witness. We do not micromanage the city._
