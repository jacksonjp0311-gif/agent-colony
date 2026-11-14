"""Hive and self-heal baseline confound: exclude the just-closed trial knob.

A self-heal trial of perturb_cooldown_cycles 6→8 must not starve a
later Hive or self-heal trial of a 6-cycle baseline when the only
fingerprint difference is that trial knob. A real code or other-knob
change still defers. The Wilson gate, Oracle, P ≥ 0.70, and 150 cap
are untouched.
"""
from __future__ import annotations

import copy

import colony.self_heal as SH
import colony.stall as S
import hive.swarm as SL
import hive.library as FL
from hive.swarm import Proposal


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(SH, "STATE_PATH", tmp_path / "self_heal.json")
    monkeypatch.setattr(SH, "EVENT_LOG", tmp_path / "self_heal.jsonl")
    monkeypatch.setattr(S, "STATE_PATH", tmp_path / "stall_state.json")
    monkeypatch.setattr(FL, "LIBRARY_LOG", tmp_path / "fix_library.jsonl")
    monkeypatch.setattr(FL, "LIBRARY_SNAPSHOT", tmp_path / "swarm_library.json")
    monkeypatch.setattr(SL, "STATE_PATH", tmp_path / "swarm_learn.json")
    monkeypatch.setattr(SL, "EVENT_LOG", tmp_path / "swarm_learn.jsonl")
    monkeypatch.setattr(SL, "RULES_PATH", tmp_path / "swarm_rules.json")


def _metric(cycle_id, fp, env=None, score=0.0):
    row = {
        "cycle_id": cycle_id,
        "new_oracle_targets": 0,
        "new_depth": 0,
        "oracle_passes": 528,
        "oracle_pass_delta": 0,
        "score": score,
        "env_fingerprint": fp,
    }
    if env is not None:
        row["environment"] = copy.deepcopy(env)
    return row


def _with_signal(rows):
    """Item 58: a baseline must carry signal. Alternate oracle_pass_delta
    +1/-1 in pairs so every paired row moves but the window score stays 0."""
    n = len(rows) - (len(rows) % 2)
    for i, r in enumerate(rows):
        d = (1 if i % 2 == 0 else -1) if i < n else 0
        r["oracle_pass_delta"] = d
        r["score"] = SH.score_metrics(int(r.get("new_oracle_targets") or 0),
                                      int(r.get("new_depth") or 0), d) if d else r.get("score", 0.0)
    return rows


def _two_knob_fingerprints():
    """Digests for the same code with perturb_cooldown_cycles at 6 and at 8."""
    st = SH.load_state()
    knobs = dict(SH.default_knobs())
    knobs["perturb_cooldown_cycles"] = 6
    st["knobs"] = knobs
    SH.save_state(st)
    env6 = SH.environment_fingerprint(state=st)
    knobs8 = dict(knobs)
    knobs8["perturb_cooldown_cycles"] = 8
    st8 = dict(st)
    st8["knobs"] = knobs8
    env8 = SH.environment_fingerprint(state=st8)
    assert env6["digest"] != env8["digest"]
    # Excluding the trial knob, both match.
    ex6 = SH.environment_fingerprint(exclude_knob="perturb_cooldown_cycles", state=st)
    ex8 = SH.environment_fingerprint(exclude_knob="perturb_cooldown_cycles", state=st8)
    assert ex6["digest"] == ex8["digest"]
    return st, env6, env8


