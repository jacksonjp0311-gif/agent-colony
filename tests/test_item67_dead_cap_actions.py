"""Item 67: Hive and self-heal stop circling a used-up cap value.

(a) An apply deferred as no_bound_predicted_target retires that exact
    action under the current state (append-only evidence), so the vote
    moves on. The retirement lapses when the state key changes.
(b) Cap-knob raises step from the live frontier (a bound target's
    recorded cap) when the plain step binds nothing; bounds unchanged.
(c) When a cap raise was the remedy and no cap can bind any target,
    self-heal falls through to a non-cap, non-meta knob instead of
    stopping at no_bearing_signal. Adopt is still strictly better.
Plus: self-heal cycle_index keeps rising past the 80-id cycles list,
so knob cooldowns expire.
"""
from __future__ import annotations

import colony.hive_adapter  # noqa: F401  binds Hive to live self-heal
import colony.oeis_conjectures as O
import colony.self_heal as SH
import colony.stall as S
import hive.host as host
import hive.library as FL
import hive.swarm as SL


def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(SH, "STATE_PATH", tmp_path / "self_heal.json")
    monkeypatch.setattr(SH, "EVENT_LOG", tmp_path / "self_heal.jsonl")
    monkeypatch.setattr(S, "STATE_PATH", tmp_path / "stall_state.json")
    monkeypatch.setattr(FL, "LIBRARY_LOG", tmp_path / "fix_library.jsonl")
    monkeypatch.setattr(FL, "LIBRARY_SNAPSHOT", tmp_path / "swarm_library.json")
    monkeypatch.setattr(SL, "STATE_PATH", tmp_path / "swarm_learn.json")
    monkeypatch.setattr(SL, "EVENT_LOG", tmp_path / "swarm_learn.jsonl")
    monkeypatch.setattr(SL, "RULES_PATH", tmp_path / "swarm_rules.json")


def _log(*rows):
    return {"attempts": list(rows), "by_cycle": {}}


HOLD = {"id": "oc_A165064_0", "status": "holds_on_range", "planned": 10700,
        "verified_depth": 10699, "depth": 10699, "cap_reason": "term_cap", "cap_value": 10700}


# --- (b) frontier values --------------------------------------------------

def test_cap_frontier_values_reads_bound_term_caps():
    assert SH.cap_frontier_values("fast_term_cap", attempt_log=_log(HOLD)) == [10700]
    assert SH.cap_frontier_values("deep_digits", attempt_log=_log(HOLD)) == []


def test_cap_frontier_values_uses_last_row_per_target():
    old = dict(HOLD, cap_value=8000, verified_depth=7999, planned=8000)
    assert SH.cap_frontier_values("fast_term_cap", attempt_log=_log(old, HOLD)) == [10700]


def test_frontier_value_steps_past_used_up_cap(monkeypatch):
    monkeypatch.setattr(SH, "predicted_new_targets",
                        lambda k, v, **kw: ["oc_A165064_0"] if float(v) > 10700 else [])
    nv = SH.frontier_cap_value("fast_term_cap", "up", current=8000, step_size=0.15,
                               attempt_log=_log(HOLD))
    assert nv == 10700 + int(round(0.15 * (20000 - 2000)))  # 13400
    spec = SH.KNOB_SPECS["fast_term_cap"]
    assert spec.lo <= nv <= spec.hi


def test_frontier_keeps_plain_step_when_it_binds(monkeypatch):
    monkeypatch.setattr(SH, "predicted_new_targets", lambda k, v, **kw: ["oc_X"])
    nv = SH.frontier_cap_value("fast_term_cap", "up", current=8000, step_size=0.15,
                               attempt_log=_log(HOLD))
    assert nv == 10700


def test_frontier_falls_back_to_plain_step_when_nothing_binds(monkeypatch):
    monkeypatch.setattr(SH, "predicted_new_targets", lambda k, v, **kw: [])
    nv = SH.frontier_cap_value("fast_term_cap", "up", current=8000, step_size=0.15,
                               attempt_log=_log(HOLD))
    assert nv == 10700


def test_frontier_stays_inside_knob_bounds(monkeypatch):
    monkeypatch.setattr(SH, "predicted_new_targets",
                        lambda k, v, **kw: ["oc_X"] if float(v) > 10700 else [])
    hi_hold = dict(HOLD, cap_value=19500, planned=19500, verified_depth=19499)
    nv = SH.frontier_cap_value("fast_term_cap", "up", current=8000, step_size=0.15,
                               attempt_log=_log(hi_hold))
    assert nv == SH.KNOB_SPECS["fast_term_cap"].hi


