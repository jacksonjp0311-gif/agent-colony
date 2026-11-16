"""Item 105 replay: which menu targets held on the published range only would reopen with a widened
definition (NAME grammar, non-conjectural FORMULA lines, guessed recurrences), and by which source.

Read-only on the attempt log; writes society/systems/oeis_widened_definitions.json (the table the
desk reads) only with --write. Usage: python scripts/replay_item105_widened_definitions.py [--write]
"""
from __future__ import annotations

import collections
import json
import os
import sys
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
from colony import oeis_conjectures as OC  # noqa: E402
from colony import oeis_definitions as OD  # noqa: E402


def main() -> int:
    menu = OC.load_menu()
    log = OC.load_attempt_log()
    os.environ["COLONY_OEIS_DEF_WIDEN"] = "off"      # the baseline: what is held today
    held = [e for e in menu if OC.held_on_published_only(e["id"], e, log)]
    table = OD.build(menu, seconds=20.0)
    if "--write" in sys.argv:
        OD.save_defs(table)
    rows = table.get("entries") or {}
    by: collections.Counter = collections.Counter()
    reopened = []
    for e in held:
        d = (rows.get(e["id"]) or {}).get("definition")
        if not d:
            by["none"] += 1
            continue
        by[d["provenance"]] += 1
        reopened.append({"id": e["id"], "anum": e["anum"], "provenance": d["provenance"], "kind": d["kind"],
                         "source": d.get("source", "")[:120]})
    out = {"held_published_only": len(held), "reopened": len(reopened),
           "reopened_sound_name": by[OD.PROV_NAME], "reopened_formula": by[OD.PROV_FORMULA],
           "reopened_guessed": by[OD.PROV_GUESS], "still_held": by["none"], "targets": reopened}
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
