# Benchmark witness — 2026-11-20T03:01:57Z

- ok_all: `True`
- aggregate_score: `0.875`
- delta_vs_previous: `-0.0113`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.002506 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.6427 err=7.367024535821709e-11 s=0.012142 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=0.000155 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.8636 err=0.0 s=1.158633 impl=lemma_impl_v2_basic10_hard187
- `kinematics_microbench` ok=True score=0.8688 err=0.0 s=0.000118 impl=kinematics_impl_v1_enabled5

