# Benchmark witness — 2026-10-17T09:28:24Z

- ok_all: `True`
- aggregate_score: `0.8674`
- delta_vs_previous: `-0.0099`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.002551 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.6407 err=7.367024535821709e-11 s=0.012401 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=0.000137 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.8712 err=0.0 s=0.534998 impl=lemma_impl_v2_basic10_hard133
- `kinematics_microbench` ok=True score=0.825 err=0.0 s=0.00011 impl=kinematics_impl_v1_enabled4

