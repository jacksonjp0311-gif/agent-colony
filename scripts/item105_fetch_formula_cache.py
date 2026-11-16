"""Item 105: cache the NAME and FORMULA text lines of menu entries that have no definition.

Free public OEIS JSON (one request per 2 s). Data only: no PROGRAM / LODA / Maple / Mathematica
line is stored or executed. The cache is read by colony/oeis_definitions.py, which parses the text
into its own vetted evaluator and accepts a definition only if it reproduces the entry's whole
stored b-file. Usage: python scripts/item105_fetch_formula_cache.py [--all]
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
from colony import oeis_conjectures as OC  # noqa: E402
from colony import oeis_definitions as OD  # noqa: E402


def fetch(anum: str) -> dict | None:
    url = "https://oeis.org/search?fmt=json&q=id:%s" % anum
    req = urllib.request.Request(url, headers={"User-Agent": "agent-colony (public research; contact via GitHub)"})
    with urllib.request.urlopen(req, timeout=30) as fh:
        d = json.loads(fh.read().decode("utf-8"))
    rows = d if isinstance(d, list) else (d or {}).get("results") or []
    for r in rows:
        if "A%06d" % int(r.get("number") or 0) == anum:
            return {"name": str(r.get("name") or ""), "formula": [str(x) for x in (r.get("formula") or [])]}
    return None


def main() -> int:
    cache = OD.load_formula_cache()
    menu = OC.load_menu()
    want = sorted({e["anum"] for e in menu if (not e.get("definition")) or "--all" in sys.argv})
    got = 0
    for a in want:
        if a in cache.get("entries", {}):
            continue
        try:
            row = fetch(a)
        except Exception as ex:  # noqa: BLE001
            print(a, "fetch failed", ex)
            time.sleep(2)
            continue
        if row:
            row["fetched"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            cache.setdefault("entries", {})[a] = row
            got += 1
        time.sleep(2)
    cache["note"] = ("OEIS NAME and FORMULA text only (data). Never executed; parsed by "
                     "colony/oeis_definitions.py into its own evaluator.")
    OD.FORMULA_CACHE.parent.mkdir(parents=True, exist_ok=True)
    OD.FORMULA_CACHE.write_text(json.dumps(cache, indent=1, sort_keys=True) + "\n")
    print("fetched", got, "cached", len(cache.get("entries", {})))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
