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


# --- round 3: credit post-apply OEIS depth in the trial-start cycle ------

def _attempt(cid, *, verified, prior, extended, tid="oc_A165064_0"):
    return {
        "id": tid, "anum": "A165064", "form": "gf", "depth": verified,
        "bfile_hi": 100, "beyond": True, "status": "holds_on_range",
        "cycle_id": cid, "planned": verified + 1, "verified_depth": verified,
        "prior_tested_hi": prior, "extended": extended,
        "cap_reason": "term_cap", "cap_value": verified + 1,
    }


def test_finalize_credits_start_cycle_depth_to_trial_not_baseline(tmp_path, monkeypatch):
    """Live bug: oeis_conjectures runs after start_trial in the same cycle,
    so the cap-enabled depth (A165064 7999→10699) never entered any metric
    row and could not help the trial. Surplus goes to the trial, not the
    already-recorded baseline row."""
    _isolate(tmp_path, monkeypatch)
    st = _signal_state()
    st = SH.start_trial({
        "knob": "fast_term_cap", "from": 8000, "to": 10700, "direction": "up",
        "reason": "depth_at_physical_cap", "window": 6, "baseline_score": 3.0,
        "baseline_metrics": st["metrics"][-6:], "trial_metrics": [],
        "started_cycle": "start", "predicted_targets": ["oc_A165064_0"],
        "applied_to_live_oracle": False, "authorized": False,
    }, state=st, cycle_id="start")
    # Metric row already recorded for the start cycle (pre-OEIS, new_depth 0),
    # and it is the last baseline cycle — same as the live run.
    start_row = _metric("start")
    st["metrics"] = st["metrics"] + [start_row]
    st["trial"]["baseline_metrics"] = st["metrics"][-6:]
    st["trial"]["baseline_score"] = 3.0
    SH.save_state(st)

    log = {"attempts": [
        {"id": "oc_A165064_0", "anum": "A165064", "verified_depth": 7999,
         "bfile_hi": 100, "cycle_id": "old", "extended": 6800, "planned": 8000,
         "status": "holds_on_range", "beyond": True},
        _attempt("start", verified=10699, prior=7999, extended=2700),
    ]}
    st = SH.finalize_cycle_metrics("start", state=SH.load_state(), attempt_log=log, stall_state={})
    apply = st["trial"]["apply_cycle_metrics"]
    assert apply["new_depth"] == 1
    assert apply["score"] == SH.score_metrics(0, 1, 0)
    assert apply["source"] == "apply_cycle_surplus"
    # Baseline row is unchanged: the work must not be credited there.
    recorded = [r for r in st["metrics"] if r["cycle_id"] == "start"][-1]
    assert recorded["new_depth"] == 0
    assert recorded["score"] == 0.0
    assert st["trial"]["baseline_score"] == 3.0


