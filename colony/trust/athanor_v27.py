"""Athanor v2.5-v2.7 gate on desk self-edits (REPORT-ONLY by default).

Ported from James Jackson's ATHANOR (github.com/jacksonjp0311-gif/Athanor, v2.5.0-v2.7.0).
The ΔΦ / C / H7 math and the APPROVE / REFINE / REJECT rule are James's and are used unchanged
from ``colony.athanor_coherence``.

What this module adds for each lemma-desk change (old impl -> new impl):

1. Validity pre-gate (Athanor 2.5 ``core/validity.py``): every value the after-change bench
   reports (score, seconds, each check) must be numeric and finite, and the bench must not carry
   an error. A failure is a hard REJECT before the coherence gate runs.

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

from colony.athanor_coherence import snapshot_validity

ROOT = Path(__file__).resolve().parent.parent.parent
STATE = ROOT / "society" / "systems" / "athanor_v27.json"
KEEP_ROWS = 50
MODES = ("off", "shadow")


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gate_mode() -> str:
    m = (os.environ.get("COLONY_ATHANOR_GATE") or "shadow").strip().lower()
    return m if m in MODES else "shadow"


def assess_change(*, before: dict[str, Any] | None, after: dict[str, Any] | None,
                  src: str = "", new_src: str = "", before_score: float | None = None,
                  after_score: float | None = None) -> dict[str, Any]:
    """Pure assessment of one change. No side effects."""
    validity = snapshot_validity(after)
    if not validity["passed"]:
        return {"verdict": "REJECT", "reason": "validity pre-gate failed", "validity": validity}
    return {"verdict": "APPROVE", "reason": "validity pre-gate passed", "validity": validity}


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
    try:
        a = assess_change(before=before, after=after, src=src, new_src=new_src,
                          before_score=before_score, after_score=after_score)
        row.update(verdict=a["verdict"], reason=a["reason"], validity_passed=a["validity"]["passed"],
                   validity_failures=a["validity"]["failures"],
                   validity_first_failure=a["validity"].get("first_failure"))
    except Exception as exc:  # noqa: BLE001
        row.update(verdict="ERROR", reason=f"assess_error:{type(exc).__name__}:{exc}"[:200])
    row["would_block"] = bool(tentative_keep and row.get("verdict") != "APPROVE")
    row["block"] = False
    try:
        st = _load()
        tot = st.setdefault("totals", {})
        tot["assessed"] = int(tot.get("assessed", 0)) + 1
        tot[f"verdict_{row.get('verdict')}"] = int(tot.get(f"verdict_{row.get('verdict')}", 0)) + 1
        if row.get("validity_passed") is False:
            tot["validity_failed"] = int(tot.get("validity_failed", 0)) + 1
        if row["would_block"]:
            tot["would_block_keep"] = int(tot.get("would_block_keep", 0)) + 1
        st["rows"] = (st.get("rows") or [])[-(KEEP_ROWS - 1):] + [row]
        st["updated_at"] = row["ts"]
        st["note"] = ("Athanor v2.5-v2.7 gate (James Jackson's ATHANOR) on desk self-edits. "
                      "shadow = report-only: never changes keep/revert, scores, P, Oracle or authorize.")
        _save(st)
    except Exception:  # noqa: BLE001
        pass
    return row
