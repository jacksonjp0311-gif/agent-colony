"""Item 114 replay (read-only): would the tie fix have stopped the Nov 18-19 self-heal thrash?

Walks self-heal evidence in order. Cycle indices come from the union of cycle ids in the
evidence's own baseline/trial metric rows plus the remembered cycle list. At every trial
start since SINCE it asks, using only evidence closed before that start:
  * was the started (knob, direction) on the item-114 tie cooldown?
  * would high_revert_rate still fire with ties excluded (when that was the trial's reason)?
Prints counts as JSON. Writes nothing.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("COLONY_ARM", "treatment")

from colony import self_heal as sh  # noqa: E402

SINCE = "20261118T121400Z"  # Nov 18 7:14 AM ET


def main() -> dict:
    st = json.loads((ROOT / "society" / "systems" / "self_heal.json").read_text())
    ev = [e for e in st.get("evidence") or [] if isinstance(e, dict)]
    ids = set(st.get("cycles") or [])
    for e in ev:
        for k in ("baseline_metrics", "trial_metrics"):
            for r in e.get(k) or []:
                if isinstance(r, dict) and r.get("cycle_id"):
                    ids.add(str(r["cycle_id"]))
        for k in ("cycle_id", "started_cycle"):
            if e.get(k):
                ids.add(str(e[k]))
    cycles = sorted(ids)
    pos = {c: i for i, c in enumerate(cycles)}
    closes = [e for e in ev if e.get("event") in ("adopt", "revert", "trial_inconclusive", "trial_voided_confound")
              and str(e.get("started_cycle") or "") >= SINCE]
    window = int(sh.state_knob(st, "evaluation_window"))
    out = {"trials": 0, "self_heal_trials": 0, "blocked_by_tie_cooldown": 0, "high_revert_rate_trials": 0,
           "high_revert_rate_still_fires": 0, "rows": []}
    for e in closes:
        start = str(e["started_cycle"])
        prior = [x for x in ev if str(x.get("cycle_id") or "") < start and x.get("event") in ("adopt", "revert")]
        sim = {"evidence": [dict(x, closed_index=pos.get(str(x.get("cycle_id")))) for x in prior
                            if pos.get(str(x.get("cycle_id"))) is not None],
               "cycle_index": pos[start], "cycles": [], "knobs": {"evaluation_window": window}}
        out["trials"] += 1
        swarm = bool(e.get("swarm_fingerprint"))
        if not swarm:
            out["self_heal_trials"] += 1
        tc = sh.tie_cooldown(sim, str(e.get("knob")), str(e.get("direction")))
        blocked = tc is not None and not swarm
        out["blocked_by_tie_cooldown"] += int(blocked)
        hrr = None
        if str(e.get("reason") or "") == "high_revert_rate" or (e.get("finding_reason") == "high_revert_rate"):
            out["high_revert_rate_trials"] += 1
            nt = [x for x in prior if not sh.is_tie_revert(x)
                  and not (x.get("event") == "revert" and x.get("reason") == "high_revert_rate")][-6:]
            rv = [x for x in nt if x.get("event") == "revert"]
            hrr = len(nt) >= 3 and len(rv) >= 2 and len(rv) >= (len(nt) + 1) // 2
            out["high_revert_rate_still_fires"] += int(hrr)
        out["rows"].append({"start": start, "knob": e.get("knob"), "direction": e.get("direction"),
                            "event": e.get("event"), "tie": sh.is_tie_revert(e), "swarm": swarm,
                            "tie_cooldown": bool(tc), "hrr_without_ties": hrr})
    return out


if __name__ == "__main__":
    print(json.dumps(main(), indent=1))
