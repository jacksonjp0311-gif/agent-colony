"""Thin readers over existing colony surfaces.

No new math. No new authority. Swarm and connective tissue call these
so they read Athanor H7, residuals, failure modes, and sensors that
already exist. Fail-soft.
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

def athanor_h7(traj: List[List[float]] | None = None) -> Dict[str, Any]:
    """Call existing Athanor coherence. Default empty traj returns neutral."""
    try:
        from colony.athanor_coherence import delta_phi, coherence_from_dphi, h7_horizon
        if not traj:
            return {"ok": True, "h7": None, "note": "no_traj"}
        dphi = delta_phi(traj)
        C = coherence_from_dphi(dphi)
        h7 = h7_horizon(C)
        return {"ok": True, "h7": h7, "mean_C": sum(C)/len(C) if C else None}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}

def residual_snapshot(role: str | None = None) -> Dict[str, Any]:
    """Read existing residual state. Does not update."""
    try:
        from colony.residuals import ResidualField
        # ResidualField expects state; we only report if a snapshot exists
        snap = _read_json(ROOT / "society" / "systems" / "residuals.json", {})
        if role and isinstance(snap, dict):
            return {"ok": True, "role": role, "entry": snap.get(role)}
        return {"ok": True, "roles": list(snap.keys())[:12] if isinstance(snap, dict) else []}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}

def recent_failures(limit: int = 5) -> Dict[str, Any]:
    """Tail of the existing self-change failure log."""
    log = ROOT / "data" / "commons" / "self_change_failures.jsonl"
    if not log.exists():
        return {"ok": True, "count": 0, "items": []}
    lines = log.read_text(encoding="utf-8").splitlines()[-limit:]
    items = []
    for line in lines:
        try:
            items.append(json.loads(line))
        except Exception:
            continue
    return {"ok": True, "count": len(items), "items": items}

def sensors_snapshot() -> Dict[str, Any]:
    snap = _read_json(ROOT / "society" / "systems" / "sensors.json", {})
    return {
        "ok": True,
        "trends": snap.get("trends", {}),
        "stall": snap.get("stall", {}),
        "feeds": snap.get("feeds", {}),
    }
