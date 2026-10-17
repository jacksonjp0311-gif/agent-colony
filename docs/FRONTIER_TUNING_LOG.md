# Frontier conjecture generator — tuning log

Calibrated 2026-10-17T22:19:21Z by `evals/frontier/calibrate.py`. Seeds = past desk cycle timestamps; tuning before 2026-10-16T23:20:31Z, held-out after. Rule fixed in advance: smallest FIT_N with tuning false-surprise rate <= 0.05 (a surprise that fails the farther re-test is a false surprise). OEIS index: available.

| FIT_N | split | tested | survived | held-out kills | surprises | false surprises | machine-checked | trivial dropped | Brier |
|---|---|---|---|---|---|---|---|---|---|
| 12 | tuning | 100 | 61 | 39 | 8 | 0 (0.0) | 27 | 425 | 0.2002 |
| 12 | held_out | 100 | 62 | 38 | 9 | 0 (0.0) | 25 | 405 | 0.2207 |
| 16 | tuning | 121 | 79 | 42 | 9 | 0 (0.0) | 34 | 375 | 0.1992 |
| 20 | tuning | 110 | 74 | 36 | 12 | 0 (0.0) | 32 | 366 | 0.1937 |
| 24 | tuning | 119 | 79 | 40 | 12 | 0 (0.0) | 34 | 340 | 0.1736 |
| 30 | tuning | 136 | 94 | 42 | 15 | 0 (0.0) | 36 | 317 | 0.1947 |
| 40 | tuning | 127 | 75 | 52 | 7 | 0 (0.0) | 31 | 337 | 0.1805 |

Chosen FIT_N = 12.
