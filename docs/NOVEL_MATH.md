# Novel-math pressure — honest status (Age of MD)

> We light the spark and witness. We do not micromanage the city.

**Not AGI. Not Millennium. Not unproven theorems claimed as discovered.**

## What "novel-math pressure" means here

| Layer | Role | Honest bound |
|-------|------|----------------|
| **Paper pulse** | arXiv / OpenAlex metadata + abstracts → `data/research_cache/papers.jsonl` | Bibliographic **pointers**, not original research |
| **Lemma microbench** | Machine-check of coded algebraic/integer lemmas | Score is harness fitness — **not** theorem discovery |
| **Hard tier** | Adversarial ranges + multi-step / derived checkers | Stops textbook identity dumps from acing ~0.95 |
| **Conjecture desk** | Propose candidates; mutate lemmas; **keep** only on score rise | Candidates until machine-check **+ human authorize** |
| **Hearing** | Rejects bare "we discovered X" without bench/proof path | Theater filter |

## Hard tier (current mile)

- **Basic tier:** classical identities (square-of-sum, Pascal, Frobenius, sum-of-cubes, …).
- **Hard tier:** adversarial sum-of-cubes / binomial–Pascal ranges; Vandermonde; hockey-stick; Cassini; multi-step `workload_derived_chain`.
- **Score rule:** all enabled checks must pass; textbook-only (no hard pass) is capped ~0.58; both tiers green still leave headroom under ~0.95.
- **Desk rule:** hard-enable mutations may keep; easy-check padding must **fail keep**.

## Claim boundary

- Colony may **propose** conjectures and small lemmas.
- Durable **discovered** requires machine-check (or reproducible derivation) **+ human authorize**.
- Never claim Riemann / P vs NP / other Millennium problems solved.
- Graphic ethos: [`docs/assets/spark_witness.svg`](./assets/spark_witness.svg).

## Operator pointers

- Harness: `society/benchmarks/lemma_microbench.py` + `artifacts/lemma_impl.py`
- Desk: `colony/conjecture_desk.py` → `conjecture_history.jsonl` + `WITNESS_CONJECTURE.md`
- Briefs: `society/briefs/CREATOR_BRIEF_hard_lemma_mile.md` (this mile)
- Cron: [`GITHUB_CRON.md`](./GITHUB_CRON.md) — CI does **not** auto-accept

## Measured (this mile)

| Metric | Value |
|--------|-------|
| Lemma before harden (textbook) | 0.9417 |
| Lemma post-harden | 0.6971 |
| Lemma after hard keeps | **0.8371** |
| Hard checks enabled | 6 / 6 pass |
| Conjecture keeps | vandermonde_conv, hockey_stick, cassini, workload_derived_chain |
| Conjecture reverts | easy_pad_square_again (×2) |
| cycle_count | 104 |
| Authorize | accepted 6 / rejected 16 |
| Ethos graphic | `docs/assets/spark_witness.svg` |

**Novel math beyond textbook?** No — harder pressure only; still coded classical identities + paper pointers.
