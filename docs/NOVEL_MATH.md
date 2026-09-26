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


## Bridge dynamics (this mile)

| Piece | Rule |
|-------|------|
| **External mind** | Model/heuristic proposes lemma candidates or paper-derived critique (`colony/external_mind.py`) |
| **Keep rule** | Colony keeps ONLY if hard-tier bench score rises (easy pads fail keep) |
| **Shared memory** | Commons of verified lifts — kept lemmas, failed pads, paper cites with bench paths; new cycles read first |
| **Harder workloads** | Prize/fitness only when hard bar moves; no textbook pad wins |
| **Ethos** | We light the spark and witness. We do not micromanage the city. |
| **Durable discovered** | Machine-check + human authorize. Not AGI. Not Millennium. |

## Claim boundary

- Colony may **propose** conjectures and small lemmas.
- Durable **discovered** requires machine-check (or reproducible derivation) **+ human authorize**.
- Never claim Riemann / P vs NP / other Millennium problems solved.
- Graphic ethos: [`docs/assets/spark_witness_city.jpg`](./assets/spark_witness_city.jpg) (hand painting).

## Operator pointers

- Harness: `society/benchmarks/lemma_microbench.py` + `artifacts/lemma_impl.py`
- Desk: `colony/conjecture_desk.py` → `conjecture_history.jsonl` + `WITNESS_CONJECTURE.md`
- External mind: `colony/external_mind.py` → proposals + commons append on keep/revert
- Briefs: `society/briefs/CREATOR_BRIEF_bridge_dynamics.md` (this mile)
- Cron: [`GITHUB_CRON.md`](./GITHUB_CRON.md) — CI does **not** auto-accept

## Measured (this mile)

| Metric | Value |
|--------|-------|
| Lemma before bridge (prior hard mile) | 0.8371 |
| Lemma after bridge hard keeps | **0.9071** |
| Hard checks enabled | 9 / 9 pass |
| Bridge keeps | binomial_sum_row, fibonacci_addition, catalan_bounded |
| Bridge reverts | easy_pad_square_again (hard_pass flat → fail keep) |
| External-mind proposals | 6 (structured + paper); keeps only on hard rise |
| cycle_count | 112 |
| Authorize (bridge) | accepted 3 / rejected 12 |
| Ethos graphic | `docs/assets/spark_witness_city.jpg` |

**Novel math beyond textbook?** No — harder pressure + more classical coded identities; still not theorem discovery.
