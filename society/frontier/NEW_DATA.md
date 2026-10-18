# New data ledger (colony.new_data)

Every term here was computed past the OEIS b-file of its entry and recomputed by an independent second method; both agree. "Beyond published frontier" means beyond the OEIS b-file on the date checked; papers or external tables may go further. This is new data, not a theorem.

| OEIS | name | index range | first new term | last new term | methods (A / B) | frontier source | checked | CPU s | how sure it is unpublished |
|---|---|---|---|---|---|---|---|---|---|
| A002375 | From Goldbach conjecture: number of decompositions of 2n into an unord | 20001..21000 | a(20001) = 593 | a(21000) = 984 | numpy FFT convolution of the prime indicator (floating point, rounded) / direct integer enumeration over an independent odd-only sieve | https://oeis.org/A002375/b002375.txt (k <= 20000) | 2026-10-18T12:22:31Z | 0.642 | beyond the OEIS b-file and every table linked from the entry on the date checked; other sources (papers, personal sites) not checked; easy extension (under 5 CPU-seconds): the b-file is short, not the edge of what is known, so these values are very likely computed elsewhere |

Full values: `society/frontier/data/<A-number>_beyond.txt` (b-file format).

## Targets the colony identified

| OEIS | menu item | published frontier (b-file k max) | status | tries | new terms | CPU s |
|---|---|---|---|---|---|---|
| A002375 | gb_u_odd:terms | 20000 | computed beyond published frontier (verified 2 ways) | 1 | 1000 | 0.642 |
