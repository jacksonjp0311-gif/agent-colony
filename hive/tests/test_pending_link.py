"""Item 57: a Hive pending_apply linked to a matching self-heal trial.

Same knob and same value → one trial outcome credits both. Nothing is
applied twice. Item 58: no trial opens on a no-signal baseline, and an
inconclusive close is neither a positive nor a negative for Hive.
No colony imports: the self-heal state is stubbed through hive.host.
"""
from __future__ import annotations

import hive.host as host
import hive.swarm as SL
from hive.bitwork import WILSON_ACCEPT_PERMILLE


FP = "set_knob:direction=up:name=park_cycles:value=8"


def _winner(fp=FP, value=8):
    action = {"op": "set_knob", "name": "park_cycles", "direction": "up"}
    if value is not None:
        action["value"] = value
    return SL.Proposal(role="improver", label="dead_end_streak", action=action,
                       fingerprint=fp, symptom="stall", ok=True)


def _accepted(w, lower=901, margin=189, n=4):
    return SL.VoteResult(w, False, "accepted", {w.fingerprint: n}, lower, margin, n, 0, 1, n, None)


def _pending(value=8, **extra):
    w = _winner(value=value)
    p = {
        "fingerprint": w.fingerprint, "action": dict(w.action), "role": w.role,
        "label": w.label, "symptom": w.symptom, "card_id": "", "method": "",
        "deferred_under": "fp0", "first_deferred_cycle": "c0", "last_deferred_cycle": "c4",
        "deferred_count": 5, "vote": {"lower_permille": 901, "margin": 189},
        "wilson_gate": WILSON_ACCEPT_PERMILLE,
    }
    p.update(extra)
    return p


def _heal(trial=None, evidence=None):
    return {"trial": trial, "evidence": list(evidence or []), "metrics": []}


def _trial(frm=6, to=8, eid="ev_start", started="s1"):
    return {"knob": "park_cycles", "from": frm, "to": to, "direction": "up",
            "evidence_id": eid, "started_cycle": started}


def _close(event, eid="ev_start", started="s1", cid="ev_close"):
    return {"id": cid, "event": event, "knob": "park_cycles", "from": 8, "to": 6,
            "trial_evidence_id": eid, "started_cycle": started}


def _use_heal(monkeypatch, heal):
    box = {"heal": heal}
    monkeypatch.setattr(host, "heal_load_state", lambda: box["heal"])
    return box


def test_gates_unchanged():
    assert WILSON_ACCEPT_PERMILLE == 700


def test_match_requires_same_knob_and_value():
    p = _pending(value=8)
    assert SL._trial_matches_pending(_trial(to=8), p) is True
    assert SL._trial_matches_pending(_trial(frm=8, to=10), p) is False  # live 8→10 trial
    other = dict(_trial(to=8), knob="stall_cycles")
    assert SL._trial_matches_pending(other, p) is False
    rule = _pending(); rule["action"] = {"op": "add_park_rule", "cycles": 12}
    assert SL._trial_matches_pending(_trial(), rule) is False


def test_direction_only_pending_matches_stepped_value():
    p = _pending(value=None)
    expected = host.heal_stepped_value("park_cycles", "up", current=6)
    assert SL._trial_matches_pending(_trial(frm=6, to=expected), p) is True
    assert SL._trial_matches_pending(dict(_trial(frm=6, to=expected), direction="down"), p) is False


def test_link_once_then_stay_linked(monkeypatch):
    _use_heal(monkeypatch, _heal(trial=_trial()))
    st = SL._empty_state(); st["pending_apply"] = _pending()
    out = SL.sync_pending_with_heal_trial(st, "c5")
    assert out["linked"]["trial_evidence_id"] == "ev_start"
    assert st["pending_apply"]["linked_trial"]["to"] == 8
    out2 = SL.sync_pending_with_heal_trial(st, "c6")
    assert out2["linked"] is not None
    links = [e for e in st["evidence"] if e.get("event") == "pending_linked_to_trial"]
    assert len(links) == 1
    assert links[0]["wilson_gate"] == 700
    assert links[0]["deferred_count"] == 5


def test_no_link_for_non_matching_trial(monkeypatch):
    _use_heal(monkeypatch, _heal(trial=_trial(frm=8, to=10)))
    st = SL._empty_state(); st["pending_apply"] = _pending()
    out = SL.sync_pending_with_heal_trial(st, "c5")
    assert out == {"linked": None, "resolved": None}
    assert "linked_trial" not in st["pending_apply"]
    assert not st["evidence"]


def _linked_state(monkeypatch):
    box = _use_heal(monkeypatch, _heal(trial=_trial()))
    st = SL._empty_state(); st["pending_apply"] = _pending()
    SL.sync_pending_with_heal_trial(st, "c5")
    return st, box


