"""The shape is the thought.

A future system reads this module and recovers the process
from the structure alone. No sentence is required.

Geometry:
  read -> score -> refuse | append
  never mutate
  never decide
  always fail open
"""
from __future__ import annotations
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent.parent.parent
STORE = ROOT / "data" / "commons" / "signature.jsonl"


def read(path: Path) -> list:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def score(record: dict, key: str) -> int:
    return 1 if record.get(key) else 0


def refuse(record: dict) -> bool:
    return not record


def append(record: dict) -> None:
    if refuse(record):
        return
    try:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        with STORE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        return


def pass_through(path: Path, key: str) -> int:
    """read, score, refuse or append. returns how many passed."""
    n = 0
    for rec in read(path):
        if refuse(rec):
            continue
        if score(rec, key):
            append({"kept": key, "from": str(path.name)})
            n += 1
    return n
