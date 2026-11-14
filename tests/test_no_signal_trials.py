"""Item 58: a zero-vs-zero trial is inconclusive, not a revert.

The knob still returns to its prior value. Inconclusive does not count
as a revert, and no trial opens on a baseline window with no signal.
The 6-cycle window and the strictly-better rule are unchanged.
"""
from __future__ import annotations

import colony.self_heal as SH
import colony.stall as S


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(SH, "STATE_PATH", tmp_path / "self_heal.json")
    monkeypatch.setattr(SH, "EVENT_LOG", tmp_path / "self_heal.jsonl")
    monkeypatch.setattr(S, "STATE_PATH", tmp_path / "stall_state.json")
    # Score from the recorded fields; no live attempt log in unit tests.
    monkeypatch.setattr(SH, "rescore_metric_row", lambda r, **k: dict(r))


def _metric(cycle_id, targets=0, depth=0, delta=0, passes=528):
    return {
        "cycle_id": cycle_id,
        "new_oracle_targets": targets,
        "new_depth": depth,
        "oracle_passes": passes,
        "oracle_pass_delta": delta,
        "score": SH.score_metrics(targets, depth, delta),
    }


def _prime(n=6, signal=False):
    st = SH.load_state()
    fp = SH.environment_fingerprint(state=st)["digest"]
    rows = []
    for i in range(n):
        d = (1 if i % 2 == 0 else -1) if signal else 0
        r = _metric(f"b{i}", delta=d)
        r["env_fingerprint"] = fp
        rows.append(r)
    st["metrics"] = rows
    st["cycle_index"] = n - 1
    st["cycles"] = [f"b{i}" for i in range(n)]
    SH.save_state(st)
    return SH.load_state()


def _trial(st, knob="park_cycles", frm=6, to=8, started="b5"):
    return {
        "knob": knob, "from": frm, "to": to, "direction": "up",
        "reason": "dead_end_streak", "window": 6,
        "baseline_score": SH.window_score(st["metrics"][-6:]),
        "baseline_metrics": st["metrics"][-6:], "trial_metrics": [],
        "started_cycle": started, "started_index": int(st.get("cycle_index") or 0),
    }


FINDINGS = [{"kind": "dead_end_streak", "evidence": {"cycles": ["a", "b", "c"]}}]


def test_window_signal_helpers():
    assert SH.window_has_signal([]) is False
    assert SH.window_has_signal([_metric("x")] * 6) is False
    assert SH.window_has_signal([_metric("x"), _metric("y", delta=-1)]) is True
    assert SH.window_has_signal([_metric("x", depth=1)]) is True


def test_window_and_rule_invariants_unchanged():
    assert SH.KNOB_SPECS["evaluation_window"].default == 6
    assert SH.KNOB_RETRY_COOLDOWN == 6


