"""Item 95 replay: re-judge every past novelty-gate row with the old vs the new held-out logic.

Read-only (prints a JSON report; writes nothing). Only ``stem_enable`` rows can change: every
other kind goes through the unchanged held-out code. For a stem_enable row the new verdict
is the old kill list with the old ``held_out:*`` kill replaced by the new STEM held-out
verdict, plus the STEM triviality kill. A FLIP is a row that was killed and would now be
novel. ``looser`` lists any row where the new held-out survives while the old test's own
non-kind conditions (lemma hard tier green, n_hard_pass > 0) would not hold — must be empty.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from colony.stem_held_out import held_out, triviality  # noqa: E402

LOG = ROOT / "data" / "commons" / "novelty_gate.jsonl"


def main(log: Path = LOG) -> dict:
    rows = [json.loads(x) for x in Path(log).read_text(encoding="utf-8").splitlines() if x.strip()]
    by_kind: dict[str, int] = {}
    stem, flips, looser = [], [], []
    cache: dict[str, tuple[dict, dict]] = {}
    for r in rows:
        kind = str(r.get("kind") or "")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        if kind != "stem_enable":
            continue
        name = str(r.get("mutation") or "")
        if name not in cache:
            cache[name] = (held_out(name), triviality(name))
        h, t = cache[name]
        old_kills = list(r.get("kills") or [])
        new_kills = [k for k in old_kills if not str(k).startswith("held_out:")]
        if not h.get("survives"):
            new_kills.append(f"held_out:{h.get('reason')}")
        if t.get("trivial"):
            new_kills.append(f"trivial:{t.get('reason')}")
        old_novel = bool(r.get("novel_to_commons"))
        new_novel = not new_kills
        rec = {"ts": r.get("ts"), "mutation": name, "old_novel": old_novel, "old_kills": old_kills,
               "new_novel": new_novel, "new_kills": new_kills, "held_out": h.get("reason"),
               "triviality": t.get("reason")}
        stem.append(rec)
        if new_novel and not old_novel:
            flips.append(rec)
        if h.get("survives") and not (int(h.get("hard_pass") or 0) > 0):
            looser.append(rec)
    return {"rows": len(rows), "by_kind": by_kind, "stem_enable_rows": stem,
            "flips_kill_to_novel": flips, "looser_cases": looser,
            "non_stem_rows_unchanged": sum(v for k, v in by_kind.items() if k != "stem_enable")}


if __name__ == "__main__":
    print(json.dumps(main(), indent=1, default=str))
