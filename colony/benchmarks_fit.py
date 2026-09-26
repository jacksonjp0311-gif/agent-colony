"""Read society/benchmarks/latest.json into fitness prize components.

Institution names do not count. Score 0 unless benches ok.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LATEST = ROOT / "society" / "benchmarks" / "latest.json"
HISTORY = ROOT / "society" / "benchmarks" / "history.jsonl"


def _load_latest() -> dict[str, Any] | None:
    if not LATEST.exists():
        return None
    try:
        return json.loads(LATEST.read_text())
    except Exception:
        return None


def _previous_aggregate() -> float | None:
    if not HISTORY.exists():
        return None
    try:
        lines = [ln for ln in HISTORY.read_text().splitlines() if ln.strip()]
        if len(lines) < 2:
            return None
        prev = json.loads(lines[-2])
        return float(prev.get("aggregate_score") or 0.0)
    except Exception:
        return None


def bench_prize_components() -> dict[str, float]:
    """Return math_prize / compute_usefulness in [0,1] from measured benches."""
    data = _load_latest()
    if not data or not data.get("ok_all"):
        return {
            "math_prize": 0.0,
            "compute_usefulness": 0.0,
            "bench_score": 0.0,
            "bench_delta": 0.0,
            "bench_ok": 0.0,
        }
    score = float(data.get("aggregate_score") or 0.0)
    prev = _previous_aggregate()
    delta = 0.0 if prev is None else max(0.0, score - prev)
    # Correctness+speed score drives compute; small delta bonus for improvement
    compute = min(1.0, score)
    math = min(1.0, 0.85 * score + 0.15 * min(1.0, delta * 5.0))
    return {
        "math_prize": round(math, 4),
        "compute_usefulness": round(compute, 4),
        "bench_score": round(score, 4),
        "bench_delta": round(delta if prev is not None else 0.0, 4),
        "bench_ok": 1.0,
    }
