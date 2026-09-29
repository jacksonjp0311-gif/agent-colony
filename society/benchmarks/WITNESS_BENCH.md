# Benchmark witness — 2026-09-29T22:29:22Z

- ok_all: `True`
- aggregate_score: `0.8786`
- delta_vs_previous: `-0.0002`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.001705 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.6907 err=7.367024535821709e-11 s=0.007997 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=0.0001 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.8771 err=0.0 s=0.019091 impl=lemma_impl_v2_basic10_hard25
- `kinematics_microbench` ok=True score=0.825 err=0.0 s=0.000112 impl=kinematics_impl_v1_enabled4

