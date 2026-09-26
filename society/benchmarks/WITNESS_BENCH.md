# Benchmark witness — 2026-09-26T14:13:27Z

- ok_all: `True`
- aggregate_score: `0.9112`
- delta_vs_previous: `0.0056`

- `fft_microbench` ok=True score=1.0 err=6.25e-12 s=0.0009 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.8075 err=7.37e-11 s=0.0043 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.48e-11 s=0.00002 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.8371 err=0.0 s=0.002 n_hard=6 n_hard_pass=6 impl=lemma_impl_v2_basic10_hard6
