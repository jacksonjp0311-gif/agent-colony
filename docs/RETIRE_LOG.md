# Retire log

Rule-based retirement of low-value authored checks (`colony/retire.py`, flag `COLONY_RETIRE`).
Retired checks are archived with full source in `society/systems/retired_checks.json`; restore with
`python -m colony.retire restore NAME` (comes back disabled, must pass the Oracle again) or git revert.

## Report-only run on main (2026-10-18T02:41:34Z)

11 of 150 authored checks would be retired: {'sweep': 8, 'textbook_pair': 2, 'trivial_frontier': 1}.

- `authored_sieve_hl_within_g6_2_w1` [sweep] — near-duplicate parameter sweep of proven family `authored_sieve_hl_within`: 17 other Oracle-passed members, expected = s/(s+K) = 0.994 >= 0.95 (K=0.10921); 17 members stay
- `authored_sieve_residue_bal_g2_4_2_w1` [sweep] — near-duplicate parameter sweep of proven family `authored_sieve_residue_bal`: 17 other Oracle-passed members, expected = s/(s+K) = 0.994 >= 0.95 (K=0.10921); 17 members stay
- `authored_sieve_residue_bal_g4_2_w1` [sweep] — near-duplicate parameter sweep of proven family `authored_sieve_residue_bal`: 16 other Oracle-passed members, expected = s/(s+K) = 0.993 >= 0.95 (K=0.10921); 16 members stay
- `authored_sieve_residue_bal_g2_6_w1` [sweep] — near-duplicate parameter sweep of proven family `authored_sieve_residue_bal`: 15 other Oracle-passed members, expected = s/(s+K) = 0.993 >= 0.95 (K=0.10921); 15 members stay
- `authored_sieve_two_counter_g4_2_4_w1` [sweep] — near-duplicate parameter sweep of proven family `authored_sieve_two_counter`: 17 other Oracle-passed members, expected = s/(s+K) = 0.994 >= 0.95 (K=0.10921); 17 members stay
- `authored_sieve_two_counter_g6_6_w1` [sweep] — near-duplicate parameter sweep of proven family `authored_sieve_two_counter`: 16 other Oracle-passed members, expected = s/(s+K) = 0.993 >= 0.95 (K=0.10921); 16 members stay
- `authored_sieve_two_counter_g6_4_w1` [sweep] — near-duplicate parameter sweep of proven family `authored_sieve_two_counter`: 15 other Oracle-passed members, expected = s/(s+K) = 0.993 >= 0.95 (K=0.10921); 15 members stay
- `authored_sieve_two_counter_g2_4_w1` [sweep] — near-duplicate parameter sweep of proven family `authored_sieve_two_counter`: 14 other Oracle-passed members, expected = s/(s+K) = 0.992 >= 0.95 (K=0.10921); 14 members stay
- `authored_pascal_identity__vandermonde_conv_w1` [textbook_pair] — plain pairing of textbook lemmas pascal_identity + vandermonde_conv on separate windows: the claim is implied by its two parts
- `authored_sum_first_n_odds__binomial_inversion_small_w1` [textbook_pair] — plain pairing of textbook lemmas sum_first_n_odds + binomial_inversion_small on separate windows: the claim is implied by its two parts
- `authored_frontier_le_x46c5cc8a_w1` [trivial_frontier] — the current triviality filter flags this frontier claim as a rewrite

Protected:
- on a receipt (authorized / decided): 110
- a proposal meeting the bar depends on it: 26
- named in colony/ or tests/ code: 3

## Applied (Oct 17, 2026 ~10:45 PM ET, `COLONY_RETIRE=live`, one run)

The 11 checks above were retired and archived (full source + catalog entry + reason) in
`society/systems/retired_checks.json`. The bench check inside `apply` re-ran every remaining check first (all pass).

Sanity check (local, 3 runs each, `society/benchmarks/run_benchmarks`):

| | before | after |
|---|---|---|
| lemma bench score | 0.8629 / 0.8631 / 0.8632 | 0.8645 / 0.8648 / 0.8649 |
| hard checks passing | 213 / 213 | 202 / 202 |
| lemma bench seconds | 1.25 to 1.31 | 0.96 to 1.02 |
| aggregate (noisy fft_stress timing) | 0.8968 to 0.9016 | 0.8813 to 0.9021 |
| ok_all | true | true |

The lemma score does not drop because the hard component is capped (HARD_DENOM = 28 << 202) and fewer checks run faster.
`fitness.hard_tier_delta` adds retired checks back, so retirement is not read as a hard-tier regression.

## Rule change (Oct 18, 2026, 1:48 AM ET approval): bar protection covers building blocks only

Report-only run on main (02:01 AM ET):

27 of 145 authored checks would be retired: {'sweep': 11, 'textbook_pair': 12, 'trivial_frontier': 4}. 115 protected.

