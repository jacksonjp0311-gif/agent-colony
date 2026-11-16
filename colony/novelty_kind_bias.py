"""Item 99: bias the desk's mutation order away from proposal families that keep repeating.

Measured (scripts/item99_novelty_kinds_report.py): in the last 30 novelty-gate rows the 11 kills
are all re-proposals (10 stem_enable, 1 authored_mut) killed as already-in-ledger / held-out /
trivial, while every auto-built OEIS family was a hit (7/7). The desk's order
(exploration_budget.pick_mutation_order) knew nothing about that.

This module gives each proposal FAMILY (name prefix) an order factor from its own record in the
append-only novelty-gate log: Laplace hit rate 2*(hits+1)/(rows+2), plus an exploration bonus for
families with fewer than 3 rows (under-tried), clamped to [0.25, 2.0]. It only multiplies the
existing order weight of the non-boosted candidates: nothing is removed, no gate changes, the
Oracle / novelty gate / cooldowns decide exactly as before.

Switch ``COLONY_NOVELTY_KIND_BIAS`` = live (default) | off. Always off on the control arm.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
GATE_LOG = ROOT / "data" / "commons" / "novelty_gate.jsonl"
LOOKBACK = 200
MIN_F, MAX_F = 0.25, 2.0
UNDER_TRIED_ROWS = 3
UNDER_TRIED_BONUS = 0.5
PREFIXES = ("stem_", "oeis_", "authored_frontier_", "authored_sieve_", "authored_mut_", "authored_",
            "adversarial_", "easy_pad")
# Only desk judgments steer the desk's order (claim_theme / process rows are proposal titles).
DESK_KINDS = ("hard_enable", "stem_enable", "easy_pad", "stem_easy_pad", "hard_check")


def enabled() -> bool:
    try:
        from colony.arm import self_mod_enabled
        if not self_mod_enabled():
            return False
    except Exception:  # noqa: BLE001
        return False
    return (os.environ.get("COLONY_NOVELTY_KIND_BIAS") or "live").strip().lower() == "live"


def family(name: str) -> str:
    n = (name or "").strip().lower()
    for p in PREFIXES:
        if n.startswith(p):
            return p.rstrip("_")
    return "catalog"


def _rows(path: Path | None = None, lookback: int = LOOKBACK) -> list[dict[str, Any]]:
    p = path or GATE_LOG
    out: list[dict[str, Any]] = []
    try:
        for ln in p.read_text(encoding="utf-8").splitlines()[-lookback:]:
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return out


def family_stats(rows: list[dict[str, Any]], *, desk_only: bool = True) -> dict[str, dict[str, int]]:
    st: dict[str, dict[str, int]] = {}
    seen: Counter = Counter()
    for r in rows:
        if desk_only and str(r.get("kind") or "") not in DESK_KINDS:
            continue
        m = str(r.get("mutation") or "")
        f = family(m) if desk_only else f"{r.get('kind')}/{family(m)}"
        s = st.setdefault(f, {"rows": 0, "hits": 0, "repeats": 0})
        s["rows"] += 1
        s["hits"] += int(bool(r.get("novel_to_commons")))
        if seen[m]:
            s["repeats"] += 1
        seen[m] += 1
    return st


def factor_for(stats: dict[str, int] | None) -> float:
    n = int((stats or {}).get("rows") or 0)
    h = int((stats or {}).get("hits") or 0)
    f = 2.0 * (h + 1) / (n + 2)
    if n < UNDER_TRIED_ROWS:
        f += UNDER_TRIED_BONUS
    return max(MIN_F, min(MAX_F, f))


def factors(names: list[str], rows: list[dict[str, Any]] | None = None) -> dict[str, float]:
    st = family_stats(_rows() if rows is None else rows)
    return {n: factor_for(st.get(family(n))) for n in names}


def report(rows: list[dict[str, Any]] | None = None, *, desk_only: bool = True) -> list[dict[str, Any]]:
    st = family_stats(_rows() if rows is None else rows, desk_only=desk_only)
    out = [{"family": f, **s, "factor": round(factor_for(s), 3)} for f, s in st.items()]
    return sorted(out, key=lambda r: (-r["repeats"], -r["rows"]))
