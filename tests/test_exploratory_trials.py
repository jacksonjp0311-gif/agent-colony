"""Idle-colony unstick: empty-pool detection after a dry session, and
exploratory cap trials that are credited only for the targets they
make eligible. Gates are unchanged: 6-cycle window, strictly better,
zero-vs-zero inconclusive, control arm frozen.
"""
from __future__ import annotations

import colony.oeis_conjectures as O
import colony.self_heal as SH
import colony.stall as S


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(SH, "STATE_PATH", tmp_path / "self_heal.json")
    monkeypatch.setattr(SH, "EVENT_LOG", tmp_path / "self_heal.jsonl")
    monkeypatch.setattr(S, "STATE_PATH", tmp_path / "stall_state.json")
    monkeypatch.setattr(SH, "rescore_metric_row", lambda r, **k: dict(r))
    monkeypatch.setattr(SH, "baseline_environment_confounded", lambda *a, **k: False)


def _metric(cid, targets=0, depth=0, delta=0):
    return {"cycle_id": cid, "new_oracle_targets": targets, "new_depth": depth,
            "oracle_passes": 528, "oracle_pass_delta": delta,
            "score": SH.score_metrics(targets, depth, delta)}


def _prime_zero(n=6):
    st = SH.load_state()
    st["metrics"] = [_metric(f"b{i}") for i in range(n)]
    st["cycle_index"] = n - 1
    st["cycles"] = [f"b{i}" for i in range(n)]
    SH.save_state(st)
    return SH.load_state()


def _fake_eligibility(monkeypatch, opens=None):
    """Eligible ids depend on the (read-only) cap override, like the real pool."""
    opens = opens or {"fast_term_cap": "oc_FAST", "gf_term_cap": "oc_GF"}
    keys = {"fast_term_cap": "fast_term_cap", "gf_term_cap": "gf_terms"}

    def ids(stall_state=None):
        out = set()
        for knob, tid in opens.items():
            if keys[knob] in O._CAP_OVERRIDES:
                out.add(tid)
        return out
    monkeypatch.setattr(SH, "eligible_target_ids", ids)


CAP_FINDINGS = [
    {"kind": "dead_end_streak", "evidence": {}},
    {"kind": "depth_at_physical_cap", "evidence": {}, "suggest": [("fast_term_cap", "up")]},
]


# --- empty pool after a dry session -------------------------------------

def _dry_exit_stall(blocked=True):
    st = {
        "pass_history": [{"cycle_id": "e", "pass_total": 528}, {"cycle_id": "now", "pass_total": 528}],
        "perturb": {
            "active": False, "exit_reason": "no_candidates", "exit_cycle": "old",
            "session_progress": True, "session_targets": ["oc_A1_0", "oc_A2_0"],
            "no_candidates_pass_total": 528 if blocked else None,
        },
        "turns": [], "targets_tried": [],
    }
    return st


def test_dry_session_is_empty_pool_while_reentry_blocked(monkeypatch):
    monkeypatch.setattr(S, "has_eligible_progress_target", lambda state=None: False)
    assert SH._is_empty_perturb_pool(_dry_exit_stall(), "now") is True


def test_dry_session_not_empty_once_target_eligible(monkeypatch):
    monkeypatch.setattr(S, "has_eligible_progress_target", lambda state=None: True)
    assert SH._is_empty_perturb_pool(_dry_exit_stall(), "now") is False


def test_dry_session_not_empty_once_passes_move(monkeypatch):
    monkeypatch.setattr(S, "has_eligible_progress_target", lambda state=None: False)
    st = _dry_exit_stall()
    st["pass_history"][-1]["pass_total"] = 529
    assert SH._is_empty_perturb_pool(st, "now") is False


def test_supply_finding_reaches_supply(monkeypatch):
    called = {}
    monkeypatch.setattr("colony.authoring.authored_count", lambda: 101)
    monkeypatch.setattr("colony.target_generator.author_targets",
                        lambda **k: called.setdefault("k", k) and ["authored_mut_x"])
    out = SH.maybe_supply_oracle_targets("c", findings=[{"kind": "empty_perturb_pool"}])
    assert out["invited"] is True and called["k"]["max_new"] == 1


def test_supply_respects_150_cap(monkeypatch):
    from colony.authoring import MAX_AUTHORED_TOTAL
    assert MAX_AUTHORED_TOTAL == 150
    monkeypatch.setattr("colony.authoring.authored_count", lambda: 150)
    out = SH.maybe_supply_oracle_targets("c", findings=[{"kind": "empty_perturb_pool"}])
    assert out["invited"] is False and out["reason"] == "at_authored_cap"


# --- read-only counterfactual -------------------------------------------

