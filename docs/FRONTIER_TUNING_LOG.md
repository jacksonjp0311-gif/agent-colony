# Frontier conjecture generator — tuning log

Calibrated 2026-10-18T02:33:56Z by `evals/frontier/calibrate.py`. Seeds = past desk cycle timestamps; tuning before 2026-10-16T23:20:31Z, held-out after. Rule fixed in advance: smallest FIT_N with tuning false-surprise rate <= 0.05 (a surprise that fails the farther re-test is a false surprise). OEIS index: available.

| FIT_N | split | tested | survived | held-out kills | surprises | false surprises | machine-checked | trivial dropped | Brier |
|---|---|---|---|---|---|---|---|---|---|
| 12 | tuning | 89 | 56 | 33 | 2 | 0 (0.0) | 27 | 404 | 0.2164 |
| 12 | held_out | 102 | 57 | 45 | 3 | 0 (0.0) | 28 | 391 | 0.2086 |
| 16 | tuning | 107 | 68 | 39 | 11 | 0 (0.0) | 27 | 336 | 0.1975 |
| 20 | tuning | 129 | 85 | 44 | 16 | 0 (0.0) | 33 | 373 | 0.2005 |
| 24 | tuning | 123 | 79 | 44 | 13 | 0 (0.0) | 34 | 357 | 0.1875 |
| 30 | tuning | 117 | 81 | 36 | 13 | 0 (0.0) | 34 | 265 | 0.1828 |
| 40 | tuning | 129 | 86 | 43 | 14 | 0 (0.0) | 33 | 269 | 0.1934 |

Chosen FIT_N = 12.
