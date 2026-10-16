# A104062 a(8), a(9), a(10), a(11) — computed, not proof; pending OEIS review (2026-10-16)

A104062(n) = number of primes p(i), i ≤ 2·10^n, whose next three consecutive primes are p+6, p+12, p+18.
Boundary rule: a quadruple is counted only when all four primes lie inside the first N = 2·10^n primes.
At both new boundaries no quadruple straddles p(N), so the rule doesn't change either value (checked by listing the
primes around p(N): `primesieve <P-18> <P+60> -p`).

| n | N = 2·10^n | p(N) (`primesieve -n`) | a(n) |
|---|---|---|---|
| 8 | 2,000,000,000 | 47,055,833,459 | **1,031,312** |
| 9 | 20,000,000,000 | 518,649,879,439 | **7,863,231** |

a(1..6) = 1, 12, 64, 416, 2748, 19348 (published) and a(7) = 138994 (see `../2026-10-16-a104062-a7/`) were reproduced
by every method below.

## a(10) and a(11) (added 2026-10-16 evening)

| n | N | p(N) | a(n) |
|---|---|---|---|
| 10 | 2·10^11 | 5,665,449,960,167 | **61,341,010** |
| 11 | 2·10^12 | 61,427,839,512,211 | **487,855,645** |

- **a(10), on the box (8 cores), three counters agree exactly.** `qs` (iterator, sharded), `qk` and
  `tools/a104062/qk_range.c` (array API, 10^9 blocks) each give 61341010 with π(P)=2·10^11 (`a10_outputs.txt`).
  `primesieve -n 2e11` gives 5665449960167.
- **a(11), on GitHub Actions, workflow "A104062 shards", run 38969154507 (green).** p(N) comes from `primecount --nth-prime`
  (primecount 7.16 → 61427839512211). Pass A is `tools/a104062/qs_range.c` over 20 shards; pass B is
  `tools/a104062/qk_range.c` over 19 shards with different boundaries. Each shard counts quadruples whose first prime is
  in its range and reads past its end for the next 3 primes, so edge-crossing quadruples are counted exactly once.
  Pass A gives 487855645 quadruples and Pass B gives 487855645; both count exactly 2·10^12 primes ≤ P, which independently
  confirms P = p(2·10^12). The workflow was validated first on N = 2·10^8 (run 38965729478 → 138994). The runners use
  primesieve 12.0; the box uses 12.7.
- **p(2·10^12) confirmed on the box:** `primesieve -n 2e12` (primesieve 12.7) → **61427839512211** (2583 s, `nth_prime.txt`), matching primecount.
- **Boundary:** no quadruple straddles p(N) at either cutoff (primes around P listed with `primesieve <P-18> <P+60> -p`).
- **The colony burst was not run for a(10) or a(11).** About 5·10^4 windows of 10^8 would be needed, well over 50 burst
  runs, which is not a reasonable use of free compute. So the a(10) and a(11) checks are independent C programs, not the colony.
- **HL ratio actual/consecutive:** n=10: 1.000121, n=11: 0.999995. This crosses 1, so it is consistent with fluctuation
  around the HL prediction. It is evidence, not proof.

## Verifications of a(8), a(9) (all agree exactly)
1. **primesieve 12.7 text pipeline + `q9.c`** (the a(7) counter `/workspace/q.c`, extended to N up to 2·10^10, 64-bit):
   `primesieve 1 518649879439 -p | ./q9` → `q9_pipeline_output.txt` (single thread, 21 min on the box).
2. **libprimesieve iterator, sharded, OpenMP (`qs.c`)**: `./qs 47055833459 8`, `./qs 518649879439 8` →
   `qs_output.txt`. It also counts π(P), which returns exactly 2·10^9 and 2·10^10 primes. It ran in 1.3 s and 16 s.
3. **`qk.c`**: an independent single-pass loop that counts runs of k consecutive gaps of 6 (k=1..4) → `qk.txt`. Its k=3
   column matches. k=4 is always 0, as it must be: p..p+24 covers every residue mod 5.
4. **Colony frontier burst** (GitHub Actions, workflow "Frontier burst"; numpy segmented sieve per 10^8 window). Every
   window had the Challenger and a Miller-Rabin sub-window recount, and every published term was reproduced or the
   target would freeze. The colony's values are in `society/benchmarks/frontier.json` → `oeis_A104062_next.colony_terms`:
   `2000000000: {count: 1031312, prime_at_index: 47055833459}`, `20000000000: {count: 7863231, prime_at_index: 518649879439}`. These are exact matches with methods 1–3. Final verified range is [2, 518690000001] and the target status is `done`.
   Runs: 38952344745 (a(8) reached), 38953601645, 38954841443, 38956031261, 38957253669, 38958466920, 38961249736, 38962488768 (a(9) reached), all green; each committed `ci(frontier): burst …`.

