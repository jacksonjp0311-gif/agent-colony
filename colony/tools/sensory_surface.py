"""Unified sensory surface — agents and Hive query external + internal signals.

Aggregates existing feeds, external array, PulseMesh, sensors, and the
evidence graph. Returns plain dicts with provenance. Fail-soft.
Correlations are debate input only. Not discovery. Not AGI.
"""
from __future__ import annotations
from typing import Any, Dict, List
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent.parent.parent

def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def sense(query: str = "", limit: int = 20) -> Dict[str, Any]:
    """Return a snapshot of available sensory channels."""
    out: Dict[str, Any] = {"query": query, "channels": {}}
    # Internal sensors
    sensors = _read_json(ROOT / "society" / "systems" / "sensors.json", {})
    out["channels"]["sensors"] = {
        "trends": sensors.get("trends", {}),
        "stall": sensors.get("stall", {}),
        "feeds_health": sensors.get("feeds", {}),
    }
    # External array snapshot
    ext = _read_json(ROOT / "society" / "systems" / "external_array.json", {})
    out["channels"]["external_array"] = {
        "sources": list(ext.get("sources", []))[:5] if isinstance(ext.get("sources"), list) else [],
        "last_ok": ext.get("last_ok"),
    }
    # PulseMesh
    pm = _read_json(ROOT / "society" / "systems" / "pulsemesh_feeds.json", {})
    out["channels"]["pulsemesh"] = {
        "collectors": list(pm.keys())[:8] if isinstance(pm, dict) else [],
    }
    # Evidence graph recent
    try:
        from colony.tools.evidence_graph import query_by_type
        recent = query_by_type("claim", limit=limit)
        out["channels"]["evidence_recent"] = len(recent)
    except Exception:
        out["channels"]["evidence_recent"] = 0
    out["ok"] = True
    return out
