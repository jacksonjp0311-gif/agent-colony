"""Hunter Persistence — write confirmed counterexamples before state update.

Ensures a hit is recorded in the evidence graph and a durable log even if the process restarts.
"""
from __future__ import annotations
from typing import Dict, Any
from colony.tools.evidence_graph import append_node

def persist_hit(claim_id: str, counterexample: Dict[str, Any]) -> str:
    payload = {"claim_id": claim_id, "counterexample": counterexample, "confirmed": True}
    return append_node("counterexample_hit", payload)
