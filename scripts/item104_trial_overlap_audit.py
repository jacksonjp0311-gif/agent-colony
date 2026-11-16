"""Item 104 (read-only): which experiment trials overlapped, and which blueprint verdicts
were scored over a window (or baseline) another trial shared.

    python scripts/item104_trial_overlap_audit.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from colony import self_build as SB  # noqa: E402
from colony.experiment_reservation import overlapping, trial_intervals  # noqa: E402


def audit() -> dict:
    ivs = trial_intervals()
    pairs = []
    for i, a in enumerate(ivs):
        for b in ivs[i + 1:]:
            if a["slot"] == b["slot"]:
                continue
            if overlapping(a["start"], a["end"], [b]):
                pairs.append({"a": a, "b": b})
    rows = SB._paired_rows(SB.load_board())
    ts = [r.get("ts") for r in rows]
    verdicts = []
    opened = {}
    for r in SB.load_log():
        if r.get("event") == "blueprint_trial_open":
            opened[r.get("blueprint")] = r
        if r.get("event") != "blueprint_trial_close":
            continue
        o = opened.get(r.get("blueprint"))
        if not o:
            continue
        from colony.experiment_reservation import cycle_ts
        t0 = cycle_ts(o["cycle_id"])
        start = max((i for i, t in enumerate(ts) if t and t <= t0), default=-1)
        w = int(o.get("window_rows") or 2)
        win = (ts[start], ts[start + w] if start + w < len(ts) else None)
        base = (ts[start - w] if start - w >= 0 else None, ts[start])
        verdicts.append({
            "blueprint": r.get("blueprint"), "outcome": r.get("outcome"), "verdict": r.get("verdict"),
            "window": win, "baseline": base,
            "window_overlaps": overlapping(win[0], win[1], ivs, exclude_id=r.get("blueprint")),
            "baseline_overlaps": overlapping(base[0], base[1], ivs, exclude_id=r.get("blueprint")),
        })
    return {"intervals": len(ivs), "cross_slot_overlaps": pairs, "blueprint_verdicts": verdicts}


if __name__ == "__main__":
    print(json.dumps(audit(), indent=1))
