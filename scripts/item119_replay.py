"""Item 119 replay: which desk slots the learned-family skip would have freed, and where they go.

Read-only over the append-only logs (generator log, lessons, Oracle, novelty gate).
For every generated ``authored_mut_*`` check, in authoring order, the family is
"learned" if a sibling (same source claim) had a judged lesson strictly before
the check was authored. Those checks would not have been authored, so the desk
turn that later judged them is freed.

``--targets N`` additionally dry-runs (write=False, cache first, polite) the next
N slot refills over the pending bank-v2 pages to show which targets the freed
turns go to. No log row, state or menu is written; nothing fetched is executed.
"""
from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from colony import learned_family_skip as LFS  # noqa: E402


def _ts(cid: str) -> str:
    c = str(cid or "")
    return f"{c[0:4]}-{c[4:6]}-{c[6:8]}T{c[9:11]}:{c[11:13]}:{c[13:15]}Z" if len(c) >= 16 else ""


def replay(since: str = "") -> dict:
    gen = LFS._generator_rows()
    lessons = LFS._jsonl(LFS.LESSONS)
    orc: dict[str, list] = {}
    for o in LFS._jsonl(ROOT / "data" / "commons" / "oracle.jsonl"):
        orc.setdefault(str(o.get("mutation") or ""), []).append(bool(o.get("passed")))
    nov: dict[str, list] = {}
    for o in LFS._jsonl(ROOT / "data" / "commons" / "novelty_gate.jsonl"):
        nov.setdefault(str(o.get("mutation") or ""), []).append(o)
    authored = sorted((r for r in gen if r.get("event") == "authored"), key=lambda r: str(r.get("cycle_id") or ""))
    rows = []
    for r in authored:
        t = _ts(r.get("cycle_id"))
        if since and t < since:
            continue
        snap = LFS.Snapshot(gen, lessons, before=t)
        by = snap.learned_by_statement(r.get("source_statement"))
        n = str(r["name"])
        rows.append({"name": n, "authored": t, "skip": bool(by), "learned_by": by,
                     "family": LFS.family_key(r.get("source_statement")),
                     "oracle_pass": any(orc.get(n, [])),
                     "novel": any(bool(x.get("novel_to_commons")) for x in nov.get(n, [])),
                     "ledger_kill": any("already_in_lesson_ledger_or_history" in (x.get("kills") or [])
                                        for x in nov.get(n, []))})
    freed = [x for x in rows if x["skip"]]
    return {"since": since or "all", "authored": len(rows), "freed_slots": len(freed),
            "freed_oracle_passes": sum(x["oracle_pass"] for x in freed),
            "freed_ledger_kills": sum(x["ledger_kill"] for x in freed),
            "freed_novel_hits": sum(x["novel"] for x in freed),
            "kept_novel_hits": sum(x["novel"] for x in rows if not x["skip"]),
            "kept_oracle_passes": sum(x["oracle_pass"] for x in rows if not x["skip"]),
            "families_learned": len({x["family"] for x in freed}),
            "freed_by_kind": dict(Counter(x["name"].split("_")[2] for x in freed)),
            "freed": freed}


def slot_targets(n_slots: int, budget: int = 40) -> list[dict]:
    from colony import oeis_conjectures as OC
    from colony import target_supply as TS
    st = copy.deepcopy(TS.load_state())
    menu = OC.load_menu() or []
    tool = TS._tool()
    out, added = [], []
    for i in range(n_slots):
        rep = TS.refill(f"item119_replay_slot{i + 1}", net=TS.BudgetNet(budget=budget), tool=tool,
                        menu=menu + added, st=st, heal=TS._heal(), library_rows=[], write=False)
        added += rep.pop("entries", [])
        out.append({"slot": i + 1, "pages_read": rep["pages_read"], "requests": rep["requests"],
                    "new": [e["id"] for e in rep["new"]]})
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    n_targets = 0
    if "--targets" in args:
        i = args.index("--targets")
        n_targets = int(args[i + 1])
        del args[i:i + 2]
    since = args[0] if args else ""
    rep = replay(since)
    if n_targets:
        rep["slot_targets"] = slot_targets(n_targets)
    print(json.dumps(rep, indent=1))
