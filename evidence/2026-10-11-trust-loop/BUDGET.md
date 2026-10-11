# Execution budget (declared before any experiment ran)

Declared: 2026-10-11 ~10:25 AM ET, before the first ablation/evolution run.

| Limit | Value |
|---|---|
| Wall clock for experiments (ablations + adversarial + spark) | 45 minutes total |
| Candidate-mutation experiments (bounded spark) | at most 3 |
| Seeds per ablation arm | 5 (fixed list: 11, 23, 37, 41, 53) |
| Desk cycles per arm per seed (compute budget, matched across arms) | 14 |
| Challenger probe budget | unchanged: DESK_BUDGET_S = 3.0 s per challenge, SAMPLES = 10 |
| Holdout exposures | 1 (final frozen batch); any re-run is logged as re-exposure |
| Compute | this box only (shared Linux box, CPU); no paid APIs, no GPU, no network calls inside experiments (feeds disabled) |
| Tool-call limit for this session | ~150 agent tool calls; no external writes except pushing the feature branch |
| Persistent/autonomous runs | none; no cron, no workflow_dispatch, no push to main |

Stop conditions: budget exhausted, integrity violation (holdout manifest hash mismatch,
live-state pollution), unrecoverable failure, or a permission boundary. Resume point is
recorded in README.md ("Resume point").
