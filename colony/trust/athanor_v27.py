"""Athanor v2.5-v2.7 gate on desk self-edits (REPORT-ONLY by default).

Ported from James Jackson's ATHANOR (github.com/jacksonjp0311-gif/Athanor, v2.5.0-v2.7.0).
The ΔΦ / C / H7 math and the APPROVE / REFINE / REJECT rule are James's and are used unchanged
from ``colony.athanor_coherence``.

What this module adds for each lemma-desk change (old impl -> new impl):

1. Validity pre-gate (Athanor 2.5 ``core/validity.py``): every value the after-change bench
   reports (score, seconds, each check) must be numeric and finite, and the bench must not carry
   an error. A failure is a hard REJECT before the coherence gate runs.
2. Conservative adaptive drift tolerance (Athanor 2.5 ``TUNED_ADAPTIVE_CONSERVATIVE``, registry
   ``selfmod/adaptive@1.1.0``: tau 0.75, gamma 6, p 3, basis best, cap 6, floor 0.7, half-life 50).
   The change is turned into Athanor's self-edit trajectory over probes = every bench check plus
   the (speed-neutral) score: per probe, behaviour drift = 1 if a check flips or is lost (0 if a
   new check is added passing), and |Δscore| / κ for the score (κ = 0.10, Athanor's TSP choice);
   plus w_s · S, the AST token-bag distance between old and new impl (w_s = 0.5). ΔΦ_t = ‖d_t‖,
   C = 1/(1+ΔΦ), H7 at tau, verdict by the unchanged rule. Only APPROVE would let a keep through.
   The error term is e = 1 − lemma score before the change (the desk's own objective, chosen a
   priori, not tuned); t counts assessed changes. The tsp/adaptive@1.1.0 retune (tau 0.78, no
   decay) and the colony's fixed-tolerance tau 0.70 gate are reported alongside for comparison.

Mode (one env var, ``COLONY_ATHANOR_GATE``):

* ``shadow`` (default) — assess and log only. Never changes a keep/revert, a score, a P value,
  an Oracle verdict, authorization or the 0.70 gate.
* ``off``    — do nothing (no assessment, no log).

State: society/systems/athanor_v27.json (totals + last rows).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from colony.athanor_coherence import (
    ADAPTIVE_PROFILES,
    CONSERVATIVE_PROFILE,
    CoherenceGovernor,
    edit_trajectory,
    scheduled_tolerance,
    snapshot_validity,
    structural_distance,
)

ROOT = Path(__file__).resolve().parent.parent.parent
STATE = ROOT / "society" / "systems" / "athanor_v27.json"
KEEP_ROWS = 50
MODES = ("off", "shadow")
KAPPA = 0.10            # score probe scale (Athanor 2.6 TSP: relative change of 10 % = one unit)
STRUCTURE_WEIGHT = 0.5  # Athanor w_s


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gate_mode() -> str:
    m = (os.environ.get("COLONY_ATHANOR_GATE") or "shadow").strip().lower()
    return m if m in MODES else "shadow"


def behaviour_drift(before: dict[str, Any] | None, after: dict[str, Any] | None,
                    before_score: float | None = None, after_score: float | None = None) -> list[float]:
    """Raw (tol = 1) behaviour drift per probe: every bench check, then the score."""
    b = (before or {}).get("checks") or {}
    a = (after or {}).get("checks") or {}
    out: list[float] = []
    for k in sorted(set(b) | set(a)):
        if k in b and k in a:
            out.append(abs(float(bool(a[k])) - float(bool(b[k]))))
        elif k in a:  # newly added check: coverage, not a behaviour change, if it passes
            out.append(0.0 if a[k] else 1.0)
        else:  # check lost
            out.append(1.0)
    bs = before_score if before_score is not None else (before or {}).get("score")
    as_ = after_score if after_score is not None else (after or {}).get("score")
    try:
        out.append(abs(float(as_) - float(bs)) / KAPPA)
    except (TypeError, ValueError):
        out.append(float("inf"))
    return out


def profile_verdict(profile: str, behaviour: list[float], structural: float, *, e_cur: float,
                    e_best: float, step: int) -> dict[str, Any]:
    cfg = ADAPTIVE_PROFILES[profile]
    tol = scheduled_tolerance(e_cur ** 2, e_best ** 2, 1.0, step, cfg.get("gamma"), cfg)
    traj = edit_trajectory(behaviour, structural, tol=tol, structure_weight=STRUCTURE_WEIGHT)
    v = CoherenceGovernor(threshold_h7=cfg["threshold_h7"], refine_floor=cfg["refine_floor"]).verify_trajectory(traj)
    return {"verdict": v.verdict, "reason": v.reason, "h7": round(v.h7, 6), "tau": cfg["threshold_h7"],
            "tol": round(tol, 6), "dphi_max": round(max((abs(x) for x in _dphi(traj)), default=0.0), 6)}


def _dphi(traj: list[list[float]]) -> list[float]:
    from colony.athanor_coherence import delta_phi
    return delta_phi(traj)


def gate_profile() -> str:
    """Profile the gate verdict uses: the conservative setting, unless the promotion suite (or a
    human) names another registered profile in COLONY_ATHANOR_PROFILE."""
    p = (os.environ.get("COLONY_ATHANOR_PROFILE") or "").strip()
    return p if p in ADAPTIVE_PROFILES else CONSERVATIVE_PROFILE


def assess_change(*, before: dict[str, Any] | None, after: dict[str, Any] | None,
                  src: str = "", new_src: str = "", before_score: float | None = None,
                  after_score: float | None = None, step: int = 0,
                  best_e: float | None = None) -> dict[str, Any]:
    """Pure assessment of one change (validity pre-gate, then the conservative coherence gate)."""
    validity = snapshot_validity(after)
    bs = before_score if before_score is not None else (before or {}).get("score")
    try:
        e_cur = max(0.0, 1.0 - float(bs))
    except (TypeError, ValueError):
        e_cur = float("inf")
    e_best = min(e_cur, best_e) if best_e is not None else e_cur
    out: dict[str, Any] = {"validity": validity, "e_cur": e_cur, "e_best": e_best, "step": int(step)}
    if not validity["passed"]:
        out.update(verdict="REJECT", reason="validity pre-gate failed", profiles={})
        return out
    beh = behaviour_drift(before, after, before_score, after_score)
    S = structural_distance(src, new_src) if (src or new_src) else 0.0
    profiles = {name: profile_verdict(name, beh, S, e_cur=e_cur, e_best=e_best, step=step)
                for name in ADAPTIVE_PROFILES}
    gp = gate_profile()
    g = profiles[gp]
    out.update(verdict=g["verdict"], reason=f"{gp}: {g['reason']}", gate_profile=gp, profiles=profiles,
               n_probes=len(beh), drift_nonzero=[round(x, 6) for x in beh if x], structural=round(S, 6))
    return out


def _load() -> dict[str, Any]:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"version": 1, "totals": {}, "rows": []}


def _save(st: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=2, default=list) + "\n", encoding="utf-8")


def gate_desk_change(*, before: dict[str, Any] | None, after: dict[str, Any] | None, src: str = "",
                     new_src: str = "", before_score: float | None = None,
                     after_score: float | None = None, mutation: str = "", kind: str = "",
                     cycle_id: str = "", tentative_keep: bool = False) -> dict[str, Any] | None:
    """Assess one desk change and log it. Returns the row; ``row['block']`` is always False here."""
    mode = gate_mode()
    if mode == "off":
        return None
    row: dict[str, Any] = {"ts": _utc(), "cycle_id": cycle_id, "mutation": mutation, "kind": kind,
                           "mode": mode, "tentative_keep": bool(tentative_keep)}
    st = _load()
    sched = st.setdefault("schedule", {"step": 0, "best_e": None})
    try:
        a = assess_change(before=before, after=after, src=src, new_src=new_src,
                          before_score=before_score, after_score=after_score,
                          step=int(sched.get("step") or 0), best_e=sched.get("best_e"))
        row.update(verdict=a["verdict"], reason=a["reason"], validity_passed=a["validity"]["passed"],
                   validity_failures=a["validity"]["failures"],
                   validity_first_failure=a["validity"].get("first_failure"),
                   profiles=a.get("profiles"), n_probes=a.get("n_probes"),
                   drift_nonzero=a.get("drift_nonzero"), structural=a.get("structural"),
                   e_cur=a["e_cur"], e_best=a["e_best"], step=a["step"], gate_profile=a.get("gate_profile"))
        if a["e_best"] == a["e_best"] and a["e_best"] != float("inf"):
            sched["best_e"] = a["e_best"]
        sched["step"] = int(sched.get("step") or 0) + 1
    except Exception as exc:  # noqa: BLE001
        row.update(verdict="ERROR", reason=f"assess_error:{type(exc).__name__}:{exc}"[:200])
    row["would_block"] = bool(tentative_keep and row.get("verdict") != "APPROVE")
    row["block"] = False
    row["would_block_by_profile"] = {n: bool(tentative_keep and (row.get("validity_passed") is False
                                                                 or pv["verdict"] != "APPROVE"))
                                     for n, pv in (row.get("profiles") or {}).items()}
    try:
        tot = st.setdefault("totals", {})
        tot["assessed"] = int(tot.get("assessed", 0)) + 1
        tot[f"verdict_{row.get('verdict')}"] = int(tot.get(f"verdict_{row.get('verdict')}", 0)) + 1
        if row.get("validity_passed") is False:
            tot["validity_failed"] = int(tot.get("validity_failed", 0)) + 1
        if row["would_block"]:
            tot["would_block_keep"] = int(tot.get("would_block_keep", 0)) + 1
        for name, pv in (row.get("profiles") or {}).items():
            key = f"profile:{name}:{pv['verdict']}"
            tot[key] = int(tot.get(key, 0)) + 1
            if row["would_block_by_profile"].get(name):
                kb = f"profile:{name}:would_block_keep"
                tot[kb] = int(tot.get(kb, 0)) + 1
        st["rows"] = (st.get("rows") or [])[-(KEEP_ROWS - 1):] + [row]
        st["updated_at"] = row["ts"]
        st["note"] = ("Athanor v2.5-v2.7 gate (James Jackson's ATHANOR) on desk self-edits. "
                      "shadow = report-only: never changes keep/revert, scores, P, Oracle or authorize.")
        _save(st)
    except Exception:  # noqa: BLE001
        pass
    return row