`primesieve -n 2e9` → 47055833459, `primesieve -n 2e10` → 518649879439 (`nth_prime.txt`).

## Pattern across scales
Hardy–Littlewood-type prediction for **consecutive** primes p, p+6, p+12, p+18 (no prime strictly between).
- **Tuple constant (standard):** the HL k-tuple conjecture (Hardy & Littlewood 1923, *Partitio Numerorum III*) gives
  #{p ≤ x : p+h prime ∀h∈H} ~ 𝔖(H)∫₂ˣ dt/log^k t, with 𝔖(H)=∏_p (1−ν_p(H)/p)(1−1/p)^(−k).
- **Consecutiveness (method of Odlyzko–Rubinstein–Wolf, "Jumping champions", Experimental Math. 8 (1999)):**
  inclusion–exclusion over the interior points {2,4,8,10,14,16}. Every interior point is coprime to 6 relative to p.
  Pred(x)=Σ_S (−1)^|S| 𝔖({0,6,12,18}∪S) ∫₂ˣ dt/log^{4+|S|} t. Only 7 sets S have 𝔖≠0; the rest cover all residues
  mod 3 or mod 5.
- **Constants computed here (derived here, not quoted from literature):** 𝔖({0,6,12,18}) = **8.30236**,
  with ±{2},{8},{10},{16}: 10.1318 each, and {2,8},{10,16}: 17.2986. These are products over primes ≤ 10^7 with the exact
  remaining factors. As a sanity check, the same code gives 2C₂ = 1.32032 for {0,2} and 2.85825 for {0,2,6}, matching the
  published values. I did not find 8.30236 for this exact constellation in a source I could cite, so treat it as derived here.

| n | a(n) | a(n)/a(n−1) | HL tuple only | HL consecutive | actual / consecutive |
|---|---|---|---|---|---|
| 1 | 1 | - | 33.7 | 16.8 | 0.05935 |
| 2 | 12 | 12.0000 | 55.9 | 27.7 | 0.43248 |
| 3 | 64 | 5.3333 | 156.4 | 88.2 | 0.72531 |
| 4 | 416 | 6.5000 | 706.1 | 456.8 | 0.91077 |
| 5 | 2748 | 6.6058 | 4064.2 | 2867.2 | 0.95843 |
| 6 | 19348 | 7.0408 | 26174.0 | 19514.7 | 0.99146 |
| 7 | 138994 | 7.1839 | 179868.7 | 139407.5 | 0.99703 |
| 8 | 1031312 | 7.4198 | 1293518.9 | 1032215.2 | 0.99912 |
| 9 | 7863231 | 7.6245 | 9631449.0 | 7863975.6 | 0.99991 |
| 10 | 61341010 | 7.8010 | 73737902.8 | 61333608.5 | 1.000121 |
| 11 | 487855645 | 7.9532 | 577585671.6 | 487857895.1 | 0.999995 |

`hl.py` holds the derivation, `hl.json` the numbers, `plot.py` the plot, and the plot is `a104062_actual_vs_hl.png`.

Findings:
- **Consecutive prediction:** the ratio climbs monotonically: 0.06, 0.43, 0.73, 0.91, 0.96, 0.991, 0.997, 0.9991, 0.9999.
  At small n the log-integrals are poor approximations, as expected.
- **Tuple-only prediction:** this ignores consecutiveness and overshoots by ~20% even at n=9.
- **Growth ratio:** a(n+1)/a(n) is rising slowly (7.18, 7.42, 7.62). It should creep towards 10 as
  (log x_n / log x_{n+1})^4 → 1.
- **Context (same run, `qk.txt`):** consecutive gap-6 pairs, i.e. two primes with gap 6 = 1,869,250,533. Gap-6 triples
  (two gaps of 6) = 142,975,739, within the first 2·10^10 primes.

**Honest note:** agreement with Hardy–Littlewood is evidence, not proof. The k-tuple conjecture is unproven, and the
near-1 ratio is consistent with it but proves nothing. The values themselves are machine computations, cross-checked by
independent code paths. They are not a proof and await OEIS review.

## Reproduce
`gcc -O2 -fopenmp qs.c -o qs -l:libprimesieve.so.12 && ./qs $(primesieve -n 2e10 -q) 8`
