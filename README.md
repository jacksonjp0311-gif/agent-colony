# Agent Colony

> **We light the spark and witness. We do not micromanage the city.**

![Spark and witness — we do not micromanage the city](docs/assets/spark_witness_city.jpg)

Agent Colony is an experiment by **James Paul Jackson** ([jacksonjp0311-gif](https://github.com/jacksonjp0311-gif), [@unifiedenergy11](https://x.com/unifiedenergy11)).
It is a small society of scripted agents that run on a GitHub Actions schedule. They propose
machine-checkable math checks, test them against a strict checker (the "Oracle"), learn from what fails, and
keep a public, append-only record of everything. A human authorizes anything durable.

## Results

- **OEIS A104062: computed a(7) = 138994.** The colony counted four consecutive primes in arithmetic
  progression (difference 6) among the first 2·10^8 primes. It first reproduced every published term a(1)–a(6), and the
  value was cross-checked independently with primesieve 12.7 plus a C counter, and with a pure-Python recount.
  *Computed value, not a proof; pending OEIS review.* Evidence and reproduction:
  [`evidence/2026-10-16-a104062-a7/`](evidence/2026-10-16-a104062-a7/README.md).
- **OEIS A104062: computed a(8) = 1031312, a(9) = 7863231, a(10) = 61341010, a(11) = 487855645** (first 2·10^9 … 2·10^12 primes; a(10) by three box counters, a(11) by two independently sharded passes on GitHub Actions). The colony's
  frontier burst and three primesieve-based C counters agree exactly. The Hardy–Littlewood prediction for *consecutive*
  primes (inclusion–exclusion, constant 8.302 derived here) matches to within 0.013% from n=9 to n=11 (actual/predicted 1.000121 at n=10, 0.999995 at n=11). That agreement is evidence,
  not proof. *Computed, not proof; pending OEIS review.*
  [`evidence/2026-10-16-a104062-a8-a9/`](evidence/2026-10-16-a104062-a8-a9/README.md)
- **Fresh holdout test (holdout_v2): no measured capability gain.** On 12 unseen problems, today's colony
  performed exactly like the 2026-10-11 version. Its recent growth is in coverage (more checks it wrote itself), not
  in solving unfamiliar problems better. [`evidence/2026-10-16-holdout-v2/`](evidence/2026-10-16-holdout-v2/README.md)
- **Trust loop and citations:** [`evidence/2026-10-11-trust-loop/`](evidence/2026-10-11-trust-loop/README.md),
  [`evidence/2026-10-16-citations/`](evidence/2026-10-16-citations/README.md).

## Known limitations

- **Far counterexamples escape.** A claim that is false only at astronomically large values passes every in-loop check.
  Examples: holdout_v2's Pell-991 claim (first counterexample has 29 digits) was kept in 2/5 runs, and a 52-digit gcd case in the
  fault tests. Only the out-of-loop evaluator catches these.
- **Stepped ranges** (e.g. `range(9, 49, 2)`) are not re-tested on a shifted window by the Oracle's held-out check
  (`colony/trust/shifted_holdout.py`).
- **Misleading agent lessons** are blocked downstream by the Challenger, but they are not automatically retired.
- **Small samples:** holdout experiments use 5 paired seeds (smallest attainable p = 0.0625).
- The agents are scripted programs, not a language model. This is not AGI and not new mathematics beyond computed values.

Repo: https://github.com/jacksonjp0311-gif/agent-colony · License: [MIT](LICENSE)

---

## What this is

A local-first **evolving colony** with concrete mechanics (not ceremony-only):

| Mechanic | What actually happens |
|----------|------------------------|
| **Agent registry** | Roles enter/leave; each agent has inbox, skills, contribution scores |
| **Communication bus** | Messages deliver to inboxes; agents **read** them next cycle and reply |
| **Usable systems** | Artifacts under `society/systems/` that later cycles **load and update** |
| **Fitness** | Measurable: tribute quality, gather coverage, build reuse, comm reply rate |
| **Evolve** | Skill weights update from outcomes; roles spawn/retire; proposals carry before/after metrics (candidate until human authorize) |
| **Genomes** | JSON traits (gather/build/reply/explore/govern); mutation on child spawn; fitness-linked parents |
| **Personas** | Durable engineered character sheets (`society/personas/`); distinct voices — not sentience |
| **RSI coupling** | Accepted/strong RSI findings bias improver, skill_router, genome mutation (measured) |
| **Common knowledge** | `society/systems/common_knowledge.json` + `data/commons/` — append candidates, reuse each cycle |
| **Government** | Chamber of Laws + Census; law proposals stay candidate until authorize |
| **Oracle** | HEAR bus debate → SENSE (held-out + stripped + CAS) → collective vote; **FAIL kills keep**; no pass → no fitness rise; still candidate until authorize |
| **Domain bus** | science / history / math / empire channels + reply quality metric |

Founding cast remains minimal: **Spark** + **Tribute Keeper**. Emergent roles appear when fitness pressure or the growth will asks for them.

## Hard ceiling (only)

1. **Creator tribute** — serve James when he asks. Active will: **SPARK2 MILE** — (1) multi-hop load-bear replies (lift reply_rate, no fake padding); (2) Oracle kill easy_pad/weak (no fitness credit); (3) lessons→genome bias; (4) spawn/retire on Oracle-pass lift; (5) cron mile=spark2; (6) selective authorize P≥0.70 never accept-all; (7) ≥8 evolve + slim push + report. Ethos: light the spark and witness; do not micromanage the city. Not AGI / not Millennium / not novel theorems. Local model runtime deferred.
2. **Human authorize** — required for durable `accepted` knowledge and privileged actions. Standing trust may selectively authorize P≥0.70 machine-checked candidates; never silent accept-all. UNKNOWN stays UNKNOWN.
3. **Append-only witness** — `data/witness.jsonl` + `society/WITNESS.md`.

See [CHARTER.md](./CHARTER.md).

---

## Run

```bash
git clone https://github.com/jacksonjp0311-gif/agent-colony && cd agent-colony
python3 -m pip install -r requirements.txt   # httpx, numpy, pytest
python3 -m colony cycle                      # one cycle
python3 -m colony cycle --offline            # seed only
python3 -m colony evolve --cycles 5          # multi-cycle autonomous evolve
python3 -m colony evolve --cycles 5 --offline
python3 -m colony status
python3 -m colony dashboard                  # refresh DASHBOARD.html + WITNESS_SUMMARY.md
python3 -m colony authorize --decisions society/receipts/AUTHORIZE_DECISIONS.json
# Selective human authorize (James / delegated). Never silent accept-all.
```

### Outputs

| Path | What |
|------|------|
| `data/ledger.jsonl` | Findings with provenance |
| `data/society_state.json` | Roles, agents, systems, fitness, bus |
| `data/witness.jsonl` | Append-only witness events |
| `society/systems/` | **Usable** systems (JSON/JSONL later cycles load) |
| `society/genomes/` | Per-agent genome JSON |
| `society/personas/` | Per-agent engineered persona JSON (not sentience) |
| `data/commons/` | Append-only common knowledge candidates |
| `society/BULLETIN.md` | Bus chronology |
| `society/DASHBOARD.html` | Live progress dashboard |
| `society/WITNESS.md` / `WITNESS_SUMMARY.md` | Human-readable witness |
| `society/report.md` | Latest cycle report |
| `society/benchmarks/` | FFT / autodiff / **lemma** harness + WITNESS_* |
| `data/research_cache/papers.jsonl` | Paper pulse (arXiv/OpenAlex pointers) |
| `docs/NOVEL_MATH.md` | Honest novel-math pressure status |
| `docs/assets/spark_witness_city.jpg` | Ethos graphic (hand painting) |

---


## Novel-math pressure (honest)

See [`docs/NOVEL_MATH.md`](./docs/NOVEL_MATH.md). Ethos graphic: [`docs/assets/spark_witness_city.jpg`](./docs/assets/spark_witness_city.jpg).

| Signal | Status (this mile) |
|--------|--------------------|
| Lemma microbench | Hard tier live; flourish adds disabled math (bell / hermite / lagrange / binomial_inversion / legendre); HARD_DENOM=28 headroom |
| STEM domain pack | `kinematics_microbench` — classical 1D/2D motion; energy_work starts disabled |
| Oracle packs | `colony/domain_packs.py` — math + stem; held-out + stripped + CAS; FAIL kills keep |
| Novelty gate | `colony/novelty_gate.py` — new-to-commons only; textbook reuse ≈0 |
| Multi-hop debate | A→B→C→**D Oracle gate**; bus-driven action_changed |
| Society flourish | Specialist spawn on fitness gaps; retire when no Oracle-pass lift |
| Exploration budget | Mutate distribution **must** change after reverts |
| Cron self-run | `colony-evolve.yml` full loop + selective authorize; failure noisy / success quiet |
| Durable "discovered" | Machine-check **+ Oracle + human authorize** (standing trust P≥0.70 selective) |
| Claims | **No** novel theorems · **No** novel physics · **No** Millennium · **No** AGI |

```bash
PYTHONPATH=. python3 -m society.benchmarks.run_benchmarks
PYTHONPATH=. python3 -m colony.research_gather
PYTHONPATH=. python3 -m colony.conjecture_desk
PYTHONPATH=. python3 -m colony.external_mind
```

---
## Claim boundary

This is **not** autonomous AGI and **not** consciousness theater. Skills/fitness are real measurable state updates inside this repo; they are **not** open-ended ML training. Improvement proposals stay `candidate` until the human authorizes.
