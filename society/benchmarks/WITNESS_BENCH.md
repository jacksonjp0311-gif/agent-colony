# Benchmark witness — 2026-11-24T05:23:06Z

- ok_all: `True`
- aggregate_score: `0.866`
- delta_vs_previous: `-0.0205`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.002509 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.5975 err=7.367024535821709e-11 s=0.023697 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=9.1e-05 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.8637 err=0.0 s=1.1487 impl=lemma_impl_v2_basic10_hard187
- `kinematics_microbench` ok=True score=0.8688 err=0.0 s=0.000115 impl=kinematics_impl_v1_enabled5

