"""Invariant Contracts — machine-checkable preconditions for credit.

No unverified depth, no overlapping experiments, no frontier advance past untested values.
"""
from typing import Dict, Any

def check_verified_depth_contract(claim: Dict[str, Any]) -> bool:
    return bool(claim.get("independent_path_recorded", False))

def check_no_overlap(experiment_id: str, active: set) -> bool:
    return experiment_id not in active

def check_frontier_safe(frontier_advanced: bool, tested: bool) -> bool:
    if frontier_advanced and not tested:
        return False
    return True
