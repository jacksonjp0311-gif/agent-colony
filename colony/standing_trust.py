"""Standing trust gate — P≥0.70 selective authorize (James / SPARK2 telemetry mile).

Never silent accept-all. UNKNOWN stays UNKNOWN when evidence is thin.
Not AGI. Not novel theorems.
"""
from __future__ import annotations

# SPARK2: lowered from 0.75 → 0.70 (selective; never accept-all)
STANDING_TRUST_P_MIN: float = 0.70
STANDING_TRUST_P_MIN_BEFORE: float = 0.75  # prior mile compare field


def meets_standing_trust(confidence: float | None, *, machine_checked: bool = False) -> bool:
    """True iff confidence ≥ P_MIN and evidence is machine-checked. Selective gate."""
    if not machine_checked:
        return False
    if confidence is None:
        return False
    try:
        p = float(confidence)
    except (TypeError, ValueError):
        return False
    return p >= STANDING_TRUST_P_MIN


def threshold_compare(confidence: float | None) -> dict:
    """Before/after compare for authorize receipts (0.75 → 0.70)."""
    try:
        p = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        p = None
    return {
        "confidence": p,
        "P_min_before": STANDING_TRUST_P_MIN_BEFORE,
        "P_min_after": STANDING_TRUST_P_MIN,
        "would_pass_before": (p is not None and p >= STANDING_TRUST_P_MIN_BEFORE),
        "would_pass_after": (p is not None and p >= STANDING_TRUST_P_MIN),
        "newly_eligible_at_0_70": (
            p is not None
            and p >= STANDING_TRUST_P_MIN
            and p < STANDING_TRUST_P_MIN_BEFORE
        ),
    }
