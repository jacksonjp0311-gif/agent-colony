"""Standing trust gate — P≥0.70 selective authorize (James / SPARK2 telemetry mile).

Never silent accept-all. UNKNOWN stays UNKNOWN when evidence is thin.
Not AGI. Not novel theorems.
"""
from __future__ import annotations

# SPARK2: lowered from 0.75 → 0.70 (selective; never accept-all)
STANDING_TRUST_P_MIN: float = 0.70
STANDING_TRUST_P_MIN_BEFORE: float = 0.75  # prior mile compare field


def meets_standing_trust(confidence: float | None, *, machine_checked: bool = False) -> bool:
    """True iff confidence ≥ P_MIN and evidence is machine-checked. Selective gate."""
    if not machine_checked:
        return False
    if confidence is None:
        return False
    try:
        p = float(confidence)
    except (TypeError, ValueError):
        return False
    return p >= STANDING_TRUST_P_MIN


def threshold_compare(confidence: float | None) -> dict:
    """Before/after compare for authorize receipts (0.75 → 0.70)."""
    try:
        p = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        p = None
    return {
        "confidence": p,
        "P_min_before": STANDING_TRUST_P_MIN_BEFORE,
        "P_min_after": STANDING_TRUST_P_MIN,
        "would_pass_before": (p is not None and p >= STANDING_TRUST_P_MIN_BEFORE),
        "would_pass_after": (p is not None and p >= STANDING_TRUST_P_MIN),
        "newly_eligible_at_0_70": (
            p is not None
            and p >= STANDING_TRUST_P_MIN
            and p < STANDING_TRUST_P_MIN_BEFORE
        ),
    }


import math
from typing import Any


def compute_proposal_P(
    *,
    mutation: str = "",
    action: str = "",
    fingerprint: str = "",
    oracle: dict[str, Any] | None = None,
    novelty: dict[str, Any] | None = None,
    bench_delta: float | None = None,
    lesson_consistency: float | None = None,
) -> tuple[float | None, dict[str, float]]:
    """Machine-checked selective P for authorize queue.

    P = clip(0.35*P_oracle + 0.25*P_novelty + 0.25*P_bench + 0.15*P_lesson)
    Returns (P, terms). If critical evidence missing → P=None (UNKNOWN, not eligible).
    """
    terms: dict[str, float] = {}
    # --- P_oracle ---
    p_oracle = None
    ora = oracle
    if ora is None:
        # Look up last oracle row for this mutation/theme
        try:
            from pathlib import Path as _P
            import json as _json
            log = _P(__file__).resolve().parent.parent / "data" / "commons" / "oracle.jsonl"
            if log.exists():
                for ln in reversed(log.read_text(encoding="utf-8").splitlines()):
                    if not ln.strip():
                        continue
                    try:
                        e = _json.loads(ln)
                    except Exception:
                        continue
                    mut = str(e.get("mutation") or "")
                    if mut and (mut == mutation or mut in mutation or mutation in mut):
                        ora = e
                        break
        except Exception:
            ora = None
    if ora is not None:
        passed = bool(ora.get("passed"))
        hear = ora.get("hear") or {}
        bus_ok = bool(hear.get("bus_ok"))
        credit = bool(ora.get("fitness_credit"))
        if passed and bus_ok and credit:
            p_oracle = 1.0
        elif passed and not bus_ok:
            p_oracle = 0.5  # legacy
        else:
            p_oracle = 0.0
    # Missing oracle → UNKNOWN for authorize eligibility (still compute soft P for display)
    terms["P_oracle"] = float(p_oracle) if p_oracle is not None else 0.0

    # --- P_novelty ---
    nov = novelty or {}
    if not nov:
        try:
            from colony.novelty_gate import evaluate as novelty_evaluate
            nov = novelty_evaluate(mutation=mutation or action, kind="process", claim_text=action)
        except Exception:
            nov = {"textbook_reuse": 0.5}
    _tr = nov.get("textbook_reuse")
    p_nov = max(0.0, 1.0 - float(1.0 if _tr is None else _tr))
    # Repeat fingerprint → 0
    if fingerprint:
        try:
            from colony.lessons import load_lessons
            for e in load_lessons(limit=200):
                if e.get("proposal_fingerprint") == fingerprint and e.get("type") == "repeat_proposal":
                    p_nov = 0.0
                    nov = {**nov, "repeat_blocked": True}
                    break
        except Exception:
            pass
    if nov.get("repeat_blocked"):
        p_nov = 0.0
    terms["P_novelty"] = round(p_nov, 4)

    # --- P_bench ---
    if bench_delta is None:
        p_bench = 0.5
    elif bench_delta <= 0:
        p_bench = 0.3
    else:
        p_bench = 1.0 / (1.0 + math.exp(-10.0 * float(bench_delta)))
    terms["P_bench"] = round(float(p_bench), 4)

    # --- P_lesson ---
    if lesson_consistency is not None:
        p_les = float(lesson_consistency)
    else:
        p_les = 0.4  # neutral
        try:
            from colony.lessons import load_lessons, load_human_guides, catalog_hints_from_lessons
            # Match catalog_hint / human_guide
            hints = catalog_hints_from_lessons(lookback=30)
            blob = f"{mutation} {action}".lower()
            for h in hints:
                add = str(h.get("add_mutation") or "").lower()
                if add and add in blob:
                    p_les = 1.0
                    break
            for e in load_human_guides():  # guides apply however old they are
                if any(t in blob for t in (e.get("tags") or []) if isinstance(t, str)):
                    p_les = max(p_les, 1.0)
            for e in load_lessons(limit=40):
                if e.get("type") == "hearing_reject" and fingerprint and e.get("proposal_fingerprint") == fingerprint:
                    p_les = 0.0
                    break
        except Exception:
            pass
    terms["P_lesson"] = round(float(p_les), 4)

    # If oracle entirely missing, return None (UNKNOWN — not eligible)
    if p_oracle is None and not mutation and not action:
        return None, terms

    P = 0.35 * terms["P_oracle"] + 0.25 * terms["P_novelty"] + 0.25 * terms["P_bench"] + 0.15 * terms["P_lesson"]
    P = round(max(0.0, min(1.0, P)), 4)
    # Soft rule: if oracle missing for a themed mutation, mark UNKNOWN
    if p_oracle is None and mutation:
        # Still return computed P but callers that require machine_checked oracle may treat None
        # Plan: UNKNOWN when any critical term missing → use None when oracle missing
        return None, terms
    return P, terms


def attach_P_to_proposal(prop: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Stamp P + terms onto a proposal dict."""
    P, terms = compute_proposal_P(
        mutation=kwargs.get("mutation") or prop.get("title") or "",
        action=kwargs.get("action") or prop.get("action") or "",
        fingerprint=kwargs.get("fingerprint") or prop.get("fingerprint") or "",
        oracle=kwargs.get("oracle"),
        novelty=kwargs.get("novelty"),
        bench_delta=kwargs.get("bench_delta"),
        lesson_consistency=kwargs.get("lesson_consistency"),
    )
    prop["P"] = P
    prop["P_terms"] = terms
    prop["confidence"] = P
    prop["machine_checked"] = P is not None
    return prop
