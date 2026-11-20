
# RECEIPT ONLY. Canonical memory and drift live in Cortex sidecar + Cerebrum
# boundary. This log is an append-only trace the swarm may query. It never
# promotes, never authorizes, never overrides residuals or Athanor.
"""Multi-rate memory organ on top of the evidence graph.

- working: last N nodes (volatile query)
- durable: explicit promote (still candidate until human authorize)
- retained: spectral-style decay count so older evidence fades but remains queryable

Fail-soft. Does not auto-promote. Human authorize remains the ceiling.
"""
from __future__ import annotations
from typing import Any, Dict, List
from pathlib import Path
import json
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent.parent
MEMORY_LOG = ROOT / "data" / "commons" / "memory_organ.jsonl"

def _append(rec: Dict[str, Any]) -> None:
    MEMORY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with MEMORY_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")

def remember(kind: str, payload: Dict[str, Any], rate: str = "working") -> str:
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "rate": rate,  # working | durable | retained
        "payload": payload,
        "id": f"mem:{hash(json.dumps(payload, sort_keys=True)) & 0xffffffff:08x}",
    }
    _append(rec)
    # also mirror into evidence graph
    try:
        from colony.tools.evidence_graph import append_node
        append_node("memory", rec)
    except Exception:
        pass
    return rec["id"]

def recall(kind: str | None = None, rate: str | None = None, limit: int = 30) -> List[Dict[str, Any]]:
    if not MEMORY_LOG.exists():
        return []
    out = []
    for line in MEMORY_LOG.read_text(encoding="utf-8").splitlines()[-200:]:
        try:
            rec = json.loads(line)
            if kind and rec.get("kind") != kind:
                continue
            if rate and rec.get("rate") != rate:
                continue
            out.append(rec)
            if len(out) >= limit:
                break
        except Exception:
            continue
    return out
