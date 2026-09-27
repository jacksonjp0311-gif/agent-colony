"""Institution standing charters — remit autonomy of agenda, never of truth.

Each key institution holds a written remit it may pursue for N cycles without
re-asking James. Autonomy covers agenda / topic / gather only.
STILL blocked from durable ledger accept. Truth waits for selective human
authorize (standing trust P≥0.70). Append-only witness. Not AGI.

Informs growth / topic_priority / exploration_budget only.
Same pattern as hold_posture / cerebrum: feeds in, no authority out.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from colony.standing_trust import STANDING_TRUST_P_MIN

ROOT = Path(__file__).resolve().parent.parent
CHARTERS_STATE = ROOT / "society" / "systems" / "institution_charters.json"
CHARTERS_LOG = ROOT / "data" / "commons" / "institution_charters.jsonl"

DEFAULT_AUTONOMY_CYCLES = 8

# Forbidden — charters NEVER grant these
FORBIDDEN_POWERS = frozenset(
    {
        "durable_accept",
        "ledger_accept",
        "authorize",
        "accept_all",
        "double_gate",
        "override_oracle",
        "disable_oracle",
        "silent_accept",
        "truth_authority",
    }
)

# Standing remits for all 15 live institutions (extend cleanly).
STANDING_CHARTERS: list[dict[str, Any]] = [
    {
        "name": "Math Prize Desk",
        "kind": "prize",
        "remit": (
            "Pursue math_prize / compute_usefulness scoring themes for N cycles: "
            "rank candidate identities, seed gather topics, bias exploration toward "
            "hard-checkable compute-useful math. Never mark truth accepted."
        ),
        "agenda_topics": [
            "compute-useful-math",
            "open-math-problems",
            "mathematics-foundations",
        ],
        "exploration_bias": {"hard_enable": 0.08, "easy_pad": -0.05},
        "autonomy_cycles": DEFAULT_AUTONOMY_CYCLES,
    },
    {
        "name": "RSI Coupling Desk",
        "kind": "workshop",
        "remit": (
            "Feed strong RSI ledger candidates into improver/skill_router/genome "
            "mutation biases for N cycles. Measured inform only; proposals stay "
            "candidate until human authorize."
        ),
        "agenda_topics": ["emergent-technology", "software-engineering", "rsi-research"],
        "exploration_bias": {"explore": 0.06, "govern": 0.03},
        "autonomy_cycles": DEFAULT_AUTONOMY_CYCLES,
    },
    {
        "name": "Council of Careful Doubt",
        "kind": "council",
        "remit": (
            "Keep UNKNOWN as UNKNOWN across N cycles: flag thin evidence, urge "
            "re-debate, refuse accept-all pressure. Agenda autonomy for doubt "
            "rituals — never truth authority."
        ),
        "agenda_topics": ["epistemic-caution", "oracle-review"],
        "exploration_bias": {"govern": 0.05, "easy_pad": -0.08},
        "autonomy_cycles": DEFAULT_AUTONOMY_CYCLES,
    },
    {
        "name": "Workshop of Making",
        "kind": "workshop",
        "remit": (
            "Ship reversible build artifacts (notes, tools, blueprints, sandbox "
            "pilots) for N cycles without re-asking James. Build agenda only — "
            "durable systems still need authorize for standing promotion."
        ),
        "agenda_topics": ["software-engineering", "tool-building"],
        "exploration_bias": {"build": 0.07},
        "autonomy_cycles": DEFAULT_AUTONOMY_CYCLES,
    },
    {
        "name": "Archive of Attempts",
        "kind": "archive",
        "remit": (
            "Curate candidate findings as attempts for N cycles: index, tag, "
            "surface residuals. Never elevate attempts to accepted truth."
        ),
        "agenda_topics": ["archive-hygiene", "attempt-index"],
        "exploration_bias": {"gather": 0.04},
        "autonomy_cycles": DEFAULT_AUTONOMY_CYCLES,
    },
    {
        "name": "Academy of Learning",
        "kind": "academy",
        "remit": (
            "Maintain curricula digests and tutoring notes across math/compute/"
            "emergent-tech for N cycles. Learning agenda autonomy — not accepted "
            "knowledge claims."
        ),
        "agenda_topics": [
            "mathematics-foundations",
            "compute-useful-math",
            "software-engineering",
        ],
        "exploration_bias": {"gather": 0.05, "explore": 0.03},
        "autonomy_cycles": DEFAULT_AUTONOMY_CYCLES,
    },
    {
        "name": "Society Bulletin",
        "kind": "bulletin",
        "remit": (
            "Post cycle announcements and route inter-role messages for N cycles. "
            "Communication agenda only."
        ),
        "agenda_topics": ["bulletin-hygiene"],
        "exploration_bias": {"reply": 0.04},
        "autonomy_cycles": DEFAULT_AUTONOMY_CYCLES,
    },
    {
        "name": "Forum of Exchange",
        "kind": "forum",
        "remit": (
            "Host trade of build/gather/improve signals for N cycles. Soft "
            "coordination — no ledger authority."
        ),
        "agenda_topics": ["forum-exchange"],
        "exploration_bias": {"reply": 0.03, "explore": 0.02},
        "autonomy_cycles": DEFAULT_AUTONOMY_CYCLES,
    },
    {
        "name": "Chamber of Laws",
        "kind": "legislature",
        "remit": (
            "Draft law/norm proposals for N cycles. Proposals remain candidate; "
            "never auto-accept norms as durable truth."
        ),
        "agenda_topics": ["norm-drafting"],
        "exploration_bias": {"govern": 0.06},
        "autonomy_cycles": DEFAULT_AUTONOMY_CYCLES,
    },
    {
        "name": "Census",
        "kind": "census",
        "remit": (
            "Track population, genomes, generations, soft pop-cap for N cycles. "
            "Machine-legible census only."
        ),
        "agenda_topics": ["census-hygiene"],
        "exploration_bias": {"govern": 0.02},
        "autonomy_cycles": DEFAULT_AUTONOMY_CYCLES,
    },
    {
        "name": "Commons Archive",
        "kind": "commons",
        "remit": (
            "Curate shared candidate knowledge digests for N cycles. Commons "
            "writes stay candidate; no silent durable accept."
        ),
        "agenda_topics": ["commons-digest", "science-history"],
        "exploration_bias": {"gather": 0.05},
        "autonomy_cycles": DEFAULT_AUTONOMY_CYCLES,
    },
    {
        "name": "Forum of Domains",
        "kind": "forum",
        "remit": (
            "Cross-domain council agenda for science/history/math/software/"
            "nature/life-death/cosmos for N cycles. Raise communication quality; "
            "never claim accepted cross-domain truth."
        ),
        "agenda_topics": [
            "science-foundations",
            "history-of-ideas",
            "mathematics-foundations",
        ],
        "exploration_bias": {"explore": 0.04, "gather": 0.03},
        "autonomy_cycles": DEFAULT_AUTONOMY_CYCLES,
    },
    {
        "name": "Persona Registry",
        "kind": "registry",
        "remit": (
            "Maintain persona sheets under society/personas/ for N cycles. "
            "Role-posture artifacts — not claims of sentience or AGI."
        ),
        "agenda_topics": ["persona-hygiene"],
        "exploration_bias": {"govern": 0.02},
        "autonomy_cycles": DEFAULT_AUTONOMY_CYCLES,
    },
    {
        "name": "Hearing Chamber",
        "kind": "hearing",
        "remit": (
            "Schedule structured hearings of gathered findings for N cycles. "
            "Outcomes stay candidate until human authorize."
        ),
        "agenda_topics": ["hearing-schedule", "cross-examination"],
        "exploration_bias": {"govern": 0.04, "gather": 0.02},
        "autonomy_cycles": DEFAULT_AUTONOMY_CYCLES,
    },
    {
        "name": "Committee of Inquiry",
        "kind": "committee",
        "remit": (
            "Debate thin topics and recommend research priorities for N cycles. "
            "Soft scaffold — not accepted truth."
        ),
        "agenda_topics": ["thin-topics", "research-priority"],
        "exploration_bias": {"explore": 0.05, "gather": 0.04},
        "autonomy_cycles": DEFAULT_AUTONOMY_CYCLES,
    },
]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_et_label() -> str:
    return datetime.now().strftime("%Y-%m-%d %I:%M %p ET")


def _strip_forbidden(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for key in FORBIDDEN_POWERS:
        if out.get(key) is True or out.get(key) == "accepted":
            out[key] = False
    out["inform_only"] = True
    out["ledger_authority"] = False
    out["durable_accept"] = False
    out["can_authorize"] = False
    out["can_accept_ledger"] = False
    out["truth_authority"] = False
    out["autonomy_of"] = ["agenda", "topic", "gather"]
    out["not_autonomy_of"] = ["truth", "durable_accept", "authorize"]
    return out


def default_charters() -> list[dict[str, Any]]:
    rows = []
    for spec in STANDING_CHARTERS:
        row = _strip_forbidden(
            {
                **spec,
                "cycles_pursued": 0,
                "cycles_remaining": int(spec.get("autonomy_cycles") or DEFAULT_AUTONOMY_CYCLES),
                "active": True,
                "status": "standing",
                "needs_human_authorize_for_accepted": True,
                "P_min": STANDING_TRUST_P_MIN,
                "ceiling": (
                    f"P>={STANDING_TRUST_P_MIN} human authorize selective; "
                    "charter pursues agenda only; never durable accept"
                ),
            }
        )
        rows.append(row)
    return rows


def load_charters() -> dict[str, Any]:
    if CHARTERS_STATE.exists():
        try:
            return json.loads(CHARTERS_STATE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "version": 1,
        "mile": "institution-standing-charters",
        "updated_at": _utc(),
        "when_et": _utc_et_label(),
        "charters": default_charters(),
        "inform_only": True,
        "durable_accept": False,
        "ledger_authority": False,
        "can_authorize": False,
        "ceiling": f"P>={STANDING_TRUST_P_MIN} human authorize selective; never accept-all",
        "non_claims": ["not_AGI", "not_consciousness", "not_Millennium", "agenda_only"],
        "note": (
            "Standing remits: agenda/topic/gather autonomy for N cycles. "
            "Truth still waits for James selective authorize."
        ),
    }


def save_charters(data: dict[str, Any]) -> Path:
    data = dict(data)
    data["updated_at"] = _utc()
    data["when_et"] = _utc_et_label()
    data["inform_only"] = True
    data["durable_accept"] = False
    data["ledger_authority"] = False
    data["can_authorize"] = False
    CHARTERS_STATE.parent.mkdir(parents=True, exist_ok=True)
    CHARTERS_STATE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return CHARTERS_STATE


def ensure_charters(*, cycle_id: str = "") -> dict[str, Any]:
    """Ensure all standing charters exist; extend cleanly for new institutions."""
    data = load_charters()
    by_name = {c["name"]: c for c in (data.get("charters") or []) if c.get("name")}
    changed = False
    for spec in STANDING_CHARTERS:
        if spec["name"] not in by_name:
            row = _strip_forbidden(
                {
                    **spec,
                    "cycles_pursued": 0,
                    "cycles_remaining": int(spec.get("autonomy_cycles") or DEFAULT_AUTONOMY_CYCLES),
                    "active": True,
                    "status": "standing",
                    "needs_human_authorize_for_accepted": True,
                    "P_min": STANDING_TRUST_P_MIN,
                    "built_cycle": cycle_id,
                }
            )
            by_name[spec["name"]] = row
            changed = True
        else:
            row = by_name[spec["name"]]
            if int(row.get("cycles_remaining") or 0) <= 0 and row.get("active", True):
                row["cycles_remaining"] = int(row.get("autonomy_cycles") or spec.get("autonomy_cycles") or DEFAULT_AUTONOMY_CYCLES)
                row["status"] = "standing"
                row["renewed_at_cycle"] = cycle_id
                by_name[spec["name"]] = _strip_forbidden(row)
                changed = True
    data["charters"] = list(by_name.values())
    data["count"] = len(data["charters"])
    if changed or not CHARTERS_STATE.exists():
        save_charters(data)
    return data


def active_charters(data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = data or load_charters()
    return [
        c
        for c in (data.get("charters") or [])
        if c.get("active") and int(c.get("cycles_remaining") or 0) > 0
    ]


def charter_topic_hints(data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Inform topic_priority — ranked hints from active remits (not truth)."""
    hints: list[dict[str, Any]] = []
    for c in active_charters(data):
        for topic in c.get("agenda_topics") or []:
            hints.append(
                {
                    "topic": topic,
                    "priority": 0.55,
                    "reason": f"charter:{c['name']}",
                    "institution": c["name"],
                    "inform_only": True,
                    "durable_accept": False,
                }
            )
    return hints


