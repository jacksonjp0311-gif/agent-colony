# Benchmark improve witness — 2026-09-27T21:30:40Z

Measure → patch → re-measure → **keep** if aggregate_score rises, else **revert**.

- note: cycle_id=20260927T213039Z_cd1c7c

- `fft_add_slow_loops` → **revert** before=0.8841 after=0.8693 delta=-0.0148 — aggregate did not rise or Oracle killed keep (trial=0.8693, delta=-0.0148); reverted (Increase SLOW_EXTRA_LOOPS — deliberate regression); restored_agg=0.8834

## Recent history

- 2026-09-27T05:30:37Z `autodiff_busy_loop` **revert** 0.8791→0.8791 (+0.0)
- 2026-09-27T12:16:21Z `fft_add_slow_loops` **revert** 0.8881→0.8688 (-0.0193)
- 2026-09-27T12:16:23Z `autodiff_busy_loop` **revert** 0.8882→0.8938 (+0.0056)
- 2026-09-27T12:16:45Z `fft_add_slow_loops` **revert** 0.8965→0.8758 (-0.0207)
- 2026-09-27T12:17:07Z `fft_add_slow_loops` **revert** 0.8958→0.8755 (-0.0203)
- 2026-09-27T17:07:03Z `fft_add_slow_loops` **revert** 0.8834→0.8687 (-0.0147)
- 2026-09-27T17:07:05Z `fft_add_slow_loops` **revert** 0.8839→0.8788 (-0.0051)
- 2026-09-27T17:07:43Z `fft_add_slow_loops` **revert** 0.9029→0.8792 (-0.0237)
- 2026-09-27T17:08:12Z `fft_add_slow_loops` **revert** 0.9029→0.8794 (-0.0235)
- 2026-09-27T21:29:54Z `fft_add_slow_loops` **revert** 0.8726→0.8652 (-0.0074)
- 2026-09-27T21:29:57Z `fft_add_slow_loops` **revert** 0.8808→0.8686 (-0.0122)
- 2026-09-27T21:30:40Z `fft_add_slow_loops` **revert** 0.8841→0.8693 (-0.0148)

