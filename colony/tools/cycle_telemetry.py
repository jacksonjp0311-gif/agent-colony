"""Cycle telemetry — one append-only line per cycle.

Records what the non-LLM loop can actually observe:
residual magnitudes, foreign fingerprints seen, bias effect,
keep/revert, adoption feedback count.
Fail-open. No new dependencies. Lineage-preserving.
"""
from __future__ import annotations
from typing import Any, Dict
from pathlib import Path
import json
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent.parent
LOG = ROOT / "data" / "commons" / "cycle_telemetry.jsonl"

def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()

def emit(
    source: str,
    *,
    cycle_id: str = "",
    residual_max: float = 0.0,
    foreign_fps: int = 0,
    bias_delta: int = 0,
    outcome: str = "",
    adoption_notes: int = 0,
    extra: Dict[str, Any] | None = None,
) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": _utc(),
            "source": source,
            "lineage": source,
            "cycle_id": cycle_id,
            "residual_max": round(float(residual_max), 4),
            "foreign_fps": int(foreign_fps),
            "bias_delta": int(bias_delta),
            "outcome": outcome,
            "adoption_notes": int(adoption_notes),
        }
        if extra:
            rec["extra"] = extra
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass

def tail(n: int = 5) -> list:
    if not LOG.exists():
        return []
    lines = LOG.read_text(encoding="utf-8").splitlines()[-n:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out