def test_frontier_down_and_non_cap_are_plain_steps():
    assert SH.frontier_cap_value("fast_term_cap", "down", current=8000) == SH.stepped_value(
        "fast_term_cap", "down", current=8000)
    assert SH.frontier_cap_value("park_cycles", "up", current=6) == SH.stepped_value(
        "park_cycles", "up", current=6)


def test_control_arm_keeps_plain_step(monkeypatch):
    import colony.arm as arm
    monkeypatch.setattr(arm, "self_mod_enabled", lambda *a, **k: False)
    monkeypatch.setattr(SH, "predicted_new_targets",
                        lambda k, v, **kw: ["oc_X"] if float(v) > 10700 else [])
    nv = SH.frontier_cap_value("fast_term_cap", "up", current=8000, step_size=0.15,
                               attempt_log=_log(HOLD))
    assert nv == 10700


def test_retire_key_changes_when_frontier_moves(monkeypatch):
    monkeypatch.setattr(SH, "cap_frontier_values", lambda k, **kw: [10700])
    a = SH.cap_retire_key("fast_term_cap")
    monkeypatch.setattr(SH, "cap_frontier_values", lambda k, **kw: [13400])
    assert SH.cap_retire_key("fast_term_cap") != a


def test_cap_knobs_exhausted(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    monkeypatch.setattr(SH, "predicted_new_targets", lambda k, v, **kw: [])
    assert SH.cap_knobs_exhausted(SH.load_state()) is True
    monkeypatch.setattr(SH, "predicted_new_targets",
                        lambda k, v, **kw: ["oc_G"] if k == "gf_term_cap" else [])
    assert SH.cap_knobs_exhausted(SH.load_state()) is False


# --- Hive proposals carry the frontier value -------------------------------

def test_hive_cap_proposal_uses_frontier_value(monkeypatch):
    monkeypatch.setattr(host, "heal_frontier_cap_value", lambda n, d, current=None: 13400)
    out = SL._with_frontier_value({"op": "set_knob", "name": "fast_term_cap", "direction": "up"})
    assert out["value"] == 13400


def test_hive_explicit_value_and_non_cap_unchanged(monkeypatch):
    monkeypatch.setattr(host, "heal_frontier_cap_value", lambda n, d, current=None: 13400)
    a = {"op": "set_knob", "name": "fast_term_cap", "direction": "up", "value": 10700}
    assert SL._with_frontier_value(a) == a
    b = {"op": "set_knob", "name": "park_cycles", "direction": "up"}
    assert SL._with_frontier_value(b) == b


def test_standalone_host_frontier_is_plain_step(monkeypatch):
    monkeypatch.setattr(host, "_heal", None)
    assert host.heal_cap_retire_key("fast_term_cap") == ""


# --- (a) retire the dead action ------------------------------------------

def _prime_signal(n=6):
    st = SH.load_state()
    fp = SH.environment_fingerprint(state=st)["digest"]
    rows = []
    for i in range(n):
        d = 1 if i % 2 == 0 else -1
        rows.append({"cycle_id": f"b{i}", "new_oracle_targets": 0, "new_depth": 0,
                     "oracle_passes": 528, "oracle_pass_delta": d,
                     "score": SH.score_metrics(0, 0, d), "env_fingerprint": fp})
    st["metrics"] = rows
    st["cycle_index"] = n - 1
    st["cycles"] = [f"b{i}" for i in range(n)]
    SH.save_state(st)


def _p(name, value, label="depth_at_physical_cap", role="surveyor"):
    action = {"op": "set_knob", "name": name, "direction": "up", "value": value}
    return SL.Proposal(role=role, label=label, action=action,
                       fingerprint=f"set_knob:direction=up:name={name}:value={value}",
                       symptom="cap", ok=True)


def _stub_cycle(monkeypatch, props):
    def _vote(proposals, router):
        legal = [p for p in proposals if p.ok and not p.veto]
        if not legal:
            return SL.VoteResult(None, True, "no_legal_proposal", {}, 0, 0, 0, 0)
        w = legal[0]
        return SL.VoteResult(w, False, "accepted", {p.fingerprint: 1 for p in legal},
                             901, 189, len(legal), 0, 1, 4, legal[1] if len(legal) > 1 else None)
    monkeypatch.setattr(SL, "observe", lambda cycle_id="": [{"kind": "depth_at_physical_cap", "evidence": {}}])
    monkeypatch.setattr(SL, "swarm_propose", lambda *a, **k: [SL.Proposal(**{**p.__dict__}) for p in props])
    monkeypatch.setattr(SL, "vote", _vote)
    monkeypatch.setattr(SL, "_window_is_confounded", lambda: False)
    monkeypatch.setattr(SL, "harvest_self_heal_outcomes", lambda *a, **k: [])
    monkeypatch.setattr("hive.library.mine_all", lambda **k: [])


def test_dead_action_is_retired_and_vote_moves_on(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _prime_signal()
    dead = _p("fast_term_cap", 10700)
    other = _p("park_cycles", 8, label="dead_end_streak", role="improver")
    _stub_cycle(monkeypatch, [dead, other])
    monkeypatch.setattr(host, "heal_cap_retire_key", lambda n: "k1" if n == "fast_term_cap" else "kp")
    monkeypatch.setattr(SH, "predicted_new_targets", lambda k, v, **kw: [])
    monkeypatch.setattr(host, "heal_frontier_cap_value", lambda n, d, current=None: 10700)
    st = SL.load_state()
    st["pending_apply"] = {"fingerprint": dead.fingerprint, "action": dict(dead.action),
                           "deferred_count": 8}
    SL.save_state(st)
    SL.run_cycle("c1")
    st = SL.load_state()
    ret = [e for e in st["evidence"] if e.get("event") == "action_retired"]
    assert len(ret) == 1 and ret[0]["fingerprint"] == dead.fingerprint
    assert ret[0]["reason"] == "no_bound_predicted_target"
    assert st["retired_actions"][dead.fingerprint]["key"] == "k1"
    assert not st.get("pending_apply")
    assert any(e.get("event") == "pending_apply_dropped" and e.get("reason") == "action_retired"
               for e in st["evidence"])
    # Next cycle: the retired action is out of the vote; the runner-up wins.
    started = []
    monkeypatch.setattr(SL, "start_knob_trial",
                        lambda w, **k: started.append(w.fingerprint) or {"ok": False, "reason": "confounded_baseline"})
    SL.run_cycle("c2")
    assert started == [other.fingerprint]
    st = SL.load_state()
    last = [e for e in st["evidence"] if e.get("event") == "apply_deferred"][-1]
    assert last["retired_dropped"] == [dead.fingerprint]
    # Retiring is recorded once, not every cycle.
    assert len([e for e in st["evidence"] if e.get("event") == "action_retired"]) == 1


def test_retirement_lapses_when_state_key_changes(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    dead = _p("fast_term_cap", 10700)
    st = SL._empty_state()
    box = {"k": "k1"}
    monkeypatch.setattr(host, "heal_cap_retire_key", lambda n: box["k"])
    SL.retire_action(st, dead, "c1")
    assert SL.is_retired(st, dead) is True
    box["k"] = "k2"
    assert SL.is_retired(st, dead) is False
    assert SL.drop_retired_proposals(st, [dead]) == []
    assert dead.ok is True


def test_non_knob_actions_are_never_retired(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = SL.Proposal(role="improver", label="dead_end", action={"op": "add_park_rule", "cycles": 12},
                    fingerprint="add_park_rule:cycles=12", symptom="s", ok=True)
    st = SL._empty_state()
    assert SL.retire_action(st, p, "c1") is None
    assert not st.get("retired_actions")


# --- (c) self-heal falls through when caps are used up ----------------------

def _supply_only_window(tmp_path, monkeypatch):
    monkeypatch.setattr(SH, "rescore_metric_row", lambda r, **k: dict(r))
    monkeypatch.setattr(SH, "baseline_environment_confounded", lambda *a, **k: False)
    st = SH.load_state()
    st["metrics"] = [
        {"cycle_id": f"b{i}", "new_oracle_targets": i % 2, "new_depth": 0,
         "oracle_passes": 528, "oracle_pass_delta": 0,
         "score": SH.score_metrics(i % 2, 0, 0)} for i in range(6)
    ]
    st["cycle_index"] = 5
    st["cycles"] = [f"b{i}" for i in range(6)]
    SH.save_state(st)
    return SH.load_state()


FINDINGS = [
    {"kind": "depth_at_physical_cap", "evidence": {}, "suggest": [("fast_term_cap", "up")]},
    {"kind": "flat_passes", "evidence": {}},
    {"kind": "high_revert_rate", "evidence": {}},
]


def test_fallthrough_to_non_cap_knob_when_caps_exhausted(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    st = _supply_only_window(tmp_path, monkeypatch)
    monkeypatch.setattr(SH, "eligible_target_ids", lambda stall_state=None: set())
    prop = SH.propose_trial(FINDINGS, state=st, cycle_id="c")
    assert prop is not None
    assert prop["fallthrough"] == "caps_exhausted"
    assert prop["knob"] not in SH.CAP_KNOBS
    assert SH.KNOB_SPECS[prop["knob"]].group not in ("meta", "caps")
    assert prop["authorized"] is False
    assert not prop.get("predicted_targets")


def test_no_fallthrough_while_a_cap_can_bind(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    st = _supply_only_window(tmp_path, monkeypatch)
    monkeypatch.setattr(SH, "predicted_new_targets",
                        lambda k, v, **kw: ["oc_G"] if k == "gf_term_cap" else [])
    # gf_term_cap (a depth_at_physical_cap remedy) still binds a target:
    # the predicted cap trial opens; no fall-through.
    prop = SH.propose_trial(FINDINGS, state=st, cycle_id="c")
    assert prop is not None
    assert prop["knob"] == "gf_term_cap"
    assert prop["predicted_targets"] == ["oc_G"]
    assert "fallthrough" not in prop


def test_no_fallthrough_without_a_cap_finding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    st = _supply_only_window(tmp_path, monkeypatch)
    monkeypatch.setattr(SH, "eligible_target_ids", lambda stall_state=None: set())
    prop = SH.propose_trial(FINDINGS[1:], state=st, cycle_id="c")
    assert prop is None


def test_fallthrough_not_repeated_after_inconclusive(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    st = _supply_only_window(tmp_path, monkeypatch)
    monkeypatch.setattr(SH, "eligible_target_ids", lambda stall_state=None: set())
    first = SH.propose_trial(FINDINGS, state=st, cycle_id="c")
    st["evidence"].append({"event": "trial_inconclusive", "knob": first["knob"],
                           "from": first["to"], "to": first["from"], "fallthrough": "caps_exhausted"})
    second = SH.propose_trial(FINDINGS, state=st, cycle_id="c2")
    assert second is None or (second["knob"], second["to"]) != (first["knob"], first["to"])


def test_fallthrough_trial_start_records_flag(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    st = _supply_only_window(tmp_path, monkeypatch)
    monkeypatch.setattr(SH, "eligible_target_ids", lambda stall_state=None: set())
    prop = SH.propose_trial(FINDINGS, state=st, cycle_id="c")
    st = SH.start_trial(prop, state=st, cycle_id="c")
    ev = [e for e in SH.load_state()["evidence"] if e.get("event") == "trial_start"][-1]
    assert ev["fallthrough"] == "caps_exhausted"


# --- cycle_index keeps rising past the 80-id list ---------------------------

def test_cycle_index_monotonic_past_keep_limit():
    st = {"cycles": [f"c{i}" for i in range(80)], "cycle_index": 79}
    for i in range(80, 90):
        st = SH._remember_cycle(st, f"c{i}")
    assert st["cycle_index"] == 89
    assert len(st["cycles"]) == SH.CYCLES_KEEP
    assert st["cycles_dropped"] == 10
    # Re-seeing a kept id maps back to its absolute index.
    assert SH._remember_cycle(dict(st), "c85")["cycle_index"] == 85


def test_cooldown_expires_after_list_is_full(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    st = SH.load_state()
    st["cycles"] = [f"c{i}" for i in range(80)]
    st["cycle_index"] = 80
    st["knob_last_trial"] = {"fast_term_cap": {"direction": "up", "cycle_index": 80}}
    assert SH._knob_on_cooldown(st, "fast_term_cap", "up") is True
    for i in range(80, 80 + SH.KNOB_RETRY_COOLDOWN + 2):
        st = SH._remember_cycle(st, f"n{i}")
    SH.save_state(st)
    st = SH.load_state()
    assert st["cycles_dropped"] > 0
    assert SH._knob_on_cooldown(st, "fast_term_cap", "up") is False


def test_hive_cap_trial_starts_at_frontier_value(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _prime_signal()
    monkeypatch.setattr(SH, "predicted_new_targets",
                        lambda k, v, **kw: ["oc_A165064_0"] if float(v) > 10700 else [])
    monkeypatch.setattr(SH, "cap_frontier_values", lambda k, **kw: [10700] if k == "fast_term_cap" else [])
    import colony.self_heal_score as SC
    monkeypatch.setattr(SC, "snapshot_pre_trial_depths", lambda ids, **k: {t: 10699 for t in ids})
    w = SL.Proposal(role="surveyor", label="depth_at_physical_cap",
                    action={"op": "set_knob", "name": "fast_term_cap", "direction": "up", "value": 13400},
                    fingerprint="set_knob:direction=up:name=fast_term_cap:value=13400", symptom="cap", ok=True)
    out = SL.start_knob_trial(w, cycle_id="t0", state=SL._empty_state())
    assert out["ok"] is True, out
    live = SH.load_state()["trial"]
    assert live["from"] == 8000 and live["to"] == 13400
    assert live["predicted_targets"] == ["oc_A165064_0"]
    assert live["pre_trial_depths"] == {"oc_A165064_0": 10699}