def test_cap_override_is_transient():
    base = O.evaluator_caps()["fast_term_cap"]
    with O.cap_override("fast_term_cap", base + 1234):
        assert O.evaluator_caps()["fast_term_cap"] == base + 1234
    assert O.evaluator_caps()["fast_term_cap"] == base
    assert O._CAP_OVERRIDES == {}
    with O.cap_override("park_cycles", 99):  # not a cap: no effect
        assert O._CAP_OVERRIDES == {}


def test_predicted_new_targets_only_for_caps(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _fake_eligibility(monkeypatch)
    assert SH.predicted_new_targets("fast_term_cap", 10700) == ["oc_FAST"]
    assert SH.predicted_new_targets("park_cycles", 8) == []
    assert SH.predicted_new_targets("perturb_epsilon", 0.4) == []
    assert O._CAP_OVERRIDES == {}


def test_predictor_writes_nothing(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _prime_zero()
    before = (tmp_path / "self_heal.json").read_text()
    SH.predicted_new_targets("fast_term_cap", 10700)
    assert (tmp_path / "self_heal.json").read_text() == before


# --- proposing on a no-signal baseline ----------------------------------

def test_no_signal_baseline_opens_only_predicted_cap_trial(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _fake_eligibility(monkeypatch)
    st = _prime_zero()
    prop = SH.propose_trial(CAP_FINDINGS, state=st, cycle_id="c")
    assert prop["knob"] == "fast_term_cap"  # park_cycles had no predicted effect
    assert prop["exploratory"] is True and prop["baseline_signal"] is False
    assert prop["predicted_targets"] == ["oc_FAST"]
    assert prop["baseline_score"] == 0.0
    assert prop["window"] == 6


def test_no_signal_without_prediction_still_skips(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(SH, "eligible_target_ids", lambda stall_state=None: set())
    st = _prime_zero()
    assert SH.propose_trial(CAP_FINDINGS, state=st, cycle_id="c") is None
    skip = st["trial_skip"]
    assert skip["reason"] == "no_signal_baseline"
    checked = {c["knob"] for c in skip["explore_checked"]}
    assert "fast_term_cap" in checked and "park_cycles" in checked


def test_signal_baseline_unchanged_not_exploratory(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(SH, "eligible_target_ids", lambda stall_state=None: set())
    st = _prime_zero()
    st["metrics"][0] = _metric("b0", delta=1)
    st["metrics"][1] = _metric("b1", delta=-1)
    prop = SH.propose_trial(CAP_FINDINGS, state=st, cycle_id="c")
    assert prop["knob"] == "park_cycles"
    assert "exploratory" not in prop


def test_failed_exploration_not_repeated(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _fake_eligibility(monkeypatch)
    st = _prime_zero()
    st["evidence"] = [{"event": "trial_inconclusive", "knob": "fast_term_cap", "from": 10700,
                       "to": 8000, "exploratory": True, "predicted_targets": ["oc_FAST"]}]
    prop = SH.propose_trial(CAP_FINDINGS + [{"kind": "x", "suggest": [("gf_term_cap", "up")]}],
                            state=st, cycle_id="c")
    assert prop["knob"] == "gf_term_cap"


# --- closing with attribution -------------------------------------------

def _open_exploratory(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _fake_eligibility(monkeypatch)
    st = _prime_zero()
    prop = SH.propose_trial(CAP_FINDINGS, state=st, cycle_id="b5")
    st = SH.start_trial(prop, state=st, cycle_id="b5")
    assert SH.current_knob("fast_term_cap") == 10700
    ev = [e for e in st["evidence"] if e["event"] == "trial_start"][-1]
    assert ev["exploratory"] is True and ev["predicted_targets"] == ["oc_FAST"]
    return st


def test_exploratory_not_closed_early_by_reconcile(tmp_path, monkeypatch):
    _open_exploratory(tmp_path, monkeypatch)
    out = SH.run_cycle("t0", metrics=_metric("t0"))
    assert out["trial"] is not None and out["trial"]["knob"] == "fast_term_cap"


def _finish(monkeypatch, rows, attributed):
    monkeypatch.setattr(SH, "attributable_progress", lambda trial, **k: list(attributed))
    st = SH.load_state()
    st["trial"]["trial_metrics"] = rows
    return SH.maybe_close_trial(st, "t6")


def test_exploratory_adopts_on_attributed_strict_gain(tmp_path, monkeypatch):
    _open_exploratory(tmp_path, monkeypatch)
    rows = [_metric("t0", depth=1)] + [_metric(f"t{i}") for i in range(1, 6)]
    st = _finish(monkeypatch, rows, ["oc_FAST"])
    ev = st["evidence"][-1]
    assert ev["event"] == "adopt" and ev["exploratory"] is True
    assert ev["attributed_targets"] == ["oc_FAST"]
    assert st["knobs"]["fast_term_cap"] == 10700


def test_exploratory_gain_elsewhere_is_inconclusive(tmp_path, monkeypatch):
    _open_exploratory(tmp_path, monkeypatch)
    rows = [_metric("t0", targets=1)] + [_metric(f"t{i}") for i in range(1, 6)]
    st = _finish(monkeypatch, rows, [])
    ev = st["evidence"][-1]
    assert ev["event"] == "trial_inconclusive" and ev["reason"] == "signal_not_attributable"
    assert st["knobs"]["fast_term_cap"] == 8000
    assert st["reverted_count"] == 0


def test_exploratory_zero_is_inconclusive(tmp_path, monkeypatch):
    _open_exploratory(tmp_path, monkeypatch)
    st = _finish(monkeypatch, [_metric(f"t{i}") for i in range(6)], [])
    assert st["evidence"][-1]["event"] == "trial_inconclusive"
    assert st["evidence"][-1]["reason"] == "no_signal"


def test_exploratory_pass_drop_reverts(tmp_path, monkeypatch):
    _open_exploratory(tmp_path, monkeypatch)
    rows = [_metric("t0", delta=-1)] + [_metric(f"t{i}") for i in range(1, 6)]
    st = _finish(monkeypatch, rows, [])
    assert st["evidence"][-1]["event"] == "revert"
    assert st["knobs"]["fast_term_cap"] == 8000


def test_attributable_progress_counts_only_predicted():
    trial = {"predicted_targets": ["oc_FAST"], "trial_metrics": [{"cycle_id": "t1"}, {"cycle_id": "t2"}]}
    log = {"attempts": []}
    import colony.self_heal as M
    orig = M.targets_with_new_depth
    try:
        M.targets_with_new_depth = lambda lg, cid: {"t1": ["oc_OTHER"], "t2": ["oc_FAST"]}.get(cid, [])
        got = SH.attributable_progress(trial, attempt_log=log, stall_state={"turns": []})
    finally:
        M.targets_with_new_depth = orig
    assert got == ["oc_FAST"]
    assert SH.attributable_progress({"trial_metrics": []}, attempt_log=log, stall_state={}) == []


def test_control_arm_never_proposes(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _fake_eligibility(monkeypatch)
    import colony.arm as arm
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: False)
    st = _prime_zero()
    assert SH.propose_trial(CAP_FINDINGS, state=st, cycle_id="c") is None


# --- round 2: supply during trials, predicted-effect candidates first ----

def _signal_state():
    st = _prime_zero()
    st["metrics"][0] = _metric("b0", targets=1)
    SH.save_state(st)
    return SH.load_state()


def test_signal_baseline_prefers_predicted_effect_candidate(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _fake_eligibility(monkeypatch)
    st = _signal_state()
    prop = SH.propose_trial(CAP_FINDINGS, state=st, cycle_id="c")
    assert prop["knob"] == "fast_term_cap"  # ahead of park_cycles (no mechanism)
    assert prop["baseline_score"] == 1.0
    assert prop["predicted_targets"] == ["oc_FAST"]
    assert "exploratory" not in prop  # standard strictly-better close


def test_signal_trial_close_is_plain_strictly_better(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _fake_eligibility(monkeypatch)
    st = _signal_state()
    st = SH.start_trial(SH.propose_trial(CAP_FINDINGS, state=st, cycle_id="b5"), state=st, cycle_id="b5")
    st["trial"]["trial_metrics"] = [_metric("t0", targets=1)] + [_metric(f"t{i}") for i in range(1, 6)]
    st = SH.maybe_close_trial(st, "t6")
    assert st["evidence"][-1]["event"] == "revert"  # 1.0 is not > 1.0


def test_supply_runs_while_a_trial_is_open(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _fake_eligibility(monkeypatch)
    st = _signal_state()
    SH.start_trial(SH.propose_trial(CAP_FINDINGS, state=st, cycle_id="b5"), state=st, cycle_id="b5")
    calls = []
    monkeypatch.setattr(SH, "maybe_supply_oracle_targets",
                        lambda cycle_id="", findings=None: calls.append(cycle_id) or {"invited": True, "authored": ["x"]})
    out = SH.run_cycle("t0", metrics=_metric("t0"), findings=[{"kind": "empty_perturb_pool"}])
    assert out["trial"] is not None
    assert calls == ["t0"]
    assert out["supply"]["invited"] is True
    assert out["trial_started"] is False


def test_control_arm_supply_still_disabled(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    import colony.arm as arm
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: False)
    monkeypatch.setattr(arm, "is_control", lambda: True, raising=False)
    authored = []
    monkeypatch.setattr("colony.target_generator.author_targets",
                        lambda **k: authored.append(k) or [])
    _prime_zero()
    out = SH.run_cycle("c0", metrics=_metric("c0"), findings=[{"kind": "empty_perturb_pool"}])
    assert out["trial_started"] is False
    assert SH.load_state().get("trial") is None
