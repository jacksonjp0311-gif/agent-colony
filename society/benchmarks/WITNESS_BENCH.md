# Benchmark witness — 2026-11-20T03:46:50Z

- ok_all: `True`
- aggregate_score: `0.8819`
- delta_vs_previous: `-0.0139`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.001836 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.6752 err=7.367024535821709e-11 s=0.008983 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=0.000109 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.8657 err=0.0 s=0.872801 impl=lemma_impl_v2_basic10_hard187
- `kinematics_microbench` ok=True score=0.8688 err=0.0 s=0.000126 impl=kinematics_impl_v1_enabled5

