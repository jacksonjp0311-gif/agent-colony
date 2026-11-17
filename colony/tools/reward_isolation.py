"""Reward Path Isolation — refuse credit when invariants fail.

Wrapper that agents can call before awarding fitness or keep.
"""
from __future__ import annotations
from typing import Dict, Any
from colony.tools.invariant_contracts import check_verified_depth_contract, check_frontier_safe

def can_award_credit(claim: Dict[str, Any], frontier_advanced: bool = False, tested: bool = True) -> bool:
    if not check_verified_depth_contract(claim):
        return False
    if not check_frontier_safe(frontier_advanced, tested):
        return False
    return True
