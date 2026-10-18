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
