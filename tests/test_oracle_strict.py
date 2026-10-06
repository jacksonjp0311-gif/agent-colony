"""Phase 0 — Oracle fail-closed: saturated themes kill; bus_ok requires msg_ids."""
from __future__ import annotations

import os

from colony.oracle import evaluate, hear, _held_out_for_theme


def test_easy_pad_still_dies():
    v = evaluate(mutation="easy_pad_square_again", kind="easy_pad", source="test")
    assert v.passed is False
    assert v.fitness_credit is False


def test_claim_theme_without_bus_fail_closed(monkeypatch):
    monkeypatch.setenv("ORACLE_STRICT_CLAIMS", "1")
    v = evaluate(
        mutation="vandermonde",
        kind="claim_theme",
        claim_text="textbook vandermonde claim",
        source="test",
        bus=None,
    )
    assert v.passed is False
    assert "oracle_blocked_no_bus" in v.kills


def test_held_out_saturated_theme_fails():
    r = _held_out_for_theme("vandermonde", after_snapshot={"ok": True, "n_hard_pass": 25, "n_hard": 25})
    assert r.get("ok_for_oracle") is False
    assert "saturated" in str(r.get("reason") or "") or "no_theme" in str(r.get("reason") or "") or r.get("theme_window")


def test_bus_ok_requires_msg_ids():
    class FakeBus:
        def post(self, **kwargs):
            return {"id": "msg_test_1"}

        def record_peer_cite(self, **kwargs):
            return None

        def record_action_changed(self, **kwargs):
            return None

    h = hear(mutation="cassini", kind="hard_enable", bus=FakeBus(), cycle_id="t1")
    assert h.get("bus_ok") is True
    assert h.get("msg_ids")

    h2 = hear(mutation="cassini", kind="hard_enable", bus=None, cycle_id="t1")
    assert h2.get("bus_ok") is False


def test_oracle_can_kill_false_claim_theme(monkeypatch):
    monkeypatch.setenv("ORACLE_STRICT_CLAIMS", "1")

    class FakeBus:
        def post(self, **kwargs):
            return {"id": f"msg_{kwargs.get('from_role')}"}

        def record_peer_cite(self, **kwargs):
            return None

        def record_action_changed(self, **kwargs):
            return None

    v = evaluate(
        mutation="vandermonde",
        kind="claim_theme",
        claim_text="already saturated theme",
        source="test",
        bus=FakeBus(),
        cycle_id="test_kill",
    )
    # Saturated theme held-out should fail closed
    assert v.passed is False
