"""Item 97 replay: re-judge every novelty-gate row with the current gate, with and without the
ledger exemptions (colony/ledger_exemptions.py). Read-only, prints JSON.

For a stem_enable row the current gate replaces the old held-out kill with the item-95 STEM
held-out and adds the STEM triviality kill (as in the item-95 replay). A logged ledger kill is
dropped under the exemptions only if every earlier ledger trace of the name is an exempt entry.
Kills that were not logged cannot appear. Every other kill is kept as logged. Non-STEM rows
cannot change: no exempt entry names a non-STEM candidate (checked).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from colony import ledger_exemptions as LX  # noqa: E402
from colony.stem_held_out import held_out, triviality  # noqa: E402

GATE = ROOT / "data" / "commons" / "novelty_gate.jsonl"
LESSONS = ROOT / "data" / "commons" / "lessons.jsonl"
HISTORY = ROOT / "society" / "benchmarks" / "conjecture_history.jsonl"


def main(gate: Path = GATE, lessons: Path = LESSONS, history: Path = HISTORY) -> dict:
    recs = LX.bug_only_rows(gate, lessons, history)
    exempt = {(r["source"], r["line_id"]) for r in recs}
    les, his = LX._read(lessons), LX._read(history)
    cache: dict[str, tuple[dict, dict]] = {}
    changed, flips = [], []
    for _raw, row in LX._read(gate):
        kind, name, ts = str(row.get("kind") or ""), str(row.get("mutation") or ""), str(row.get("ts") or "")
        old = [str(k) for k in (row.get("kills") or [])]
        if kind != "stem_enable":
            continue
        if name not in cache:
            cache[name] = (held_out(name), triviality(name))
        h, t = cache[name]
        cur = [k for k in old if k != LX.BUG_KILL]
        if LX.BUG_KILL in old and not h.get("survives"):
            cur.append(f"held_out:{h.get('reason')}")
        if t.get("trivial") and f"trivial:{t.get('reason')}" not in cur:
            cur.append(f"trivial:{t.get('reason')}")
        ex = list(cur)
        if LX.LEDGER_KILL in ex:
            prior = LX._traces(name, les, his, ts)
            if prior and all((s, i) in exempt for s, i, _e in prior):
                ex.remove(LX.LEDGER_KILL)
        rec = {"ts": ts, "mutation": name, "logged_novel": bool(row.get("novel_to_commons")),
               "logged_kills": old, "current_gate_kills": cur, "with_exemption_kills": ex,
               "novel_with_exemption": not ex}
        if ex != old:
            changed.append(rec)
        if not ex and not row.get("novel_to_commons"):
            rec["flip_cause"] = "item95_held_out" if not cur else "item97_exemption"
            flips.append(rec)
    non_stem = [r for r in recs if not r["mutation"].startswith("stem_")]
    return {"exempt_entries": len(recs), "exempt_non_stem": non_stem, "flips": flips,
            "changed_rows": changed, "flip_names": sorted({f["mutation"] for f in flips})}


if __name__ == "__main__":
    print(json.dumps(main(), indent=1, default=str))
