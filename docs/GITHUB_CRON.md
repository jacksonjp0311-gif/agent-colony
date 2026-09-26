# GitHub cron for Agent Colony (autonomy mile)

GitHub Actions workflow: `.github/workflows/colony-evolve.yml`

| Trigger | When |
|---------|------|
| `schedule` | `26 */6 * * *` UTC — every 6 hours |
| `workflow_dispatch` | Manual (Actions tab → Colony evolve → Run) |

## Production self-run loop

Each run (failure **noisy**, success **quiet**):

1. **Hard benches** — `run_benchmarks` (+ optional `bench-improve`); `ok_all=false` emits `::error::`
2. **Gather → claim** — claim pipeline preflight (raw scrape ≠ discovery)
3. **Evolve** — N cycles: desk keep/revert → lessons → novelty gate → multi-hop debate → exploration budget
4. **Selective authorize** — standing trust P≥0.75 for machine-checked keeps / bus-driven multihop only; **never accept-all**; easy_pad/reverts rejected
5. **Slim receipts** — `SOCIETY_SLIM_AUTONOMY.json`, dashboard, EVOLVE_STATUS (skip rewriting giant JSONL as the point of the commit)
6. **Push** — bot commit of society/data deltas

## Inputs

| Input | Default | Meaning |
|-------|---------|---------|
| `cycles` | `3` | Evolve cycles |
| `offline` | `false` | Seed-only HTTP off |
| `authorize` | `true` | Selective standing-trust authorize |

**Notes**
- Cron is always **UTC** on GitHub.
- Scheduled workflows only run on the default branch and may be delayed when the repo is inactive.
- Hard ceiling still applies: CI does **not** silent-accept; authorize step is selective under James standing trust.
- See [`NOVEL_MATH.md`](./NOVEL_MATH.md) and `society/briefs/CREATOR_BRIEF_autonomy.md`.
