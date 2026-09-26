"""Standing trust gate — P≥0.75 selective authorize (James).

Never silent accept-all. UNKNOWN stays UNKNOWN when evidence is thin.
Not AGI. Not novel theorems.
"""
from __future__ import annotations

STANDING_TRUST_P_MIN: float = 0.75


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