def test_just_closed_trial_knob_is_not_a_confound(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st, env6, env8 = _two_knob_fingerprints()
    # Live knobs are back at 6 (reverted). Window is the 6 trial cycles at 8.
    st["knobs"]["perturb_cooldown_cycles"] = 6
    st["last_self_change"] = {
        "event": "revert",
        "knob": "perturb_cooldown_cycles",
        "from": 8,
        "to": 6,
        "direction": "up",
    }
    st["trial"] = None
    rows = _with_signal([_metric(f"t{i}", env8["digest"], env8) for i in range(6)])
    st["metrics"] = rows
    SH.save_state(st)
    assert SH.baseline_environment_confounded(rows, state=st) is False


def test_digest_only_legacy_rows_also_exclude_the_trial_knob(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st, env6, env8 = _two_knob_fingerprints()
    st["knobs"]["perturb_cooldown_cycles"] = 6
    st["last_self_change"] = {
        "event": "revert",
        "knob": "perturb_cooldown_cycles",
        "from": 8,
        "to": 6,
    }
    rows = [_metric(f"t{i}", env8["digest"]) for i in range(6)]  # no environment parts
    st["metrics"] = rows
    SH.save_state(st)
    assert SH.baseline_environment_confounded(rows, state=st) is False


def test_a_different_knob_change_is_still_a_confound(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st, env6, env8 = _two_knob_fingerprints()
    st["knobs"]["perturb_cooldown_cycles"] = 6
    st["knobs"]["fast_term_cap"] = int(st["knobs"]["fast_term_cap"]) + 1000
    st["last_self_change"] = {
        "event": "revert",
        "knob": "perturb_cooldown_cycles",
        "from": 8,
        "to": 6,
    }
    rows = _with_signal([_metric(f"t{i}", env8["digest"], env8) for i in range(6)])
    st["metrics"] = rows
    SH.save_state(st)
    assert SH.baseline_environment_confounded(rows, state=st) is True


def test_matching_full_digest_is_not_confounded(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st, env6, env8 = _two_knob_fingerprints()
    st["knobs"]["perturb_cooldown_cycles"] = 6
    st["last_self_change"] = None
    st["trial"] = None
    rows = [_metric(f"b{i}", env6["digest"], env6) for i in range(6)]
    assert SH.baseline_environment_confounded(rows, state=st) is False


def test_missing_row_fingerprint_is_a_confound(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st, env6, _env8 = _two_knob_fingerprints()
    rows = [_metric(f"b{i}", env6["digest"], env6) for i in range(5)]
    rows.append({"cycle_id": "bare", "score": 0.0})
    assert SH.baseline_environment_confounded(rows, state=st) is True


def test_start_rule_trial_opens_after_just_closed_knob_trial(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st, env6, env8 = _two_knob_fingerprints()
    st["knobs"]["perturb_cooldown_cycles"] = 6
    st["last_self_change"] = {
        "event": "revert",
        "knob": "perturb_cooldown_cycles",
        "from": 8,
        "to": 6,
    }
    st["trial"] = None
    rows = _with_signal([_metric(f"t{i}", env8["digest"], env8) for i in range(6)])
    st["metrics"] = rows
    st["cycle_index"] = 20
    SH.save_state(st)

    proposal = Proposal(
        role="improver",
        label="empty_perturb_pool",
        action={"op": "add_family_rotation", "family": "algebraic"},
        fingerprint="add_family_rotation:family=algebraic",
        symptom="empty perturb pool",
        ok=True,
    )
    swarm_st = SL._empty_state()
    out = SL.start_rule_trial(proposal, cycle_id="now", state=swarm_st)
    assert out["ok"] is True, out
    assert out["reason"] == "trial_started"
    assert swarm_st["trial"]["fingerprint"] == proposal.fingerprint


def test_start_knob_trial_opens_after_just_closed_cooldown_trial(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st, env6, env8 = _two_knob_fingerprints()
    st["knobs"]["perturb_cooldown_cycles"] = 6
    st["last_self_change"] = {
        "event": "revert",
        "knob": "perturb_cooldown_cycles",
        "from": 8,
        "to": 6,
        "direction": "up",
    }
    st["trial"] = None
    rows = _with_signal([_metric(f"t{i}", env8["digest"], env8) for i in range(6)])
    st["metrics"] = rows
    st["cycle_index"] = 20
    SH.save_state(st)

    proposal = Proposal(
        role="surveyor",
        label="empty_perturb_pool",
        action={"op": "set_knob", "name": "fast_term_cap", "direction": "up"},
        fingerprint="set_knob:direction=up:name=fast_term_cap",
        symptom="empty perturb pool cap",
        ok=True,
    )
    # Fingerprint will be filled by validate path; start_knob_trial uses the action.
    out = SL.start_knob_trial(proposal, cycle_id="now", state=SL._empty_state())
    assert out["ok"] is True, out
    assert out["reason"] == "trial_started"
    assert out["trial"]["knob"] == "fast_term_cap"
    assert out["trial"]["from"] != out["trial"]["to"]


def test_propose_trial_also_excludes_the_just_closed_knob(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st, env6, env8 = _two_knob_fingerprints()
    st["knobs"]["perturb_cooldown_cycles"] = 6
    st["last_self_change"] = {
        "event": "revert",
        "knob": "perturb_cooldown_cycles",
        "from": 8,
        "to": 6,
        "direction": "up",
    }
    st["trial"] = None
    rows = _with_signal([_metric(f"t{i}", env8["digest"], env8) for i in range(6)])
    st["metrics"] = rows
    st["cycle_index"] = 20
    # knob_last_trial for cooldown should not block a *cap* trial
    st["knob_last_trial"] = {
        "perturb_cooldown_cycles": {"direction": "up", "cycle_index": 20},
    }
    SH.save_state(st)
    findings = [{
        "kind": "empty_perturb_pool",
        "suggest": [("fast_term_cap", "up")],
        "evidence": {"cap_holds": [{"cap_reason": "term_cap"}]},
    }]
    proposal = SH.propose_trial(findings, state=st, cycle_id="now")
    assert proposal is not None, "just-closed cooldown trial must not block a cap trial"
    assert proposal["knob"] == "fast_term_cap"
