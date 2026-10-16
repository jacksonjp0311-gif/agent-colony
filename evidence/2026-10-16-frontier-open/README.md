# Open frontier targets past published records — 2026-10-16

**Mechanism.** A new frontier family, `prime_run_count`, counts OEIS "prime-run" terms incrementally.
The colony works one segmented-sieve window per cycle with a carried prime index and count, and records a
term whenever the prime index crosses a threshold. Each window is checked three ways:
- a Miller-Rabin sub-window recount, which must equal the sieve count;
- every published term, which must be reproduced exactly (any mismatch freezes the target for review);
- the prime at each new threshold, re-checked by Miller-Rabin.

The Challenger also gets a block-only sieve-vs-MR probe for this family. A term past the published record is
recorded only as `new_term_review` (CANDIDATE). It is never claimed, and it needs human re-computation before any OEIS
submission. Targets marked `beyond_record` are scheduled first. The label stays "bounded evidence, not proof".
The Oracle, the 0.70 gate and the scoring tiers are untouched; frontier evidence is still never scored.

**Target added: `oeis_A104062_next`.** A104062 counts primes p(i), i ≤ 20·10^n, whose next three consecutive
primes are p+6, p+12, p+18.
- Published record: a(1)…a(6) = 1, 12, 64, 416, 2748, 19348, i.e. the first 2·10^7 primes (p ≤ 373,587,883).
  Source: https://oeis.org/A104062 (keyword "more"; b-file synthesized from the entry; last edited
  2024-11-03; checked 2026-10-16).
- Colony work: recompute a(1..6), then a(7) (first 2·10^8 primes, p up to ≈ 4.22·10^9).
- **Update (same day, commit a8c2cd7):** a numpy sieve and multi-window "Frontier burst" runs replaced the planned
  one-window-per-cycle schedule (originally estimated at ~12 days). One burst run finished the search:
  **a(7) = 138994**, see [`../2026-10-16-a104062-a7/`](../2026-10-16-a104062-a7/README.md).
- A local dry run of the first 3 windows reproduced a(1)…a(5) exactly, with no mismatch.

**Searched and rejected as not cheap.** Ranges past the published limits for the existing classical targets are
not reachable cheaply: Goldbach 4·10^18, Collatz ≈ 2^71, Erdős–Straus 10^17, twin-prime counts to 10^18.
The same goes for other OEIS "more" sequences reviewed (e.g. A140331, A215050, A360324, A239790, A393910), whose
next term needs 10^10+ work or huge-number primality tests. Only one genuinely cheap open target was found.