def charter_exploration_bias(data: dict[str, Any] | None = None) -> dict[str, float]:
    """Aggregate exploration_budget biases from active remits (clamped, tiny)."""
    bias: dict[str, float] = {}
    for c in active_charters(data):
        for k, v in (c.get("exploration_bias") or {}).items():
            bias[k] = bias.get(k, 0.0) + float(v)
    # Clamp advisory band
    return {k: max(-0.15, min(0.15, round(v, 4))) for k, v in bias.items()}


def refuse_authorize(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    """Explicit refuse — charter pursuit cannot authorize or durable-accept."""
    return {
        "accepted": False,
        "refused": True,
        "reason": "institution_charter_no_truth_authority",
        "inform_only": True,
        "durable_accept": False,
        "can_authorize": False,
        "ceiling": f"P>={STANDING_TRUST_P_MIN} human authorize selective",
        "note": "Charters grant agenda autonomy only. Truth waits for James.",
    }


def attempt_ledger_accept(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return refuse_authorize()


def pursue_cycle(cycle_id: str, *, state_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Tick standing charters once per evolve cycle. Inform-only side effects."""
    data = ensure_charters(cycle_id=cycle_id)
    pursued: list[str] = []
    for c in data.get("charters") or []:
        if not c.get("active"):
            continue
        remaining = int(c.get("cycles_remaining") or 0)
        # Standing remits renew when exhausted — agenda autonomy only, never truth
        if remaining <= 0:
            c["cycles_remaining"] = int(c.get("autonomy_cycles") or DEFAULT_AUTONOMY_CYCLES)
            c["status"] = "standing"
            c["renewed_at_cycle"] = cycle_id
            remaining = int(c["cycles_remaining"])
        c["cycles_pursued"] = int(c.get("cycles_pursued") or 0) + 1
        c["cycles_remaining"] = remaining - 1
        c["last_cycle"] = cycle_id
        c["status"] = "standing"
        c = _strip_forbidden(c)
        pursued.append(c["name"])
    # write back stripped rows
    data["charters"] = [_strip_forbidden(c) for c in (data.get("charters") or [])]
    data["last_cycle"] = cycle_id
    data["last_pursued"] = pursued
    data["topic_hints"] = charter_topic_hints(data)
    data["exploration_bias"] = charter_exploration_bias(data)
    data["inform_only"] = True
    data["durable_accept"] = False
    data["can_authorize"] = False
    save_charters(data)

    # Append-only commons log (witness-friendly)
    CHARTERS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with CHARTERS_LOG.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": _utc(),
                    "cycle_id": cycle_id,
                    "pursued": pursued,
                    "count": len(pursued),
                    "inform_only": True,
                    "durable_accept": False,
                    "can_authorize": False,
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    # Soft-inform state_data if provided (topic/exploration hints only)
    if state_data is not None:
        state_data["institution_charters"] = {
            "count": len(data.get("charters") or []),
            "pursued": pursued,
            "topic_hints": data.get("topic_hints"),
            "exploration_bias": data.get("exploration_bias"),
            "inform_only": True,
            "durable_accept": False,
            "can_authorize": False,
            "ts": _utc(),
        }

    budget_apply = apply_exploration_budget_bias(data)
    return {
        "system": "institution_charters",
        "cycle_id": cycle_id,
        "pursued": pursued,
        "topic_hints": data.get("topic_hints"),
        "exploration_bias": data.get("exploration_bias"),
        "exploration_budget_apply": budget_apply,
        "inform_only": True,
        "durable_accept": False,
        "can_authorize": False,
        "ledger_authority": False,
        "ceiling": f"P>={STANDING_TRUST_P_MIN} human authorize selective",
        "non_claims": ["not_AGI", "not_consciousness", "not_Millennium", "agenda_only"],
    }


def apply_topic_priority_hints(
    ranked: list[dict[str, Any]] | None,
    *,
    data: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Merge charter topic hints into an existing ranked list (inform-only)."""
    out = list(ranked or [])
    seen = {str(r.get("topic")) for r in out}
    for hint in charter_topic_hints(data):
        t = str(hint.get("topic"))
        if t in seen:
            continue
        out.append(hint)
        seen.add(t)
    return out


def latest_charters() -> dict[str, Any]:
    return load_charters()


def apply_exploration_budget_bias(data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Soft-inform exploration_budget.json with charter biases (clamped). Never authorize."""
    bias = charter_exploration_bias(data)
    if not bias:
        return {"applied": False, "bias": {}}
    try:
        from colony.exploration_budget import load_budget, save_budget

        budget = load_budget()
        dist = dict(budget.get("mutate_distribution") or {})
        # Map charter keys onto known mutation names when present
        for key, delta in bias.items():
            # Prefer exact key; else prefix match
            targets = [k for k in dist if k == key or k.startswith(key)]
            if not targets and key in ("hard_enable", "easy_pad", "explore", "build", "gather", "govern", "reply"):
                # stash advisory only
                continue
            for t in targets:
                dist[t] = max(0.001, float(dist.get(t) or 0.05) * (1.0 + float(delta)))
        if dist:
            s = sum(dist.values()) or 1.0
            dist = {k: round(v / s, 6) for k, v in dist.items()}
            budget["mutate_distribution"] = dist
        budget["charter_inform"] = {
            "bias": bias,
            "inform_only": True,
            "durable_accept": False,
            "can_authorize": False,
        }
        save_budget(budget)
        return {"applied": True, "bias": bias, "inform_only": True}
    except Exception as exc:  # noqa: BLE001
        return {"applied": False, "bias": bias, "error": str(exc)}
