# Benchmark witness — 2026-10-09T06:30:14Z

- ok_all: `True`
- aggregate_score: `0.8887`
- delta_vs_previous: `0.0004`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.001503 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.7114 err=7.367024535821709e-11 s=0.006969 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=8.6e-05 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.9071 err=0.0 s=0.044393 impl=lemma_impl_v2_basic10_hard56
- `kinematics_microbench` ok=True score=0.825 err=0.0 s=0.000101 impl=kinematics_impl_v1_enabled4

