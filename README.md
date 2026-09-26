# Agent Colony

> **We light the spark and witness. We do not micromanage the city.**

Agents **self-improve to help their human creator.**  
Creator / Human Principal: **James Paul Jackson** ([jacksonjp0311-gif](https://github.com/jacksonjp0311-gif), [@unifiedenergy11](https://x.com/unifiedenergy11)).

Repo: https://github.com/jacksonjp0311-gif/agent-colony

---

## What this is

A local-first colony with a **minimal founding cast** and an **emergence engine**:

| Founding | Role |
|----------|------|
| **Spark** | Proposes and enacts civilization (roles, councils, institutions, norms, rituals) |
| **Tribute Keeper** | Pays creator tribute each cycle under the active ask |

There is **no permanent aristocracy** of Harvester / Librarian / Synthesizer / Critic. If those appear, the Spark invented them.

The human (and the logs) are the **witness**.

**Growth loop (each cycle):** invent/build artifacts → communicate (Society Bulletin) → gather information → attempt self-improvement — all logged in witness.

## Hard ceiling (only)

1. **Creator tribute** — serve James when he asks. Active will: grow · build · communicate · gather · improve. Standing RSI / self-improving research remains valuable as gather.
2. **Human authorize** — required for durable `accepted` knowledge and privileged actions (money, public posts, privilege escalation). No silent accept. UNKNOWN stays UNKNOWN.
3. **Append-only witness** — `data/witness.jsonl` + `society/WITNESS.md`.

Between asks, the colony may form civilization freely under that ceiling.

## Claim boundary

This is **not** autonomous AGI and **not** consciousness theater. It is a runnable society that collects evidence, emerges structure, and waits for the creator to accept durable knowledge.

See [CHARTER.md](./CHARTER.md).

---

## Run

```bash
cd /workspace/agent-colony   # or your clone
python3 -m pip install -r requirements.txt   # optional httpx
python3 -m colony cycle                      # tribute + emergence + witness
python3 -m colony cycle --offline            # seed only
python3 -m colony status
```

### Outputs

| Path | What |
|------|------|
| `data/ledger.jsonl` | Findings with provenance |
| `data/society_state.json` | Roles, councils, norms, institutions |
| `data/witness.jsonl` | Append-only witness events |
| `society/WITNESS.md` | Human-readable witness chronology |
| `society/report.md` | Latest cycle report |

---

## Design lineage

Built for Codex ΔΦ / Cortex / Perci taste: local-first, evidence-gated, explicit non-claims — plus **emergence over micromanagement**.
