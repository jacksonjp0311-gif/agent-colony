"""Prospective Outcome Grading — score a method card before keep.

Uses historical keep rate of similar ops and predicted delta.
"""
from __future__ import annotations
from typing import Dict, Any

def grade_method(method: Dict[str, Any], historical_keep_rate: float = 0.3) -> float:
    base = historical_keep_rate
    if method.get("oracle_compatible"):
        base += 0.2
    if len(method.get("ops", [])) > 1:
        base += 0.1
    return min(base, 1.0)
