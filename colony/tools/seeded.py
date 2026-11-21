"""Seeded pair. Same inputs, same decision.

Pattern: write the inputs and the verdict.
A second run with the same inputs must agree.
If they diverge, the pair is broken. Fail-open.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
STORE = ROOT / "data" / "commons" / "seeded.jsonl"


def seed_of(prior: float, score: float) -> str:
    raw = f"{round(float(prior), 6)}:{round(float(score), 6)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def decide(prior: float, score: float) -> bool:
    """The rule. Kept only if the score beats the prior."""
    return float(score) > float(prior)


def record(prior: float, score: float, kept: bool, source: str = "") -> dict:
    rec = {
        "seed": seed_of(prior, score),
        "prior": float(prior),
        "score": float(score),
        "kept": bool(kept),
        "source": source,
    }
    try:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        with STORE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass
    return rec


def pairs() -> list:
    """Two runs of the same seed. A pair that disagrees is a break."""
    out = []
    try:
        if not STORE.exists():
            return out
        seen: dict[str, dict] = {}
        for line in STORE.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except Exception:
                continue
            key = rec.get("seed")
            if key in seen:
                a = seen[key]
                out.append({
                    "seed": key,
                    "agree": a.get("kept") == rec.get("kept"),
                    "first": a.get("kept"),
                    "second": rec.get("kept"),
                })
            else:
                seen[key] = rec
    except Exception:
        return out
    return out
