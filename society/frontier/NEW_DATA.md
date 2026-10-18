# New data ledger (colony.new_data)

Every term here was computed past the OEIS b-file of its entry and recomputed by an independent second method; both agree. "Beyond published frontier" means beyond the OEIS b-file on the date checked; papers or external tables may go further. This is new data, not a theorem.

| OEIS | name | index range | first new term | last new term | methods (A / B) | frontier source | checked | CPU s | how sure it is unpublished |
|---|---|---|---|---|---|---|---|---|---|
| A002375 | From Goldbach conjecture: number of decompositions of 2n into an unord | 20001..21000 | a(20001) = 593 | a(21000) = 984 | numpy FFT convolution of the prime indicator (floating point, rounded) / direct integer enumeration over an independent odd-only sieve | https://oeis.org/A002375/b002375.txt (k <= 20000) | 2026-10-18T12:22:31Z | 0.642 | beyond the OEIS b-file and every table linked from the entry on the date checked; other sources (papers, personal sites) not checked; easy extension (under 5 CPU-seconds): the b-file is short, not the edge of what is known, so these values are very likely computed elsewhere |
| A006577 | Number of halving and tripling steps to reach 1 in '3x+1' problem, or  | 10001..11000 | a(10001) = 179 | a(11000) = 42 | memoized iteration (stops at the first smaller value) / naive bit-level iteration with the (3x+1)/2 shortcut | https://oeis.org/A006577/b006577.txt (k <= 10000) | 2026-10-18T12:57:24Z | 0.039 | beyond the OEIS b-file and every table linked from the entry on the date checked; other sources (papers, personal sites) not checked; easy extension (under 5 CPU-seconds): the b-file is short, not the edge of what is known, so these values are very likely computed elsewhere |
| A006666 | Number of halving steps to reach 1 in '3x+1' problem, or -1 if this ne | 10001..11000 | a(10001) = 115 | a(11000) = 31 | memoized iteration (stops at the first smaller value) / naive bit-level iteration with the (3x+1)/2 shortcut | https://oeis.org/A006666/b006666.txt (k <= 10000) | 2026-10-18T13:02:20Z | 0.02 | beyond the OEIS b-file and every table linked from the entry on the date checked; other sources (papers, personal sites) not checked; easy extension (under 5 CPU-seconds): the b-file is short, not the edge of what is known, so these values are very likely computed elsewhere |
| A006667 | Number of tripling steps to reach 1 from n in '3x+1' problem, or -1 if | 10001..11000 | a(10001) = 64 | a(11000) = 11 | memoized iteration (stops at the first smaller value) / naive bit-level iteration with the (3x+1)/2 shortcut | https://oeis.org/A006667/b006667.txt (k <= 10000) | 2026-10-18T12:58:56Z | 0.039 | beyond the OEIS b-file and every table linked from the entry on the date checked; other sources (papers, personal sites) not checked; easy extension (under 5 CPU-seconds): the b-file is short, not the edge of what is known, so these values are very likely computed elsewhere |
| A025586 | Largest value in '3x+1' trajectory of n. | 10001..11000 | a(10001) = 250504 | a(11000) = 20896 | memoized iteration (stops at the first smaller value) / naive bit-level iteration with the (3x+1)/2 shortcut | https://oeis.org/A025586/b025586.txt (k <= 10000) | 2026-10-18T13:03:33Z | 0.02 | beyond the OEIS b-file and every table linked from the entry on the date checked; other sources (papers, personal sites) not checked; easy extension (under 5 CPU-seconds): the b-file is short, not the edge of what is known, so these values are very likely computed elsewhere |
| A035026 | Number of times that i and 2n-i are both prime, for i = 1, ..., 2n-1. | 10001..11000 | a(10001) = 352 | a(11000) = 544 | numpy FFT convolution of the prime indicator (floating point, rounded) / direct integer enumeration over an independent odd-only sieve | https://oeis.org/A035026/b035026.txt (k <= 10000) | 2026-10-18T12:50:00Z | 0.376 | beyond the OEIS b-file and every table linked from the entry on the date checked; other sources (papers, personal sites) not checked; easy extension (under 5 CPU-seconds): the b-file is short, not the edge of what is known, so these values are very likely computed elsewhere |
| A047160 | For n >= 2, a(n) = smallest number m >= 0 such that n-m and n+m are bo | 10001..11000 | a(10001) = 60 | a(11000) = 27 | sieve scan downward from n / Miller-Rabin scan outward from n | https://oeis.org/A047160/b047160.txt (k <= 10000) | 2026-10-18T12:55:48Z | 0.091 | beyond the OEIS b-file and every table linked from the entry on the date checked; other sources (papers, personal sites) not checked; easy extension (under 5 CPU-seconds): the b-file is short, not the edge of what is known, so these values are very likely computed elsewhere |
| A102419 | "Dropping time" in 3x+1 problem starting at n (number of steps to reac | 10001..11000 | a(10001) = 3 | a(11000) = 1 | memoized iteration (stops at the first smaller value) / naive bit-level iteration with the (3x+1)/2 shortcut | https://oeis.org/A102419/b102419.txt (k <= 10000) | 2026-10-18T13:04:41Z | 0.02 | beyond the OEIS b-file and every table linked from the entry on the date checked; other sources (papers, personal sites) not checked; easy extension (under 5 CPU-seconds): the b-file is short, not the edge of what is known, so these values are very likely computed elsewhere |

## Sparse entries (Stage 1b: OEIS keyword more/hard, short published frontier)

Found by OEIS search; identified by recomputing every published term; method B rescans the whole range. These are the claims that could be genuinely new data.

| OEIS | name | keywords | published terms | new terms | first new | last new | item:op | scanned to k | methods (A / B) | frontier source | checked | how sure it is unpublished |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (none yet) | | | | | | | | | | | | |

### Sparse targets the colony identified

| OEIS | name | published terms | matched as | status | scanned to k | tries | new terms | CPU s |
|---|---|---|---|---|---|---|---|---|
| A091592 | Numbers n such that there are no twin primes between n^2 and (n+1)^2. | 12 | pat_twin_sq_all:zeros (shift 0) | engine cap k = 5000 reached (cycle budget) | 5000 | 3 | 0 | 0.206 |
| A228014 | Numbers k whose Collatz sequence length is greater than k+1 (counting both the x | 28 | col_steps:fgtk (shift 0) | engine cap k = 1000000 reached (cycle budget) | 1000000 | 6 | 0 | 1.43 |
| A352229 | Numbers that can be expressed as the sum of two primes in exactly 7 ways. | 18 | gb_prime_m:eq7 (shift 0) | engine cap k = 1000000 reached (cycle budget) | 1000000 | 6 | 0 | 0.181 |
| A352230 | Numbers that can be expressed as the sum of two primes in exactly 8 ways. | 20 | gb_prime_m:eq8 (shift 0) | engine cap k = 1000000 reached (cycle budget) | 1000000 | 6 | 0 | 0.175 |
| A352231 | Numbers that can be expressed as the sum of two primes in exactly 9 ways. | 23 | gb_prime_m:eq9 (shift 0) | engine cap k = 1000000 reached (cycle budget) | 1000000 | 6 | 0 | 0.175 |
| A352233 | Numbers that can be expressed as the sum of two primes in exactly 10 ways. | 16 | gb_prime_m:eq10 (shift 0) | engine cap k = 1000000 reached (cycle budget) | 1000000 | 6 | 0 | 0.214 |

Full values: `society/frontier/data/<A-number>_beyond.txt` (b-file format).

## Targets the colony identified

| OEIS | menu item | published frontier (b-file k max) | status | tries | new terms | CPU s |
|---|---|---|---|---|---|---|
| A002375 | gb_u_odd:terms | 20000 | computed beyond published frontier (verified 2 ways) | 1 | 1000 | 0.642 |
| A006577 | col_steps:terms | 10000 | computed beyond published frontier (verified 2 ways) | 1 | 1000 | 0.039 |
| A006666 | col_even:terms | 10000 | computed beyond published frontier (verified 2 ways) | 1 | 1000 | 0.02 |
| A006667 | col_odd:terms | 10000 | computed beyond published frontier (verified 2 ways) | 1 | 1000 | 0.039 |
| A006877 | col_steps:recpos | 148 | published records reach n ~ 14727207461063895712; beyond the CPU budget | 1 | 0 | 0.0 |
| A006878 | col_steps:recval | 148 | matches published | 1 | 0 | 0.387 |
| A006884 | col_max:recpos | 98 | published records reach n ~ 2358909599867980429760; beyond the CPU budget | 1 | 0 | 0.0 |
| A006885 | col_max:recval | 97 | matches published | 1 | 0 | 0.187 |
| A025586 | col_max:terms | 10000 | computed beyond published frontier (verified 2 ways) | 1 | 1000 | 0.02 |
| A033958 | col_odd:recpos | 71 | published records reach n ~ 166763117680; beyond the CPU budget | 1 | 0 | 0.0 |
| A033959 | col_odd:recval | 57 | matches published | 1 | 0 | 0.385 |
| A035026 | gb_o_all:terms | 10000 | computed beyond published frontier (verified 2 ways) | 1 | 1000 | 0.376 |
| A047160 | gb_close:terms | 10000 | computed beyond published frontier (verified 2 ways) | 1 | 1000 | 0.091 |
| A053033 | gb_u_all:recpos | 266 | published records reach n ~ 9699691; beyond the CPU budget | 1 | 0 | 0.0 |
| A102419 | col_stop:terms | 10000 | computed beyond published frontier (verified 2 ways) | 1 | 1000 | 0.02 |
| A155764 | gb_close:recval | 64 | matches published | 1 | 0 | 0.611 |
| A155765 | gb_close:recpos | 61 | published records reach n ~ 2117398595; beyond the CPU budget | 1 | 0 | 0.0 |
