"""Item 98: scope the Athanor per-area veto to the bench it was calibrated on.

Finding (replay in scripts/replay_item98_veto_scope.py): every stem_enable since the STEM pack went
live was blocked by ``area veto: score beyond calibrated limit``. The veto thresholds in
colony/trust/athanor_probe_calibration.json were calibrated (evals/athanor_probe/calibrate.py) only
on historical lemma-desk hard_enable changes measured on the LEMMA microbench, whose hard
component is saturated (>= 28 hard passes), so one added check moves the score block by ~1e-4 and
the calibrated score limit is 0.015. A stem_enable is measured on the KINEMATICS microbench (4 hard
checks); one added passing check honestly moves its score 0.825 -> 0.8688 and hard_pass/28 by
1/28, so the score-block drift is a constant 0.056515 for every STEM enable regardless of what the
check is. The veto there measures the size of the STEM bench, not the integrity of the edit:
a category mismatch.

Scope (nothing in Athanor's math, ΔΦ / C / H7, thresholds, profiles or the calibration file
changes; the Athanor verdict itself still has to be APPROVE): the ``score`` veto area is waived
for a change only when ALL hold —
  * kind == "stem_enable" (a change judged on the kinematics bench, not the calibrated lemma bench)
  * ``score`` is the ONLY vetoed area (every other area still vetoes as before)
  * the drift is exactly one added passing check: checks_basic, checks_authored and tier_ok drift
    0, checks_catalog drift == 0.5 (one absent->pass), hard_pass after == before + 1, score did not
    fall
  * the STEM triviality filter says not a tautology and the STEM held-out test survives (so a
    textbook tautology can never be kept through this path)
Everything else (lemma desk, hard_enable, any other kind, any other area) is untouched.

Switch: ``COLONY_ATHANOR_VETO_SCOPE`` = live (default) | shadow (log only) | off. Always off on the
control arm (self_mod_enabled() is False there).
"""
from __future__ import annotations

import os
from typing import Any

MODES = ("off", "shadow", "live")
SCOPED_KIND = "stem_enable"
WAIVABLE_AREA = "score"
EPS = 1e-6


def scope_mode() -> str:
    try:
        from colony.arm import self_mod_enabled
        if not self_mod_enabled():
            return "off"
    except Exception:  # noqa: BLE001
        return "off"
    m = (os.environ.get("COLONY_ATHANOR_VETO_SCOPE") or "live").strip().lower()
    return m if m in MODES else "off"


def _hard_pass(snap: dict[str, Any] | None) -> int | None:
    s = snap or {}
    if s.get("n_hard_pass") is not None:
        try:
            return int(s["n_hard_pass"])
        except (TypeError, ValueError):
            return None
    checks = s.get("checks")
    if isinstance(checks, dict):
        return sum(1 for k, v in checks.items() if not str(k).startswith("basic:") and v)
    return None


def structural_match(*, kind: str, veto: dict[str, Any] | None, raw: dict[str, Any] | None,
                     hard_pass_before: int | None, hard_pass_after: int | None,
                     score_before: float | None, score_after: float | None) -> dict[str, Any]:
    """Pure: is this veto the bench-size category mismatch (one added passing STEM check)?"""
    v, r = veto or {}, raw or {}
    why: list[str] = []
    if kind != SCOPED_KIND:
        why.append("kind_not_stem_enable")
    if not v.get("vetoed"):
        why.append("not_vetoed")
    if list(v.get("areas") or []) != [WAIVABLE_AREA]:
        why.append("areas_not_only_score")
    for k in ("checks_basic", "checks_authored", "tier_ok"):
        if abs(float(r.get(k, 0.0) or 0.0)) > EPS:
            why.append(f"{k}_drift")
    if abs(float(r.get("checks_catalog", 0.0) or 0.0) - 0.5) > EPS:
        why.append("not_exactly_one_added_check")
    if hard_pass_before is None or hard_pass_after is None or hard_pass_after != hard_pass_before + 1:
        why.append("hard_pass_not_plus_one")
    try:
        if float(score_after) + EPS < float(score_before):
            why.append("score_fell")
    except (TypeError, ValueError):
        why.append("score_missing")
    return {"match": not why, "why_not": why}


def stem_quality(mutation: str) -> dict[str, Any]:
    """Not a tautology AND survives the STEM held-out (item 95 tests, read-only)."""
    try:
        from colony.stem_held_out import held_out, triviality
        t = triviality(mutation) or {}
        if t.get("trivial") is not False:
            return {"ok": False, "why": f"trivial_or_unknown:{t.get('reason')}"}
        h = held_out(mutation) or {}
        if not h.get("survives"):
            return {"ok": False, "why": f"held_out:{h.get('reason') or 'failed'}"}
        return {"ok": True, "why": "non_trivial_and_held_out"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "why": f"error:{type(exc).__name__}"}


def assess(*, kind: str, mutation: str, veto: dict[str, Any] | None, raw: dict[str, Any] | None,
           before: dict[str, Any] | None, after: dict[str, Any] | None,
           score_before: float | None, score_after: float | None) -> dict[str, Any]:
    """Return {'mode', 'waive', ...}. ``waive`` is True only in live mode when every condition holds."""
    mode = scope_mode()
    out: dict[str, Any] = {"mode": mode, "waive": False, "item": 98}
    if mode == "off":
        return out
    sm = structural_match(kind=kind, veto=veto, raw=raw, hard_pass_before=_hard_pass(before),
                          hard_pass_after=_hard_pass(after), score_before=score_before,
                          score_after=score_after)
    out["structural"] = sm
    if not sm["match"]:
        return out
    q = stem_quality(mutation)
    out["quality"] = q
    out["would_waive"] = bool(q["ok"])
    out["waive"] = bool(q["ok"] and mode == "live")
    return out
