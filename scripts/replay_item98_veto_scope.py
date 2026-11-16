"""Item 98 replay: which past Athanor area vetoes would the scope waive? Read-only.

Sources: society/systems/athanor_gate.json (per-row raw block drift + veto) joined with
data/commons/desk_outcomes.jsonl (hard_pass and score before/after from the desk note).
Prints one line per vetoed row and a summary; asserts no non-stem_enable row changes.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from colony.trust.athanor_veto_scope import stem_quality, structural_match  # noqa: E402

NOTE = re.compile(r"score ([0-9.]+)→([0-9.]+) .*?hard_pass (\d+)→(\d+)")


def main() -> int:
    gate = json.loads((ROOT / "society/systems/athanor_gate.json").read_text(encoding="utf-8"))
    outcomes = {}
    for line in (ROOT / "data/commons/desk_outcomes.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if "area veto" in (r.get("note") or ""):
            outcomes[(r.get("cycle_id"), r.get("mutation"))] = r
    rows = gate.get("rows") or []
    vetoed = [r for r in rows if (r.get("veto") or {}).get("vetoed") and r.get("tentative_keep")]
    non_stem_vetoed = [r for r in vetoed if r.get("kind") != "stem_enable"]
    flips, stays, quality_cache = [], [], {}
    for r in vetoed:
        o = outcomes.get((r.get("cycle_id"), r.get("mutation"))) or {}
        m = NOTE.search(o.get("note") or "")
        sb, sa, hb, ha = (float(m[1]), float(m[2]), int(m[3]), int(m[4])) if m else (None, None, None, None)
        sm = structural_match(kind=r.get("kind") or "", veto=r.get("veto"), raw=r.get("state_drift_raw"),
                              hard_pass_before=hb, hard_pass_after=ha, score_before=sb, score_after=sa)
        mut = r.get("mutation") or ""
        if sm["match"]:
            q = quality_cache.setdefault(mut, stem_quality(mut))
        else:
            q = {"ok": False, "why": ",".join(sm["why_not"])}
        line = (f"{r['ts']} {r.get('kind')} {mut} areas={r['veto'].get('areas')} "
                f"score_drift={(r.get('state_drift_raw') or {}).get('score')} hard_pass {hb}->{ha} "
                f"structural={sm['match']} quality={q['why']} -> {'WAIVE' if q['ok'] else 'veto stays'}")
        print(line)
        (flips if q["ok"] else stays).append(mut)
    all_outcome_vetoes = len(outcomes)
    non_stem_outcomes = sum(1 for o in outcomes.values() if o.get("kind") != "stem_enable")
    print(f"\nvetoed tentative keeps in gate state: {len(vetoed)} (desk_outcomes area-veto rows: {all_outcome_vetoes})")
    print(f"non-stem_enable vetoes: gate={len(non_stem_vetoed)} desk_outcomes={non_stem_outcomes} (scope cannot touch them)")
    print(f"would waive: {len(flips)} rows -> {sorted(set(flips))}")
    print(f"veto stays: {len(stays)} rows -> {sorted(set(stays))}")
    other = [r for r in rows if r.get("kind") != "stem_enable"]
    changed = [r for r in other if structural_match(kind=r.get("kind") or "", veto=r.get("veto"),
                                                    raw=r.get("state_drift_raw"), hard_pass_before=0,
                                                    hard_pass_after=1, score_before=0, score_after=1)["match"]]
    print(f"non-STEM gate rows checked: {len(other)}; changed: {len(changed)}")
    assert not changed
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
