# Benchmark improve witness — 2026-09-26T12:46:58Z

Measure → patch → re-measure → **keep** if aggregate_score rises, else **revert**.

- note: cycle_id=20260926T124657Z_7044d2

- `fft_add_slow_loops` → **revert** before=0.9436 after=0.9038 delta=-0.0398 — aggregate did not rise (trial=0.9038, delta=-0.0398); reverted (Increase SLOW_EXTRA_LOOPS — deliberate regression); restored_agg=0.9339

## Recent history

- 2026-09-26T12:45:47Z `fft_remove_slow_loops` **keep** 0.8815→0.9451 (+0.0636)
- 2026-09-26T12:45:48Z `fft_add_slow_loops` **revert** 0.9442→0.9038 (-0.0404)
- 2026-09-26T12:46:55Z `autodiff_busy_loop` **keep** 0.9151→0.9315 (+0.0164)
- 2026-09-26T12:46:55Z `fft_add_slow_loops` **revert** 0.9322→0.8943 (-0.0379)
- 2026-09-26T12:46:56Z `fft_add_slow_loops` **revert** 0.9352→0.8942 (-0.041)
- 2026-09-26T12:46:56Z `fft_add_slow_loops` **revert** 0.9462→0.9039 (-0.0423)
- 2026-09-26T12:46:56Z `fft_add_slow_loops` **revert** 0.9431→0.8976 (-0.0455)
- 2026-09-26T12:46:57Z `fft_add_slow_loops` **revert** 0.9348→0.8969 (-0.0379)
- 2026-09-26T12:46:57Z `fft_add_slow_loops` **revert** 0.9438→0.8997 (-0.0441)
- 2026-09-26T12:46:58Z `fft_add_slow_loops` **revert** 0.9436→0.9038 (-0.0398)

