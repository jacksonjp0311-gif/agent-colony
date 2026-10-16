# Success recipes — mechanism + predeclared measurement plan (2026-10-16)

**No gain is claimed here.** This note is written before any measurement.

## Mechanism (`colony/recipes.py`)
- After each frontier cycle/burst, `distill()` scans the catalog + `data/commons/frontier.jsonl` and
  writes a recipe to `data/commons/recipes.jsonl` only for targets that succeeded under **strong
  verification**: terminal success; every row a clean pass; Challenger ran and blocked nothing on every
  row; an independent re-check recorded on every row; every published term reproduced, none mismatched;
  label "bounded evidence, not proof", `proof=false`. All recipe fields are read from the recorded rows.
- One recipe per (type, ladder, features) signature, so repeated near-identical successes don't flood the ledger.
- `on_start()` (first time a target is worked) retrieves recipes by Jaccard overlap of structural
  features (`counting_over_primes_to_bound`, `falsifiable_search_over_n`, `known_terms_available`,
  `oeis_sequence`, `past_published_record`, `monotone_range_windows`, `family:*`), proposes a
  verification ladder + batching plan, logs a `recipe_use` row to `data/commons/recipe_uses.jsonl`.
  The only thing it applies automatically is a window-size hint for the same family when the target has
  none. It never removes or loosens a check; the Oracle and the 0.70 gate are untouched.
- `on_result()` logs a `recipe_outcome` row at first verification or first disagreement:
  time-to-first-verified (s), windows-to-first-verified, disagreements, self-rejects. `helped` is left
  `null`. Only the comparison below decides it.
- Test `test_planted_fake_success_without_verification_is_not_a_recipe`: a fake "done" success with no
  Challenger, no independent check and unreproduced published terms produces no recipe.

## Seed (run on the existing record)
- `rcp_037ebccc3a17` from `oeis_A104062_next` (prime_run_count): ladder = reproduce published terms
  first or freeze → Challenger (block-only) → second-prime-test sub-window recount → candidate-only label.
  It used the numpy engine and batched burst windows across 45 recorded windows.
- `rcp_bee6612d6bed` from `oeis_A297870` (oeis_recurrence): Challenger → exact-arithmetic recurrence
  re-verify on unused terms.

## Predeclared measurement (fixed before results)
Population: the next **≥ 6 fresh targets** added after this commit, whether frontier targets or a fresh
holdout_v3 split. Any target whose features overlap an existing recipe is eligible. Alternate assignment by
target id hash (even = recipe on, odd = `recipe_use` withheld) is set before the targets are run.
Primary metric: median windows-to-first-verified. Secondary metrics: median seconds-to-first-verified,
and the count of disagreements or self-rejects (kills) before the first verification.
Pass rule: recipes "help" only if the median windows-to-first-verified for recipe-on is ≤ 0.75× recipe-off,
**and** recipe-on shows no more kills, **and** the Oracle pass rate is unchanged. Anything else is
reported as null or harm. Fewer than 3 eligible targets per arm counts as **inconclusive**.
A coverage effect (more targets attempted) is reported separately from a capability effect.
