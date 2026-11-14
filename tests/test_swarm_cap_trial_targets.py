"""Item 66: Hive/swarm cap-knob trials carry predicted targets.

A swarm/Hive apply that starts a cap-knob trial runs the same read-only
predictor self-heal uses (item 63 cap_reason -> knob binding), attaches
predicted_targets, and start_trial snapshots pre_trial_depths before the
first trial cycle, so item 64 depth-gain scoring applies. When no target
binds to the knob, the trial does not open (honest skip reason).
Tighten-only: no gate, window or Oracle change.
"""
from __future__ import annotations

import colony.hive_adapter  # noqa: F401  binds Hive to live self-heal
import colony.self_heal as SH
import colony.stall as S
import hive.host as host
import hive.library as FL
import hive.swarm as SL


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(SH, "STATE_PATH", tmp_path / "self_heal.json")
    monkeypatch.setattr(SH, "EVENT_LOG", tmp_path / "self_heal.jsonl")
    monkeypatch.setattr(S, "STATE_PATH", tmp_path / "stall_state.json")
    monkeypatch.setattr(FL, "LIBRARY_LOG", tmp_path / "fix_library.jsonl")
    monkeypatch.setattr(FL, "LIBRARY_SNAPSHOT", tmp_path / "swarm_library.json")
    monkeypatch.setattr(SL, "STATE_PATH", tmp_path / "swarm_learn.json")
    monkeypatch.setattr(SL, "EVENT_LOG", tmp_path / "swarm_learn.jsonl")
    monkeypatch.setattr(SL, "RULES_PATH", tmp_path / "swarm_rules.json")


def _prime_signal(n=6):
    st = SH.load_state()
    fp = SH.environment_fingerprint(state=st)["digest"]
    rows = []
    for i in range(n):
        d = 1 if i % 2 == 0 else -1
        rows.append({
            "cycle_id": f"b{i}", "new_oracle_targets": 0, "new_depth": 0,
            "oracle_passes": 528, "oracle_pass_delta": d,
            "score": SH.score_metrics(0, 0, d), "env_fingerprint": fp,
        })
    st["metrics"] = rows
    st["cycle_index"] = n - 1
    st["cycles"] = [f"b{i}" for i in range(n)]
    SH.save_state(st)


def _cap_winner(knob="fast_term_cap"):
    action = {"op": "set_knob", "name": knob, "direction": "up"}
    return SL.Proposal(role="surveyor", label="depth_at_physical_cap", action=action,
                       fingerprint=f"set_knob:direction=up:name={knob}", symptom="cap", ok=True)


def test_host_reports_cap_knobs():
    assert host.heal_is_cap_knob("fast_term_cap") is True
    assert host.heal_is_cap_knob("gf_term_cap") is True
    assert host.heal_is_cap_knob("park_cycles") is False


def test_standalone_host_has_no_cap_knobs(monkeypatch):
    monkeypatch.setattr(host, "_heal", None)
    assert host.heal_is_cap_knob("fast_term_cap") is False