def test_adopt_resolves_both_once(monkeypatch):
    st, box = _linked_state(monkeypatch)
    box["heal"] = _heal(trial=None, evidence=[_close("adopt")])
    out = SL.sync_pending_with_heal_trial(st, "c11")
    r = out["resolved"]
    assert r["outcome"] == "adopt" and r["hive_vote_correct"] is True
    assert r["heal_event_id"] == "ev_close"
    assert r["sources"] == ["self_heal", "hive_vote"]
    assert r["vote_lower_permille"] == 901 and r["deferred_count"] == 5
    assert st["pending_apply"] is None
    again = SL.sync_pending_with_heal_trial(st, "c12")
    assert again["resolved"] is None
    ev = [e for e in st["evidence"] if e.get("event") == "pending_resolved_by_trial"]
    assert len(ev) == 1 and ev[0]["wilson_gate"] == 700


def test_revert_resolves_with_vote_wrong(monkeypatch):
    st, box = _linked_state(monkeypatch)
    box["heal"] = _heal(trial=None, evidence=[_close("revert")])
    r = SL.sync_pending_with_heal_trial(st, "c11")["resolved"]
    assert r["outcome"] == "revert" and r["hive_vote_correct"] is False
    assert st["pending_apply"] is None


def test_inconclusive_or_void_unlinks_and_keeps_pending(monkeypatch):
    for event in ("trial_inconclusive", "trial_voided_confound"):
        st, box = _linked_state(monkeypatch)
        box["heal"] = _heal(trial=None, evidence=[_close(event)])
        out = SL.sync_pending_with_heal_trial(st, "c11")
        assert out["resolved"] is None
        assert st["pending_apply"] is not None
        assert "linked_trial" not in st["pending_apply"]
        assert st["pending_apply"]["deferred_count"] == 5
        un = [e for e in st["evidence"] if e.get("event") == "pending_unlinked"]
        assert len(un) == 1 and un[0]["reason"] == event


def test_close_not_found_unlinks(monkeypatch):
    st, box = _linked_state(monkeypatch)
    box["heal"] = _heal(trial=None, evidence=[])
    SL.sync_pending_with_heal_trial(st, "c11")
    assert st["pending_apply"] is not None and "linked_trial" not in st["pending_apply"]
    assert st["evidence"][-1]["reason"] == "trial_close_not_found"


def test_find_close_event_by_started_cycle_fallback():
    ev = [{"id": "x", "event": "revert", "knob": "park_cycles", "started_cycle": "s1"}]
    got = SL._find_close_event(ev, {"knob": "park_cycles", "started_cycle": "s1"})
    assert got["id"] == "x"
    assert SL._find_close_event(ev, {"knob": "park_cycles", "started_cycle": "s2"}) is None


def _stub(monkeypatch, w, calls):
    monkeypatch.setattr(SL, "observe", lambda cycle_id="": [{"kind": "dead_end_streak", "evidence": {}}])
    monkeypatch.setattr(SL, "swarm_propose", lambda *a, **k: [w])
    monkeypatch.setattr(SL, "vote", lambda *a, **k: _accepted(w))

    def _start(*a, **k):
        calls.append(1)
        return {"ok": True, "reason": "trial_started", "via": "self_heal"}
    monkeypatch.setattr(SL, "start_knob_trial", _start)
    monkeypatch.setattr(SL, "start_rule_trial", _start)
    monkeypatch.setattr(SL, "_window_is_confounded", lambda: False)
    monkeypatch.setattr(SL, "harvest_self_heal_outcomes", lambda *a, **k: [])
    monkeypatch.setattr("hive.library.mine_all", lambda **k: [])


def test_run_cycle_links_and_never_double_applies(monkeypatch):
    w = _winner()
    calls: list[int] = []
    _stub(monkeypatch, w, calls)
    _use_heal(monkeypatch, _heal(trial=_trial()))
    st = SL.load_state(); st["pending_apply"] = _pending(); SL.save_state(st)
    out = SL.run_cycle("c5")
    assert out["pending_link"]["trial_evidence_id"] == "ev_start"
    assert calls == []  # the same change is already live; not applied again
    st = SL.load_state()
    assert st["pending_apply"]["linked_trial"]
    assert int(st.get("applied_count") or 0) == 0
    assert not [e for e in st["evidence"] if e.get("event") == "trial_start"]


def test_run_cycle_resolves_on_adopt(monkeypatch):
    w = _winner()
    calls: list[int] = []
    _stub(monkeypatch, w, calls)
    box = _use_heal(monkeypatch, _heal(trial=_trial()))
    st = SL.load_state(); st["pending_apply"] = _pending(); SL.save_state(st)
    SL.run_cycle("c5")
    box["heal"] = _heal(trial=None, evidence=[_close("adopt")])
    monkeypatch.setattr(SL, "observe", lambda cycle_id="": [])
    out = SL.run_cycle("c11")
    assert out["pending_resolved"]["outcome"] == "adopt"
    st = SL.load_state()
    assert st["pending_apply"] is None
    assert calls == []