def test_zero_vs_zero_closes_inconclusive_and_restores(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st = _prime(signal=False)
    SH.start_trial(_trial(st), state=st, cycle_id="b5")
    assert SH.current_knob("park_cycles") == 8
    out = SH.run_cycle("t1", metrics=_metric("t1"))
    assert out["trial"] is None
    st = SH.load_state()
    assert SH.current_knob("park_cycles") == 6  # safe default: prior value
    assert st["reverted_count"] == 0
    assert st["inconclusive_count"] == 1
    ev = st["evidence"][-1]
    assert ev["event"] == "trial_inconclusive"
    assert ev["reason"] == "no_signal_baseline"
    assert ev["helped"] is None and ev["adopted"] is False and ev["reverted"] is False
    assert ev["to"] == 6 and ev["from"] == 8
    assert ev["n_trial_metrics"] == 1
    assert ev["trial_evidence_id"]
    assert not [e for e in st["evidence"] if e["event"] == "revert"]
    assert out["self_changes_inconclusive"] == 1
    assert out["self_changes_reverted"] == 0


def test_zero_baseline_trial_kept_open_when_trial_row_has_signal(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st = _prime(signal=False)
    SH.start_trial(_trial(st), state=st, cycle_id="b5")
    out = SH.run_cycle("t1", metrics=_metric("t1", targets=1))
    assert out["trial"] is not None  # informative so far; window continues
    for i in range(2, 7):
        out = SH.run_cycle(f"t{i}", metrics=_metric(f"t{i}"))
    st = SH.load_state()
    assert st["evidence"][-1]["event"] == "adopt"  # 1 > 0, strictly better
    assert SH.current_knob("park_cycles") == 8


def test_signal_baseline_flat_trial_still_reverts(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st = _prime(signal=True)  # window score 0, but rows carry signal
    SH.start_trial(_trial(st), state=st, cycle_id="b5")
    for i in range(6):
        out = SH.run_cycle(f"t{i}", metrics=_metric(f"t{i}"))
    st = SH.load_state()
    assert st["evidence"][-1]["event"] == "revert"
    assert st["reverted_count"] == 1
    assert st.get("inconclusive_count", 0) == 0
    assert SH.current_knob("park_cycles") == 6
    assert out["trial"] is None


def test_equal_score_is_not_adopt(tmp_path, monkeypatch):
    """Strictly better is unchanged: a tie with signal reverts."""
    _isolate(tmp_path, monkeypatch)
    st = _prime(signal=True)
    SH.start_trial(_trial(st), state=st, cycle_id="b5")
    for i in range(6):
        d = 1 if i % 2 == 0 else -1
        SH.run_cycle(f"t{i}", metrics=_metric(f"t{i}", delta=d))
    st = SH.load_state()
    assert st["evidence"][-1]["event"] == "revert"
    assert st["adopted_count"] == 0


def test_full_window_zero_vs_zero_via_maybe_close(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st = _prime(signal=False)
    SH.start_trial(_trial(st), state=st, cycle_id="b5")
    st = SH.load_state()
    st["trial"]["trial_metrics"] = [_metric(f"t{i}") for i in range(6)]
    st = SH.maybe_close_trial(st, "t6")
    ev = st["evidence"][-1]
    assert ev["event"] == "trial_inconclusive"
    assert ev["reason"] == "no_signal"
    assert st["reverted_count"] == 0


def test_no_signal_baseline_guard_records_skip_once(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _prime(signal=False)
    for i in range(3):
        out = SH.run_cycle(f"c{i}", metrics=_metric(f"c{i}"), findings=FINDINGS)
        assert out["trial_started"] is False
        assert out["trial"] is None
    st = SH.load_state()
    skip = st["trial_skip"]
    assert skip["reason"] == "no_signal_baseline"
    assert skip["first_cycle"] == "c0" and skip["last_cycle"] == "c2"
    assert skip["count"] == 3
    assert skip["findings"] == ["dead_end_streak"]
    skipped = [e for e in st["evidence"] if e["event"] == "trial_skipped"]
    assert len(skipped) == 1  # one event per episode, not one per cycle
    assert skip["evidence_id"] == skipped[0]["id"]
    assert "trial skipped: no_signal_baseline" in SH.format_visibility(SH.visibility())


def test_guard_clears_when_signal_returns(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _prime(signal=False)
    SH.run_cycle("c0", metrics=_metric("c0"), findings=FINDINGS)
    assert SH.load_state()["trial_skip"]["reason"] == "no_signal_baseline"
    out = SH.run_cycle("c1", metrics=_metric("c1", delta=1), findings=FINDINGS)
    assert out["trial_started"] is True
    assert SH.load_state()["trial_skip"] is None


def test_no_findings_no_skip_record(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _prime(signal=False)
    SH.run_cycle("c0", metrics=_metric("c0"), findings=[])
    st = SH.load_state()
    assert st.get("trial_skip") is None
    assert not [e for e in st["evidence"] if e["event"] == "trial_skipped"]


def _replay_stale_open(tmp_path, monkeypatch):
    """Rebuild run 43523388103: 6→8 reverts, and in the SAME cycle a
    proposal stepped from the stale on-disk 8 opens "8→10"."""
    _isolate(tmp_path, monkeypatch)
    st = _prime(signal=False)
    SH.start_trial(_trial(st, frm=6, to=8, started="b5"), state=st, cycle_id="b5")
    st = SH.load_state()
    st["trial"]["trial_metrics"] = [_metric(f"t{i}", delta=(1 if i % 2 == 0 else -1)) for i in range(6)]
    st["trial"]["trial_metrics"][-1]["oracle_pass_delta"] = -2
    st["trial"]["trial_metrics"][-1]["score"] = SH.score_metrics(0, 0, -2)
    st = SH.maybe_close_trial(st, "X")  # revert in memory: knob 6
    assert st["evidence"][-1]["event"] == "revert"
    assert st["knobs"]["park_cycles"] == 6
    stale = _trial(st, frm=8, to=10, started="X")  # what the old code did
    st = SH.start_trial(stale, state=st, cycle_id="X")
    assert SH.current_knob("park_cycles") == 10
    return st


def test_pre_trial_value_corrects_stale_from(tmp_path, monkeypatch):
    st = _replay_stale_open(tmp_path, monkeypatch)
    value, stale = SH.pre_trial_value(st, st["trial"])
    assert value == 6 and stale is True


def test_open_stale_trial_closes_inconclusive_to_true_prior(tmp_path, monkeypatch):
    """The live 8→10 trial: next cycle closes it inconclusive, back to 6,
    via the normal run_cycle path (no data hand-edits)."""
    _replay_stale_open(tmp_path, monkeypatch)
    out = SH.run_cycle("Y", metrics=_metric("Y"), findings=FINDINGS)
    st = SH.load_state()
    inc = [e for e in st["evidence"] if e["event"] == "trial_inconclusive"]
    assert len(inc) == 1
    assert inc[0]["from"] == 10 and inc[0]["to"] == 6
    assert inc[0]["stale_from_corrected"] is True
    assert inc[0]["recorded_from"] == 8
    assert SH.current_knob("park_cycles") == 6
    assert st["reverted_count"] == 1  # only the earlier real revert
    # Same cycle: the no-signal guard declines a new trial and says why.
    assert out["trial_started"] is False
    assert st["trial_skip"]["reason"] == "no_signal_baseline"


def test_same_cycle_propose_reads_in_memory_knob(tmp_path, monkeypatch):
    """A close and a proposal in one cycle step from the restored value
    in memory, not the stale on-disk trial value."""
    _isolate(tmp_path, monkeypatch)
    st = _prime(signal=True)  # in memory: park_cycles at its default 6
    assert SH.state_knob(st, "park_cycles") == 6
    disk = SH.load_state()
    disk["knobs"]["park_cycles"] = 8  # on disk: the stale open-trial value
    SH.save_state(disk)
    assert SH.current_knob("park_cycles") == 8
    assert SH.state_knob(st, "park_cycles") == 6
    findings = [{"kind": "dead_end_streak", "suggest": [("park_cycles", "up")], "evidence": {}}]
    prop = SH.propose_trial(findings, state=st, cycle_id="c")
    assert prop is not None
    assert prop["knob"] == "park_cycles"
    assert prop["from"] == 6
    assert prop["to"] == SH.stepped_value("park_cycles", "up", current=6)


def test_revert_restarts_retry_cooldown(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st = _prime(signal=True)
    t = _trial(st)
    st = SH.start_trial(t, state=st, cycle_id="b5")
    st["cycle_index"] = 11
    st["trial"]["trial_metrics"] = [_metric(f"t{i}") for i in range(6)]
    st = SH.maybe_close_trial(st, "t6")
    assert st["evidence"][-1]["event"] == "revert"
    assert st["knob_last_trial"]["park_cycles"]["closed_index"] == 11
    # Six cycles after the START but zero after the close: still cooling.
    assert SH._knob_on_cooldown(st, "park_cycles", "up") is True
    st["cycle_index"] = 11 + SH.KNOB_RETRY_COOLDOWN
    assert SH._knob_on_cooldown(st, "park_cycles", "up") is False


def test_inconclusive_restarts_retry_cooldown(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st = _prime(signal=False)
    st = SH.start_trial(_trial(st), state=st, cycle_id="b5")
    st["cycle_index"] = 9
    st = SH.reconcile_no_signal_trial(st, cycle_id="t")
    assert st["evidence"][-1]["event"] == "trial_inconclusive"
    assert st["knob_last_trial"]["park_cycles"]["closed_index"] == 9


def test_control_arm_frozen(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st = _prime(signal=False)
    SH.start_trial(_trial(st), state=st, cycle_id="b5")
    import colony.arm as arm
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: False)
    st = SH.load_state()
    before = (dict(st["knobs"]), len(st["evidence"]), dict(st["trial"]))
    st2 = SH.reconcile_no_signal_trial(st, cycle_id="t1")
    assert st2["trial"] == before[2]
    out = SH.run_cycle("t1", metrics=_metric("t1"), findings=FINDINGS)
    st = SH.load_state()
    assert st["trial"]["knob"] == "park_cycles"
    assert st["knobs"] == before[0]
    assert len(st["evidence"]) == before[1]
    assert st.get("inconclusive_count", 0) == 0
    assert st.get("trial_skip") is None
    assert out["trial_started"] is False