- `authored_sieve_hl_within_g6_6_6_w1` [sweep] — near-duplicate parameter sweep of proven family `authored_sieve_hl_within`: 14 other Oracle-passed members, expected = s/(s+K) = 0.992 >= 0.95 (K=0.10921); 14 members stay
- `authored_sieve_hl_within_g6_2_6_w1` [sweep] — near-duplicate parameter sweep of proven family `authored_sieve_hl_within`: 13 other Oracle-passed members, expected = s/(s+K) = 0.992 >= 0.95 (K=0.10921); 13 members stay
- `authored_sieve_hl_within_g6_2_4_w1` [sweep] — near-duplicate parameter sweep of proven family `authored_sieve_hl_within`: 12 other Oracle-passed members, expected = s/(s+K) = 0.991 >= 0.95 (K=0.10921); 12 members stay
- `authored_sieve_residue_bal_g6_6_4_w1` [sweep] — near-duplicate parameter sweep of proven family `authored_sieve_residue_bal`: 13 other Oracle-passed members, expected = s/(s+K) = 0.992 >= 0.95 (K=0.10921); 13 members stay
- `authored_sieve_residue_bal_g6_6_2_w1` [sweep] — near-duplicate parameter sweep of proven family `authored_sieve_residue_bal`: 12 other Oracle-passed members, expected = s/(s+K) = 0.991 >= 0.95 (K=0.10921); 12 members stay
- `authored_sieve_residue_bal_g4_6_6_w1` [sweep] — near-duplicate parameter sweep of proven family `authored_sieve_residue_bal`: 11 other Oracle-passed members, expected = s/(s+K) = 0.990 >= 0.95 (K=0.10921); 11 members stay
- `authored_sieve_residue_bal_g4_6_2_w1` [sweep] — near-duplicate parameter sweep of proven family `authored_sieve_residue_bal`: 10 other Oracle-passed members, expected = s/(s+K) = 0.989 >= 0.95 (K=0.10921); 10 members stay
- `authored_sieve_two_counter_g4_2_w1` [sweep] — near-duplicate parameter sweep of proven family `authored_sieve_two_counter`: 13 other Oracle-passed members, expected = s/(s+K) = 0.992 >= 0.95 (K=0.10921); 13 members stay
- `authored_sieve_two_counter_g6_4_6_w1` [sweep] — near-duplicate parameter sweep of proven family `authored_sieve_two_counter`: 12 other Oracle-passed members, expected = s/(s+K) = 0.991 >= 0.95 (K=0.10921); 12 members stay
- `authored_sieve_two_counter_g6_4_2_w1` [sweep] — near-duplicate parameter sweep of proven family `authored_sieve_two_counter`: 11 other Oracle-passed members, expected = s/(s+K) = 0.990 >= 0.95 (K=0.10921); 11 members stay
- `authored_sieve_two_counter_g4_2_6_w1` [sweep] — near-duplicate parameter sweep of proven family `authored_sieve_two_counter`: 10 other Oracle-passed members, expected = s/(s+K) = 0.989 >= 0.95 (K=0.10921); 10 members stay
- `authored_abel_summation__faulhaber_power_sums_w1` [textbook_pair] — plain pairing of textbook lemmas abel_summation + faulhaber_power_sums on separate windows: the claim is implied by its two parts
- `authored_alternating_binomial_row__cayley_hamilton_2x2_w1` [textbook_pair] — plain pairing of textbook lemmas alternating_binomial_row + cayley_hamilton_2x2 on separate windows: the claim is implied by its two parts
- `authored_bell_stirling_sum__burnside_necklaces_w1` [textbook_pair] — plain pairing of textbook lemmas bell_stirling_sum + burnside_necklaces on separate windows: the claim is implied by its two parts
- `authored_bezout_identity__cayley_hamilton_3x3_w1` [textbook_pair] — plain pairing of textbook lemmas bezout_identity + cayley_hamilton_3x3 on separate windows: the claim is implied by its two parts
- `authored_cayley_tree_count__complete_bipartite_trees_w1` [textbook_pair] — plain pairing of textbook lemmas cayley_tree_count + complete_bipartite_trees on separate windows: the claim is implied by its two parts
- `authored_crt_coprime_pair__cycle_spanning_trees_w1` [textbook_pair] — plain pairing of textbook lemmas crt_coprime_pair + cycle_spanning_trees on separate windows: the claim is implied by its two parts
- `authored_euler_pentagonal__lagrange_cyclic_orders_w1` [textbook_pair] — plain pairing of textbook lemmas euler_pentagonal + lagrange_cyclic_orders on separate windows: the claim is implied by its two parts
- `authored_fermat_little__lucas_theorem_binomial_w1` [textbook_pair] — plain pairing of textbook lemmas fermat_little + lucas_theorem_binomial on separate windows: the claim is implied by its two parts
- `authored_mobius_divisor_sum__mobius_inversion_sigma_w1` [textbook_pair] — plain pairing of textbook lemmas mobius_divisor_sum + mobius_inversion_sigma on separate windows: the claim is implied by its two parts
- `authored_multinomial_three__newton_identities_w1` [textbook_pair] — plain pairing of textbook lemmas multinomial_three + newton_identities on separate windows: the claim is implied by its two parts
- `authored_odd_distinct_partitions__partition_conjugate_parts_w1` [textbook_pair] — plain pairing of textbook lemmas odd_distinct_partitions + partition_conjugate_parts on separate windows: the claim is implied by its two parts
- `authored_polynomial_remainder__telescoping_sum_w1` [textbook_pair] — plain pairing of textbook lemmas polynomial_remainder + telescoping_sum on separate windows: the claim is implied by its two parts
- `authored_frontier_le_x9abb4c98_w1` [trivial_frontier] — the current triviality filter flags this frontier claim as a rewrite
- `authored_frontier_cong_x16b72492_w1` [trivial_frontier] — the current triviality filter flags this frontier claim as a rewrite
- `authored_frontier_cong_x0058ae91_w1` [trivial_frontier] — the current triviality filter flags this frontier claim as a rewrite
- `authored_frontier_divides_x575aa435_w1` [trivial_frontier] — the current triviality filter flags this frontier claim as a rewrite

Protected (reason counts):
- on a receipt (authorized / decided): 112
- named in colony/ or tests/ code: 3

