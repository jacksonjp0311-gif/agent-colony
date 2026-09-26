# Benchmark witness — 2026-09-26T22:26:40Z

- ok_all: `True`
- aggregate_score: `0.9051`
- delta_vs_previous: `0.003`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.001567 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.8235 err=7.367024535821709e-11 s=0.004114 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=2.1e-05 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.8771 err=0.0 s=0.009065 impl=lemma_impl_v2_basic10_hard25
- `kinematics_microbench` ok=True score=0.825 err=0.0 s=6.8e-05 impl=kinematics_impl_v1_enabled4

