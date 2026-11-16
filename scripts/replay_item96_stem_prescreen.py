"""Item 96 replay: which past submissions would the STEM triviality pre-screen have dropped?

Read-only (prints JSON). Runs ``oracle_prescreen.stem_trivial_drop`` (treatment arm) on every
Oracle row and every novelty-gate row. Reports, separately:
  * Oracle PASSES that would have been dropped (the slots saved; each is a stem_enable the
    novelty gate kills as ``trivial:stem_symbolic_tautology`` anyway),
  * novelty HITS that would have been dropped (must be 0),
  * non-stem rows touched (must be 0).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from colony.oracle_prescreen import stem_trivial_drop  # noqa: E402

ORACLE = ROOT / "data" / "commons" / "oracle.jsonl"
GATE = ROOT / "data" / "commons" / "novelty_gate.jsonl"


def _rows(p: Path) -> list[dict]:
    return [json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip()]


def main(oracle: Path = ORACLE, gate: Path = GATE) -> dict:
    cache: dict[tuple[str, str], bool] = {}

    def drop(r: dict) -> bool:
        key = (str(r.get("mutation") or ""), str(r.get("kind") or ""))
        if key not in cache:
            cache[key] = stem_trivial_drop(*key) is not None
        return cache[key]

    o, g = _rows(oracle), _rows(gate)
    o_drop = [r for r in o if drop(r)]
    g_drop = [r for r in g if drop(r)]
    return {
        "oracle_rows": len(o), "gate_rows": len(g),
        "oracle_rows_dropped": [(r.get("ts"), r.get("mutation"), "PASS" if r.get("passed") else "KILL") for r in o_drop],
        "oracle_passes_dropped": sum(1 for r in o_drop if r.get("passed")),
        "novel_hits_dropped": [(r.get("ts"), r.get("mutation")) for r in g_drop if r.get("novel_to_commons")],
        "non_stem_rows_dropped": sum(1 for r in o_drop + g_drop if str(r.get("kind") or "") != "stem_enable"),
        "dropped_gate_rows_also_trivial_in_gate": all(
            not r.get("novel_to_commons") for r in g_drop),
    }


if __name__ == "__main__":
    print(json.dumps(main(), indent=1, default=str))
