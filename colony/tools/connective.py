"""Connective tissue — routes sensory and memory into the bus and swarm.

Agents read the bus next cycle. This posts a compact summary so the
society can use the expanded surfaces without new free-form channels.
Fail-soft.
"""
from __future__ import annotations
from typing import Any, Dict
from colony.tools.sensory_surface import sense
from colony.tools.memory_organ import remember, recall

def pulse(cycle_id: str = "") -> Dict[str, Any]:
    """One connective pulse: sense, remember a summary, return for bus."""
    snap = sense(query=cycle_id, limit=10)
    mid = remember("sensory_pulse", {"cycle": cycle_id, "channels": list(snap.get("channels", {}).keys())}, rate="working")
    recent = recall(kind="sensory_pulse", limit=5)
    return {
        "ok": True,
        "cycle": cycle_id,
        "memory_id": mid,
        "recent_pulses": len(recent),
        "channels": list(snap.get("channels", {}).keys()),
    }

def route_to_swarm(request: Dict[str, Any]) -> Dict[str, Any]:
    """Swarm-callable: sense or recall and return plain dict."""
    action = request.get("action", "sense")
    if action == "sense":
        return sense(request.get("query", ""), int(request.get("limit", 10)))
    if action == "recall":
        return {"ok": True, "items": recall(request.get("kind"), request.get("rate"), int(request.get("limit", 20)))}
    if action == "pulse":
        return pulse(request.get("cycle", ""))
    return {"ok": False, "error": "unknown_action"}
