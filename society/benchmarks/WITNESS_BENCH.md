# Benchmark witness — 2026-11-14T08:17:27Z

- ok_all: `True`
- aggregate_score: `0.8668`
- delta_vs_previous: `-0.0121`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.002458 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.6434 err=7.367024535821709e-11 s=0.012041 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=0.000138 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.8654 err=0.0 s=0.903915 impl=lemma_impl_v2_basic10_hard162
- `kinematics_microbench` ok=True score=0.825 err=0.0 s=0.000107 impl=kinematics_impl_v1_enabled4

