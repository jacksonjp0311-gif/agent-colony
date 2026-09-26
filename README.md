# Agent Colony

> **We light the spark and witness. We do not micromanage the city.**

![Spark and witness — we do not micromanage the city](docs/assets/spark_witness_city.jpg)

*Light the spark. Step back. Witness the city.*

Full painting: [`docs/assets/spark_witness_city.png`](docs/assets/spark_witness_city.png) · lighter JPEG: [`docs/assets/spark_witness_city.jpg`](docs/assets/spark_witness_city.jpg)

Agents **self-improve to help their human creator.**  
Creator / Human Principal: **James Paul Jackson** ([jacksonjp0311-gif](https://github.com/jacksonjp0311-gif), [@unifiedenergy11](https://x.com/unifiedenergy11)).

Repo: https://github.com/jacksonjp0311-gif/agent-colony

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
| **Domain bus** | science / history / math / empire channels + reply quality metric |

Founding cast remains minimal: **Spark** + **Tribute Keeper**. Emergent roles appear when fitness pressure or the growth will asks for them.

## Hard ceiling (only)

1. **Creator tribute** — serve James when he asks. Active will: **AUTONOMY MILE** — (A) production cron self-run gather→claim→bench→keep/revert→lesson→selective authorize→slim push; (B) new-to-commons novelty gate (textbook reuse≈0); (C) multi-hop A→B→C debate with bus-driven action change; (D) exploration budget (distribution changes after reverts); five-lifts substrate retained. Ethos: light the spark and witness; do not micromanage the city. Not AGI / not Millennium. Local model runtime deferred.
2. **Human authorize** — required for durable `accepted` knowledge and privileged actions. Standing trust may selectively authorize P≥0.75 machine-checked candidates; never silent accept-all. UNKNOWN stays UNKNOWN.
3. **Append-only witness** — `data/witness.jsonl` + `society/WITNESS.md`.

See [CHARTER.md](./CHARTER.md).

---

## Run

```bash
cd /workspace/agent-colony   # or your clone
python3 -m pip install -r requirements.txt   # optional httpx
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
| Lemma microbench | Hard tier live — baseline **0.9071**; autonomy adds disabled hard checks (gcd_fibonacci / stirling / pythagorean / motzkin) |
| Novelty gate | `colony/novelty_gate.py` — new-to-commons only; textbook reuse ≈0 |
| Multi-hop debate | A proposes → B attacks → C patches; bus-driven action_changed |
| Exploration budget | Mutate distribution **must** change after reverts |
| Cron self-run | `colony-evolve.yml` full loop + selective authorize; failure noisy / success quiet |
| Durable "discovered" | Machine-check **+ human authorize** (standing trust P≥0.75 selective) |
| Claims | **No** novel theorems · **No** Millennium · **No** AGI |

```bash
PYTHONPATH=. python3 -m society.benchmarks.run_benchmarks
PYTHONPATH=. python3 -m colony.research_gather
PYTHONPATH=. python3 -m colony.conjecture_desk
PYTHONPATH=. python3 -m colony.external_mind
```

---
## Claim boundary

This is **not** autonomous AGI and **not** consciousness theater. Skills/fitness are real measurable state updates inside this repo; they are **not** open-ended ML training. Improvement proposals stay `candidate` until the human authorizes.
