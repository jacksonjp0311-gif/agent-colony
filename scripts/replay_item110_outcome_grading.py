"""Replay item 110 (Hive outcome grading) over the committed history. Read-only.

Reads society/systems/swarm_learn.json and self_heal.json, grades every
remembered shadow pick by measured trial outcome, and prints the old vs
new calibration buckets with Wilson lower bounds. Writes nothing.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import hive.outcome_grading as OG  # noqa: E402
from hive.bitwork import WILSON_ACCEPT_PERMILLE, wilson_lower_permille  # noqa: E402


def _totals(cal, sources):
    out = []
    for b in cal["buckets"]:
        n = sum(int((b["by_source"].get(s) or {}).get("n") or 0) for s in sources)
        c = sum(int((b["by_source"].get(s) or {}).get("correct") or 0) for s in sources)
        out.append((b["min_margin"], c, n, wilson_lower_permille(c, n)))
    return out


def main() -> int:
    st = json.loads((ROOT / "society/systems/swarm_learn.json").read_text())
    heal = json.loads((ROOT / "society/systems/self_heal.json").read_text())
    preds = OG.collect_predictions(st)
    trials = OG.collect_trials(heal.get("evidence") or [], st.get("evidence") or [])
    res = OG.grade(preds, trials)
    units = res["units"]
    uc = sum(1 for u in units if u["correct"])
    cal = copy.deepcopy(st["calibration"])
    OG.apply_to_calibration(cal, units)
    old = _totals(cal, ("replay", "shadow", "apply"))
    new = _totals(cal, ("replay", "outcome", "apply"))
    report = {
        "predictions": res["n_predictions"], "decisive_trials": len(trials),
        "graded_predictions": res["n_graded"], "correct": res["n_correct"], "wrong": res["n_wrong"],
        "abstain": res["n_abstain"],
        "per_prediction_wilson_lower_permille": wilson_lower_permille(res["n_correct"], res["n_graded"]),
        "units": len(units), "units_correct": uc,
        "units_wilson_lower_permille": wilson_lower_permille(uc, len(units)),
        "old_shadow_slice": {"n": sum(int(b["by_source"]["shadow"]["n"]) for b in cal["buckets"]),
                             "correct": sum(int(b["by_source"]["shadow"]["correct"]) for b in cal["buckets"])},
        "gate_permille": WILSON_ACCEPT_PERMILLE,
        "buckets_old": [{"min_margin": m, "correct": c, "n": n, "lower": l, "clears": l >= 700} for m, c, n, l in old],
        "buckets_new": [{"min_margin": m, "correct": c, "n": n, "lower": l, "clears": l >= 700} for m, c, n, l in new],
        "unit_rows": [{k: u[k] for k in ("family", "trial_event", "trial_start", "n_predictions", "margin", "correct")}
                      for u in units],
    }
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
