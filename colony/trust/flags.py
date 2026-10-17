"""Ablation switches. Default ON; CI's trust gate refuses to run with either switched off.

COLONY_LEARNING=0   — outcome-derived memory is ignored by the mutation picker:
                      kill cooldown, Challenger blocked_targets, revert penalties,
                      recent-revert counts, lesson catalog hints, exploration-budget updates.
                      Human guides (written by James) still apply in both arms.
COLONY_CHALLENGER=0 — the desk skips the self-challenge step (no blocks, no notes).

These exist for matched ablations only (evidence/2026-10-11-trust-loop/).
"""
from __future__ import annotations

import os


def learning_enabled() -> bool:
    return os.environ.get("COLONY_LEARNING", "1") != "0"


def challenger_enabled() -> bool:
    return os.environ.get("COLONY_CHALLENGER", "1") != "0"


def semantic_bridge_enabled() -> bool:
    """Report-only semantic bridge logging (never kills). COLONY_SEMANTIC_BRIDGE=0 turns logging off."""
    return os.environ.get("COLONY_SEMANTIC_BRIDGE", "1") != "0"


def ablation_active() -> list[str]:
    out = []
    if not learning_enabled():
        out.append("COLONY_LEARNING=0")
    if not challenger_enabled():
        out.append("COLONY_CHALLENGER=0")
    if os.environ.get("COLONY_TEST_CRASH_AFTER_APPLY") == "1":
        out.append("COLONY_TEST_CRASH_AFTER_APPLY=1")
    return out
