# Proposal shortlist — 2026-10-18 07:14 AM ET

View only: nothing here is authorized. Only James authorizes.

11 of 58 proposals meet the authorize bar (11 after grouping near-duplicates; 2 colony-authored, 9 building blocks). Rank = 0.6*P + 0.2*novelty + 0.2*builds_on.

| # | Proposal | P | Novelty | Builds on | Athanor | Similar | Shadow # (P) | What it is |
|---|---|---:|---:|---:|---|---:|---|---|
| 1 | imp_15e6c5_50 | 0.825 | 1.0 | 1.0 | APPROVE | 1 | 2 (0.825) | Enable `authored_euler_theorem__gauss_phi_divisor_sum_w1` (Oracle passed it in its own cycle); builds on euler_theorem, gauss_phi_divisor_sum; P 0.825, novelty 1.0. |
| 2 | imp_bc7717_50 | 0.825 | 1.0 | 0.0 | APPROVE | 1 | 4 (0.825) | Enable `authored_frontier_le_xdbff107c_w1` (Oracle passed it in its own cycle); builds on frontier:frontier_holds; P 0.825, novelty 1.0. |

## Building blocks enabled (9 groups meet the bar)

Textbook / classical lemmas (desk catalog incl. the 68954ec refill, or a classical identity). They meet the bar but are not novel: novelty counts as 0 for ranking and they are kept out of the top list above.

| # | Proposal | P | Kind | Athanor | Similar | Shadow # (P) | What it is |
|---|---|---:|---|---|---:|---|---|
| 1 | imp_e8a630_50 | 0.8768 | catalog_refill | APPROVE | 1 | 5 (0.7518) | Building block `cayley_hamilton_3x3` (catalog refill; textbook, not novel) — Oracle passed it in its own cycle; P 0.8768. |
| 2 | imp_dfaa7b_50 | 0.8766 | catalog_refill | APPROVE | 1 | 6 (0.7516) | Building block `polynomial_remainder` (catalog refill; textbook, not novel) — Oracle passed it in its own cycle; P 0.8766. |
| 3 | imp_2eb8c7_50 | 0.876 | catalog_refill | APPROVE | 1 | 7 (0.751) | Building block `abel_summation` (catalog refill; textbook, not novel) — Oracle passed it in its own cycle; P 0.876. |
| 4 | imp_fa5f3d_50 | 0.8754 | catalog_refill | APPROVE | 1 | 1 (0.8754) | Building block `faulhaber_power_sums` (catalog refill; textbook, not novel) — Oracle passed it in its own cycle; P 0.8754. |
| 5 | imp_0bada5_50 | 0.825 | catalog_refill | APPROVE | 1 | 8 (0.7) | Building block `newton_identities` (catalog refill; textbook, not novel) — Oracle passed it in its own cycle; P 0.825. |
| 6 | imp_1a4ec1_50 | 0.825 | catalog_refill | APPROVE | 1 | 9 (0.7) | Building block `telescoping_sum` (catalog refill; textbook, not novel) — Oracle passed it in its own cycle; P 0.825. |
| 7 | imp_3a02ab_50 | 0.825 | catalog_refill | APPROVE | 1 | 10 (0.7) | Building block `burnside_necklaces` (catalog refill; textbook, not novel) — Oracle passed it in its own cycle; P 0.825. |
| 8 | imp_bb0db0_50 | 0.825 | catalog_refill | APPROVE | 1 | 11 (0.7) | Building block `cayley_hamilton_2x2` (catalog refill; textbook, not novel) — Oracle passed it in its own cycle; P 0.825. |
| 9 | imp_f7b051_50 | 0.825 | catalog_refill | APPROVE | 1 | 3 (0.825) | Building block `lagrange_cyclic_orders` (catalog refill; textbook, not novel) — Oracle passed it in its own cycle; P 0.825. |

## Hunt shadow (view only — would-be ranking if the unknown were rewarded)

Rules in colony/hunt_shadow.py. Would meet the bar: 11 (actual 11). Unknown claims (Oracle-surviving, not textbook, not in OEIS): 4 (0 with OEIS unchecked). Would drop out of the bar: 0; would enter: 0.

