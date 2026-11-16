"""Item 97: append the exemption records for ledger entries that came only from the old STEM
held-out bug (see colony/ledger_exemptions.py). Append-only and idempotent: an entry already
listed is not listed again; nothing in lessons/history is edited. Prints what it appended."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from colony import ledger_exemptions as LX  # noqa: E402

GATE = ROOT / "data" / "commons" / "novelty_gate.jsonl"
LESSONS = ROOT / "data" / "commons" / "lessons.jsonl"
HISTORY = ROOT / "society" / "benchmarks" / "conjecture_history.jsonl"


def main(write: bool = True, out: Path | None = None, gate: Path = GATE, lessons: Path = LESSONS,
         history: Path = HISTORY) -> list[dict]:
    out = out or LX.EXEMPT_LOG
    have = LX.exempt_ids(out)
    new = [r for r in LX.bug_only_rows(gate, lessons, history) if (r["source"], r["line_id"]) not in have]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [{"ts": ts, **r, "decided_by": "James Jackson (delegated, 2026-11-16 4:33 AM ET)"} for r in new]
    if write and rows:
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return rows


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    for r in main(write=not dry):
        print(json.dumps({k: r[k] for k in ("source", "entry_id", "entry_ts", "mutation", "gate_row_ts", "gate_kills")}))
