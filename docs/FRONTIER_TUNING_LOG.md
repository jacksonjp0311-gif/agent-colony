# Frontier conjecture generator — tuning log

Calibrated 2026-10-18T09:04:36Z by `evals/frontier/calibrate.py`. Seeds = past desk cycle timestamps; tuning before 2026-10-16T23:20:31Z, held-out after. Rule fixed in advance: smallest FIT_N with tuning false-surprise rate <= 0.05 (a surprise that fails the farther re-test is a false surprise). OEIS index: available.

| FIT_N | split | tested | survived | held-out kills | surprises | false surprises | machine-checked | trivial dropped | Brier |
|---|---|---|---|---|---|---|---|---|---|
| 12 | tuning | 111 | 35 | 76 | 4 | 0 (0.0) | 24 | 547 | 0.1409 |
| 12 | held_out | 112 | 37 | 75 | 1 | 0 (0.0) | 23 | 659 | 0.1643 |
| 16 | tuning | 102 | 37 | 65 | 1 | 0 (0.0) | 24 | 426 | 0.1574 |
| 20 | tuning | 110 | 42 | 68 | 4 | 0 (0.0) | 26 | 342 | 0.1598 |
| 24 | tuning | 108 | 43 | 65 | 2 | 0 (0.0) | 29 | 325 | 0.1446 |
| 30 | tuning | 105 | 49 | 56 | 4 | 0 (0.0) | 28 | 339 | 0.1571 |
| 40 | tuning | 113 | 52 | 61 | 6 | 0 (0.0) | 27 | 332 | 0.1572 |

Chosen FIT_N = 12.

## 2026-10-18 wider menu (COLONY_FRONTIER_MENU=wide), report-only first

Ingredients added (generator menu only; Oracle and gate unchanged): Collatz total stopping time `csteps`
and max excursion `cmax`, record prime gap `maxgap`, Goldbach counts `gold` (#{p <= q prime, p + q = 2n}),
prime races `cheb4` (#3 mod 4 - #1 mod 4) and `cheb3`, base-3 digit sum `ds3`, decimal reversal `rev`;
residue classes mod 5, 7, 11 and modulus 11 (congruences fitted on 6 members of the class); new claim
kind `modpat` (n -> a(n) mod m periodic). Prime gaps (= D(prime)) and aliquot s(n) (= sigma - n) are
already expressible, so they are not new primitives (no definitional identities).
Known results recognized: Ramanujan p(5k+4), p(7k+5), p(11k+6); consequences of them with periodic
parts (implied_parts); prime-race sign claims (Chebyshev bias); Goldbach lower bounds; prime-gap upper
bounds. New general rules: primes > 2 are odd (parity of pi / prime races), Collatz maxima are even,
digit sums keep n mod (b - 1) (digit_rule), monotone outer functions, f(2n) = f(2) f(n) for odd n
(multiplicative f, inside case splits), sigma >= gpf + 1, tau >= Omega + omega, p(n) <= 2^n, Pell(n).
Shadow (12 tuning-like + 12 held-out seeds, wide): 0 and 1 surprises; base menu on the same seeds: 4.
Calibration above was run with the wide menu: FIT_N stays 12, 0 false surprises (tuning and held-out).
