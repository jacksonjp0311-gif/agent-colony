"""Stall recovery. A flat Oracle does not only get logged.

Recovery turns on when the Oracle pass total is unchanged for six cycles in a
row. It turns off on a new pass, or when the newest cycle's kill reasons were
not already seen in that flat run. While it is on, a mutation or theme whose
last few Oracle outcomes were the same kill is skipped, and the freed turn is
an OEIS attempt (see the callers). Nothing here changes the Oracle.
"""
from __future__ import annotations

import json
from typing import Any

STALL_CYCLES = 6
IDENTICAL_KILL_RUN = 3


def load_oracle_rows(limit: int = 2500) -> list[dict[str, Any]]:
    from colony.oracle import ORACLE_LOG

    if not ORACLE_LOG.exists():
        return []
    out: list[dict[str, Any]] = []
    for ln in ORACLE_LOG.read_text(encoding="utf-8").splitlines()[-limit:]:
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _kill_sig(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(k) for k in (row.get("kills") or []))


def cycle_series(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per cycle, in log order, with that cycle's new passes and kill signatures."""
    order: list[str] = []
    bucket: dict[str, dict[str, Any]] = {}
    for row in rows:
        cid = str(row.get("cycle_id") or "")
        if not cid:
            continue
        if cid not in bucket:
            order.append(cid)
            bucket[cid] = {"cycle_id": cid, "passes": 0, "kills": []}
        if row.get("passed") is True:
            bucket[cid]["passes"] += 1
        elif row.get("passed") is False:
            sig = _kill_sig(row)
            if sig:
                bucket[cid]["kills"].append(sig)
    total = 0
    series = []
    for cid in order:
        info = bucket[cid]
        total += int(info["passes"])
        series.append({
            "cycle_id": cid,
            "passes": int(info["passes"]),
            "pass_total": total,
            "kills": list(info["kills"]),
        })
    return series


def assess_recovery(rows: list[dict[str, Any]], *, cycles: int = STALL_CYCLES) -> dict[str, Any]:
    """Return ``{on, reason, pass_total}`` for a flat run of ``cycles`` cycles.

    ``on`` is true only when each of the last ``cycles`` cycles added zero
    passes and the newest cycle did not introduce a kill signature absent from
    the earlier cycles of that window.
    """
    series = cycle_series(rows)
    if len(series) < cycles:
        return {"on": False, "reason": "too_few_cycles", "pass_total": series[-1]["pass_total"] if series else 0}
    window = series[-cycles:]
    total = window[-1]["pass_total"]
    if any(item["passes"] > 0 for item in window):
        return {"on": False, "reason": "new_pass", "pass_total": total}
    earlier: set[tuple[str, ...]] = set()
    for item in window[:-1]:
        earlier.update(item["kills"])
    fresh = [sig for sig in window[-1]["kills"] if sig not in earlier]
    if fresh and earlier:
        return {"on": False, "reason": "new_kill", "pass_total": total, "new_kills": fresh}
    return {"on": True, "reason": "flat_passes", "pass_total": total}


def identical_kill_streak(
    mutation: str,
    rows: list[dict[str, Any]],
    *,
    run: int = IDENTICAL_KILL_RUN,
) -> bool:
    """True when this mutation's last ``run`` Oracle failures share one kill list."""
    name = (mutation or "").strip()
    if not name:
        return False
    mine = [_kill_sig(r) for r in rows if str(r.get("mutation") or "") == name and r.get("passed") is False]
    if len(mine) < run:
        return False
    tail = mine[-run:]
    return len(set(tail)) == 1 and bool(tail[0])


def recovery_skips(name: str, rows: list[dict[str, Any]] | None = None) -> bool:
    """True when recovery is on and ``name`` (or its theme) is on an identical-kill streak."""
    rows = load_oracle_rows() if rows is None else rows
    if not assess_recovery(rows)["on"]:
        return False
    if identical_kill_streak(name, rows):
        return True
    try:
        from colony.lessons import theme_key
        key = theme_key(name)
    except Exception:
        key = ""
    return bool(key) and key != name and identical_kill_streak(key, rows)
