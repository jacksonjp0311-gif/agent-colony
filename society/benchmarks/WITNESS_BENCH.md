# Benchmark witness — 2026-10-17T02:01:58Z

- ok_all: `True`
- aggregate_score: `0.8713`
- delta_vs_previous: `-0.0106`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.002598 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.6396 err=7.367024535821709e-11 s=0.012553 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=0.00014 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.8919 err=0.0 s=0.216058 impl=lemma_impl_v2_basic10_hard113
- `kinematics_microbench` ok=True score=0.825 err=0.0 s=0.00011 impl=kinematics_impl_v1_enabled4

