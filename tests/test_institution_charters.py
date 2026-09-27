"""Institution standing charters — agenda autonomy, never truth/authorize."""
from __future__ import annotations

from colony.institution_charters import (
    STANDING_CHARTERS,
    attempt_ledger_accept,
    charter_topic_hints,
    ensure_charters,
    pursue_cycle,
    refuse_authorize,
)
from colony.standing_trust import STANDING_TRUST_P_MIN, meets_standing_trust


REQUIRED = {
    "Math Prize Desk",
    "RSI Coupling Desk",
    "Council of Careful Doubt",
    "Workshop of Making",
    "Archive of Attempts",
    "Academy of Learning",
}


def test_charters_cover_key_institutions():
    names = {c["name"] for c in STANDING_CHARTERS}
    assert REQUIRED.issubset(names)
    assert len(STANDING_CHARTERS) >= 15  # all live institutions


def test_ensure_and_pursue_inform_only():
    data = ensure_charters(cycle_id="test_ch")
    assert data["inform_only"] is True
    assert data["durable_accept"] is False
    assert data["can_authorize"] is False
    assert data["count"] >= 15
    for c in data["charters"]:
        assert c["inform_only"] is True
        assert c["durable_accept"] is False
        assert c["can_authorize"] is False
        assert c["truth_authority"] is False
        assert "agenda" in c["autonomy_of"]
        assert "truth" in c["not_autonomy_of"]
        assert int(c["cycles_remaining"]) > 0

    state: dict = {}
    out = pursue_cycle("test_ch_cycle", state_data=state)
    assert out["inform_only"] is True
    assert out["durable_accept"] is False
    assert out["can_authorize"] is False
    assert len(out["pursued"]) >= 6
    assert out["topic_hints"]
    assert state["institution_charters"]["durable_accept"] is False
    assert state["institution_charters"]["can_authorize"] is False


def test_charter_pursuit_cannot_authorize_or_accept():
    refused = refuse_authorize(finding_id="fnd_fake", decision="accepted")
    assert refused["accepted"] is False
    assert refused["refused"] is True
    assert refused["durable_accept"] is False
    assert refused["can_authorize"] is False
    refused2 = attempt_ledger_accept(finding_id="fnd_fake")
    assert refused2["accepted"] is False
    assert refused2["refused"] is True


def test_ceiling_still_holds():
    assert STANDING_TRUST_P_MIN == 0.70
    assert meets_standing_trust(0.99, machine_checked=False) is False
    assert meets_standing_trust(0.65, machine_checked=True) is False
    hints = charter_topic_hints()
    assert all(h.get("inform_only") and not h.get("durable_accept") for h in hints)
