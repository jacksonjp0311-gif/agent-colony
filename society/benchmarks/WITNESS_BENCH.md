# Benchmark witness — 2026-10-18T02:59:36Z

- ok_all: `True`
- aggregate_score: `0.875`
- delta_vs_previous: `0.0001`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.001879 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.6886 err=7.367024535821709e-11 s=0.008118 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=0.000111 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.8612 err=0.0 s=1.860187 impl=lemma_impl_v2_basic10_hard204
- `kinematics_microbench` ok=True score=0.825 err=0.0 s=0.00011 impl=kinematics_impl_v1_enabled4

