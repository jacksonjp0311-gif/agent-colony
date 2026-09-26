# Benchmark improve witness — 2026-09-26T14:13:25Z

Measure → patch → re-measure → **keep** if aggregate_score rises, else **revert**.

- note: cycle_id=20260926T141325Z_858f1b

- `autodiff_busy_loop` → **keep** before=0.9031 after=0.9144 delta=+0.0113 — aggregate rose; kept patch (Add busy loop in autodiff grads — should revert)

## Recent history

- 2026-09-26T12:58:05Z `autodiff_busy_loop` **revert** 0.9413→0.9367 (-0.0046)
- 2026-09-26T12:58:06Z `fft_add_slow_loops` **revert** 0.9366→0.9075 (-0.0291)
- 2026-09-26T12:58:08Z `fft_add_slow_loops` **revert** 0.9427→0.9096 (-0.0331)
- 2026-09-26T12:58:09Z `fft_add_slow_loops` **revert** 0.9363→0.9081 (-0.0282)
- 2026-09-26T14:13:21Z `fft_add_slow_loops` **revert** 0.907→0.8847 (-0.0223)
- 2026-09-26T14:13:22Z `fft_add_slow_loops` **revert** 0.9183→0.8874 (-0.0309)
- 2026-09-26T14:13:22Z `fft_add_slow_loops` **revert** 0.9161→0.8866 (-0.0295)
- 2026-09-26T14:13:23Z `fft_add_slow_loops` **revert** 0.9142→0.8859 (-0.0283)
- 2026-09-26T14:13:24Z `fft_add_slow_loops` **revert** 0.9104→0.8837 (-0.0267)
- 2026-09-26T14:13:24Z `fft_add_slow_loops` **revert** 0.9095→0.8824 (-0.0271)
- 2026-09-26T14:13:25Z `fft_add_slow_loops` **revert** 0.9094→0.8869 (-0.0225)
- 2026-09-26T14:13:25Z `autodiff_busy_loop` **keep** 0.9031→0.9144 (+0.0113)

