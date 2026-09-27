# Benchmark witness — 2026-09-27T17:08:12Z

- ok_all: `True`
- aggregate_score: `0.903`
- delta_vs_previous: `0.0236`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.000922 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.813 err=7.367024535821709e-11 s=0.004278 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=5.8e-05 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.8771 err=0.0 s=0.010607 impl=lemma_impl_v2_basic10_hard25
- `kinematics_microbench` ok=True score=0.825 err=0.0 s=6.7e-05 impl=kinematics_impl_v1_enabled4

