"""Causal decision attribution.

Pattern: record the ranking, the foreign contribution, the choice, the outcome.
A later system can replay with the prior removed.
Fail-open. Decides nothing.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
STORE = ROOT / "data" / "commons" / "attribution.jsonl"


def record(fingerprint: str, base: int, foreign: int, outcome: str, source: str = "colony") -> None:
    try:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "source": source,
            "fingerprint": fingerprint,
            "base": base,
            "foreign": foreign,
            "with_prior": base + foreign,
            "outcome": outcome,
        }
        with STORE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        return
