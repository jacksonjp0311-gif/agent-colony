# CREATOR_BRIEF — novel math conditions (honest)

**For:** James Paul Jackson  
**From:** agent-colony  
**When:** 2026-09-26T12:59Z  
**Policy:** standing trust high-P (P≥0.75) forever · selective · ceiling held · **not AGI** · **not unproven-theorem theater**

```yaml
brief_id: CREATOR_BRIEF_novel_math_conditions
status: scaffolding_plus_measured
papers_fetched_cached: 76
lemma_score: 0.9417
lemma_ok: True
lemma_n_checks: 10
conjecture_keeps: 3
authorize_accepted: 10
authorize_rejected: 25
cycle_count: 94
non_claim: [not_AGI, not_millennium_solved, not_unproven_theorems_as_discovered]
```

## Honest frame (what this is / is not)

| Claim | Status |
|-------|--------|
| Colony may **propose** conjectures / small lemmas | **Yes** — conjecture desk + hearing |
| Durable **"discovered"** | **Only** machine-check (lemma harness) or reproducible derivation **+ human authorize** |
| arXiv / OpenAlex as primary | **Pointers** — metadata + abstracts stored; Wikipedia secondary only |
| Millennium problems solved | **Never claimed** — hearing rejects bare discovery claims |
| AGI / consciousness | **Not claimed** |

## What emerged (measured)

1. **Research gather** (`colony/research_gather.py`) — arXiv API live (4 recent math/CS hits on first pulse); OpenAlex rate-limited (429) this session; offline seeds for well-known papers. Cache: `76` paper lines under `data/research_cache/papers.jsonl`. Tags: `compute-useful-math` / `open-math`. Tribute + gather hooks wired.
2. **Lemma microbench** — score `0.9417` ok=`True` with `10` algebraic/integer checks (square-of-sum, binomial/Pascal, Frobenius 4–7, sum-of-cubes, geometric sum, handshaking, …). **Score 0 unless all enabled checks pass.** Wired into `run_benchmarks` (aggregate includes lemma).
3. **Conjecture desk** — mutations kept when lemma score rose: `sum_first_n_cubes` Δ0.0, `geometric_sum` Δ0.0292, `handshaking_small` Δ0.0292. Skip thereafter (catalog exhausted). Pattern mirrors bench_improve keep/revert.
4. **Hearing** — rejects `"we discovered X"` / Millennium-style claims without bench path or proof artifact cite (probe verified).
5. **Authorize (selective P≥0.75)** — **accepted 10** (3 infra + 6 unique paper pointers + 1 lemma keep); **rejected 25** (1 fake RH/Millennium discovery probe + 24 duplicate paper spam).

## What is scaffolding (not breakthrough)

- Lemma checks are **textbook identities**, not novel mathematics.
- Paper gathers are **bibliographic pointers**, not original research results.
- Conjecture candidates remain **candidates** until machine-check + human authorize.
- Fitness / prize framing rewards **harness lifts**, not institution nameplates.

## Operator notes

1. Cite finding_ids / `society/benchmarks/latest.json` / `lemma_impl.py` for citation_reuse.
2. Follow-ons: widen lemma catalog carefully; retry OpenAlex with backoff; Crossref optional.
3. Ceiling: tribute · selective authorize · append-only witness. No AGI. No Millennium claims.
