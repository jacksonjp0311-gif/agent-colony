"""Constrained Method Composition Language.

A small grammar for combining existing Oracle-verified primitives.
No free-form code; only named operators the Oracle already accepts.
"""
from __future__ import annotations
from typing import List, Dict, Any

ALLOWED_OPS = {"modular_search", "cem_sample", "companion_matrix", "residue_check", "holdout_shift"}

def compose(ops: List[str], params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    for op in ops:
        if op not in ALLOWED_OPS:
            raise ValueError(f"op not in allowed set: {op}")
    return {
        "type": "composed_method",
        "ops": ops,
        "params": params or {},
        "oracle_compatible": True,
    }
