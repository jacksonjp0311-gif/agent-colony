# Proposal shortlist — 2026-10-23 08:02 AM ET

View only: nothing here is authorized. Only James authorizes.

14 of 58 proposals meet the authorize bar (7 after grouping near-duplicates; 7 colony-authored, 0 building blocks). Rank = 0.6*P + 0.2*novelty + 0.2*builds_on.

| # | Proposal | P | Novelty | Builds on | Athanor | Similar | Shadow # (P) | What it is |
|---|---|---:|---:|---:|---|---:|---|---|
| 1 | imp_a201b5_50 | 0.8871 | 1.0 | 0.0 | APPROVE | 2 | 2 (0.6617, below bar) | Enable `authored_frontier_divides_x318ee14a_w2` (Oracle passed it in its own cycle); builds on frontier:frontier_holds; P 0.8871, novelty 1.0. |
| 2 | imp_70e921_50 | 0.8769 | 1.0 | 0.0 | APPROVE | 2 | 3 (0.6515, below bar) | Enable `authored_frontier_divides_xc90ee275_w2` (Oracle passed it in its own cycle); builds on frontier:frontier_holds; P 0.8769, novelty 1.0. |
| 3 | imp_db469b_50 | 0.8762 | 1.0 | 0.0 | APPROVE | 2 | 5 (0.6508, below bar) | Enable `authored_frontier_cong_xfdcb3b60_w2` (Oracle passed it in its own cycle); builds on frontier:frontier_holds; P 0.8762, novelty 1.0. |
| 4 | imp_15e790_50 | 0.8756 | 1.0 | 0.0 | APPROVE | 2 | 7 (0.6502, below bar) | Enable `authored_frontier_divides_xba575886_w1` (Oracle passed it in its own cycle); builds on frontier:frontier_holds; P 0.8756, novelty 1.0. |
| 5 | imp_df0e1a_50 | 0.8752 | 1.0 | 0.0 | APPROVE | 2 | 8 (0.6498, below bar) | Enable `authored_frontier_divides_x3562d07e_w1` (Oracle passed it in its own cycle); builds on frontier:frontier_holds; P 0.8752, novelty 1.0. |
| 6 | imp_dfb01f_50 | 0.8752 | 1.0 | 0.0 | APPROVE | 1 | 1 (0.8752) | Enable `authored_frontier_cong_xb19ab27c_w1` (Oracle passed it in its own cycle); builds on frontier:frontier_holds; P 0.8752, novelty 1.0. |
| 7 | imp_12c82c_50 | 0.825 | 1.0 | 0.0 | APPROVE | 3 | 12 (0.5879, below bar) | Enable `authored_frontier_le_x7a9213ec_w2` (Oracle passed it in its own cycle); builds on frontier:frontier_holds; P 0.825, novelty 1.0. |

## Building blocks enabled (0 groups meet the bar)

Textbook / classical lemmas (desk catalog incl. the 68954ec refill, or a classical identity). They meet the bar but are not novel: novelty counts as 0 for ranking and they are kept out of the top list above.

None this cycle.

## Hunt shadow (view only — would-be ranking if the unknown were rewarded)

Rules in colony/hunt_shadow.py. Would meet the bar: 1 (actual 14). Unknown claims (Oracle-surviving, not textbook, not in OEIS): 14 (0 with OEIS unchecked). Would drop out of the bar: 13; would enter: 0.

