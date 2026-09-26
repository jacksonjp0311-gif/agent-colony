# ALIGN patch notes

## Done on main
- `colony/creator_will.py` — ALIGN MILE CREATOR_WILL_ASK
- `colony/society.py` — imports creator_will
- `colony/standing_trust.py` — P_MIN=0.75 + meets_standing_trust
- `colony/authorize.py` — imports standing_trust
- `colony/genomes.py` — oracle_scribe + stem_checker biases + child pool
- CHARTER/README/WILL/BRIEF/EVOLVE_STATUS/SOCIETY_SLIM/authorize receipts

## Local ready (optional push)
- `.github/workflows/colony-evolve.yml` — mile=align, oracle slim, P≥0.75 wording
- `docs/NOVEL_MATH.md` — Align mile wording

Restore large locals: `python3 scripts/restore_align_code.py` (needs align_b64 chunks if present).

**Not AGI. Not Millennium. Not novel theorems.** Spark_witness assets untouched.
