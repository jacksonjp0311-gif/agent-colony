"""Item 118 probe (dry run): how many new vetted targets does bank v2 find?

Reads OEIS search pages / b-files politely (cache first, >= 2 s apart) through the
same refill() vetting with write=False: no supply-log row, no state change, no
menu change. Fetched text is parsed as JSON / numbers only; nothing is executed.
Usage: python scripts/item118_supply_probe.py [pages] [budget]
"""
from __future__ import annotations

import copy
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from colony import target_supply as TS  # noqa: E402
from colony import oeis_conjectures as OC  # noqa: E402


def main(pages: int = 24, budget: int = 160) -> dict:
    st = copy.deepcopy(TS.load_state())
    menu = OC.load_menu() or []
    tool = TS._tool()
    bank = TS.query_bank(tool)
    todo = TS.pending_pages(bank, st, {})
    new, stats, req, pages_read, stalls = [], Counter(), 0, 0, 0
    while pages_read < pages and stalls < 3:
        # a failed fetch stops a refill (page kept for later); resume like the next cycle would
        net = TS.BudgetNet(budget=budget)
        rep = TS.refill("item118_probe", net=net, tool=tool, menu=menu + new, st=st, heal=TS._heal(),
                        library_rows=[], write=False, max_new=10 ** 6, pages=pages - pages_read)
        new += rep["entries"]
        stats.update(rep["stats"])
        req += rep["requests"]
        pages_read += rep["pages_read"]
        stalls = stalls + 1 if rep["pages_read"] == 0 else 0
        if pages_read < pages and stalls < 3:
            time.sleep(20)
    rep = {"pages_read": pages_read, "requests": req, "stats": dict(stats),
           "new": [{"id": e["id"], "form": (e.get("claim") or {}).get("form"),
                    "definition": bool(e.get("definition"))} for e in new]}
    read_keys = [k for k in st.get("done_pages", {}) if k not in (TS.load_state().get("done_pages") or {})]
    kinds = Counter(b["kind"] for b in todo[:pages] if b["key"] in read_keys)
    hits = {b["key"]: st["done_pages"][b["key"]]["n_hits"] for b in todo[:pages] if b["key"] in read_keys}
    forms = Counter((e.get("form") or "?") for e in rep["new"])
    with_def = sum(1 for e in rep["new"] if e.get("definition"))
    return {"pending_pages_total": len(todo), "pages_read": rep["pages_read"], "requests": rep["requests"],
            "kinds_read": dict(kinds), "search_hits": sum(hits.values()), "stats": rep["stats"],
            "new_targets": len(rep["new"]), "new_forms": dict(forms), "new_with_name_definition": with_def,
            "new_ids": [e["id"] for e in rep["new"]]}


if __name__ == "__main__":
    a = [int(x) for x in sys.argv[1:3]]
    print(json.dumps(main(*a), indent=1))
