"""Item 121 replay (dry run, cache only): bank-v2 consumption before / after the supply pace fix.

Starts from the live supply state and menu, never writes (write=False, deep-copied state) and
never makes a request: every page / b-file read goes through the polite new-data fetcher in
cache-only mode, and every read (cache hit or not) is counted as the request it would cost on a
cold CI cache, so budgets bind as they would live. Warm the cache first with
``scripts/item118_supply_probe.py`` (polite, >= 2 s apart). New targets are then checked for an
item-105 / item-121 NAME definition (cache-only referenced b-files). Nothing fetched is executed.

Usage: python scripts/item121_replay.py [runs]
"""
from __future__ import annotations

import copy
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["COLONY_NEWDATA_OFFLINE"] = "1"

from colony import new_data as N  # noqa: E402
from colony import oeis_conjectures as OC  # noqa: E402
from colony import oeis_definitions as OD  # noqa: E402
from colony import target_supply as TS  # noqa: E402


class CountingNet:
    """Cache-only reads, each counted as one would-be request against the refill budget."""

    def __init__(self, budget: int):
        self.inner = N.Net(allow=False)
        self.n = 0
        self.budget = int(budget)

    def exhausted(self) -> bool:
        return self.n >= self.budget

    def get(self, url: str, name: str):
        if self.exhausted():
            return None
        self.n += 1
        return self.inner.get(url, name)


def simulate(paced: bool, runs: int, refills_per_run: int = 1) -> dict:
    os.environ["COLONY_SUPPLY_PACE"] = "live" if paced else "off"
    st = copy.deepcopy(TS.load_state())
    menu = list(OC.load_menu() or [])
    tool = TS._tool()
    bank = TS.query_bank(tool)
    v2 = {b["key"] for b in bank if b.get("bank") == 2}
    v2_left0 = sum(1 for k in v2 if k not in st["done_pages"])
    new_all, per_run = [], []
    for r in range(runs):
        used, run_new, run_pages, run_skip, refills = 0, 0, 0, 0, 0
        # One cooldown refill per run; item 121 can add a PERTURB-starved slot refill in each of
        # the run's 3 cycles, all inside RUN_REQUEST_CAP.
        for _ in range(refills_per_run if paced else 1):
            if paced:
                pages, budget = TS.STARVED_PAGES, min(TS.STARVED_REQUEST_BUDGET, TS.RUN_REQUEST_CAP - used)
            else:
                pages, budget = TS.PAGES_PER_REFILL, TS.REQUEST_BUDGET
            if budget <= 0:
                break
            net = CountingNet(budget)
            rep = TS.refill(f"item121_replay_r{r}", net=net, tool=tool, menu=menu + new_all, st=st,
                            heal=TS._heal(), library_rows=[], write=False, pages=pages)
            if rep["pages_read"] == 0 and not rep.get("pages_skipped_duplicate"):
                break
            refills += 1
            used += net.n
            run_pages += rep["pages_read"]
            run_skip += rep.get("pages_skipped_duplicate") or 0
            run_new += len(rep["entries"])
            new_all += rep["entries"]
        per_run.append({"run": r + 1, "refills": refills, "pages_read": run_pages,
                        "pages_skipped_duplicate": run_skip, "requests_upper_bound": used, "new": run_new})
        if refills == 0:
            break
    v2_left = sum(1 for k in v2 if k not in st["done_pages"])
    return {"paced": paced, "v2_pages_left_at_start": v2_left0, "v2_pages_left_after": v2_left,
            "runs": [r for r in per_run if r["refills"]], "new_targets": len(new_all), "entries": new_all}


def definitions(entries: list[dict]) -> dict:
    by, names = Counter(), []
    for e in entries:
        d, _ = OD.find_definition(e, cache={"entries": {}}, seconds=8, use_guess=False)
        by[(d or {}).get("provenance") or "none"] += 1
        if d and d.get("provenance") == OD.PROV_NAME:
            names.append({"id": e["id"], "expr": d["expr"][:80], "refs": d.get("refs_used") or []})
    return {"by_provenance": dict(by), "name_definitions": names}


def main(runs: int = 70) -> dict:
    out = {}
    for label, paced, k in (("before_item121", False, 1), ("after_item121_min", True, 1),
                            ("after_item121_max", True, 4)):
        sim = simulate(paced, runs, k)
        ents = sim.pop("entries")
        sim["forms"] = dict(Counter((e.get("claim") or {}).get("form") for e in ents))
        sim["definitions"] = definitions(ents)
        out[label] = sim
    os.environ.pop("COLONY_SUPPLY_PACE", None)
    return out


if __name__ == "__main__":
    print(json.dumps(main(*[int(x) for x in sys.argv[1:2]]), indent=1))
