"""Statistical Keep Gate — controls false-evolution rate.

A lightweight sequential check that a proposed keep must pass before
authorization. Inspired by online multiple-hypothesis testing ideas.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HISTORY = ROOT / "data" / "commons" / "keep_history.jsonl"

def record_outcome(delta: float, accepted: bool) -> None:
    rec = {"delta": delta, "accepted": accepted}
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")

def should_accept(delta: float, min_evidence: float = 0.02, false_rate_target: float = 0.05) -> bool:
    if delta <= min_evidence:
        return False
    if not HISTORY.exists():
        return True
    accepted = 0
    total = 0
    for line in HISTORY.read_text(encoding="utf-8").splitlines()[-100:]:
        try:
            rec = json.loads(line)
            total += 1
            if rec.get("accepted") and rec.get("delta", 0) <= 0:
                accepted += 1
        except Exception:
            continue
    if total == 0:
        return True
    rate = accepted / total
    return rate < false_rate_target
