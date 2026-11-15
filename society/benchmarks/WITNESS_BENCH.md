# Benchmark witness — 2026-11-15T16:12:51Z

- ok_all: `True`
- aggregate_score: `0.8665`
- delta_vs_previous: `-0.0116`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.002446 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.6426 err=7.367024535821709e-11 s=0.01215 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=0.000142 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.8651 err=0.0 s=0.942293 impl=lemma_impl_v2_basic10_hard162
- `kinematics_microbench` ok=True score=0.825 err=0.0 s=0.000105 impl=kinematics_impl_v1_enabled4

