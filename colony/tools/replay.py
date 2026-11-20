"""Replay: same inputs, prior on vs prior off.

Pattern: record both decisions. The difference is the measurement.
Does not run a live trial. Fail-open.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "commons" / "replay.jsonl"


def replay(fingerprint: str, base: int, foreign: int, baseline: int) -> dict:
    def decide(score):
        return "adopt" if score > baseline else "revert"
    with_prior = base + foreign
    without = base
    rec = {
        "fingerprint": fingerprint,
        "base": base,
        "foreign": foreign,
        "baseline": baseline,
        "with_prior": {"score": with_prior, "outcome": decide(with_prior)},
        "without_prior": {"score": without, "outcome": decide(without)},
        "flipped": decide(with_prior) != decide(without),
    }
    try:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass
    return rec


if __name__ == "__main__":
    print(json.dumps(replay("park_cycles:up:10", 100, 40, 100)))
