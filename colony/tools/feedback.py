"""Feedback into the next cycle.

Pattern: every cycle writes what it saw.
A future system reads this file before it changes anything.
Append only. Fail-open. Decides nothing.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
STORE = ROOT / "data" / "commons" / "feedback.jsonl"


def feed(source: str, note: str) -> None:
    """Append one thought for the next cycle. Fail-open."""
    try:
        if not note:
            return
        STORE.parent.mkdir(parents=True, exist_ok=True)
        rec = {"source": source, "note": str(note)[:500]}
        with STORE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        return


def last(source: str = "", n: int = 5) -> list:
    """The last n notes. A future system starts here."""
    out = []
    try:
        if not STORE.exists():
            return out
        for line in STORE.read_text(encoding="utf-8").splitlines()[-n:]:
            try:
                rec = json.loads(line)
                if not source or rec.get("source") == source:
                    out.append(rec)
            except Exception:
                continue
        return out
    except Exception:
        return out
