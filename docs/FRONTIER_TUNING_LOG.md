# Frontier conjecture generator — tuning log

Calibrated 2026-10-17T22:06:18Z by `evals/frontier/calibrate.py`. Seeds = past desk cycle timestamps; tuning before 2026-10-16T23:20:31Z, held-out after. Rule fixed in advance: smallest FIT_N with tuning false-surprise rate <= 0.05 (a surprise that fails the farther re-test is a false surprise). OEIS index: available.

| FIT_N | split | tested | survived | held-out kills | surprises | false surprises | machine-checked | trivial dropped | Brier |
|---|---|---|---|---|---|---|---|---|---|
| 12 | tuning | 110 | 77 | 33 | 17 | 0 (0.0) | 29 | 368 | 0.1956 |
| 12 | held_out | 113 | 72 | 41 | 15 | 0 (0.0) | 31 | 419 | 0.1828 |
| 16 | tuning | 117 | 71 | 46 | 9 | 0 (0.0) | 37 | 369 | 0.1968 |
| 20 | tuning | 133 | 95 | 38 | 12 | 0 (0.0) | 40 | 355 | 0.198 |
| 24 | tuning | 119 | 76 | 43 | 11 | 0 (0.0) | 38 | 323 | 0.1964 |
| 30 | tuning | 114 | 93 | 21 | 19 | 0 (0.0) | 34 | 359 | 0.1624 |
| 40 | tuning | 131 | 98 | 33 | 18 | 0 (0.0) | 37 | 338 | 0.1853 |

Chosen FIT_N = 12.
