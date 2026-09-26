# CREATOR_BRIEF — Autodiff microbench + CI harness

**For:** James Paul Jackson  
**When:** 2026-09-26T12:39Z  
**Claim level:** measured harness — **not** novel autodiff research, **not AGI**

## Target
`y = sin(a*x + b)*(x + c)` — reverse-mode grads vs central finite differences.

## Before → after (autodiff)
| | ok | score | impl |
|--|----|-------|------|
| broken | false | 0.0 | `autodiff_broken_zeros_v0` |
| after | true | 1.0 | `autodiff_reverse_tape_v1` |

Combined with FFT still green → `ok_all=true`, `aggregate_score=1.0`.

## CI
`.github/workflows/colony-evolve.yml` now runs `python -m society.benchmarks.run_benchmarks` each pulse before evolve and commits `society/benchmarks/latest.json`.

## Paths
- `society/benchmarks/autodiff_microbench.py`
- `society/benchmarks/artifacts/autodiff_impl.py`
- `society/benchmarks/run_benchmarks.py` (FFT + autodiff)
- `colony/benchmarks_fit.py` (fitness from latest.json)

## Honest note
Tape autodiff is a teaching micro-impl. The win is **failing benches block fake prize saturation** and CI records the score every cron.