| Shadow # | Proposal | Target | P → P_shadow | Shadow bar | Unknown | Expected | Actual # |
|---:|---|---|---|---|---|---:|---:|
| 1 | imp_fa5f3d_50 | `faulhaber_power_sums` | 0.8754 → 0.8754 | meets | no | 0.0 | 6 |
| 2 | imp_15e6c5_50 | `authored_euler_theorem__gauss_phi_divisor_sum_w1` | 0.825 → 0.825 | meets | yes | 0.0 | 1 |
| 3 | imp_f7b051_50 | `lagrange_cyclic_orders` | 0.825 → 0.825 | meets | no | 0.0 | 11 |
| 4 | imp_bc7717_50 | `authored_frontier_le_xdbff107c_w1` | 0.825 → 0.825 | meets | yes | 0.0 | 2 |
| 5 | imp_e8a630_50 | `cayley_hamilton_3x3` | 0.8768 → 0.7518 | meets | no | 0.0 | 3 |
| 6 | imp_dfaa7b_50 | `polynomial_remainder` | 0.8766 → 0.7516 | meets | no | 0.0 | 4 |
| 7 | imp_2eb8c7_50 | `abel_summation` | 0.876 → 0.751 | meets | no | 0.0 | 5 |
| 8 | imp_0bada5_50 | `newton_identities` | 0.825 → 0.7 | meets | no | 0.0 | 7 |
| 9 | imp_1a4ec1_50 | `telescoping_sum` | 0.825 → 0.7 | meets | no | 0.0 | 8 |
| 10 | imp_3a02ab_50 | `burnside_necklaces` | 0.825 → 0.7 | meets | no | 0.0 | 9 |

Excluded (reason: count): hearing: 2, no_oracle_pass_in_own_cycle: 11, novelty_killed: 8, status: 41, target_unresolved: 34, trivial_by_filter: 2


## Frontier conjectures (self-chosen; LIVE)

Mode `live`. Last cycle: 12 tested, 2 survived held-out, 10 falsified, 0 machine-checked, 1 surprises; dropped 85 duplicates, 65 trivial rewrites. OEIS index: available. Pre-registration Brier: 0.1883.
Totals: tested 450, survived 204, surprises 26, false surprises (failed later re-test) 0.

| Statement | Label | OEIS | Hunt v |
|---|---|---|---|
| D((digsum+lpf))(n) = 0 (mod 2) for all n = 0 (mod 2) | conjecture surviving 29994 checks | not_found | 1.0 |
| D((sigma*sqfree))(n) = 0 (mod 2) for all n = 1 (mod 2) | conjecture surviving 29994 checks | not_found | 1.0 |
| D(gcd(phi,pi))(n) = 0 (mod 2) for all n = 1 (mod 2) | conjecture surviving 29994 checks | not_found | 1.0 |
| S((lpf*phi))(n) = 1 (mod 2) for all n >= 1 | conjecture surviving 59988 checks | not_found | 1.0 |
| S((part*phi))(n) = 1 (mod 2) for all n >= 1 | conjecture surviving 3988 checks | not_found | 1.0 |
| S((phi*rad))(n) = 1 (mod 2) for all n >= 1 | conjecture surviving 59988 checks | not_found | 1.0 |
| S((pi*pi))(n) = 1 (mod 2) for all n = 0 (mod 2) | conjecture surviving 29994 checks | not_found | 1.0 |
| S(gcd(digsum,phi))(n) = 1 (mod 2) for all n = 3 (mod 4) | conjecture surviving 4997 checks | not_found | 1.0 |
| D(pell)(n) = 1 (mod 2) for all n >= 1 | machine-checked (certificate) | found | 0.0 |
| D(pell)(n) = 1 (mod 2) for all n = 0 (mod 2) | machine-checked (certificate) | found | 0.0 |
| dbl(fib)(n) = 0 (mod 3) for all n = 0 (mod 2) | machine-checked (certificate) | found | 0.0 |
| dbl(n)(n) = 0 (mod 2) for all n >= 1 | machine-checked (certificate) | found | 0.0 |
