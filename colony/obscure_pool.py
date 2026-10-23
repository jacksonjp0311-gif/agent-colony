"""Less-studied OEIS entries as frontier ingredients (COLONY_OBSCURE = off | shadow | live; default off).

The pool (society/frontier/obscure_pool.json) is built by tools/build_obscure_pool.py from free OEIS
searches with a fixed obscurity filter (few comments / formulas / references, not 'core'/'nice',
keyword 'easy', a b-file that agrees with the entry's DATA). Each entry becomes a primitive
'ox' + digits (e.g. oxa078012 for A078012), table index = OEIS index (offset 0 or 1).

This changes the colony's MENU and INCENTIVES, never its targets: off = not sampled; shadow = a dry
generator pass with the pool in the menu, counted per entry, nothing registered (so nothing is
authored); live = the real generator samples them, with a sampling bonus OBSCURE_BONUS on top of
the usual UCB weights. Same triviality filter, reference check, strong known-results check,
Oracle, authored cap (150) and new-data slot cap.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
POOL = ROOT / "society" / "frontier" / "obscure_pool.json"
REPORT = ROOT / "society" / "systems" / "obscure_pool_report.json"
NOTE = ("Curated cache of less-studied OEIS entries (CC BY-SA 4.0, https://oeis.org). Built by "
        "tools/build_obscure_pool.py; terms from b-files cross-checked against DATA.")
OBSCURE_BONUS = 1.5
MAX_TERMS = 2004
MAX_DIGITS = 400
_FORCE = False


def mode() -> str:
    m = os.environ.get("COLONY_OBSCURE", "off").strip().lower()
    return m if m in ("off", "shadow", "live") else "off"


def active() -> bool:
    return _FORCE or mode() == "live"


def prim_name(anum: str) -> str:
    return "ox" + anum.lower()


def to_table(bvals: dict[int, int], off: int) -> list[int] | None:
    """Table [a(0)?, a(1), ...] indexed by n (index 0 = a(0) when offset 0, else 0); stops at the
    first gap or at a term over MAX_DIGITS digits."""
    out = [bvals.get(0, 0) if off == 0 else 0]
    n = 1
    while n in bvals and len(out) <= MAX_TERMS and len(str(abs(bvals[n]))) <= MAX_DIGITS:
        out.append(bvals[n])
        n += 1
    return out if len(out) > 120 else None


def load() -> list[dict[str, Any]]:
    try:
        return json.loads(POOL.read_text(encoding="utf-8")).get("pool") or []
    except Exception:  # noqa: BLE001
        return []


def _with_open_targets(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Open-target entries (colony/open_targets.py, COLONY_OPEN_TARGETS=live) join as ox primitives."""
    try:
        from colony import open_targets as _ot
        have = {e["anum"] for e in entries}
        return entries + [e for e in _ot.entries_for_menu() if e["anum"] not in have]
    except Exception:  # noqa: BLE001
        return entries


_ENTRIES = _with_open_targets(load())
PRIMS = tuple(prim_name(e["anum"]) for e in _ENTRIES)
POSITIVE = tuple(prim_name(e["anum"]) for e in _ENTRIES if all(v >= 1 for v in e["terms"][1:]))
ANUM = {prim_name(e["anum"]): e["anum"] for e in _ENTRIES}


def taken_anums() -> set[str]:
    from colony.known_check import ING_ANUM
    from colony.reference_check import PRIM_ANUM
    return set(PRIM_ANUM.values()) | set(ING_ANUM.values())


def table(name: str) -> list[int]:
    e = next(e for e in _ENTRIES if prim_name(e["anum"]) == name)
    return list(e["terms"])


STAGES = ("produced", "fresh", "passed_filter", "tested", "survived", "surprise", "explained_by_reference",
          "no_reference_found", "machine_checked", "explained_by_known_check")


def new_tally() -> dict[str, dict[str, int]]:
    return {p: {s: 0 for s in STAGES} for p in PRIMS}


def shadow_cycle(cycle_id: str, T: Any = None) -> dict[str, Any] | None:
    global _FORCE
    from colony import frontier_conjectures as fc
    if not PRIMS:
        return None
    tally = new_tally()
    _FORCE = True
    try:
        summ = fc.run_cycle(f"{cycle_id}:obscure", T=T, write=False, tally=tally)
    finally:
        _FORCE = False
    return record(cycle_id, "shadow", tally, summ)


def record(cycle_id: str, mode_: str, tally: dict, summ: dict | None) -> dict[str, Any]:
    try:
        st = json.loads(REPORT.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        st = {}
    tot = st.get("totals") or {}
    for p, row in tally.items():
        for k, v in row.items():
            tot.setdefault(p, {}).setdefault(k, 0)
            tot[p][k] += v
    surv = [s for s in ((summ or {}).get("new_survivors") or []) if any(p in s["statement"] for p in PRIMS)]
    agg = {k: sum(r[k] for r in tally.values()) for k in STAGES}
    hist = (st.get("history") or []) + [{"cycle_id": cycle_id, "mode": mode_, "counts": agg, "survivors": surv[:8]}]
    out = {"note": "Per-entry counts for the obscure-OEIS pool (colony/obscure_pool.py). shadow = dry pass, "
                   "nothing registered or authored; live = the real pass.", "mode": mode_, "anums": ANUM,
           "totals": tot, "history": hist[-30:]}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return out
