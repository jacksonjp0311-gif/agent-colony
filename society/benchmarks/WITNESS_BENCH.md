# Benchmark witness — 2026-11-26T06:37:57Z

- ok_all: `True`
- aggregate_score: `0.875`
- delta_vs_previous: `-0.0115`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.002471 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.6428 err=7.367024535821709e-11 s=0.012128 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=0.000155 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.8636 err=0.0 s=1.166363 impl=lemma_impl_v2_basic10_hard187
- `kinematics_microbench` ok=True score=0.8688 err=0.0 s=0.000115 impl=kinematics_impl_v1_enabled5

