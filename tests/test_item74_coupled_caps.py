"""Item 74: binding cap under current knobs, coupled cap trials, compute_bound.

Rows mirror the live A126089 shape: term cap at gf 2310 (depth cap-1) and
the 8 s time cap at gf 2865 (depth 75). Hermetic: state and attempt log are
written under tmp_path. Gates unchanged: 6-cycle window, strictly better,
single trial slot; control arm frozen.
"""
from __future__ import annotations

import json

import colony.arm as arm
import colony.oeis_conjectures as O
import colony.self_heal as SH
import colony.self_heal_coupled as C
from tests.test_exploratory_trials import _isolate, _prime_zero

T = "oc_GF"
TERM_2310 = {"id": T, "status": "holds_on_range", "planned": 2310, "verified_depth": 2309,
             "cap_reason": "term_cap", "cap_value": 2310}
TIME_2865 = {"id": T, "status": "holds_on_range", "planned": 2865, "verified_depth": 75,
             "cap_reason": "time_cap", "cap_value": 8.0}
FINDINGS = [{"kind": "depth_at_physical_cap", "evidence": {}, "suggest": [("gf_term_cap", "up")]}]


def _rows():
    return [dict(TERM_2310, cycle_id="a0"), dict(TIME_2865, cycle_id="t0"),
            dict(TERM_2310, cycle_id="a1")]


def _write_log(rows):
    O.ATTEMPT_LOG.parent.mkdir(parents=True, exist_ok=True)
    O.ATTEMPT_LOG.write_text(json.dumps({"attempts": rows}), encoding="utf-8")


def _eligibility(monkeypatch):
    """oc_GF becomes eligible under a gf or time override (as the stale latest row suggested)."""
    def ids(stall_state=None):
        return {T} if ("gf_terms" in O._CAP_OVERRIDES or "deep_seconds" in O._CAP_OVERRIDES) else set()
    monkeypatch.setattr(SH, "eligible_target_ids", ids)


def _failed_gf_trial():
    return {"id": "ev_gf2865", "event": "trial_inconclusive", "knob": "gf_term_cap", "from": 2865,
            "to": 2310, "exploratory": True, "predicted_targets": [T], "started_cycle": "t0",
            "trial_metrics": [{"cycle_id": "t0b"}]}


def _setup(tmp_path, monkeypatch, *, rows=None, evidence=None, ds=8.0):
    _isolate(tmp_path, monkeypatch)
    _eligibility(monkeypatch)
    _write_log(_rows() if rows is None else rows)
    st = _prime_zero()
    SH._apply_knob(st, "gf_term_cap", 2310)
    SH._apply_knob(st, "deep_seconds", ds)
    st["evidence"] = list(evidence if evidence is not None else [_failed_gf_trial()])
    SH.save_state(st)
    return SH.load_state()


def _control(monkeypatch):
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: False)


# --- (a) binding cap under the current knob values -------------------------

def test_binding_cap_ignores_rows_from_other_knob_values(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch, rows=[dict(TERM_2310, cycle_id="a0"), dict(TIME_2865, cycle_id="t0")])
    knobs = dict(st["knobs"])
    now = C.binding_cap_now(T, knobs)
    assert now["cap_reason"] == "term_cap" and now["cycle_id"] == "a0"  # t0 was at gf 2865
    assert C.prediction_fits(T, "gf_term_cap", knobs) is True
    assert C.prediction_fits(T, "deep_seconds", knobs) is False
    knobs["gf_term_cap"] = 2865
    assert C.binding_cap_now(T, knobs)["cap_reason"] == "time_cap"
    assert C.prediction_fits(T, "deep_seconds", knobs) is True


def test_stale_time_cap_no_longer_predicts_deep_seconds_trial(tmp_path, monkeypatch):
    # Latest row is the gf-2865 time cap, but gf is back at 2310: stale.
    st = _setup(tmp_path, monkeypatch, rows=[dict(TERM_2310, cycle_id="a0"), dict(TIME_2865, cycle_id="t0")])
    assert SH.predicted_new_targets("deep_seconds", 8.9, state=st) == []
    assert SH.predicted_new_targets("gf_term_cap", 2865, state=st) == [T]


