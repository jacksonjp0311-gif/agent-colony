# A104062 a(12) — pre-registered prediction (committed before any counting)

**a(12)** = number of consecutive prime quadruples (p, p+6, p+12, p+18) fully inside the first 2·10^13 primes
(last prime ≤ p(2·10^13) ≈ 6.62·10^14). Not counted yet.

- Prediction file: [`a12_predictions.json`](a12_predictions.json), written 2026-10-16 19:14:04 ET (-04:00),
  copied unchanged (sha256 `6ae7cd171775a86b05fe42e2404da4dca25f637fb9558bda6188b68499212396`).
- Headline reference: Hardy–Littlewood integral (consecutive, inclusion–exclusion) **3,945,984,674 ± ~125k**
  (2σ range 3,945,859,040 – 3,946,110,308).
- Honest caveat recorded in the file itself: no fitted correction model "survived" the leave-one-out checks
  (`survivors` is empty); the HL integral is listed as a reference, not a winner. HL is a conjecture.

**Rules for the count (gates unchanged).** a(12) needs two independent counts that agree exactly
(`a104062-shards.yml` passes A and B use different programs and different shard boundaries; the colony's
sieve instrument may recount sub-ranges). The result is a review candidate, never auto-claimed; Oracle,
0.70 gate, charter, TributeKeeper and Ceiling untouched. Computed, not proof.
