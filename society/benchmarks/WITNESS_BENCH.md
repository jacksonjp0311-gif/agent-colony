# Benchmark witness — 2026-09-26T12:59:10Z

- ok_all: `True`
- aggregate_score: `0.9288`
- delta_vs_previous: `-0.0039`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.001033 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.7734 err=7.367024535821709e-11 s=0.005035 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=2.3e-05 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.9417 err=0.0 s=0.000375 impl=lemma_impl_v1_n10
