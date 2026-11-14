# Benchmark witness — 2026-11-14T22:10:36Z

- ok_all: `True`
- aggregate_score: `0.873`
- delta_vs_previous: `-0.0116`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.001871 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.6727 err=7.367024535821709e-11 s=0.009169 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=0.000109 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.8671 err=0.0 s=0.756009 impl=lemma_impl_v2_basic10_hard162
- `kinematics_microbench` ok=True score=0.825 err=0.0 s=8.4e-05 impl=kinematics_impl_v1_enabled4

