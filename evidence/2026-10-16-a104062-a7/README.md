# OEIS A104062: computed a(7) = 138994

**Computed value, not a proof; pending OEIS review.** It has not been submitted to or accepted by OEIS as of 2026-10-16.

## The sequence
[A104062](https://oeis.org/A104062) (offset 1): a(n) is the number of primes p(i), i = 1 .. 20·10^n, such that
p(i+1) = p(i)+6, p(i+2) = p(i)+12 and p(i+3) = p(i)+18, i.e. four *consecutive* primes in arithmetic
progression with difference 6. OEIS lists a(1)…a(6) = 1, 12, 64, 416, 2748, 19348 (keyword `more`, entry last
edited 2024-11-03, checked 2026-10-16). a(7) covers the first 2·10^8 primes; p(2·10^8) = 4,222,234,741.

## Result
| n | 20·10^n | p(20·10^n) | a(n) | published |
|---|---|---|---|---|
| 1 | 200 | 1223 | 1 | 1 ✔ |
| 2 | 2000 | 17389 | 12 | 12 ✔ |
| 3 | 20000 | 224737 | 64 | 64 ✔ |
| 4 | 200000 | 2750159 | 416 | 416 ✔ |
| 5 | 2000000 | 32452843 | 2748 | 2748 ✔ |
| 6 | 20000000 | 373587883 | 19348 | 19348 ✔ |
| **7** | **200000000** | **4222234741** | **138994** | not listed |

## Three verifications (all agree on every row)
1. **Colony (numpy segmented sieve).** Frontier target `oeis_A104062_next`, family `prime_run_count`.
   3 windows ran during evolve, then 42 windows in the "Frontier burst" workflow
   ([run 38935330075](https://github.com/jacksonjp0311-gif/agent-colony/actions/runs/38935330075), code `a8c2cd7`,
   state committed in `b3e4fe5`). The colony reproduced every published term before recording its own; a mismatch
   would have frozen the target. Per-window log: `colony_windows.json`.
   **Scope of the in-loop check:** in each window the colony recounted one 20,000-number slice with a
   different method (pure-Python sieve vs Miller-Rabin stepping). Those slices total 900,045 numbers, about 0.02%
   of the range. That is a consistency check, **not** an independent recount of the full range. The full
   independent checks are 2 and 3.
2. **primesieve 12.7 + an independent C counter.** `primesieve` (Debian package, BSD-2) prints the primes
   ≤ p(2·10^8). `q.c` (in this folder, compiled with gcc 14.2) keeps the last four primes and reports the count at each
   index 20·10^n. `primesieve -n 200000000` = 4222234741 and `primesieve 4222234741 -c` = 200000000 confirm the
   cutoff. Exact commands and output: `primesieve_run.txt` (about 13 s).
3. **Pure-Python recount**, independent of numpy: `pure_python_recount.py` uses the colony's pure-Python
   reference scanner in 50M windows. Output: `pure_python_recount_output.txt`.

**Boundary note.** `q.c` counts a run when its fourth prime arrives, so at index N it has seen runs starting at
indices ≤ N−3. The colony counts runs starting at index ≤ N, looking ahead. These agree here because none of
the primes at indices 2·10^8−2 … 2·10^8 (4222234703, 4222234727, 4222234741) starts a run; their next gaps are 24, 14 and 22
(`primesieve_run.txt`).

## Reproduce
```bash
sudo apt install primesieve gcc             # primesieve 12.7 used here
gcc -O2 -o q evidence/2026-10-16-a104062-a7/q.c
primesieve -n 200000000                      # 4222234741
time (primesieve 4222234741 --print | ./q)   # last line: n=7 ... count=138994
python3 evidence/2026-10-16-a104062-a7/pure_python_recount.py   # several minutes
PYTHONPATH=. python3 -m colony.frontier burst --target oeis_A104062_next --budget 240   # from a fresh state
```

## What this is and is not
This is a computed term of an integer sequence, cross-checked three ways. It is not a theorem and not new mathematics
beyond the value itself. It should be treated as provisional until OEIS editors review it.
