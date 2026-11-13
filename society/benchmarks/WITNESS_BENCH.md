# Benchmark witness — 2026-11-13T18:00:37Z

- ok_all: `True`
- aggregate_score: `0.8655`
- delta_vs_previous: `-0.0175`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.002999 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.6363 err=7.367024535821709e-11 s=0.013034 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=8.4e-05 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.866 err=0.0 s=0.848273 impl=lemma_impl_v2_basic10_hard162
- `kinematics_microbench` ok=True score=0.825 err=0.0 s=9.9e-05 impl=kinematics_impl_v1_enabled4