def test_no_row_under_current_knobs_keeps_previous_rule(tmp_path, monkeypatch):
    # no row was recorded at the current deep_seconds (8.0)
    st = _setup(tmp_path, monkeypatch, rows=[dict(TIME_2865, cycle_id="t0", cap_value=9.8)])
    assert C.prediction_fits(T, "deep_seconds", dict(st["knobs"])) is None
    assert SH.predicted_new_targets("deep_seconds", 8.9, state=st) == [T]  # latest-row rule


def test_control_arm_keeps_latest_row_rule(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch, rows=[dict(TERM_2310, cycle_id="a0"), dict(TIME_2865, cycle_id="t0")])
    _control(monkeypatch)
    assert SH._predicted_target_fits_knob(T, "deep_seconds", state=st) is True


# --- (b) flip detection and the coupled trial ------------------------------

def test_detect_flip(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch)
    flip = C.detect_flip(st, T)
    assert flip["knob"] == "gf_term_cap" and flip["failed_value"] == 2865
    assert flip["other_knob"] == "deep_seconds" and flip["other_cap_reason"] == "time_cap"
    assert flip["binding_now"] == "term_cap"


def test_no_flip_when_other_cap_value_differs_now(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch, ds=9.8)  # time cap row was at 8.0
    assert C.detect_flip(st, T) is None


def test_coupled_values_scale_and_bounds():
    assert C.coupled_values("gf_term_cap", 2310, 2865, "deep_seconds", 8.0) == 12.4
    assert C.coupled_values("gf_term_cap", 2310, 2865, "deep_seconds", 15.0) == 16.0
    assert C.coupled_values("gf_term_cap", 2310, 2865, "deep_seconds", 16.0) is None


def _propose(tmp_path, monkeypatch, **kw):
    st = _setup(tmp_path, monkeypatch, **kw)
    return st, SH.propose_trial(FINDINGS, state=st, cycle_id="c")


def test_flip_opens_one_coupled_trial(tmp_path, monkeypatch):
    st, prop = _propose(tmp_path, monkeypatch)
    assert prop["knob"] == "gf_term_cap" and prop["from"] == 2310 and prop["to"] == 2865
    assert prop["coupled"] == {"knob": "deep_seconds", "from": 8.0, "to": 12.4,
                               "direction": "up", "cap_reason": "time_cap"}
    assert prop["predicted_targets"] == [T] and prop["exploratory"] is True
    assert prop["window"] == 6 and prop["authorized"] is False
    st = SH.start_trial(prop, state=st, cycle_id="c")
    assert st["knobs"]["gf_term_cap"] == 2865 and st["knobs"]["deep_seconds"] == 12.4
    start = [e for e in st["evidence"] if e["event"] == "trial_start"][-1]
    assert start["coupled"]["knob"] == "deep_seconds"
    assert SH.trial_fingerprint_mismatch(st["trial"], state=st)[0] is False
    # single slot: no second proposal while it runs
    assert SH.propose_trial(FINDINGS, state=st, cycle_id="c2") is None


def test_coupled_not_adopted_restores_both_and_retires(tmp_path, monkeypatch):
    st, prop = _propose(tmp_path, monkeypatch)
    st = SH.start_trial(prop, state=st, cycle_id="c")
    st = SH._close_trial(st, "c6", "inconclusive", reason="no_signal")
    assert st["knobs"]["gf_term_cap"] == 2310 and st["knobs"]["deep_seconds"] == 8.0
    events = [e["event"] for e in st["evidence"]]
    assert events[-2:] == ["trial_inconclusive", "target_retired"]
    ret = st["evidence"][-1]
    assert ret["reason"] == "compute_bound" and ret["target"] == T
    assert ret["authorized"] is False and ret["applied_to_live_oracle"] is False
    assert st["evidence"][-2]["coupled"]["knob"] == "deep_seconds"
    assert C.compute_bound(st, T)
    assert SH.predicted_new_targets("gf_term_cap", 2865, state=st) == []  # budget moves on


