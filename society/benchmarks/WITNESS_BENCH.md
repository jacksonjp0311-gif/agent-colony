# Benchmark witness — 2026-10-23T17:57:49Z

- ok_all: `True`
- aggregate_score: `0.8848`
- delta_vs_previous: `-0.0234`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.001313 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.729 err=7.367024535821709e-11 s=0.006286 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=7.7e-05 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.8702 err=0.0 s=0.572705 impl=lemma_impl_v2_basic10_hard163
- `kinematics_microbench` ok=True score=0.825 err=0.0 s=9.5e-05 impl=kinematics_impl_v1_enabled4

