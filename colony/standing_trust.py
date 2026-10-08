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


import json
import math
import re
from pathlib import Path
from typing import Any

ORACLE_LOG = Path(__file__).resolve().parent.parent / "data" / "commons" / "oracle.jsonl"
_TARGET_ACTION_RE = re.compile(
    r"(?:seek_enable|hard_enable|hard_check|stem_enable|enable):([a-z][a-z0-9_]{2,})"
)


def resolve_proposal_target(*, action: str = "", mutation: str = "") -> str:
    """The real lemma/check a proposal targets, from structured fields; "" if unresolved.

    Order: the action field (``seek_enable:<name>`` etc.), then a backticked name in the
    title. A name only counts if it is a real catalog entry (benchmark artifact catalog or
    desk mutation catalog) — free text never resolves.
    """
    cands: list[str] = []
    m = _TARGET_ACTION_RE.search(str(action or "").lower())
    if m:
        cands.append(m.group(1))
    m = re.search(r"`([a-z][a-z0-9_]{2,})`", str(mutation or "").lower())
    if m:
        cands.append(m.group(1))
    if not cands:
        return ""
    known: set[str] = set()
    try:
        from colony.conjecture_mutations import all_snippets
        known = {str(n) for n, _k, _s in all_snippets()}
    except Exception:
        pass
    for c in cands:
        try:
            from colony.lessons import target_enabled
            if target_enabled(c) is not None:
                return c
        except Exception:
            pass
        if c in known:
            return c
    return ""


def target_oracle_verdict(target: str, *, cycle_id: str = "", log: Path | None = None) -> dict[str, Any] | None:
    """Latest Oracle row judging exactly ``target`` (the real lemma), or None.

    Kills count whenever they are the latest verdict (fail closed). A pass only counts when
    the Oracle judged the target in the proposal's own cycle — an old pass is not credit
    for a new proposal (returns None → caller falls back).
    """
    if not target:
        return None
    path = log or ORACLE_LOG
    if not path.exists():
        return None
    latest: dict[str, Any] | None = None
    try:
        with path.open(encoding="utf-8") as fh:
            for ln in fh:
                if f'"{target}"' not in ln:
                    continue
                try:
                    e = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if str(e.get("mutation") or "") == target:
                    latest = e
    except OSError:
        return None
    if latest is None:
        return None
    if latest.get("passed") and cycle_id and str(latest.get("cycle_id") or "") != cycle_id:
        return None
    if latest.get("passed") and not cycle_id:
        return None  # cannot prove freshness → no credit from this path
    return latest


def target_judged_in_cycle(target: str, cycle_id: str, *, log: Path | None = None) -> dict[str, Any] | None:
    """Latest Oracle row judging exactly ``target`` IN ``cycle_id`` (pass or kill), else None.

    Used to decide which claim a seek proposal submits: when the Oracle judged the real
    target in the proposal's own cycle, that verdict IS the proposal's Oracle evidence and
    the separate title-text process check is not run (no phantom kill on the title).
    """
    if not target or not cycle_id:
        return None
    path = log or ORACLE_LOG
    if not path.exists():
        return None
    latest: dict[str, Any] | None = None
    try:
        with path.open(encoding="utf-8") as fh:
            for ln in fh:
                if f'"{target}"' not in ln:
                    continue
                try:
                    e = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if str(e.get("mutation") or "") == target and str(e.get("cycle_id") or "") == cycle_id:
                    latest = e
    except OSError:
        return None
    return latest


DEFERRED_TITLE_SOURCE = "novelty_gate_deferred_title"


def run_title_check(*, mutation: str, action: str, deferred: bool = False) -> dict[str, Any]:
    """The legacy title-text check, unchanged: novelty gate (+ its Oracle run) on the title
    as kind=process. Used for unresolved proposals, and deferred for resolved proposals
    whose target the Oracle did not judge in their cycle.

    A deferred run is the fail-closed path (the target was never judged), so its Oracle row is
    labelled ``novelty_gate_deferred_title`` and its kill counts toward the kill cooldown; only
    plain ``novelty_gate`` title kills of a resolved target are filtered from the cooldown.
    """
    from colony.novelty_gate import evaluate as novelty_evaluate
    if deferred:
        return novelty_evaluate(mutation=mutation or action, kind="process", claim_text=action,
                                oracle_source=DEFERRED_TITLE_SOURCE)
    return novelty_evaluate(mutation=mutation or action, kind="process", claim_text=action)


