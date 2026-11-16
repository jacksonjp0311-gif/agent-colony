"""Item 103 replay: OEIS desk picks with and without the near-miss focus (read-only)."""
from __future__ import annotations

import collections
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from colony import oeis_conjectures as oc  # noqa: E402


def main() -> int:
    log = oc.load_attempt_log()
    cycles = [str(r.get("cycle_id")) for r in (log.get("attempts") or [])][-40:]
    cycles = list(dict.fromkeys(cycles))[-12:] or ["replay"]
    menu = oc.load_menu()
    state = oc._load(oc.STATE, {"targets": {}, "families": {}})
    out = {}
    for mode in ("off", "live"):
        os.environ["COLONY_HARD_TIER_FOCUS"] = mode
        forms, window = collections.Counter(), 0
        for c in cycles:
            for e in oc.choose(menu, state, c + "_replay", oc.PICKS):
                forms[(e.get("claim") or {}).get("form")] += 1
                st = (state.get("targets") or {}).get(e.get("id")) or {}
                window += int(oc.can_search_past_bfile(e) and int(st.get("tested_hi") or 0) <= oc.bfile_hi_of(e))
        out[mode] = {"forms": dict(forms), "unexplored_past_bfile_picks": window}
        print(mode, json.dumps(out[mode]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
