"""Provenance cross-check: a machine 'keep' is authorizable only if the Oracle log holds a
matching PASS row (same mutation, same cycle). Defends the standing-trust authorize path
against fabricated ledger metrics (a finding that merely *claims* keep / P / scores)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from colony.oracle import ORACLE_LOG


def oracle_backed(mutation: str, cycle_id: str, *, log: Path | None = None) -> dict[str, Any]:
    path = log or ORACLE_LOG
    if not mutation or not cycle_id or not path.exists():
        return {"ok": False, "reason": "missing_mutation_cycle_or_log"}
    for ln in path.read_text(encoding="utf-8").splitlines():
        if mutation not in ln or cycle_id not in ln:
            continue
        try:
            e = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if e.get("mutation") == mutation and e.get("cycle_id") == cycle_id and e.get("passed") and e.get("fitness_credit"):
            return {"ok": True, "reason": "oracle_pass_row_found"}
    return {"ok": False, "reason": "no_matching_oracle_pass"}


def finding_oracle_backed(f: Any) -> dict[str, Any]:
    meta = getattr(f, "meta", None) or {}
    return oracle_backed(str(meta.get("mutation") or ""), str(meta.get("cycle_id") or ""))
