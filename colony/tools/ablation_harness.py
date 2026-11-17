"""Ablation Harness — paired runs to measure causal influence of bus or method.

Runs a short twin (with / without the factor) and records the delta in Oracle outcomes.
"""
from __future__ import annotations
from typing import Callable, Dict, Any

def run_ablation(factor_name: str, with_fn: Callable[[], Dict[str, Any]], without_fn: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
    with_result = with_fn()
    without_result = without_fn()
    return {
        "factor": factor_name,
        "with_passes": with_result.get("oracle_passes", 0),
        "without_passes": without_result.get("oracle_passes", 0),
        "delta_passes": with_result.get("oracle_passes", 0) - without_result.get("oracle_passes", 0),
        "with_depth": with_result.get("verified_depth", 0),
        "without_depth": without_result.get("verified_depth", 0),
    }
