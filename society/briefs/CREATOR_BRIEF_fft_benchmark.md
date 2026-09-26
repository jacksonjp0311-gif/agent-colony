# CREATOR_BRIEF — FFT microbench mile

**For:** James Paul Jackson  
**When:** 2026-09-26T12:36Z  
**Claim level:** measured harness only — **not** a novel math breakthrough, **not AGI**

## Target
Fixed-seed length-1024 FFT: colony artifact vs reference (`numpy.fft` or pure DFT fallback).

## Before → after
| | ok | aggregate_score | impl |
|--|----|-----------------|------|
| baseline | false | **0.0** | `fft_impl_broken_identity_v0` |
| after | true | **1.0** | `fft_impl_cooley_tukey_iter_v1` |

- max_abs_err after: ~6e-12 (tol 1e-6)
- seconds after: ~0.001 (budget 0.05)

## Paths
- Harness: `society/benchmarks/fft_microbench.py`
- Runner: `society/benchmarks/run_benchmarks.py`
- Artifact: `society/benchmarks/artifacts/fft_impl.py`
- Latest: `society/benchmarks/latest.json`
- History: `society/benchmarks/history.jsonl`
- Fitness reader: `colony/benchmarks_fit.py` (drives `math_prize` / `compute_usefulness`)

## Will
Active ask now requires benchmark-passing FFT work; hearings should kill no-delta proposals; prize fitness no longer saturates from institution names alone.

## Honest note
The passing impl is a standard iterative Cooley–Tukey — proving the **measurement loop**, not inventing FFT. Next mile: a harder bench (larger n, real workload, or autodiff check) where improvement is non-trivial.
