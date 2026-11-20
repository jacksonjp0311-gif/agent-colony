"""Item 121 definitions replay (dry run, cache only, writes nothing).

For every menu entry without a menu definition: which ones get a sound NAME definition under the
item-121 grammar that the stored item-105 table (old grammar) did not have, and how far one
attempt_disprove (fetch=False, the live evaluator caps) would test past the published range with
it. Referenced b-files come from the local polite-fetch cache only. Nothing fetched is executed.

Usage: python scripts/item121_definitions_replay.py [extra_entries.json]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["COLONY_NEWDATA_OFFLINE"] = "1"

from colony import oeis_conjectures as OC  # noqa: E402
from colony import oeis_definitions as OD  # noqa: E402


def project(entries: list[dict], table: dict) -> dict:
    rows = []
    for e in entries:
        if e.get("definition"):
            continue
        old = ((table.get(str(e.get("id"))) or {}).get("definition") or {})
        if old.get("provenance") == OD.PROV_NAME:
            continue
        d, _ = OD.find_definition(e, cache={"entries": {}}, seconds=8, use_guess=False)
        if not d or d.get("provenance") != OD.PROV_NAME:
            continue
        x = dict(e, definition=d)
        r = OC.attempt_disprove(x, fetch=False)
        pub = max(int(e["offset"]) + len(e["terms"]) - 1, int(e.get("published_hi") or 0))
        hi = max((r.get("range") or [0, 0])[1] or 0, r.get("deep_hi") or 0)
        rows.append({"id": e["id"], "expr": d["expr"][:80], "refs": d.get("refs_used") or [],
                     "status": r["status"], "published_hi": pub, "tested_hi": hi,
                     "beyond_published": max(0, hi - pub), "cap": r.get("cap_reason")})
    return {"new_sound_name_definitions": len(rows),
            "with_depth_past_published": sum(1 for r in rows if r["beyond_published"] > 0),
            "beyond_published_terms": sum(r["beyond_published"] for r in rows), "rows": rows}


def main(extra: str | None = None) -> dict:
    table = OD.load_defs().get("entries") or {}
    menu = OC.load_menu() or []
    out = {"menu": project(menu, table)}
    if extra:
        out["extra"] = project(json.loads(Path(extra).read_text()), {})
    return out


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:2]), indent=1))
