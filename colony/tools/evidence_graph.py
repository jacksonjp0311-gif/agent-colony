"""Shared Evidence Graph — append-only, queryable extension of the witness ledger.

Nodes: claims, counterexamples, method cards, experiment outcomes.
Edges: causal or temporal relations.
Agents may query; retrieval events are recorded.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent.parent
GRAPH_LOG = ROOT / "data" / "commons" / "evidence_graph.jsonl"

def append_node(node_type: str, payload: Dict[str, Any], edges: List[str] | None = None) -> str:
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": node_type,
        "payload": payload,
        "edges": edges or [],
        "id": f"{node_type}:{hash(json.dumps(payload, sort_keys=True)) & 0xffffffff:08x}",
    }
    GRAPH_LOG.parent.mkdir(parents=True, exist_ok=True)
    with GRAPH_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return rec["id"]

def query_by_type(node_type: str, limit: int = 50) -> List[Dict[str, Any]]:
    if not GRAPH_LOG.exists():
        return []
    out = []
    for line in GRAPH_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            if rec.get("type") == node_type:
                out.append(rec)
                if len(out) >= limit:
                    break
        except json.JSONDecodeError:
            continue
    return out
