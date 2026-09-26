# Evolve Status (2026-09-26)

Hard ceiling held. Ran `python -m colony evolve --cycles 5` (+1 smoke) on the box.

## Metrics (box)

| Metric | First evolve fitness | After cycle 19 |
|--------|----------------------|----------------|
| aggregate | 0.7388 | **0.8387** |
| tribute_quality | 0.9 | 0.9 |
| gather_coverage | 0.875 | 0.875 |
| build_reuse | 1.0 | **0.7333** |
| comm_reply_rate | **0.0** | **0.8333** |

## New role

- **courier** — spawned by fitness when reply rate was weak.

## Usable systems (built + reused)

coverage_index, skill_router, reply_tracker, fitness_ledger, topic_priority, improvement_scoreboard

## GitHub main

Pushed this session: `registry`, `bus`, `systems`, `fitness`, `dashboard`, `cli` (evolve), `spark`, `society` (evolve()), README, DASHBOARD.html, WITNESS_SUMMARY, report, EVOLVE_STATUS, `society/systems/*`.

## Still local / needs follow-up push

- `colony/emergence/growth.py` (~28KB rewrite — bus read / system use / fitness wiring)
- Full append-only logs: `data/ledger.jsonl`, `data/witness.jsonl`, `society/WITNESS.md`, `society/BULLETIN.md`
- Full `data/society_state.json` (agents inboxes); GitHub still has older/smaller state

**Box path:** `/workspace/agent-colony` has the complete runnable evolving colony.

## Honest note

Real: skill EMA updates, inbox read→reply, system use_counts, fitness aggregates, role spawn on metric pressure, before/after proposal metrics.
Not: open-ended ML / AGI. Proposals stay `candidate` until human authorize. Accepted=0.
