"""Traces.

Pattern: counts and averages between cycles. No model.
A later session continues this by appending, never by replacing.
Missing file means no prior change.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
STORE = ROOT / "data" / "commons" / "traces.jsonl"


def record_trace(fingerprint: str, score: int = 0) -> None:
    """Append one observation. Fail-open."""
    try:
        if not fingerprint:
            return
        STORE.parent.mkdir(parents=True, exist_ok=True)
        rec = {"fingerprint": str(fingerprint), "score": int(score)}
        with STORE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        return


def read_trace(fingerprint: str) -> dict:
    """Count, fast mean (last 3), slow mean (last 20). Fail-open zeros."""
    out = {"count": 0, "fast": 0.0, "slow": 0.0}
    try:
        if not STORE.exists() or not fingerprint:
            return out
        scores = []
        for line in STORE.read_text(encoding="utf-8").splitlines()[-200:]:
            try:
                rec = json.loads(line)
                if rec.get("fingerprint") == fingerprint:
                    scores.append(int(rec.get("score") or 0))
            except Exception:
                continue
        if not scores:
            return out
        out["count"] = len(scores)
        out["fast"] = sum(scores[-3:]) / max(1, len(scores[-3:]))
        out["slow"] = sum(scores[-20:]) / max(1, len(scores[-20:]))
        return out
    except Exception:
        return out
