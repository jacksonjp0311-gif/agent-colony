# Benchmark witness — 2026-10-23T15:40:14Z

- ok_all: `True`
- aggregate_score: `0.863`
- delta_vs_previous: `-0.0186`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.003053 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.6244 err=7.367024535821709e-11 s=0.015112 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=8.2e-05 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.8657 err=0.0 s=0.878619 impl=lemma_impl_v2_basic10_hard154
- `kinematics_microbench` ok=True score=0.825 err=0.0 s=0.000102 impl=kinematics_impl_v1_enabled4

