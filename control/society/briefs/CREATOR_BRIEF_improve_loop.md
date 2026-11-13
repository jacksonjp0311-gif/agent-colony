# CREATOR_BRIEF — Bench improve keep/revert loop

**For:** James Paul Jackson  
**When:** 2026-09-26T12:47Z  
**Claim level:** measured harness only — **not** a novel math breakthrough, **not AGI**  
**Policy:** standing trust high-P (P≥0.75) forever · selective · ceiling held

## Target
Harder FFT stress bench + improver measure→keep/revert loop with witness history.

## Scores (before → after)

| Stage | aggregate | fft_micro | fft_stress (n=4096) | autodiff | notes |
|--|--|--|--|--|--|
| Baseline (slow12) | **0.8834** | 1.0 | **0.6503** | 1.0 | deliberate SLOW_EXTRA_LOOPS=12 |
| After KEEP remove-slow | **0.9451** | 1.0 | **0.8353** | 1.0 | patch kept |
| After REVERT add-slow trial | trial **0.9038** | — | 0.7115 | — | reverted (delta −0.0404) |
| Live after evolve×8 | **0.9454** | 1.0 | **0.8363** | 1.0 | SLOW_EXTRA_LOOPS=0 |

Stress budget `0.0025s` keeps naive-but-correct below 1.0 so the improver has headroom. Existing `fft_microbench` (n=1024) unchanged.

## Improve history (keep vs revert)

1. **keep** `fft_remove_slow_loops` — 0.8815 → 0.9451 (Δ+0.0636)
2. **revert** `fft_add_slow_loops` — trial 0.9038 (Δ−0.0404), restored
3. Evolve cycles: further `fft_add_slow_loops` attempts **reverted** (correct); one noisy autodiff trial later cleaned / keep threshold tightened to Δ>0.01

## Paths
- Stress harness: `society/benchmarks/fft_stress_microbench.py`
- Runner: `society/benchmarks/run_benchmarks.py` (fft + stress + autodiff)
- Improver: `colony/bench_improve.py`
- CLI: `python -m colony bench-improve` (`--demo` for keep-then-revert)
- Growth: once per evolve cycle via `GrowthLoop`
- Witness: `society/benchmarks/improve_history.jsonl`, `WITNESS_IMPROVE.md`, `latest.json`
- Artifact: `society/benchmarks/artifacts/fft_impl.py` (`SLOW_EXTRA_LOOPS` knob)

## Authorize (standing trust P≥0.75)
- Cycle: `authorize_20260926T124638Z`
- **Accepted 3** (P=0.92 / 0.94 / 0.90): stress bench, improve-loop proof, FFT keep
- **Rejected findings 0**; **proposal rejects 40** (junk/dupe / zero-delta improve proposals)
- Receipt: `society/receipts/AUTHORIZE_authorize_20260926T124638Z.md`

## Evolve
- `python -m colony evolve --cycles 8 --offline` → cycle_count **80→88**
- Fitness aggregate ~0.84→0.83 (prize components now read 3-bench aggregate; stress <1.0 is honest)
- Dashboard refreshed

## Will / honest note
The loop proves **measurement discipline** (keep only if aggregate rises, else revert) — not inventing FFT. Next mile: real algorithmic speedups on stress (twiddle precompute / SoA) or a heavier autodiff workload where noise cannot fake a keep.
