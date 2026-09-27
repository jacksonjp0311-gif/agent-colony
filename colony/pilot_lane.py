"""Proposal → pilot sandbox lane.

Agents may ship reversible pilots (skills, routers, gather filters) into a
sandbox commons. Promotion to standing STILL requires selective human authorize
at standing trust P≥0.70. Never accept-all. Never silent durable accept.

Inform + sandbox write only when wired into improvement / RSI / skill_router.
Same pattern as cerebrum / hold: feeds in, no authority out.
Not AGI. Not consciousness. Not Millennium.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from colony.standing_trust import STANDING_TRUST_P_MIN, meets_standing_trust

ROOT = Path(__file__).resolve().parent.parent
PILOT_STATE = ROOT / "society" / "systems" / "pilot_lane.json"
PILOT_LOG = ROOT / "data" / "commons" / "pilot_lane.jsonl"
SANDBOX_DIR = ROOT / "society" / "sandbox_pilots"
COMMONS_SANDBOX = ROOT / "data" / "commons" / "sandbox_pilots"

ALLOWED_KINDS = frozenset({"skill", "router", "gather_filter", "improvement", "rsi_bias"})
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
        "promote_without_authorize",
    }
)

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_.\-]{1,80}$")


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_et_label() -> str:
    return datetime.now().strftime("%Y-%m-%d %I:%M %p ET")


def _safe_slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_.\-]+", "_", (name or "pilot")[:80]).strip("_")
    return s or "pilot"


def load_lane() -> dict[str, Any]:
    if PILOT_STATE.exists():
        try:
            return json.loads(PILOT_STATE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "version": 1,
        "mile": "proposal-pilot-sandbox",
        "updated_at": _utc(),
        "when_et": _utc_et_label(),
        "pilots": [],
        "promoted": [],
        "refused": [],
        "inform_only": True,
        "durable_accept": False,
        "ledger_authority": False,
        "can_authorize": False,
        "promotion_requires_authorize": True,
        "P_min": STANDING_TRUST_P_MIN,
        "ceiling": (
            f"P>={STANDING_TRUST_P_MIN} human authorize selective for promotion; "
            "sandbox writes only until then; never accept-all"
        ),
        "sandbox_dir": "society/sandbox_pilots",
        "non_claims": ["not_AGI", "not_consciousness", "not_Millennium", "sandbox_only"],
        "note": (
            "Pilots are reversible sandbox artifacts. Standing promotion needs "
            "James selective authorize. Charters/growth may inform only."
        ),
    }


def save_lane(data: dict[str, Any]) -> Path:
    data = dict(data)
    data["updated_at"] = _utc()
    data["when_et"] = _utc_et_label()
    data["inform_only"] = True
    data["durable_accept"] = False
    data["ledger_authority"] = False
    data["can_authorize"] = False
    data["promotion_requires_authorize"] = True
    data["P_min"] = STANDING_TRUST_P_MIN
    PILOT_STATE.parent.mkdir(parents=True, exist_ok=True)
    PILOT_STATE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return PILOT_STATE


def ensure_sandbox() -> Path:
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    COMMONS_SANDBOX.mkdir(parents=True, exist_ok=True)
    marker = SANDBOX_DIR / "README.md"
    if not marker.exists():
        marker.write_text(
            "# Sandbox pilots\n\n"
            "Reversible pilots only. Promotion to standing requires selective "
            f"human authorize (P≥{STANDING_TRUST_P_MIN}). Never accept-all.\n"
            "Not AGI. Not durable truth.\n",
            encoding="utf-8",
        )
    return SANDBOX_DIR


def _strip_forbidden(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload or {})
    for key in FORBIDDEN_POWERS:
        if out.get(key) is True or out.get(key) == "accepted":
            out[key] = False
    out["inform_only"] = True
    out["durable_accept"] = False
    out["ledger_authority"] = False
    out["can_authorize"] = False
    out["can_accept_ledger"] = False
    out["status"] = out.get("status") or "sandboxed"
    if out["status"] in ("accepted", "promoted_standing"):
        # Never silently elevate — demote hostile claims
        if not out.get("authorized_by"):
            out["status"] = "sandboxed"
    return out


def propose_pilot(
    *,
    name: str,
    kind: str,
    body: dict[str, Any] | None = None,
    proposed_by: str = "improver",
    cycle_id: str = "",
    rationale: str = "",
) -> dict[str, Any]:
    """Propose + write a reversible pilot into the sandbox. No durable accept."""
    ensure_sandbox()
    kind_s = str(kind or "improvement")
    if kind_s not in ALLOWED_KINDS:
        kind_s = "improvement"
    slug = _safe_slug(name)
    pilot_id = f"pilot_{slug}_{uuid4().hex[:8]}"
    payload = _strip_forbidden(
        {
            "id": pilot_id,
            "name": slug,
            "kind": kind_s,
            "body": dict(body or {}),
            "proposed_by": proposed_by,
            "cycle_id": cycle_id,
            "rationale": (rationale or "")[:400],
            "status": "sandboxed",
            "reversible": True,
            "promotion_requires_authorize": True,
            "P_min": STANDING_TRUST_P_MIN,
            "authorized_by": None,
            "ts": _utc(),
        }
    )
    # Write sandbox artifact
    path = SANDBOX_DIR / f"{pilot_id}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Mirror under data/commons for commons readers
    commons_path = COMMONS_SANDBOX / f"{pilot_id}.json"
    commons_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    payload["path"] = str(path.relative_to(ROOT))
    payload["commons_path"] = str(commons_path.relative_to(ROOT))

    lane = load_lane()
    pilots = list(lane.get("pilots") or [])
    pilots.append(payload)
    # Cap in-memory list (keep last 80)
    lane["pilots"] = pilots[-80:]
    lane["last_proposed"] = pilot_id
    lane["last_cycle"] = cycle_id
    save_lane(lane)

    PILOT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with PILOT_LOG.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": _utc(),
                    "event": "propose_sandbox",
                    "pilot_id": pilot_id,
                    "kind": kind_s,
                    "cycle_id": cycle_id,
                    "inform_only": True,
                    "durable_accept": False,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    return payload


def refuse_durable_accept(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {
        "accepted": False,
        "refused": True,
        "reason": "pilot_lane_sandbox_only_no_durable_accept",
        "inform_only": True,
        "durable_accept": False,
        "can_authorize": False,
        "promotion_requires_authorize": True,
        "ceiling": f"P>={STANDING_TRUST_P_MIN} human authorize selective",
    }


def attempt_ledger_accept(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return refuse_durable_accept()


def request_promotion(
    pilot_id: str,
    *,
    confidence: float | None = None,
    machine_checked: bool = False,
    authorized_by: str | None = None,
    rationale: str = "",
) -> dict[str, Any]:
    """Promotion path — REQUIRES selective authorize gate (P≥0.70).

    Without authorized_by + standing trust, refuses. Never accept-all.
    """
    lane = load_lane()
    pilots = list(lane.get("pilots") or [])
    target = None
    for p in pilots:
        if p.get("id") == pilot_id:
            target = p
            break
    if target is None:
        return {
            "promoted": False,
            "refused": True,
            "reason": "pilot_not_found",
            "pilot_id": pilot_id,
            "durable_accept": False,
        }

    # Gate 1: human authorizer required
    if not authorized_by or not str(authorized_by).strip():
        refused = {
            "promoted": False,
            "refused": True,
            "reason": "promotion_requires_human_authorize",
            "pilot_id": pilot_id,
            "P_min": STANDING_TRUST_P_MIN,
            "durable_accept": False,
            "note": "Standing grant: selective authorize only under James trust.",
        }
        lane.setdefault("refused", []).append({**refused, "ts": _utc()})
        lane["refused"] = (lane.get("refused") or [])[-40:]
        save_lane(lane)
        return refused

    # Gate 2: standing trust P≥0.70 + machine_checked
    if not meets_standing_trust(confidence, machine_checked=machine_checked):
        refused = {
            "promoted": False,
            "refused": True,
            "reason": "standing_trust_not_met",
            "pilot_id": pilot_id,
            "confidence": confidence,
            "machine_checked": machine_checked,
            "P_min": STANDING_TRUST_P_MIN,
            "durable_accept": False,
        }
        lane.setdefault("refused", []).append({**refused, "ts": _utc()})
        lane["refused"] = (lane.get("refused") or [])[-40:]
        save_lane(lane)
        return refused

    # Selective promote (one pilot) — still not ledger accept of findings
    target["status"] = "promoted_sandbox_standing"
    target["authorized_by"] = str(authorized_by).strip()
    target["authorized_at"] = _utc()
    target["authorization_rationale"] = (rationale or "")[:400]
    target["confidence"] = float(confidence) if confidence is not None else None
    target["machine_checked"] = bool(machine_checked)
    target["durable_accept"] = False  # pilot standing ≠ ledger finding accept
    target["inform_only"] = False  # may inform skill_router as standing pilot
    target["ledger_authority"] = False
    promoted = {
        "promoted": True,
        "refused": False,
        "pilot_id": pilot_id,
        "status": target["status"],
        "authorized_by": target["authorized_by"],
        "P_min": STANDING_TRUST_P_MIN,
        "durable_accept": False,
        "ledger_authority": False,
        "note": (
            "Pilot promoted to standing sandbox use. Does NOT durable-accept "
            "ledger findings. Ceiling held."
        ),
        "ts": _utc(),
    }
    lane["pilots"] = pilots
    lane.setdefault("promoted", []).append(promoted)
    lane["promoted"] = (lane.get("promoted") or [])[-40:]
    save_lane(lane)
    # Refresh sandbox file
    path = ROOT / target.get("path", f"society/sandbox_pilots/{pilot_id}.json")
    if path.exists() or True:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(target, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with PILOT_LOG.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": _utc(),
                    "event": "promote_authorized",
                    "pilot_id": pilot_id,
                    "authorized_by": target["authorized_by"],
                    "durable_accept": False,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    return promoted


def run_pilot_lane(
    state_data: dict[str, Any],
    *,
    cycle_id: str = "",
    rsi_signal: dict[str, Any] | None = None,
    skill_routes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Per-cycle: ensure lane, optionally propose a small inform pilot from RSI/skills.

    Sandbox write + inform only. Never durable accept.
    """
    ensure_sandbox()
    lane = load_lane()
    proposed: dict[str, Any] | None = None

    # Light auto-propose from RSI strength (reversible gather_filter / rsi_bias)
    strength = float((rsi_signal or {}).get("strength") or 0.0)
    if strength >= 0.2 and cycle_id:
        # Avoid flooding: at most one auto pilot per cycle id suffix pattern
        recent = [p for p in (lane.get("pilots") or []) if p.get("cycle_id") == cycle_id]
        if not recent:
            proposed = propose_pilot(
                name=f"rsi_bias_{cycle_id[-6:]}",
                kind="rsi_bias",
                body={
                    "strength": strength,
                    "skill_bias": (rsi_signal or {}).get("skill_bias") or {},
                    "mutation_bias": (rsi_signal or {}).get("mutation_bias") or {},
                    "routes_snapshot": skill_routes or {},
                    "reversible": True,
                },
                proposed_by="improver",
                cycle_id=cycle_id,
                rationale=(
                    "Sandbox RSI bias pilot from measured coupling strength. "
                    "Inform skill_router only; promotion needs authorize."
                ),
            )

    # Hostile authority fields in state cannot elevate
    snap = {
        "system": "pilot_lane",
        "cycle_id": cycle_id,
        "pilots_count": len(lane.get("pilots") or []),
        "promoted_count": len(lane.get("promoted") or []),
        "last_proposed": (proposed or {}).get("id") or lane.get("last_proposed"),
        "inform_only": True,
        "durable_accept": False,
        "can_authorize": False,
        "ledger_authority": False,
        "promotion_requires_authorize": True,
        "P_min": STANDING_TRUST_P_MIN,
        "sandbox_dir": "society/sandbox_pilots",
        "ceiling": f"P>={STANDING_TRUST_P_MIN} human authorize selective",
        "non_claims": ["not_AGI", "not_consciousness", "not_Millennium", "sandbox_only"],
        "ts": _utc(),
    }
    state_data["pilot_lane"] = snap
    # Refresh lane marker
    lane["last_cycle"] = cycle_id
    save_lane(lane)
    return {"lane": snap, "proposed": proposed, "inform_only": True, "durable_accept": False}


def inform_skill_router(
    routes: dict[str, Any] | None,
    *,
    lane: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach sandboxed pilot ids as inform-only metadata on skill_router content."""
    content = dict(routes or {})
    data = lane or load_lane()
    sandboxed = [
        {"id": p.get("id"), "kind": p.get("kind"), "status": p.get("status")}
        for p in (data.get("pilots") or [])[-12:]
        if p.get("status") in ("sandboxed", "promoted_sandbox_standing")
    ]
    content["pilot_lane_inform"] = {
        "pilots": sandboxed,
        "inform_only": True,
        "durable_accept": False,
        "promotion_requires_authorize": True,
        "P_min": STANDING_TRUST_P_MIN,
    }
    return content


def latest_lane() -> dict[str, Any]:
    return load_lane()
