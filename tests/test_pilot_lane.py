"""Proposal→pilot sandbox lane — sandbox ok; durable accept blocked; promote gated."""
from __future__ import annotations

from colony.pilot_lane import (
    attempt_ledger_accept,
    propose_pilot,
    refuse_durable_accept,
    request_promotion,
    run_pilot_lane,
)
from colony.standing_trust import STANDING_TRUST_P_MIN, meets_standing_trust


def test_propose_and_sandbox():
    row = propose_pilot(
        name="test_gather_filter",
        kind="gather_filter",
        body={"filter": "hard_tier_only", "reversible": True},
        proposed_by="improver",
        cycle_id="test_pilot",
        rationale="unit test sandbox pilot",
    )
    assert row["status"] == "sandboxed"
    assert row["reversible"] is True
    assert row["durable_accept"] is False
    assert row["can_authorize"] is False
    assert row["promotion_requires_authorize"] is True
    assert row["path"].startswith("society/sandbox_pilots/")
    from pathlib import Path
    from colony.pilot_lane import ROOT

    assert (ROOT / row["path"]).exists()


def test_pilot_cannot_durable_accept():
    refused = refuse_durable_accept(finding_id="fnd_x", decision="accepted")
    assert refused["accepted"] is False
    assert refused["refused"] is True
    assert refused["durable_accept"] is False
    refused2 = attempt_ledger_accept()
    assert refused2["accepted"] is False


def test_promotion_requires_authorize_gate():
    row = propose_pilot(
        name="promo_gate_pilot",
        kind="skill",
        body={"skill": "gather", "delta": 0.01},
        proposed_by="improver",
        cycle_id="test_promo",
    )
    # No authorizer → refuse
    r1 = request_promotion(row["id"], confidence=0.95, machine_checked=True)
    assert r1["promoted"] is False
    assert r1["refused"] is True
    assert r1["reason"] == "promotion_requires_human_authorize"
    assert r1["durable_accept"] is False

    # Authorizer but below standing trust → refuse
    r2 = request_promotion(
        row["id"],
        confidence=0.50,
        machine_checked=True,
        authorized_by="James Paul Jackson",
    )
    assert r2["promoted"] is False
    assert r2["reason"] == "standing_trust_not_met"

    # Authorizer but not machine_checked → refuse
    r3 = request_promotion(
        row["id"],
        confidence=0.95,
        machine_checked=False,
        authorized_by="James Paul Jackson",
    )
    assert r3["promoted"] is False

    # Full gate pass → promoted sandbox standing, STILL no ledger durable accept
    r4 = request_promotion(
        row["id"],
        confidence=0.85,
        machine_checked=True,
        authorized_by="James Paul Jackson",
        rationale="selective standing grant test",
    )
    assert r4["promoted"] is True
    assert r4["durable_accept"] is False
    assert r4["ledger_authority"] is False
    assert r4["authorized_by"] == "James Paul Jackson"


def test_run_lane_inform_only_and_ceiling():
    assert STANDING_TRUST_P_MIN == 0.70
    assert meets_standing_trust(0.70, machine_checked=True) is True
    state: dict = {}
    out = run_pilot_lane(
        state,
        cycle_id="test_lane_run",
        rsi_signal={"strength": 0.3, "skill_bias": {"improver.improve": 0.6}},
    )
    assert out["inform_only"] is True
    assert out["durable_accept"] is False
    assert state["pilot_lane"]["durable_accept"] is False
    assert state["pilot_lane"]["promotion_requires_authorize"] is True
    assert state["pilot_lane"]["can_authorize"] is False