def test_coupled_revert_also_retires(tmp_path, monkeypatch):
    st, prop = _propose(tmp_path, monkeypatch)
    st = SH.start_trial(prop, state=st, cycle_id="c")
    st = SH._close_trial(st, "c6", "revert")
    assert st["knobs"]["deep_seconds"] == 8.0 and C.compute_bound(st, T)


def test_coupled_adopt_keeps_both_no_retire(tmp_path, monkeypatch):
    st, prop = _propose(tmp_path, monkeypatch)
    st = SH.start_trial(prop, state=st, cycle_id="c")
    import colony.self_heal_score as SS
    monkeypatch.setattr(SS, "refresh_trial_scores", lambda trial: None)
    st["trial"]["predicted_depth_gain"] = 555  # strictly better on the predicted target
    st = SH._close_trial(st, "c6", "adopt")
    assert st["evidence"][-1]["event"] == "adopt"
    assert st["knobs"]["gf_term_cap"] == 2865 and st["knobs"]["deep_seconds"] == 12.4
    assert not C.compute_bound(st, T)


def test_void_restores_both(tmp_path, monkeypatch):
    st, prop = _propose(tmp_path, monkeypatch)
    st = SH.start_trial(prop, state=st, cycle_id="c")
    st = SH.void_trial_for_confound(st, "c2", old_fingerprint="a", new_fingerprint="b")
    assert st["knobs"]["gf_term_cap"] == 2310 and st["knobs"]["deep_seconds"] == 8.0
    assert not C.compute_bound(st, T)  # a void is not a judgment


def test_coupled_respects_cooldown(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch)
    st["knob_last_trial"] = {"deep_seconds": {"direction": "up", "cycle_index": st["cycle_index"]}}
    prop = SH.propose_trial(FINDINGS, state=st, cycle_id="c")
    assert prop is None or "coupled" not in prop


# --- (c) compute_bound retirement ------------------------------------------

def test_other_knob_at_ceiling_retires_without_trial(tmp_path, monkeypatch):
    rows = [dict(TERM_2310, cycle_id="a0"), dict(TIME_2865, cycle_id="t0", cap_value=16.0),
            dict(TERM_2310, cycle_id="a1")]
    st, prop = _propose(tmp_path, monkeypatch, rows=rows, ds=16.0)
    assert prop is None or "coupled" not in prop
    ret = [e for e in st["evidence"] if e["event"] == "target_retired"]
    assert ret and ret[0]["detail"] == "knob_at_physical_ceiling"


def test_failed_coupled_trial_is_not_repeated(tmp_path, monkeypatch):
    failed = {"event": "trial_inconclusive", "knob": "gf_term_cap", "from": 2865, "to": 2310,
              "predicted_targets": [T], "coupled": {"knob": "deep_seconds", "from": 8.0, "to": 12.4}}
    st, prop = _propose(tmp_path, monkeypatch, evidence=[_failed_gf_trial(), failed])
    assert prop is None or "coupled" not in prop
    assert C.compute_bound(st, T)


def test_refresh_unretires_when_knob_rises(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch)
    C.retire_compute_bound(st, T, cycle_id="c", why="x", knobs_at={"gf_term_cap": 2310, "deep_seconds": 8.0})
    assert C.refresh_compute_bound(st, "c1") == []
    SH._apply_knob(st, "deep_seconds", 9.8)
    assert C.refresh_compute_bound(st, "c2") == [T]
    assert not C.compute_bound(st, T)
    assert st["evidence"][-1]["event"] == "target_unretired"


def test_retirement_persists_across_load(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch)
    C.retire_compute_bound(st, T, cycle_id="c", why="x", knobs_at={})
    SH.save_state(st)
    assert C.compute_bound(SH.load_state(), T)


def test_control_arm_no_coupled_no_retire(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch)
    _control(monkeypatch)
    assert C.coupled_proposal(st, [T], cycle_id="c") is None
    assert C.retire_compute_bound(st, T, cycle_id="c", why="x", knobs_at={}) is None
    assert SH.propose_trial(FINDINGS, state=st, cycle_id="c") is None