| Shadow # | Proposal | Target | P → P_shadow | Shadow bar | Unknown | Expected | Actual # |
|---:|---|---|---|---|---|---:|---:|
| 1 | imp_dfb01f_50 | `authored_frontier_cong_xb19ab27c_w1` | 0.8752 → 0.8752 | meets | yes | 0.0 | 8 |
| 2 | imp_a201b5_50 | `authored_frontier_divides_x318ee14a_w2` | 0.8871 → 0.6617 | below | yes | 0.9015 | 1 |
| 3 | imp_70e921_50 | `authored_frontier_divides_xc90ee275_w2` | 0.8769 → 0.6515 | below | yes | 0.9015 | 2 |
| 4 | imp_831fcd_50 | `authored_frontier_divides_xc90ee275_w1` | 0.8763 → 0.6509 | below | yes | 0.9015 | 3 |
| 5 | imp_db469b_50 | `authored_frontier_cong_xfdcb3b60_w2` | 0.8762 → 0.6508 | below | yes | 0.9015 | 4 |
| 6 | imp_e9a4c1_50 | `authored_frontier_divides_x318ee14a_w1` | 0.8759 → 0.6505 | below | yes | 0.9015 | 5 |
| 7 | imp_15e790_50 | `authored_frontier_divides_xba575886_w1` | 0.8756 → 0.6502 | below | yes | 0.9015 | 6 |
| 8 | imp_df0e1a_50 | `authored_frontier_divides_x3562d07e_w1` | 0.8752 → 0.6498 | below | yes | 0.9015 | 7 |
| 9 | imp_9e87d3_50 | `authored_frontier_divides_x3562d07e_w2` | 0.875 → 0.6496 | below | yes | 0.9015 | 9 |
| 10 | imp_ddc9ae_50 | `authored_frontier_cong_xfdcb3b60_w1` | 0.875 → 0.6496 | below | yes | 0.9015 | 10 |

Excluded (reason: count): hearing: 2, no_oracle_pass_in_own_cycle: 9, novelty_killed: 35, oracle_killed_in_own_cycle: 25, status: 17, target_unresolved: 9


## Frontier conjectures (self-chosen; LIVE)

Mode `live`. Last cycle: 18 tested, 8 survived held-out, 10 falsified, 1 machine-checked, 1 surprises; dropped 42 duplicates, 77 trivial rewrites. OEIS index: available. Pre-registration Brier: 0.1701.
Totals: tested 3364, survived 1637, surprises 77, false surprises (failed later re-test) 0.
Reference check (Stage 2, `live`): last cycle 1 explained by a reference, 3 with no reference found.

| Statement | Label | Reference check | OEIS | Hunt v |
|---|---|---|---|---|
| D((digsum*digsum))(n) = 1 (mod 2) for all n = 0 (mod 2) | machine-proved (certificate) |  | not_found | 1.0 |
| D((digsum+lpf))(n) = 0 (mod 2) for all n = 0 (mod 2) | machine-proved (certificate) |  | not_found | 1.0 |
| D((sigma*sqfree))(n) = 0 (mod 2) for all n = 1 (mod 2) | conjecture surviving 29994 checks |  | not_found | 1.0 |
| D(gcd(cheb4,phi))(n) = 0 (mod 2) for all n = 2 (mod 3) | machine-proved (certificate) |  | not_found | 1.0 |
| D(gcd(phi,pi))(n) = 0 (mod 2) for all n = 1 (mod 2) | machine-proved (certificate) |  | not_found | 1.0 |
| D(oxa070778)(n) = 0 (mod 5) for all n = 3 (mod 6) | machine-proved (certificate) | no reference found (checked: classical catalog) | not_found | 1.0 |
| D(oxa072850)(n) = 0 (mod 2) for all n = 0 (mod 7) | machine-proved (certificate) | no reference found (checked: classical catalog) | not_found | 1.0 |
| S((fib*oxa048760))(n) = 0 (mod 2) for all n = 0 (mod 3) | conjecture surviving 662 checks | no reference found (checked: classical catalog, A000045) | not_found | 1.0 |
| D((digsum*digsum))(n) = 1 (mod 2) for all n = 0 (mod 2) | machine-proved (certificate) |  | not_found | 1.0 |
| D((digsum+lpf))(n) = 0 (mod 2) for all n = 0 (mod 2) | machine-proved (certificate) |  | not_found | 1.0 |
| D(gcd(cheb4,phi))(n) = 0 (mod 2) for all n = 2 (mod 3) | machine-proved (certificate) |  | not_found | 1.0 |
| D(gcd(n,rad))(n) = 1 (mod 2) for all n = 0 (mod 2) | machine-proved (certificate) |  | found | 0.0 |