def test_apply_cycle_score_counts_toward_strictly_better_after_six_cycles(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st = _signal_state()
    # baseline 3.0 from three target-1 rows in the primed+signal state? _signal_state
    # only sets metrics[0] to targets=1, others 0, baseline_score would be 1 if proposed.
    st = SH.start_trial({
        "knob": "fast_term_cap", "from": 8000, "to": 10700, "direction": "up",
        "reason": "depth_at_physical_cap", "window": 6, "baseline_score": 3.0,
        "baseline_metrics": [_metric("b0", targets=1), _metric("b1"),
                             _metric("b2", targets=1), _metric("b3"),
                             _metric("b4", targets=1), _metric("b5")],
        "trial_metrics": [],
        "started_cycle": "start", "predicted_targets": ["oc_A165064_0"],
        "applied_to_live_oracle": False, "authorized": False,
    }, state=st, cycle_id="start")
    st["trial"]["apply_cycle_metrics"] = _metric("start", depth=1)
    st["trial"]["apply_cycle_metrics"]["source"] = "apply_cycle_surplus"
    # Same supply rate as the baseline (three 1.0 scores) plus the apply-cycle
    # depth would be lost without the surplus: 3.0 is not > 3.0.
    st["trial"]["trial_metrics"] = [
        _metric("t0", targets=1), _metric("t1"), _metric("t2", targets=1),
        _metric("t3"), _metric("t4", targets=1), _metric("t5"),
    ]
    assert SH.trial_comparison_score(st["trial"]) == 4.0
    # Window still has to be full: five trial rows must not close.
    short = dict(st)
    short["trial"] = dict(st["trial"])
    short["trial"]["trial_metrics"] = st["trial"]["trial_metrics"][:5]
    short = SH.maybe_close_trial(short, "t4")
    assert short["trial"] is not None
    st = SH.maybe_close_trial(st, "t5")
    ev = st["evidence"][-1]
    assert ev["event"] == "adopt"
    assert ev["trial_score"] == 4.0
    assert ev["baseline_score"] == 3.0
    assert ev["apply_cycle_metrics"]["new_depth"] == 1
    assert st["adopted_count"] == 1
    assert st["trial"] is None


def test_apply_cycle_alone_does_not_shorten_the_window(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st = _prime_zero()
    st = SH.start_trial({
        "knob": "fast_term_cap", "from": 8000, "to": 10700, "direction": "up",
        "reason": "depth_at_physical_cap", "window": 6, "baseline_score": 0.0,
        "baseline_metrics": st["metrics"][-6:], "trial_metrics": [],
        "started_cycle": "start", "exploratory": True,
        "predicted_targets": ["oc_A165064_0"],
        "applied_to_live_oracle": False, "authorized": False,
    }, state=st, cycle_id="start")
    st["trial"]["apply_cycle_metrics"] = _metric("start", depth=1)
    st = SH.maybe_close_trial(st, "start")
    assert st["trial"] is not None  # still waiting for 6 trial cycles
    assert st["adopted_count"] == 0


def test_finalize_updates_open_trial_row_on_later_cycles(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st = _signal_state()
    st = SH.start_trial({
        "knob": "fast_term_cap", "from": 8000, "to": 10700, "direction": "up",
        "reason": "depth_at_physical_cap", "window": 6, "baseline_score": 3.0,
        "baseline_metrics": st["metrics"][-6:],
        "trial_metrics": [_metric("t0")],
        "started_cycle": "start",
        "applied_to_live_oracle": False, "authorized": False,
    }, state=st, cycle_id="start")
    # A later trial cycle was recorded with new_depth 0 before OEIS ran.
    st["metrics"] = list(st["metrics"]) + [_metric("t0")]
    SH.save_state(st)
    log = {"attempts": [
        {"id": "oc_A126089_0", "anum": "A126089", "verified_depth": 1199,
         "bfile_hi": 200, "cycle_id": "old", "extended": 100, "planned": 1200,
         "status": "holds_on_range", "beyond": True},
        _attempt("t0", verified=2310, prior=1199, extended=1111, tid="oc_A126089_0"),
    ]}
    st = SH.finalize_cycle_metrics("t0", state=SH.load_state(), attempt_log=log, stall_state={})
    row = [r for r in st["metrics"] if r["cycle_id"] == "t0"][-1]
    assert row["new_depth"] == 1
    trow = [r for r in st["trial"]["trial_metrics"] if r["cycle_id"] == "t0"][-1]
    assert trow["new_depth"] == 1
    assert trow["score"] == SH.score_metrics(0, 1, 0)


def test_attributable_progress_includes_apply_cycle(tmp_path, monkeypatch):
    trial = {
        "predicted_targets": ["oc_A165064_0"],
        "started_cycle": "start",
        "trial_metrics": [{"cycle_id": "t0"}],
        "apply_cycle_metrics": {"cycle_id": "start", "new_depth": 1, "score": 1.0},
    }
    log = {"attempts": []}
    import colony.self_heal as M
    orig = M.targets_with_new_depth
    try:
        M.targets_with_new_depth = lambda lg, cid: {"start": ["oc_A165064_0"], "t0": []}.get(cid, [])
        got = SH.attributable_progress(trial, attempt_log=log, stall_state={"turns": []})
    finally:
        M.targets_with_new_depth = orig
    assert got == ["oc_A165064_0"]


def test_trial_is_no_signal_respects_apply_cycle_metrics():
    trial = {
        "baseline_metrics": [_metric("b0")],
        "trial_metrics": [_metric("t0")],
        "apply_cycle_metrics": _metric("start", depth=1),
    }
    assert SH.trial_is_no_signal(trial) is False

