# Benchmark witness — 2026-10-09T13:40:08Z

- ok_all: `True`
- aggregate_score: `0.8816`
- delta_vs_previous: `0.0005`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.001791 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.6757 err=7.367024535821709e-11 s=0.00895 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=0.000125 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.9071 err=0.0 s=0.071681 impl=lemma_impl_v2_basic10_hard61
- `kinematics_microbench` ok=True score=0.825 err=0.0 s=0.000112 impl=kinematics_impl_v1_enabled4