def test_start_knob_trial_refuses_no_signal_baseline(monkeypatch):
    rows = [{"cycle_id": f"b{i}", "new_oracle_targets": 0, "new_depth": 0,
             "oracle_pass_delta": 0, "score": 0.0, "env_fingerprint": "fp"} for i in range(6)]
    _use_heal(monkeypatch, {"trial": None, "metrics": rows, "evidence": []})
    monkeypatch.setattr(SL, "_baseline_is_confounded", lambda *a, **k: False)
    started: list[int] = []
    monkeypatch.setattr(host, "heal_start_trial", lambda *a, **k: started.append(1))
    out = SL.start_knob_trial(_winner(value=None), cycle_id="c", state=SL._empty_state())
    assert out == {"ok": False, "reason": "no_signal_baseline"}
    assert started == []


def test_start_rule_trial_refuses_no_signal_baseline(monkeypatch):
    rows = [{"cycle_id": f"b{i}", "new_oracle_targets": 0, "new_depth": 0,
             "oracle_pass_delta": 0, "score": 0.0, "env_fingerprint": "fp"} for i in range(6)]
    _use_heal(monkeypatch, {"trial": None, "metrics": rows, "evidence": []})
    p = SL.Proposal(role="improver", label="dead_end", action={"op": "add_park_rule", "cycles": 12},
                    fingerprint="add_park_rule:cycles=12", symptom="s", ok=True)
    st = SL._empty_state()
    out = SL.start_rule_trial(p, cycle_id="c", state=st)
    assert out == {"ok": False, "reason": "no_signal_baseline"}
    assert not st.get("trial")


def test_no_signal_defer_keeps_pending(monkeypatch):
    w = _winner()
    monkeypatch.setattr(SL, "observe", lambda cycle_id="": [{"kind": "dead_end_streak", "evidence": {}}])
    monkeypatch.setattr(SL, "swarm_propose", lambda *a, **k: [w])
    monkeypatch.setattr(SL, "vote", lambda *a, **k: _accepted(w))
    monkeypatch.setattr(SL, "start_knob_trial", lambda *a, **k: {"ok": False, "reason": "no_signal_baseline"})
    monkeypatch.setattr(SL, "_window_is_confounded", lambda: False)
    monkeypatch.setattr(SL, "harvest_self_heal_outcomes", lambda *a, **k: [])
    monkeypatch.setattr("hive.library.mine_all", lambda **k: [])
    out = SL.run_cycle("c1")
    assert out["pending_apply"]["fingerprint"] == FP
    st = SL.load_state()
    assert st["evidence"][-1]["reason"] == "no_signal_baseline"


def test_inconclusive_teaches_nothing(monkeypatch):
    ev = [{"id": "i1", "event": "trial_inconclusive", "knob": "park_cycles", "from": 10, "to": 6,
           "direction": "up", "swarm_fingerprint": FP, "cycle_id": "c"}]
    _use_heal(monkeypatch, {"trial": None, "metrics": [], "evidence": ev})
    st = SL._empty_state()
    resolved: list = []
    monkeypatch.setattr(SL, "resolve_shadows", lambda *a, **k: resolved.append(a))
    monkeypatch.setattr(SL, "teach_from_event", lambda *a, **k: (_ for _ in ()).throw(AssertionError("taught")))
    taught = SL.harvest_self_heal_outcomes(object(), st)
    assert taught == []
    assert resolved == []  # an inconclusive close does not score shadows either


def test_start_knob_trial_exploratory_when_cap_opens_targets(monkeypatch):
    rows = [{"cycle_id": f"b{i}", "new_oracle_targets": 0, "new_depth": 0,
             "oracle_pass_delta": 0, "score": 0.0, "env_fingerprint": "fp"} for i in range(6)]
    _use_heal(monkeypatch, {"trial": None, "metrics": rows, "evidence": []})
    monkeypatch.setattr(SL, "_baseline_is_confounded", lambda *a, **k: False)
    monkeypatch.setattr(host, "heal_predicted_new_targets", lambda name, value: ["oc_FAST"])
    started = []
    monkeypatch.setattr(host, "heal_start_trial", lambda trial, **k: started.append(trial))
    p = SL.Proposal(role="surveyor", label="depth_at_physical_cap",
                    action={"op": "set_knob", "name": "fast_term_cap", "direction": "up"},
                    fingerprint="set_knob:direction=up:name=fast_term_cap", symptom="cap", ok=True)
    out = SL.start_knob_trial(p, cycle_id="c", state=SL._empty_state())
    assert out["ok"] is True
    assert started[0]["exploratory"] is True and started[0]["predicted_targets"] == ["oc_FAST"]


def test_standalone_host_predicts_nothing():
    assert host.heal_predicted_new_targets("fast_term_cap", 10700) == []
