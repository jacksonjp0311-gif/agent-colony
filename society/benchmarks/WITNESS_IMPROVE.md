# Benchmark improve witness — 2026-09-26T22:26:40Z

Measure → patch → re-measure → **keep** if aggregate_score rises, else **revert**.

- note: cycle_id=20260926T222639Z_0c38b7

- `autodiff_busy_loop` → **revert** before=0.9042 after=0.9021 delta=-0.0021 — aggregate did not rise or Oracle killed keep (trial=0.9021, delta=-0.0021); reverted (Add busy loop in autodiff grads — should revert); restored_agg=0.9051

## Recent history

- 2026-09-26T22:16:52Z `fft_add_slow_loops` **revert** 0.9046→0.8825 (-0.0221)
- 2026-09-26T22:17:00Z `fft_add_slow_loops` **revert** 0.8928→0.8741 (-0.0187)
- 2026-09-26T22:17:08Z `fft_add_slow_loops` **revert** 0.9046→0.8773 (-0.0273)
- 2026-09-26T22:17:16Z `fft_add_slow_loops` **revert** 0.9014→0.8839 (-0.0175)
- 2026-09-26T22:24:57Z `fft_add_slow_loops` **revert** 0.8954→0.8779 (-0.0175)
- 2026-09-26T22:25:12Z `fft_add_slow_loops` **revert** 0.9002→0.8771 (-0.0231)
- 2026-09-26T22:25:26Z `fft_add_slow_loops` **revert** 0.897→0.8766 (-0.0204)
- 2026-09-26T22:25:41Z `fft_add_slow_loops` **revert** 0.8937→0.8764 (-0.0173)
- 2026-09-26T22:25:56Z `fft_add_slow_loops` **revert** 0.8976→0.8786 (-0.019)
- 2026-09-26T22:26:11Z `autodiff_busy_loop` **revert** 0.9023→0.9038 (+0.0015)
- 2026-09-26T22:26:25Z `autodiff_busy_loop` **revert** 0.8986→0.9029 (+0.0043)
- 2026-09-26T22:26:40Z `autodiff_busy_loop` **revert** 0.9042→0.9021 (-0.0021)

