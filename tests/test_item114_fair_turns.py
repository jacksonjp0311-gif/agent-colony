"""Item 114: tie reverts do not feed high_revert_rate, tie cooldown, fair experiment turns."""
from __future__ import annotations

import json

import colony.self_heal as SH


def _rev(knob, direction, cid, b, t, reason="flat_passes", **kw):
    return {"event": "revert", "knob": knob, "direction": direction, "cycle_id": cid,
            "baseline_score": b, "trial_score": t, "reason": reason, **kw}


def _state(evidence, n_cycles=40, idx=None):
    cycles = [f"c{i:03d}" for i in range(n_cycles)]
    return {"evidence": evidence, "cycles": cycles, "cycles_dropped": 0,
            "cycle_index": n_cycles - 1 if idx is None else idx, "knobs": {"evaluation_window": 7}}


def test_tie_detection():
    assert SH.is_tie_revert(_rev("k", "up", "c1", 4.0, 4.0))
    assert not SH.is_tie_revert(_rev("k", "up", "c1", 4.0, 0.0))
    assert not SH.is_tie_revert({"event": "adopt", "baseline_score": 1, "trial_score": 1})
    assert not SH.is_tie_revert(_rev("k", "up", "c1", 0.0, 0.0, baseline_activity_score=1, activity_score=2))
    assert SH.is_tie_revert(_rev("k", "up", "c1", 0.0, 3.0, tie=True))


def test_tie_cooldown_after_two_ties(monkeypatch):
    monkeypatch.setenv("COLONY_ARM", "treatment")
    ev = [_rev("step_size", "down", "c010", 4.0, 4.0)]
    assert SH.tie_cooldown(_state(ev, idx=12), "step_size", "down") is None
    ev.append(_rev("step_size", "down", "c020", 4.0, 4.0))
    tc = SH.tie_cooldown(_state(ev, idx=25), "step_size", "down")
    assert tc and tc["cooldown"] == 21 and tc["until_index"] == 41
    assert SH._knob_on_cooldown(_state(ev, idx=25), "step_size", "down")
    # Other direction / knob untouched.
    assert SH.tie_cooldown(_state(ev, idx=25), "step_size", "up") is None
    # Expires after 3 evaluation windows.
    assert SH.tie_cooldown(_state(ev, idx=41), "step_size", "down") is None
    # A loss in between does not reset; an adopt does.
    ev2 = ev[:1] + [_rev("step_size", "down", "c015", 8.0, 4.0)] + ev[1:]
    assert SH.tie_cooldown(_state(ev2, idx=25), "step_size", "down") is not None
    ev3 = ev[:1] + [{"event": "adopt", "knob": "step_size", "direction": "down", "cycle_id": "c015"}] + ev[1:]
    assert SH.tie_cooldown(_state(ev3, idx=25), "step_size", "down") is None


def test_switch_off_and_control_arm(monkeypatch):
    ev = [_rev("step_size", "down", "c010", 4.0, 4.0), _rev("step_size", "down", "c020", 4.0, 4.0)]
    st = _state(ev, idx=25)
    monkeypatch.setenv("COLONY_ARM", "treatment")
    monkeypatch.setenv("COLONY_HEAL_FAIR_TURNS", "off")
    assert not SH.fair_turns_enabled()
    assert not SH._knob_on_cooldown(st, "step_size", "down")
    monkeypatch.delenv("COLONY_HEAL_FAIR_TURNS")
    monkeypatch.setenv("COLONY_ARM", "control")
    assert not SH.fair_turns_enabled()


def test_high_revert_rate_ignores_ties_and_self_fed_reverts(tmp_path, monkeypatch):
    monkeypatch.setenv("COLONY_ARM", "treatment")
    monkeypatch.setattr(SH, "STATE_PATH", tmp_path / "self_heal.json")
    monkeypatch.setattr(SH, "EVENT_LOG", tmp_path / "self_heal.jsonl")
    ties = [_rev("step_size", "down", f"c{i:03d}", 4.0, 4.0) for i in range(6)]
    st = SH.load_state()
    st["evidence"] = ties

    def kinds(state):
        return [f.get("kind") for f in SH.diagnose("cX", stall_state={}, heal_state=state)]

    assert "high_revert_rate" not in kinds(st)
    st["evidence"] = [_rev("evaluation_window", "up", f"c{i:03d}", 4.0, 0.0, reason="high_revert_rate")
                      for i in range(6)]
    assert "high_revert_rate" not in kinds(st)
    st["evidence"] = [_rev("park_cycles", "up", f"c{i:03d}", 4.0, 0.0) for i in range(6)]
    assert "high_revert_rate" in kinds(st)
    monkeypatch.setenv("COLONY_HEAL_FAIR_TURNS", "off")
    st["evidence"] = ties
    assert "high_revert_rate" in kinds(st)


def test_fair_turn_yield_bounded(tmp_path, monkeypatch):
    import hive.swarm as SW
    monkeypatch.setenv("COLONY_ARM", "treatment")
    hive_state = tmp_path / "swarm_learn.json"
    monkeypatch.setattr(SW, "STATE_PATH", hive_state)
    from colony import self_build as SB
    monkeypatch.setattr(SB, "load_state", lambda *a, **k: {})
    st = {"fair_last_close_index": 100, "cycle_index": 101, "knobs": {"evaluation_window": 7}}
    assert SH.fair_turn_yield(st) is None          # nobody waiting
    hive_state.write_text(json.dumps({"pending_apply": {"fingerprint": "x"}, "trial": None}))
    y = SH.fair_turn_yield(st)
    assert y and y["waiting"] == ["hive_pending_apply"] and y["limit"] == 14
    st["cycle_index"] = 114                         # 2 windows later: self-heal's turn again
    assert SH.fair_turn_yield(st) is None
    st["cycle_index"] = 101
    monkeypatch.setenv("COLONY_HEAL_FAIR_TURNS", "off")
    assert SH.fair_turn_yield(st) is None


def test_revert_evidence_records_tie_and_index(tmp_path, monkeypatch):
    monkeypatch.setenv("COLONY_ARM", "treatment")
    monkeypatch.setattr(SH, "STATE_PATH", tmp_path / "self_heal.json")
    monkeypatch.setattr(SH, "EVENT_LOG", tmp_path / "self_heal.jsonl")
    st = SH.load_state()
    st["cycle_index"] = 9
    st["trial"] = {"knob": "unused_menu_cycles", "from": 20, "to": 24, "direction": "up",
                   "reason": "high_revert_rate", "baseline_score": 2.0, "trial_metrics": [],
                   "window": 6}
    monkeypatch.setattr(SH, "trial_comparison_score", lambda t: 2.0)
    st = SH._close_trial(st, "c9", "revert")
    ev = st["evidence"][-1]
    assert ev["event"] == "revert" and ev["tie"] is True and ev["closed_index"] == 9
    assert ev["trial_reason"] == "high_revert_rate"
