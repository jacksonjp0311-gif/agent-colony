# Frontier conjecture generator — tuning log

Calibrated 2026-10-18T05:54:34Z by `evals/frontier/calibrate.py`. Seeds = past desk cycle timestamps; tuning before 2026-10-16T23:20:31Z, held-out after. Rule fixed in advance: smallest FIT_N with tuning false-surprise rate <= 0.05 (a surprise that fails the farther re-test is a false surprise). OEIS index: available.

| FIT_N | split | tested | survived | held-out kills | surprises | false surprises | machine-checked | trivial dropped | Brier |
|---|---|---|---|---|---|---|---|---|---|
| 12 | tuning | 79 | 45 | 34 | 2 | 0 (0.0) | 23 | 443 | 0.2176 |
| 12 | held_out | 92 | 44 | 48 | 1 | 0 (0.0) | 28 | 437 | 0.1885 |
| 16 | tuning | 102 | 71 | 31 | 9 | 0 (0.0) | 32 | 457 | 0.1966 |
| 20 | tuning | 93 | 62 | 31 | 11 | 0 (0.0) | 31 | 390 | 0.1745 |
| 24 | tuning | 114 | 62 | 52 | 8 | 0 (0.0) | 32 | 391 | 0.1642 |
| 30 | tuning | 118 | 75 | 43 | 12 | 0 (0.0) | 34 | 416 | 0.1939 |
| 40 | tuning | 120 | 64 | 56 | 10 | 0 (0.0) | 32 | 397 | 0.148 |

Chosen FIT_N = 12.
