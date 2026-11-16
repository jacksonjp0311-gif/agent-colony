"""Item 108 replay: projected novelty effect of the MAP-Elites order factor on past desk proposals.

For each desk row i of the append-only novelty-gate log (chronological), the archive is rebuilt from
rows < i only (no look-ahead). The candidate pool at i is the set of distinct desk mutations proposed
in rows i .. i+W-1 (what was available around then); the ACTUAL pick is row i's mutation, the
MAP-Elites pick is the pool member with the highest factor (ties: the actual order). Each pick gets a
projected hit probability = the Laplace hit rate of its cell on rows < i (an empty cell gets the
global prior). Reported: mean projected hit probability of actual vs MAP picks, and the share of
picks that land in an empty/thin cell. This is a PROJECTION from past logs, not a measured result.
Usage: python scripts/replay_item108_map_elites.py [--window 20]
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
from colony import map_elites as ME  # noqa: E402


def main() -> int:
    W = 20
    if "--window" in sys.argv:
        W = int(sys.argv[sys.argv.index("--window") + 1])
    gate = [r for r in ME._read(ME.GATE_LOG, 100000) if str(r.get("kind") or "") in ME.DESK_KINDS]
    desk = ME._read(ME.DESK_LOG, 100000)
    hits = defaultdict(lambda: [0, 0])
    tot = [0, 0]
    act_p = map_p = 0.0
    act_thin = map_thin = 0
    changed = 0
    n = 0
    for i, r in enumerate(gate):
        if i < 30:
            c = ME.cell_of(r["kind"], r["mutation"])[:2]
            hits[c][0] += int(bool(r.get("novel_to_commons"))); hits[c][1] += 1
            tot[0] += int(bool(r.get("novel_to_commons"))); tot[1] += 1
            continue
        arch = ME.build(gate[:i], [d for d in desk if str(d.get("ts") or "") < str(r.get("ts") or "")])
        pool, seen = [], set()
        for q in gate[i:i + W]:
            if q["mutation"] not in seen:
                seen.add(q["mutation"])
                pool.append((q["mutation"], q["kind"], ""))
        f = ME.factors(pool, arch)
        best = max(pool, key=lambda t: (f[t[0]], -pool.index(t)))
        prior = (tot[0] + 1) / (tot[1] + 2)

        def p(t):
            h, m = hits.get(ME.cell_of(t[1], t[0])[:2], [0, 0])
            return (h + 2 * prior) / (m + 2) if m else prior

        def thin(t):
            return hits.get(ME.cell_of(t[1], t[0])[:2], [0, 0])[1] < 3
        a = pool[0]
        act_p += p(a); map_p += p(best)
        act_thin += int(thin(a)); map_thin += int(thin(best))
        changed += int(best[0] != a[0])
        n += 1
        c = ME.cell_of(r["kind"], r["mutation"])[:2]
        hits[c][0] += int(bool(r.get("novel_to_commons"))); hits[c][1] += 1
        tot[0] += int(bool(r.get("novel_to_commons"))); tot[1] += 1
    snap = ME.snapshot(ME.build(gate, desk))
    out = {"rows_replayed": n, "window": W, "pick_changed": changed,
           "projected_hit_rate_actual": round(act_p / max(1, n), 4),
           "projected_hit_rate_map_elites": round(map_p / max(1, n), 4),
           "thin_cell_share_actual": round(act_thin / max(1, n), 4),
           "thin_cell_share_map_elites": round(map_thin / max(1, n), 4),
           "archive_cells": snap["n_cells"], "archive_elites": snap["n_elites"],
           "note": "projection from past logs (cell hit rates known before each row), not a measured result"}
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
