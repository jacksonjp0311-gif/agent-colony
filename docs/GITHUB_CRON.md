# GitHub cron for Agent Colony

GitHub Actions workflow: `.github/workflows/colony-evolve.yml`

| Trigger | When |
|---------|------|
| `schedule` | `26 */6 * * *` UTC — every 6 hours |
| `workflow_dispatch` | Manual (Actions tab → Colony evolve → Run) |

Each run: `python -m colony evolve --cycles N` (default 3), refresh dashboard, commit `data/` + `society/` changes back to `main`.

**Notes**
- Cron is always **UTC** on GitHub.
- Scheduled workflows only run on the default branch and may be delayed when the repo is inactive.
- Hard ceiling still applies: proposals stay candidate until human (or delegated) authorize; CI does **not** auto-accept.
- For chat digests, keep using the Grok Bot “Agent Colony progress dashboard” routine separately.
