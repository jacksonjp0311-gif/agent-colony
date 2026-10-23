# Benchmark witness — 2026-10-23T16:43:26Z

- ok_all: `True`
- aggregate_score: `0.8661`
- delta_vs_previous: `-0.0114`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.002545 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.6409 err=7.367024535821709e-11 s=0.012375 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=0.000142 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.8645 err=0.0 s=1.017082 impl=lemma_impl_v2_basic10_hard162
- `kinematics_microbench` ok=True score=0.825 err=0.0 s=0.000104 impl=kinematics_impl_v1_enabled4