def test_swarm_cap_trial_attaches_predicted_targets_and_pre_depths(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _prime_signal()
    calls = []

    def _pred(knob, value, **k):
        calls.append((knob, value))
        return ["oc_A165064_0"]

    monkeypatch.setattr(SH, "predicted_new_targets", _pred)
    import colony.self_heal_score as SC
    monkeypatch.setattr(SC, "snapshot_pre_trial_depths", lambda ids, **k: {t: 7999 for t in ids})
    out = SL.start_knob_trial(_cap_winner(), cycle_id="t0", state=SL._empty_state())
    assert out["ok"] is True, out
    assert calls and calls[0][0] == "fast_term_cap"
    live = SH.load_state()["trial"]
    assert live["source"] == "swarm"
    assert live["predicted_targets"] == ["oc_A165064_0"]
    assert live["pre_trial_depths"] == {"oc_A165064_0": 7999}
    assert not live.get("exploratory")  # baseline had signal
    assert live["authorized"] is False
    start = [e for e in SH.load_state()["evidence"] if e.get("event") == "trial_start"][-1]
    assert start["predicted_targets"] == ["oc_A165064_0"]
    assert start["pre_trial_depths"] == {"oc_A165064_0": 7999}


def test_swarm_cap_trial_skips_when_no_target_binds(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _prime_signal()
    monkeypatch.setattr(SH, "predicted_new_targets", lambda knob, value, **k: [])
    before = SH.current_knob("fast_term_cap")
    out = SL.start_knob_trial(_cap_winner(), cycle_id="t0", state=SL._empty_state())
    assert out["ok"] is False
    assert out["reason"] == "no_bound_predicted_target"
    assert out["detail"]["knob"] == "fast_term_cap"
    assert SH.load_state().get("trial") is None
    assert SH.current_knob("fast_term_cap") == before


def test_swarm_cap_skip_respects_cap_reason_binding(tmp_path, monkeypatch):
    """Item 63 binding: a target newly eligible but held by a digit/time
    cap does not count for a term-cap knob, so the trial does not open."""
    _isolate(tmp_path, monkeypatch)
    _prime_signal()
    pools = iter([set(), {"oc_DIGITS_0"}])
    monkeypatch.setattr(SH, "eligible_target_ids", lambda *a, **k: next(pools))
    monkeypatch.setattr(SH, "_predicted_target_fits_knob", lambda tid, knob, **k: False)
    out = SL.start_knob_trial(_cap_winner(), cycle_id="t0", state=SL._empty_state())
    assert out["reason"] == "no_bound_predicted_target"
    assert SH.load_state().get("trial") is None


def test_swarm_non_cap_knob_does_not_need_predictor(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _prime_signal()

    def _boom(*a, **k):
        raise AssertionError("predictor must not run for a non-cap knob with signal")

    monkeypatch.setattr(SH, "predicted_new_targets", _boom)
    p = SL.Proposal(role="improver", label="no_progress_perturb",
                    action={"op": "set_knob", "name": "perturb_cooldown_cycles", "direction": "up"},
                    fingerprint="set_knob:direction=up:name=perturb_cooldown_cycles",
                    symptom="no progress perturb", ok=True)
    out = SL.start_knob_trial(p, cycle_id="t0", state=SL._empty_state())
    assert out["ok"] is True, out
    assert not SH.load_state()["trial"].get("predicted_targets")


def test_run_cycle_records_honest_skip_reason(tmp_path, monkeypatch):
    """The skip is logged as apply_deferred with the reason and detail,
    and does not create a pending_apply (it is not a confound wait)."""
    _isolate(tmp_path, monkeypatch)
    _prime_signal()
    w = _cap_winner()
    vr = SL.VoteResult(w, False, "accepted", {w.fingerprint: 4}, 901, 189, 4, 0, 1, 4, None)
    monkeypatch.setattr(SL, "observe", lambda cycle_id="": [{"kind": "depth_at_physical_cap", "evidence": {}}])
    monkeypatch.setattr(SL, "swarm_propose", lambda *a, **k: [w])
    monkeypatch.setattr(SL, "vote", lambda *a, **k: vr)
    monkeypatch.setattr(SL, "_window_is_confounded", lambda: False)
    monkeypatch.setattr(SL, "harvest_self_heal_outcomes", lambda *a, **k: [])
    monkeypatch.setattr("hive.library.mine_all", lambda **k: [])
    monkeypatch.setattr(SH, "predicted_new_targets", lambda knob, value, **k: [])
    SL.run_cycle("c6")
    st = SL.load_state()
    deferred = [e for e in st["evidence"] if e.get("event") == "apply_deferred"]
    assert deferred and deferred[-1]["reason"] == "no_bound_predicted_target"
    assert deferred[-1]["detail"]["knob"] == "fast_term_cap"
    assert not st.get("pending_apply")
    assert not [e for e in st["evidence"] if e.get("event") == "trial_start"]
    assert SH.load_state().get("trial") is None
