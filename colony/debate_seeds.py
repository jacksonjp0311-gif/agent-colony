"""Fresh debate seeds outside comfort zone — force multi-hop across colony domains.

Domains: math/STEM kinematics, gather→claim, hearings, Oracle, commons, government.
Avoid duplicate weak-spot loops. Wired into debate_multihop / hearing / forum.
Not AGI. Not Millennium.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SEED_STATE = ROOT / "society" / "systems" / "debate_seeds.json"
SEED_LOG = ROOT / "data" / "commons" / "debate_seeds.jsonl"

# Curated seeds the colony hasn't circled on (cross-domain, multi-hop)
FRESH_SEEDS: list[dict[str, Any]] = [
    {
        "id": "seed_kinematics_gather",
        "domains": ["math", "gather", "claim"],
        "claim": (
            "SEED: Treat STEM kinematics identity checks as gather→claim filters — "
            "a citation earns ledger weight only if a stripped baseline still fails the same kinematic constraint. "
            "Hop: geometer proposes constraint → pathfinder gathers counterexample → legislator hearing → Oracle SENSE."
        ),
    },
    {
        "id": "seed_oracle_commons_budget",
        "domains": ["oracle", "commons", "government"],
        "claim": (
            "SEED: Commons exploration budget should shrink when Oracle easy_pad_kills rise cycle-over-cycle — "
            "government proposes a soft norm, hearing weighs, authorize stays selective. Not accept-all."
        ),
    },
    {
        "id": "seed_hearing_external_array",
        "domains": ["hearing", "cosmos", "weather"],
        "claim": (
            "SEED: Hearing evidence packets must cite at least one EXTERNAL ARRAY snapshot "
            "(arXiv OR NOAA Kp OR Open-Meteo) before accept_candidate on environment-coupled proposals. "
            "Missing feed → UNKNOWN, not silent pass."
        ),
    },
    {
        "id": "seed_residual_redebate",
        "domains": ["residuals", "debate", "forum"],
        "claim": (
            "SEED: When peer residual confidence_gap≥0.35, forum must open a re-debate hop before fitness credit — "
            "high-arousal agents speak first; conflicting residuals logged with Oracle metrics."
        ),
    },
    {
        "id": "seed_gov_authorize_threshold",
        "domains": ["government", "authorize", "standing_trust"],
        "claim": (
            "SEED: Standing trust P≥0.70 (was 0.75) — government records before/after eligibility compare on each "
            "authorize batch; newly-eligible (0.70–0.75) items still need machine-checked evidence; UNKNOWN stays UNKNOWN."
        ),
    },
    {
        "id": "seed_time_revision_arxiv",
        "domains": ["time_revision", "arxiv", "math"],
        "claim": (
            "SEED: TIME REVISION — a prior 'preprints are low priority' conclusion must be revised when "
            "publications×space patterns fire; revise confidence + claim text, do not only append a new finding."
        ),
    },
    {
        "id": "seed_telemetry_query_debate",
        "domains": ["telemetry", "debate", "fitness"],
        "claim": (
            "SEED: Mid-debate, agents must query colony.telemetry (fitness delta, reply_rate, Oracle pass/kill/easy_pad) "
            "and cite the snapshot id in the patch hop — decisions without telemetry cite are deferred by hearing."
        ),
    },
    {
        "id": "seed_solar_ops_gather",
        "domains": ["cosmos", "gather", "government"],
        "claim": (
            "SEED: If NOAA Kp≥4 or DONKI notifications non-empty, pathfinder gathers ops-impact pointers into commons "
            "and legislator schedules a hearing — kinematics of environment signals, not prophecy. Not novel physics."
        ),
    },
]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_state() -> dict[str, Any]:
    if SEED_STATE.exists():
        try:
            return json.loads(SEED_STATE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"version": 1, "cursor": 0, "used": [], "last_seed_id": None}


def next_seed(cycle_id: str = "", *, avoid_recent: int = 4) -> dict[str, Any]:
    """Rotate fresh seeds; avoid immediate duplicate weak-spot loops."""
    st = _load_state()
    used = list(st.get("used") or [])
    recent = set(used[-avoid_recent:])
    # pick next not in recent
    n = len(FRESH_SEEDS)
    cursor = int(st.get("cursor") or 0) % n
    chosen = None
    for i in range(n):
        idx = (cursor + i) % n
        cand = FRESH_SEEDS[idx]
        if cand["id"] not in recent:
            chosen = cand
            cursor = (idx + 1) % n
            break
    if chosen is None:
        chosen = FRESH_SEEDS[cursor]
        cursor = (cursor + 1) % n
    used.append(chosen["id"])
    st = {
        "version": 1,
        "cursor": cursor,
        "used": used[-40:],
        "last_seed_id": chosen["id"],
        "last_cycle_id": cycle_id,
        "ts": _utc(),
        "n_seeds": n,
        "note": "Fresh debate seeds outside comfort zone. Multi-hop across colony domains.",
    }
    SEED_STATE.parent.mkdir(parents=True, exist_ok=True)
    SEED_STATE.write_text(json.dumps(st, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    row = {**chosen, "cycle_id": cycle_id, "ts": _utc()}
    SEED_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SEED_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def seed_claim_for_cycle(cycle_id: str = "") -> str:
    s = next_seed(cycle_id)
    return s.get("claim") or FRESH_SEEDS[0]["claim"]


def all_seed_ids() -> list[str]:
    return [s["id"] for s in FRESH_SEEDS]
