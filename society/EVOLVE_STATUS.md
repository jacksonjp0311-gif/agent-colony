# Evolve Status (2026-09-26)

Hard ceiling held. Ran `python -m colony evolve --cycles 5` (+1 smoke) locally.

## Metrics (measured on box)

| Metric | First evolve fitness | After cycle 19 |
|--------|----------------------|----------------|
| aggregate | 0.7388 | **0.8387** |
| tribute_quality | 0.9 | 0.9 |
| gather_coverage | 0.875 | 0.875 |
| build_reuse | 1.0 | **0.7333** (systems reused each cycle) |
| comm_reply_rate | **0.0** | **0.8333** |

## New role

- **courier** spawned when `comm_reply_rate` was below threshold (fitness pressure).

## On GitHub main (this session)

Pushed: registry, bus, systems, cli (`evolve`), README, dashboard module, spark, society (`evolve()`), DASHBOARD.html, WITNESS_SUMMARY, report, EVOLVE_STATUS, society/systems/*.

## Still primarily on the box (push pending / large)

- `colony/fitness.py`, `colony/emergence/growth.py` (critical for full clone run)
- Full `data/society_state.json`, `data/ledger.jsonl`, `data/witness.jsonl`, `society/WITNESS.md`, `society/BULLETIN.md`

Clone may need those two Python modules before `python -m colony evolve` works end-to-end. Local box has the complete evolving colony.

## Honest note

Skills/fitness are real measurable state updates inside this repo (EMA skill weights, reply rates, system use_counts). They are **not** open-ended ML training. Improvement proposals stay `candidate` until human authorize.
