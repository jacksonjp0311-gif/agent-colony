# Benchmark witness — 2026-10-23T10:15:46Z

- ok_all: `True`
- aggregate_score: `0.8665`
- delta_vs_previous: `-0.0115`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.002472 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.6422 err=7.367024535821709e-11 s=0.012197 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=0.000141 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.8652 err=0.0 s=0.930671 impl=lemma_impl_v2_basic10_hard150
- `kinematics_microbench` ok=True score=0.825 err=0.0 s=0.000104 impl=kinematics_impl_v1_enabled4