def _p_oracle_from_target(row: dict[str, Any]) -> float:
    """Map the real Oracle verdict on the target to P_oracle.

    1.0 = passed + fitness_credit + sense checks (held-out, stripped, CAS) all passed on the
          real lemma. The proposal's own hearing is enforced separately (Hearing Chamber
          verdict; rejected proposals never enter the queue), so bus_ok is not re-required.
    0.5 = passed without fitness credit.  0.0 = killed.
    """
    passed = bool(row.get("passed"))
    credit = bool(row.get("fitness_credit"))
    sense = row.get("sense") or {}
    sense_pass = bool(sense.get("sense_pass", passed))
    if passed and credit and sense_pass:
        return 1.0
    if passed:
        return 0.5
    return 0.0


def compute_proposal_P(
    *,
    mutation: str = "",
    action: str = "",
    fingerprint: str = "",
    oracle: dict[str, Any] | None = None,
    novelty: dict[str, Any] | None = None,
    bench_delta: float | None = None,
    lesson_consistency: float | None = None,
    cycle_id: str = "",
    defer_title_check: bool = False,
) -> tuple[float | None, dict[str, float]]:
    """Machine-checked selective P for authorize queue.

    P = clip(0.35*P_oracle + 0.25*P_novelty + 0.25*P_bench + 0.15*P_lesson)
    Returns (P, terms). If critical evidence missing → P=None (UNKNOWN, not eligible).

    P_oracle: when the proposal's target lemma resolves (action/title → catalog entry) and
    the Oracle judged that real lemma (this cycle for a pass; any time for a kill), use that
    verdict; a resolved target with no fresh verdict gets 0 (fail closed). Unresolved
    targets keep the legacy title lookup unchanged.

    Title check (which claim is submitted — the Oracle's checks are unchanged):
    - resolved target judged by the Oracle in ``cycle_id`` → that verdict is the evidence;
      the title-text process check is NOT run (P_novelty uses the same textbook-reuse score
      the gate would compute, without submitting the title to the Oracle).
    - resolved target not (yet) judged and ``defer_title_check`` → skip now, flag
      ``title_check_deferred``; the caller runs :func:`run_title_check` at measurement if
      the target still has no verdict in that cycle (fail closed: the kill still lands).
    - unresolved → legacy title check, unchanged.
    """
    terms: dict[str, float] = {}
    _target_for_title = ""
    try:
        _target_for_title = resolve_proposal_target(action=action, mutation=mutation)
    except Exception:
        _target_for_title = ""
    # --- P_oracle ---
    p_oracle = None
    ora = oracle
    if ora is None:
        target = ""
        try:
            target = resolve_proposal_target(action=action, mutation=mutation)
            row = target_oracle_verdict(target, cycle_id=cycle_id) if target else None
        except Exception:
            row = None
        if row is not None:
            p_oracle = _p_oracle_from_target(row)
            terms["P_oracle_target_resolved"] = 1.0
        elif target:
            # Real target named but no fresh Oracle verdict on it: fail closed, no credit
            # (never borrow a title match or an old pass).
            p_oracle = 0.0
            terms["P_oracle_target_resolved"] = 0.0
    if ora is None and p_oracle is None:
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
    if ora is not None and p_oracle is None:
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
        judged = None
        if _target_for_title:
            try:
                judged = target_judged_in_cycle(_target_for_title, cycle_id)
            except Exception:
                judged = None
        if _target_for_title and (judged is not None or defer_title_check):
            try:
                from colony.novelty_gate import textbook_reuse_score
                nov = {"textbook_reuse": textbook_reuse_score((mutation or action).strip(), action)}
            except Exception:
                nov = {"textbook_reuse": 0.5}
            if judged is not None:
                terms["title_check_skipped_target_judged"] = 1.0
            else:
                terms["title_check_deferred"] = 1.0
        else:
            try:
                nov = run_title_check(mutation=mutation, action=action)
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
        cycle_id=kwargs.get("cycle_id") or prop.get("cycle_id") or "",
    )
    prop["P"] = P
    prop["P_terms"] = terms
    prop["confidence"] = P
    prop["machine_checked"] = P is not None
    return prop
