"""Re-judge checks the Oracle killed because the old shifter saw no literal range.

The kill ``held_out_shift_not_applicable(no_literal_range)`` was the shifter
refusing a window-tuple loop. The current shifter (colony.trust.shifted_holdout)
either runs a disjoint window or reports ``no_data_headroom``. This module
re-runs that sensor and enables a killed check only when the sensor returns a
real pass. A check with no data headroom stays out. The Oracle budget, the
authored-check cap, and the catalog format are unchanged. Nothing here is a
special case for one check name.
"""
from __future__ import annotations

import ast
import json
from typing import Any, Callable

from colony.authoring import (
    AUTHORED_PREFIX,
    MAX_AUTHORED_TOTAL,
    _entries,
    insert_disabled,
    strip_authored_check,
)
from colony.conjecture_mutations import enable_hard

# The Oracle prefixes the shifter reason with held_out_.
LITERAL_RANGE_KILL = "held_out_shift_not_applicable(no_literal_range)"
HEADROOM_REASON = "shift_not_applicable(no_data_headroom)"

Probe = Callable[[str, str], dict[str, Any]]


def literal_range_kills(history: str) -> list[str]:
    """Unique mutations reverted with the no-literal-range Oracle kill, first seen first."""
    out: list[str] = []
    seen: set[str] = set()
    for ln in (history or "").splitlines():
        if LITERAL_RANGE_KILL not in ln:
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if row.get("decision") != "revert":
            continue
        if LITERAL_RANGE_KILL not in str(row.get("note") or ""):
            continue
        name = str(row.get("mutation") or "").strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _catalog_flag(src: str, name: str) -> bool | None:
    """True/False when the catalog lists name, else None."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    for n, _node, flag in _entries(tree):
        if n == name:
            return flag
    return None


def _authored_count(src: str) -> int:
    tree = ast.parse(src)
    return sum(1 for n, _c, _f in _entries(tree) if str(n).startswith(AUTHORED_PREFIX))


def _passed(result: dict[str, Any] | None) -> bool:
    if not result:
        return False
    return result.get("status") == "pass" and result.get("ok") is True and result.get("applied") is True


def apply_rejudge(
    src: str,
    history: str,
    probe: Probe,
    recover: dict[str, str] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Enable killed checks the probe passes. Leave no-headroom checks out.

    ``probe(name, src)`` is the Oracle's shifted-window sensor (or a test double).
    ``recover`` supplies the function source for a name no longer in the catalog.
    A recovered check is inserted disabled, probed, and removed again unless the
    probe passes. An already-enabled check is left enabled. The authored cap is
    not raised: a new authored name is not inserted once the catalog is full.
    """
    bodies = recover or {}
    report: list[dict[str, Any]] = []
    for name in literal_range_kills(history):
        flag = _catalog_flag(src, name)
        inserted = False
        if flag is None:
            body = bodies.get(name)
            if not body:
                report.append({"name": name, "action": "missing", "reason": "no_source"})
                continue
            if name.startswith(AUTHORED_PREFIX) and _authored_count(src) >= MAX_AUTHORED_TOTAL:
                report.append({"name": name, "action": "kept_out", "reason": "authored_cap"})
                continue
            nxt = insert_disabled(src, name, body.strip() + "\n")
            if not nxt:
                report.append({"name": name, "action": "missing", "reason": "insert_failed"})
                continue
            src = nxt
            inserted = True
            flag = False
        if flag is True:
            report.append({"name": name, "action": "already_enabled"})
            continue
        try:
            result = probe(name, src)
        except Exception as exc:  # noqa: BLE001 — a broken probe is not a pass
            result = {"ok": False, "status": "not_tested", "reason": f"probe_error:{type(exc).__name__}", "applied": False}
        if _passed(result):
            enabled = enable_hard(src, name)
            if enabled:
                src = enabled
                report.append({"name": name, "action": "restored", "reason": result.get("reason")})
            else:
                report.append({"name": name, "action": "kept_out", "reason": "enable_failed"})
                if inserted:
                    src = strip_authored_check(src, name) or src
            continue
        reason = str((result or {}).get("reason") or "not_a_pass")
        if inserted:
            src = strip_authored_check(src, name) or src
        report.append({
            "name": name,
            "action": "kept_out",
            "reason": reason,
            "headroom": reason == HEADROOM_REASON,
        })
    return src, report
