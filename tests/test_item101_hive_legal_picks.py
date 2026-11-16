"""Item 101: Hive roles skip knob moves already at their bound (candidate side; gate unchanged)."""
from __future__ import annotations

from types import SimpleNamespace

import hive.swarm as swarm


def _fake_validate(bound: set[str]):
    def v(action):
        return SimpleNamespace(ok=action.get("name") not in bound, reason="step_hits_bound")
    return v


def test_first_legal_knob_skips_bound(monkeypatch):
    monkeypatch.delenv("HIVE_SKIP_BOUND_KNOBS", raising=False)
    monkeypatch.setattr(swarm.FA, "validate", _fake_validate({"fast_term_cap"}))
    monkeypatch.setattr(swarm, "_with_frontier_value", lambda a: dict(a))
    cands = [{"op": "set_knob", "name": "fast_term_cap", "direction": "up"},
             {"op": "set_knob", "name": "gf_term_cap", "direction": "up"}]
    assert swarm._first_legal_knob(cands)["name"] == "gf_term_cap"


def test_none_legal_keeps_old_first_pick(monkeypatch):
    monkeypatch.delenv("HIVE_SKIP_BOUND_KNOBS", raising=False)
    monkeypatch.setattr(swarm.FA, "validate", _fake_validate({"a", "b"}))
    monkeypatch.setattr(swarm, "_with_frontier_value", lambda a: dict(a))
    cands = [{"op": "set_knob", "name": "a", "direction": "up"}, {"op": "set_knob", "name": "b", "direction": "up"}]
    assert swarm._first_legal_knob(cands)["name"] == "a"


def test_kill_switch_restores_old_pick(monkeypatch):
    monkeypatch.setenv("HIVE_SKIP_BOUND_KNOBS", "off")
    monkeypatch.setattr(swarm.FA, "validate", _fake_validate({"fast_term_cap"}))
    cands = [{"op": "set_knob", "name": "fast_term_cap", "direction": "up"},
             {"op": "set_knob", "name": "gf_term_cap", "direction": "up"}]
    assert swarm._first_legal_knob(cands)["name"] == "fast_term_cap"


def test_surveyor_on_depth_cap_uses_next_suggestion(monkeypatch):
    from hive import host
    monkeypatch.delenv("HIVE_SKIP_BOUND_KNOBS", raising=False)
    monkeypatch.setattr(swarm.FA, "validate", _fake_validate({"fast_term_cap"}))
    monkeypatch.setattr(swarm, "_with_frontier_value", lambda a: dict(a))
    monkeypatch.setattr(host, "DIAGNOSIS_SUGGESTIONS",
                        {"depth_at_physical_cap": [("fast_term_cap", "up"), ("gf_term_cap", "up")]}, raising=False)
    a = swarm._action_for_role("surveyor", {"kind": "depth_at_physical_cap", "evidence": {}}, None)
    assert a == {"op": "set_knob", "name": "gf_term_cap", "direction": "up"}


def test_wilson_gate_constant_unchanged():
    assert swarm.WILSON_ACCEPT_PERMILLE == 700


def test_control_arm_still_skips_hive(monkeypatch):
    monkeypatch.setenv("COLONY_ARM", "control")
    from colony import hive_adapter
    assert hive_adapter.run_cycle("t").get("skipped") is True
