# Novel-math pressure — honest status (Age of MD)

> We light the spark and witness. We do not micromanage the city.

**Not AGI. Not Millennium. Not unproven theorems claimed as discovered.**

## What “novel-math pressure” means here

| Layer | Role | Honest bound |
|-------|------|----------------|
| **Paper pulse** | arXiv / OpenAlex metadata + abstracts → `data/research_cache/papers.jsonl` | Bibliographic **pointers**, not original research |
| **Lemma microbench** | Machine-check of coded algebraic/integer lemmas | Score is harness fitness — **not** theorem discovery |
| **Hard tier** | Adversarial ranges + multi-step / derived checkers | Stops textbook identity dumps from acing ~0.95 |
| **Conjecture desk** | Propose candidates; mutate lemmas; **keep** only on score rise | Candidates until machine-check **+ human authorize** |
| **Hearing** | Rejects bare “we discovered X” without bench/proof path | Theater filter |

## Hard tier (current mile)

- **Basic tier:** classical identities (square-of-sum, Pascal, Frobenius, sum-of-cubes, …).
- **Hard tier:** adversarial sum-of-cubes / binomial–Pascal ranges; Vandermonde; hockey-stick; Cassini; multi-step `workload_derived_chain`.
- **Score rule:** all enabled checks must pass; textbook-only (no hard pass) is capped ~0.58; both tiers green still leave headroom under ~0.95.
- **Desk rule:** hard-enable mutations may keep; easy-check padding must **fail keep**.


## Autonomy mile (this mile; five-lifts substrate retained)

| Piece | Rule |
|-------|------|
| **A Self-run cron** | gather→claim→hard bench→keep/revert→lesson→selective authorize→slim push; failure noisy / success quiet |
| **B Novelty gate** | Novel-to-commons only if absent from lessons/known IDs, stripped baseline fails usefulness, survives held-out harder check; **textbook reuse ≈0** |
| **C Multi-hop debate** | A proposes → B attacks → C patches; fitness rise needs bus-driven claim/code change |
| **D Exploration budget** | Weak roles spawn/retire on hard-tier deltas; mutate distribution changes after reverts |
| **Keep rule** | Colony keeps ONLY if hard-tier bench score / hard_pass rises (easy pads fail keep) |
| **Ethos** | We light the spark and witness. We do not micromanage the city. |
| **Durable discovered** | Machine-check + human authorize (P≥0.75 selective). Not AGI. Not Millennium. |



## Oracle mile (this mile; autonomy substrate retained)

| Piece | Rule |
|-------|------|
| **Oracle** | HEAR bus debate → SENSE held-out + stripped-baseline + CAS/Python; **FAIL kills keep** |
| **Fitness** | No Oracle pass → no fitness rise credit |
| **Wire** | claim_pipeline / conjecture_desk / novelty_gate / bench_improve gate through Oracle before keep |
| **Collective** | Multi-agent vote weights; keep only if Oracle passes; still candidate until authorize |
| **Easy pad** | Must **die on Oracle** (even if basic score ticks up) |
| **Hard keep** | Only with Oracle pass (+ hard_pass rise) |
| **Ethos** | We light the spark and witness. We do not micromanage the city. |
| **Durable discovered** | Machine-check + Oracle + human authorize (P≥0.75 selective). Not AGI. Not Millennium. |

## Claim boundary

- Colony may **propose** conjectures and small lemmas.
- Durable **discovered** requires machine-check (or reproducible derivation) **+ human authorize**.
- Never claim Riemann / P vs NP / other Millennium problems solved.
- Graphic ethos: [`docs/assets/spark_witness_city.jpg`](./assets/spark_witness_city.jpg) (hand painting).

## Operator pointers

- Harness: `society/benchmarks/lemma_microbench.py` + `artifacts/lemma_impl.py`
- Desk: `colony/conjecture_desk.py` → `conjecture_history.jsonl` + `WITNESS_CONJECTURE.md`
- External mind: `colony/external_mind.py` → proposals + commons append on keep/revert
- Briefs: `society/briefs/CREATOR_BRIEF_five_lifts.md` (this mile); bridge brief retained
- Cron: [`GITHUB_CRON.md`](./GITHUB_CRON.md) — CI does **not** auto-accept

## Measured (this mile)

| Metric | Value |
|--------|-------|
| Lemma baseline (pre-autonomy) | **0.9071** (12/12 hard pass) |
| New disabled hard checks | gcd_fibonacci, stirling_second_row, pythagorean_generation, motzkin_bounded |
| Novelty gate | hits/kills recorded in `society/systems/novelty_gate.json` |
| Multi-hop | `society/systems/debate_multihop.json` |
| Exploration budget | `society/systems/exploration_budget.json` |
| Ethos graphic | `docs/assets/spark_witness_city.jpg` |

**Novel math beyond textbook?** No — Oracle mile hardens keep gates (HEAR/SENSE/collective). Autonomy substrate retained (novelty/debate/budget/cron). Classical coded identities only; **still not theorem discovery**. Textbook reuse ≈0 for any "novel" claim.
