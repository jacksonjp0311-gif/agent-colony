"""Diversity / Novelty Filter grounded in Oracle outcomes.

Rejects a proposal if its Oracle signature is too close to recent accepted ones.
"""
from __future__ import annotations
from typing import Dict, Any, List
import hashlib
import json

def signature(claim: Dict[str, Any]) -> str:
    key = json.dumps(claim.get("ops", claim.get("type", "")), sort_keys=True)
    return hashlib.sha256(key.encode()).hexdigest()[:16]

def is_novel(claim: Dict[str, Any], recent_signatures: List[str], threshold: int = 2) -> bool:
    sig = signature(claim)
    matches = sum(1 for s in recent_signatures if s == sig)
    return matches < threshold
