# Benchmark improve witness — 2026-09-27T12:17:07Z

Measure → patch → re-measure → **keep** if aggregate_score rises, else **revert**.

- note: cycle_id=20260927T121706Z_58f03a

- `fft_add_slow_loops` → **revert** before=0.8958 after=0.8755 delta=-0.0203 — aggregate did not rise or Oracle killed keep (trial=0.8755, delta=-0.0203); reverted (Increase SLOW_EXTRA_LOOPS — deliberate regression); restored_agg=0.8957

## Recent history

- 2026-09-27T05:29:55Z `fft_add_slow_loops` **revert** 0.8686→0.8656 (-0.003)
- 2026-09-27T05:29:57Z `fft_add_slow_loops` **revert** 0.8791→0.8657 (-0.0134)
- 2026-09-27T05:30:17Z `autodiff_busy_loop` **revert** 0.8796→0.8792 (-0.0004)
- 2026-09-27T05:30:37Z `autodiff_busy_loop` **revert** 0.8791→0.8791 (+0.0)
- 2026-09-27T12:16:21Z `fft_add_slow_loops` **revert** 0.8881→0.8688 (-0.0193)
- 2026-09-27T12:16:23Z `autodiff_busy_loop` **revert** 0.8882→0.8938 (+0.0056)
- 2026-09-27T12:16:45Z `fft_add_slow_loops` **revert** 0.8965→0.8758 (-0.0207)
- 2026-09-27T12:17:07Z `fft_add_slow_loops` **revert** 0.8958→0.8755 (-0.0203)

