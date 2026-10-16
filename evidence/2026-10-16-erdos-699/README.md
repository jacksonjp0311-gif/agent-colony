# Erdős Problem #699 — no counterexample for n ≤ 10^9

**Label: bounded evidence, not proof.** This is a finite computer check, not a proof. The problem is still open.

- Problem: https://www.erdosproblems.com/699 (Erdős–Szekeres 1978; Guy B31).
- **Main statement:** for every 1 ≤ i < j ≤ n/2, some prime p ≥ i divides both C(n,i) and C(n,j).
- **Strict version:** the same statement with p > i. It has known exceptions.

## Result

| | |
|---|---|
| Range checked | every n with 4 ≤ n ≤ 1,000,000,000 (n ≤ 3 has no pair i < j ≤ n/2) |
| Main counterexamples | **none** |
| Strict exceptions found | (10,3,5) (16,2,6) (28,3,14) (28,5,14) (244,3,122) (512,2,147) (2048,2,713) (2188,3,1094) (1594324,3,797162). This is exactly Cong's list. |
| New strict exceptions with i ≥ 4 | **none.** (28,5,14) is still the only one. |
| Previous published bound | n ≤ 10^7 (Cong, forum thread 699, 2026-01-06) |
| Compute | 47,029 CPU-seconds (about 13 core-hours) on free GitHub-hosted runners |

Each triple is (n, i, smallest j) such that no prime p > i divides both C(n,i) and C(n,j).

## Method (fast699.c)

1. **Prime-free window.** If a prime q lies in (n−i, n], then q > n/2 ≥ j > i. Such a q divides C(n,i) and C(n,j). So only composite n and i ≤ n − prevprime(n) need checking. This reduction is from Del Pin and MaxDKaos (forum, July 2026).
2. **Which primes divide C(n,i).** For p > i, Kummer's theorem says p | C(n,i) exactly when some multiple of p lies in (n−i, n], which is the same as n mod p < i. For p = i prime, p | C(n,p) exactly when ⌊n/p⌋ ≡ 0 (mod p) (Lucas).
3. **Which j escape a prime.** p ∤ C(n,j) exactly when every base-p digit of j is ≤ the matching digit of n (Lucas/Kummer). In particular j mod p ≤ n mod p < i.
4. **Searching for a bad j.** The checker chooses a subset of S, the primes p > i dividing C(n,i), so as to minimise ∏(b_p+1)·⌈(n/2)/∏p⌉, where b_p = n mod p. It then lists every residue of j allowed by step 3 using CRT, lifts each one to every j ≤ n/2, and runs the full digit test against every p in S. For the main version it also tests p = i.

Factorisations come from a segmented sieve with a 4096-number margin. The program exits with an error if a prime gap is larger than the margin or if the window holds too many primes. Neither happened.

## Independent checker (brute699.c, no shared code)

- **`full` mode** uses no reduction at all. For every pair i < j ≤ n/2 it keeps the exact prime exponents of C(n,k) through C(n,k) = C(n,k−1)(n−k+1)/k, and stores one bitset per j of the primes dividing C(n,j).
- **`lite` mode** uses only step 1 above. It tests every j in (i, n/2] by direct Kummer carry-addition of j and n−j, with primes found by trial division and Legendre valuations. It does no CRT or digit enumeration.

## Cross-checks (all agree)

| Check | Range | Result |
|---|---|---|
| fast699 vs brute699 **full** (all pairs, no reduction) | every n ≤ 20,000 | identical output: 8 strict exceptions, 0 main (`logs/brute_full_summaries.txt`) |
| fast699 vs brute699 **lite** | every n ≤ 100,000 | identical output, and identical (n,i) pair counts (779,987) (`logs/brute_lite_le_1e5.txt`) |
| fast699 vs brute699 lite, random blocks (seed 699) | 3 blocks × 600 n in [10^6, 10^7), 3 × 100 in [10^7, 10^8), 3 × 10 in [10^8, 10^9) | identical output and pair counts (`logs/brute_lite_vs_fast_blocks.txt`) |
| brute699 lite at n = 1594324 | 1594300 to 1594330 | reproduces the strict exception (1594324,3,797162) |
| fast699 on the box (not on CI) | every n ≤ 10^7 | the 9 strict exceptions above, 0 main (`logs/fast_le_1e7_box.txt`) |
| Failure path | n ≤ 3000, strict version | the checker reports exactly the 8 known exceptions, so its "bad" branch demonstrably fires |

A CI self-test gate runs before every search: `python -m colony.erdos699 selftest`. It requires the known strict exceptions up to 3000, 0 main counterexamples up to 10^6, and agreement between fast and full brute up to 3000. If any of those fail, the target freezes.

## Runs (GitHub Actions, `.github/workflows/erdos-699.yml`, free ubuntu-latest, 4 vCPU each)

| Run | Range | Shards | Wall time | Result |
|---|---|---|---|---|
| 38944843509 | 10^7 to 10^8 | 18 | about 3 min | search succeeded, but a workflow bug meant nothing was recorded. Fixed in a740417. |
| 38945552262 | 10^7+1 to 10^8 | 18 | 3.3 min | 0 main, 0 strict; 2,975 CPU-seconds |
| 38946059972 | 4 to 10^7, and 10^8+1 to 10^9 | 20 | 13.4 min | 0 main; only the 9 known strict exceptions (all ≤ 10^7) |

Per-shard records are in `society/systems/erdos699/ranges/*.json`, and the merged result is in `society/systems/erdos699/status.json`.

**Cost:** about 3,300 CPU-seconds per 10^8 near 10^8, rising to about 5,000 to 6,000 CPU-seconds per 10^8 near 10^9. That is about 1.5 core-hours per 10^8, or about 10 to 12 minutes of wall time per 10^8 on one 4-core runner.

## Reproduce

```bash
gcc -O2 -o fast699  society/benchmarks/frontier/erdos699/fast699.c -lm
gcc -O2 -o brute699 society/benchmarks/frontier/erdos699/brute699.c
./fast699 4 3000                    # prints the 8 known strict exceptions, then SUMMARY ... main=0
./brute699 full 4 3000              # same lines, computed with no reduction
./fast699 999000000 1000000000      # about 40 s on one core
PYTHONPATH=. python -m colony.erdos699 selftest
gh workflow run erdos-699.yml -f lo=4 -f hi=1000000000 -f shards=20 -f budget_min=300   # only checks gaps that are not yet recorded
```

## Caveats

- Above 10^8, coverage rests on fast699. The independent checker only sampled that range (random blocks), because a brute check of every pair is infeasible there.
- The reduction in step 1 is a short elementary argument, but it is the one mathematical ingredient both checkers share. Only `brute699 full` (n ≤ 20,000) avoids it.
- Any counterexample would be re-checked by brute699 and written to `review.jsonl` for human review. None occurred.
- The code was written by an AI agent (Grok Bot) under James Jackson's direction. If this is posted to the erdosproblems.com forum, its AI-disclosure policy applies.
