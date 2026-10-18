# New data ledger (colony.new_data)

Every term here was computed past the OEIS b-file of its entry and recomputed by an independent second method; both agree. "Beyond published frontier" means beyond the OEIS b-file on the date checked; papers or external tables may go further. This is new data, not a theorem.

| OEIS | name | index range | first new term | last new term | methods (A / B) | frontier source | checked | CPU s | how sure it is unpublished |
|---|---|---|---|---|---|---|---|---|---|
| A002375 | From Goldbach conjecture: number of decompositions of 2n into an unord | 20001..21000 | a(20001) = 593 | a(21000) = 984 | numpy FFT convolution of the prime indicator (floating point, rounded) / direct integer enumeration over an independent odd-only sieve | https://oeis.org/A002375/b002375.txt (k <= 20000) | 2026-10-18T12:22:31Z | 0.642 | beyond the OEIS b-file and every table linked from the entry on the date checked; other sources (papers, personal sites) not checked; easy extension (under 5 CPU-seconds): the b-file is short, not the edge of what is known, so these values are very likely computed elsewhere |
| A006577 | Number of halving and tripling steps to reach 1 in '3x+1' problem, or  | 10001..11000 | a(10001) = 179 | a(11000) = 42 | memoized iteration (stops at the first smaller value) / naive bit-level iteration with the (3x+1)/2 shortcut | https://oeis.org/A006577/b006577.txt (k <= 10000) | 2026-10-18T12:57:24Z | 0.039 | beyond the OEIS b-file and every table linked from the entry on the date checked; other sources (papers, personal sites) not checked; easy extension (under 5 CPU-seconds): the b-file is short, not the edge of what is known, so these values are very likely computed elsewhere |
| A006667 | Number of tripling steps to reach 1 from n in '3x+1' problem, or -1 if | 10001..11000 | a(10001) = 64 | a(11000) = 11 | memoized iteration (stops at the first smaller value) / naive bit-level iteration with the (3x+1)/2 shortcut | https://oeis.org/A006667/b006667.txt (k <= 10000) | 2026-10-18T12:58:56Z | 0.039 | beyond the OEIS b-file and every table linked from the entry on the date checked; other sources (papers, personal sites) not checked; easy extension (under 5 CPU-seconds): the b-file is short, not the edge of what is known, so these values are very likely computed elsewhere |
| A035026 | Number of times that i and 2n-i are both prime, for i = 1, ..., 2n-1. | 10001..11000 | a(10001) = 352 | a(11000) = 544 | numpy FFT convolution of the prime indicator (floating point, rounded) / direct integer enumeration over an independent odd-only sieve | https://oeis.org/A035026/b035026.txt (k <= 10000) | 2026-10-18T12:50:00Z | 0.376 | beyond the OEIS b-file and every table linked from the entry on the date checked; other sources (papers, personal sites) not checked; easy extension (under 5 CPU-seconds): the b-file is short, not the edge of what is known, so these values are very likely computed elsewhere |
| A047160 | For n >= 2, a(n) = smallest number m >= 0 such that n-m and n+m are bo | 10001..11000 | a(10001) = 60 | a(11000) = 27 | sieve scan downward from n / Miller-Rabin scan outward from n | https://oeis.org/A047160/b047160.txt (k <= 10000) | 2026-10-18T12:55:48Z | 0.091 | beyond the OEIS b-file and every table linked from the entry on the date checked; other sources (papers, personal sites) not checked; easy extension (under 5 CPU-seconds): the b-file is short, not the edge of what is known, so these values are very likely computed elsewhere |

Full values: `society/frontier/data/<A-number>_beyond.txt` (b-file format).

## Targets the colony identified

| OEIS | menu item | published frontier (b-file k max) | status | tries | new terms | CPU s |
|---|---|---|---|---|---|---|
| A002375 | gb_u_odd:terms | 20000 | computed beyond published frontier (verified 2 ways) | 1 | 1000 | 0.642 |
| A006577 | col_steps:terms | 10000 | computed beyond published frontier (verified 2 ways) | 1 | 1000 | 0.039 |
| A006667 | col_odd:terms | 10000 | computed beyond published frontier (verified 2 ways) | 1 | 1000 | 0.039 |
| A006877 | col_steps:recpos | 148 | published records reach n ~ 14727207461063895712; beyond the CPU budget | 1 | 0 | 0.0 |
| A006878 | col_steps:recval | 148 | matches published | 1 | 0 | 0.387 |
| A033958 | col_odd:recpos | 71 | published records reach n ~ 166763117680; beyond the CPU budget | 1 | 0 | 0.0 |
| A033959 | col_odd:recval | 57 | matches published | 1 | 0 | 0.385 |
| A035026 | gb_o_all:terms | 10000 | computed beyond published frontier (verified 2 ways) | 1 | 1000 | 0.376 |
| A047160 | gb_close:terms | 10000 | computed beyond published frontier (verified 2 ways) | 1 | 1000 | 0.091 |
| A053033 | gb_u_all:recpos | 266 | published records reach n ~ 9699691; beyond the CPU budget | 1 | 0 | 0.0 |
| A155764 | gb_close:recval | 64 | matches published | 1 | 0 | 0.611 |
| A155765 | gb_close:recpos | 61 | published records reach n ~ 2117398595; beyond the CPU budget | 1 | 0 | 0.0 |
