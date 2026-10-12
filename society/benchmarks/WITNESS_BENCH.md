# Benchmark witness — 2026-10-12T15:52:53Z

- ok_all: `True`
- aggregate_score: `0.8751`
- delta_vs_previous: `-0.0124`

- `fft_microbench` ok=True score=1.0 err=6.253262709264633e-12 s=0.002372 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `fft_stress_microbench` ok=True score=0.6433 err=7.367024535821709e-11 s=0.012059 impl=fft_impl_cooley_tukey_iter_v1_slow0
- `autodiff_microbench` ok=True score=1.0 err=6.47925602059729e-11 s=0.000128 impl=autodiff_reverse_tape_v1
- `lemma_microbench` ok=True score=0.9071 err=0.0 s=0.09205 impl=lemma_impl_v2_basic10_hard76
- `kinematics_microbench` ok=True score=0.825 err=0.0 s=0.000103 impl=kinematics_impl_v1_enabled4

