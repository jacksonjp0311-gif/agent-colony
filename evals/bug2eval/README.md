# bug2eval cases — Agent Colony fixes (2026-10-16/17)

Each `.b2e` file is a portable regression eval made with
[bug2eval](https://github.com/jacksonjp0311-gif/bug2eval): a BEFORE snapshot (the parent of the fix
plus the fix's regression test) that must FAIL, and an AFTER snapshot (the fix) that must PASS, with
the test file and `tests/conftest.py` protected (`--protect`). Snapshots hold `colony/`,
`society/benchmarks/`, `society/systems/`, the one test file, `tests/conftest.py`, `requirements.txt`
and `data/research_cache/offline_seeds.json` (no other `data/`).

| Case | Fix | Regression test | Bug |
|---|---|---|---|
| B2E-COL-001 | `3c906a1` | `tests/test_instrument_oracle_path.py` | Sieve instrument checks were authored but never reached the Oracle (desk picker dropped instrument-sourced disabled checks); slot burn; twin-only rotation; external_mind ImportError |
| B2E-COL-002 | `79cccce` | `tests/test_speed_noise_and_same_day.py` | Wall-clock speed noise killed correct checks before a real Oracle verdict; same target re-killed and kills stacked |
| B2E-COL-003 | `9811ad2` | `tests/test_arxiv_rate_limit.py` | arXiv 429 counted as a live failure every cycle (plain http, no Retry-After, no last-good cache) |
| B2E-COL-004 | `b1c43ba` | `tests/test_proposal_dedupe_cycle.py` | Same seek proposal filed twice per cycle; the `(cycle N)` copy was Hearing-rejected |

Validate (not part of every evolve cycle): `evals/bug2eval/validate_all.sh`, or the manual/weekly
GitHub workflow `bug2eval-validate`. Rebuild one case: `evals/bug2eval/build_case.sh ID SHA TEST "TITLE" tags`.
