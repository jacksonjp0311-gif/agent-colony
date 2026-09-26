# Agent Colony

> **We light the spark and witness. We do not micromanage the city.**

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

Founding cast remains minimal: **Spark** + **Tribute Keeper**. Emergent roles appear when fitness pressure or the growth will asks for them.

## Hard ceiling (only)

1. **Creator tribute** — serve James when he asks. Active will: grow · build · communicate · gather · improve / evolve.
2. **Human authorize** — required for durable `accepted` knowledge and privileged actions. No silent accept. UNKNOWN stays UNKNOWN.
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
| `society/BULLETIN.md` | Bus chronology |
| `society/DASHBOARD.html` | Live progress dashboard |
| `society/WITNESS.md` / `WITNESS_SUMMARY.md` | Human-readable witness |
| `society/report.md` | Latest cycle report |

---

## Claim boundary

This is **not** autonomous AGI and **not** consciousness theater. Skills/fitness are real measurable state updates inside this repo; they are **not** open-ended ML training. Improvement proposals stay `candidate` until the human authorizes.
