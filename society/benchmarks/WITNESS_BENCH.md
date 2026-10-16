# Benchmark witness — 2026-10-16T16:38:51Z

- ok_all: `True`
- aggregate_score: `0.8801`
- delta_vs_previous: `-0.0076`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.001968 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.6683 err=7.367024535821709e-11 s=0.009506 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=0.000106 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.9071 err=0.0 s=0.11531 impl=lemma_impl_v2_basic10_hard100
- `kinematics_microbench` ok=True score=0.825 err=0.0 s=9.1e-05 impl=kinematics_impl_v1_enabled4

