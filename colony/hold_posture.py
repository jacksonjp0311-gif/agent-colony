"""Hold + selective authorize posture (spark3-hold).

Default posture: HOLD — light evolve watch only.
Authorize ONLY new themes that clear hard checks AND Oracle at score ≥0.70.
UNKNOWN stays UNKNOWN. Never accept-all.
Athanor + PulseMesh remain inform-only (no double-gate, no durable accept).

Hard ceiling: creator tribute; human authorize for durable accepted
(standing trust P≥0.70 selective); append-only witness.
Not AGI / consciousness / Millennium / novel theorems / novel physics.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from colony.standing_trust import STANDING_TRUST_P_MIN, meets_standing_trust

ROOT = Path(__file__).resolve().parent.parent
HOLD_STATE = ROOT / "society" / "systems" / "hold_posture.json"
RECEIPTS = ROOT / "society" / "receipts"

DEFAULT_POSTURE = "HOLD"
ORACLE_SCORE_FLOOR = 0.70  # hard+oracle theme score gate (aligns with standing trust P)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_et_label() -> str:
    # Box clock is America/New_York
    return datetime.now().strftime("%Y-%m-%d %I:%M %p ET")


def accepted_themes(ledger: Any) -> set[str]:
    out: set[str] = set()
    for f in ledger.all():
        if f.status != "accepted":
            continue
        theme = (f.meta or {}).get("theme_id")
        if theme:
            out.add(str(theme))
        for t in f.tags or []:
            if t in (
                "vandermonde",
                "binomial_identities",
                "fibonacci_identities",
                "catalan",
            ):
                out.add(str(t))
    return out


def parse_theme_score(notes: str) -> float | None:
    m = re.search(r"score=([0-9.]+)", notes or "")
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def scan_new_authorize_themes(
    ledger: Any,
    *,
    score_floor: float = ORACLE_SCORE_FLOOR,
    lookback: int = 400,
) -> list[dict[str, Any]]:
    """Find NEW hard+oracle-PASS themes with score ≥ floor, not yet accepted.

    Selective: at most one finding per theme (newest eligible).
    Never accept-all. UNKNOWN / thin evidence → omitted.
    """
    already = accepted_themes(ledger)
    findings = list(ledger.all())
    window = findings[-max(int(lookback), 1) :]
    by_theme: dict[str, dict[str, Any]] = {}
    for f in window:
        if f.status != "candidate":
            continue
        tags = set(f.tags or [])
        if "hard_checked" not in tags:
            continue
        theme = (f.meta or {}).get("theme_id")
        if not theme:
            continue
        theme = str(theme)
        if theme in already:
            continue
        notes = f.notes or ""
        if "oracle=PASS" not in notes:
            continue
        score = parse_theme_score(notes)
        if score is None or score < float(score_floor):
            # UNKNOWN / below floor — stay UNKNOWN
            continue
        # Standing trust gate (machine-checked hard path)
        if not meets_standing_trust(score, machine_checked=True):
            continue
        row = {
            "finding_id": f.id,
            "theme": theme,
            "score": score,
            "title": f.title,
            "notes": notes[:240],
            "cycle_id": (f.meta or {}).get("cycle_id"),
            "hard_ok": bool((f.meta or {}).get("hard_ok")),
            "oracle": "PASS",
            "P_min": STANDING_TRUST_P_MIN,
            "meets_standing_trust": True,
        }
        # Keep newest per theme
        by_theme[theme] = row
    return list(by_theme.values())


def persist_hold_state(
    *,
    posture: str = DEFAULT_POSTURE,
    cycle_id: str = "",
    scan: list[dict[str, Any]] | None = None,
    authorize_action: dict[str, Any] | None = None,
    evolve: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snap = {
        "ts": _utc(),
        "when_et": _utc_et_label(),
        "version": 1,
        "mile": "spark3-hold",
        "posture": posture,
        "default_posture": DEFAULT_POSTURE,
        "policy": {
            "light_evolve_watch": True,
            "authorize_only_new_hard_oracle_pass": True,
            "score_floor": ORACLE_SCORE_FLOOR,
            "P_min": STANDING_TRUST_P_MIN,
            "never_accept_all": True,
            "unknown_stays_unknown": True,
            "athanor_inform_only": True,
            "pulsemesh_inform_only": True,
            "no_double_gate": True,
            "no_silent_durable_accept": True,
        },
        "cycle_id": cycle_id,
        "scan_eligible": scan or [],
        "authorize_action": authorize_action or {"did_authorize": False, "reason": "not_run"},
        "evolve": evolve or {},
        "ceiling": (
            "P>=0.70 human authorize selective; tribute; append-only witness; "
            "Athanor/PulseMesh inform-only"
        ),
        "non_claims": [
            "not_AGI",
            "not_consciousness",
            "not_Millennium",
            "not_novel_theorems",
            "not_novel_physics",
        ],
        "ethos": "We light the spark and witness. We do not micromanage the city.",
    }
    if extra:
        snap["extra"] = extra
    HOLD_STATE.parent.mkdir(parents=True, exist_ok=True)
    HOLD_STATE.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return snap


def latest_hold() -> dict[str, Any]:
    if HOLD_STATE.exists():
        try:
            return json.loads(HOLD_STATE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"posture": DEFAULT_POSTURE, "policy": {"never_accept_all": True}}


def build_selective_decisions(
    eligible: list[dict[str, Any]],
    *,
    mile: str = "spark3-hold",
    cap: int = 4,
) -> dict[str, Any]:
    """Build authorize decisions payload — selective, capped, never accept-all."""
    selected = eligible[: max(0, int(cap))]
    items = [
        {
            "finding_id": e["finding_id"],
            "decision": "accepted",
            "rationale": (
                f"Hold-watch selective: theme `{e['theme']}` hard-checked + Oracle PASS "
                f"score={e['score']} ≥ {ORACLE_SCORE_FLOOR}. Standing trust P≥{STANDING_TRUST_P_MIN}. "
                "Not accept-all. Not theorem discovery. UNKNOWN stays UNKNOWN for others."
            ),
        }
        for e in selected
    ]
    return {
        "items": items,
        "policy": "hold_posture_P>=0.70_selective_never_accept_all",
        "mile": mile,
        "P_min": STANDING_TRUST_P_MIN,
        "score_floor": ORACLE_SCORE_FLOOR,
        "never_accept_all": True,
        "unknown_stays_unknown": True,
        "candidates_scanned_eligible": len(eligible),
        "selected": len(items),
        "themes": [e["theme"] for e in selected],
        "authorizer": "James Paul Jackson",
        "delegated_via": "New Bot standing grant (selective authorize under James trust; hold posture)",
    }


__all__ = [
    "DEFAULT_POSTURE",
    "ORACLE_SCORE_FLOOR",
    "accepted_themes",
    "parse_theme_score",
    "scan_new_authorize_themes",
    "scan_all_candidates",
    "persist_hold_state",
    "latest_hold",
    "build_selective_decisions",
]


def scan_all_candidates(
    ledger: Any,
    state: Any | None = None,
    *,
    lookback: int = 400,
) -> list[dict[str, Any]]:
    """Union of theme candidates + improvement proposals with computed P.

    Eligible only when P >= STANDING_TRUST_P_MIN. Never accept-all. Cap elsewhere.
    """
    eligible = scan_new_authorize_themes(ledger, lookback=lookback)
    # Stamp P from score for themes (score already used as confidence proxy)
    for e in eligible:
        if "P" not in e:
            e["P"] = e.get("score")
    # Improvement proposals from society state
    try:
        data = None
        if state is not None:
            data = state.data if hasattr(state, "data") else state
        if data is None:
            from colony.society_state import SocietyState
            data = SocietyState.load().data
        for prop in (data.get("improvement_proposals") or [])[-80:]:
            if prop.get("status") not in ("candidate", "candidate_measured"):
                continue
            # Hearing stays binding: a hearing-rejected proposal never enters the queue,
            # even after close_open_proposals re-labels it candidate_measured.
            if prop.get("hearing_verdict") == "reject":
                continue
            P = prop.get("P")
            if P is None:
                try:
                    from colony.standing_trust import compute_proposal_P
                    P, terms = compute_proposal_P(
                        mutation=prop.get("title") or "",
                        action=prop.get("action") or "",
                        fingerprint=prop.get("fingerprint") or "",
                        bench_delta=(prop.get("delta_aggregate")),
                        cycle_id=prop.get("cycle_id") or "",
                    )
                    prop["P"] = P
                    prop["P_terms"] = terms
                except Exception:
                    P = None
            if P is None or float(P) < STANDING_TRUST_P_MIN:
                continue
            if not meets_standing_trust(P, machine_checked=True):
                continue
            eligible.append({
                "finding_id": prop.get("id"),
                "theme": "improvement_proposal",
                "score": float(P),
                "P": float(P),
                "title": prop.get("title"),
                "notes": (prop.get("hypothesis") or "")[:240],
                "P_min": STANDING_TRUST_P_MIN,
                "meets_standing_trust": True,
                "kind": "improvement_proposal",
            })
    except Exception:
        pass
    # Final P gate
    return [e for e in eligible if float(e.get("P") or e.get("score") or 0) >= STANDING_TRUST_P_MIN]
