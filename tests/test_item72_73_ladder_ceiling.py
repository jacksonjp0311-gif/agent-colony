"""Items 72/73: ceiling retirement, overshoot narrowing, cap-ladder
diminishing returns, empty-pool refill visibility.

Tighten-only: the strictly-better rule, 6-cycle windows, Oracle, P>=0.70,
150 cap and Wilson gate are untouched. Every new mechanism is a no-op on the
control arm. Hermetic: all state is built in tmp_path.
"""
from __future__ import annotations

import json

import colony.arm as arm
import colony.oeis_conjectures as O
import colony.self_heal as SH
import colony.self_heal_ladder as L
from tests.test_exploratory_trials import (
    CAP_FINDINGS,
    _fake_eligibility,
    _isolate,
    _metric,
    _prime_zero,
)


def _control(monkeypatch):
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: False)


# --- 73a: retire cap knobs at their physical ceiling ----------------------

def test_ceiling_is_knob_spec_hi():
    assert L.ceiling_of("fast_term_cap") == SH.KNOB_SPECS["fast_term_cap"].hi
    assert L.ceiling_of("park_cycles") is None


def test_retire_at_ceiling_once_then_unretire(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st = SH.load_state()
    SH._apply_knob(st, "fast_term_cap", 20000)
    evs = L.retire_ceiling_cap_knobs(st, "c1")
    assert [e["knob"] for e in evs] == ["fast_term_cap"]
    ev = evs[0]
    assert ev["event"] == "action_retired" and ev["reason"] == "at_physical_ceiling"
    assert ev["authorized"] is False and ev["applied_to_live_oracle"] is False
    assert L.retired_knob(st, "fast_term_cap")
    assert L.retire_ceiling_cap_knobs(st, "c2") == []  # no duplicate event
    n = len(st["evidence"])
    SH._apply_knob(st, "fast_term_cap", 18800)
    L.retire_ceiling_cap_knobs(st, "c3")
    assert not L.retired_knob(st, "fast_term_cap")
    assert len(st["evidence"]) == n  # un-retire appends nothing, deletes nothing


def test_retire_noop_on_control_arm(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _control(monkeypatch)
    st = SH.load_state()
    SH._apply_knob(st, "fast_term_cap", 20000)
    assert L.retire_ceiling_cap_knobs(st, "c1") == []
    assert not st.get("retired_cap_knobs")


def test_filter_drops_cap_finding_with_only_retired_knobs():
    st = {"retired_cap_knobs": {"fast_term_cap": {}}}
    only = [{"kind": "depth_at_physical_cap", "suggest": [("fast_term_cap", "up")]}]
    assert L.filter_retired_findings(only, st) == []
    mixed = [{"kind": "depth_at_physical_cap",
              "suggest": [("fast_term_cap", "up"), ("gf_term_cap", "up")]}]
    out = L.filter_retired_findings(mixed, st)
    assert out[0]["suggest"] == [("gf_term_cap", "up")]
    assert out[0]["retired_suggestions"] == ["fast_term_cap"]
    other = [{"kind": "dead_end_streak", "suggest": [("fast_term_cap", "up")]}]
    assert L.filter_retired_findings(other, st)[0]["suggest"] == []


def test_run_cycle_retires_and_filters(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st = _prime_zero()
    SH._apply_knob(st, "fast_term_cap", 20000)
    SH.save_state(st)
    monkeypatch.setattr(SH, "maybe_supply_oracle_targets", lambda *a, **k: {})
    finding = [{"kind": "depth_at_physical_cap", "evidence": {}, "suggest": [("fast_term_cap", "up")]}]
    monkeypatch.setattr(SH, "diagnose", lambda *a, **k: [dict(f) for f in finding])
    SH.run_cycle("c9", metrics=_metric("c9"))
    st = SH.load_state()
    assert any(e.get("event") == "action_retired" and e.get("knob") == "fast_term_cap"
               for e in st["evidence"])
    assert "fast_term_cap" in st["retired_cap_knobs"]
    assert not st.get("trial")


# --- 73b: narrow a repeat exploration that overshot into another cap ------

def _failed_gf(value=2310, cycles=("e0", "e1")):
    return {"event": "trial_inconclusive", "knob": "gf_term_cap", "from": value, "to": 1200,
            "exploratory": True, "predicted_targets": ["oc_GF"], "started_cycle": cycles[0],
            "trial_metrics": [{"cycle_id": c} for c in cycles[1:]]}


def _log(cap_reason="time_cap", cycle="e1"):
    return {"attempts": [{"id": "oc_GF", "cycle_id": cycle, "status": "holds_on_range",
                          "cap_reason": cap_reason, "cap_value": 8.0}]}


def test_overshoot_cap_only_for_other_knobs_cap():
    ev = _failed_gf()
    assert L.overshoot_cap(ev, "gf_term_cap", attempt_log=_log("time_cap")) == "time_cap"
    own = {"attempts": [{"id": "oc_GF", "cycle_id": "e1", "status": "holds_on_range",
                         "cap_reason": "term_cap", "cap_value": 2310}]}
    assert L.overshoot_cap(ev, "gf_term_cap", attempt_log=own) == ""  # its own cap: not an overshoot
    assert L.overshoot_cap(ev, "gf_term_cap", attempt_log=_log("time_cap", cycle="zz")) == ""


def test_narrower_midpoint_after_overshoot(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st = {"evidence": [_failed_gf()]}
    got = L.narrower_after_overshoot(st, "gf_term_cap", 1200, 2310, ["oc_GF"],
                                     predict=lambda k, v: ["oc_GF"], attempt_log=_log())
    assert got == (1755, ["oc_GF"], "time_cap")
    # midpoint already failed the same way -> halve again
    st["evidence"].append(_failed_gf(1755, ("f0", "f1")))
    log = {"attempts": _log()["attempts"] + _log(cycle="f1")["attempts"]}
    got = L.narrower_after_overshoot(st, "gf_term_cap", 1200, 2310, ["oc_GF"],
                                     predict=lambda k, v: ["oc_GF"], attempt_log=log)
    assert got[0] == 1478


def test_no_narrowing_without_overshoot_or_prediction_or_on_control(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st = {"evidence": [_failed_gf()]}
    empty = {"attempts": []}
    assert L.narrower_after_overshoot(st, "gf_term_cap", 1200, 2310, ["oc_GF"],
                                      predict=lambda k, v: ["oc_GF"], attempt_log=empty) is None
    assert L.narrower_after_overshoot(st, "gf_term_cap", 1200, 2310, ["oc_GF"],
                                      predict=lambda k, v: [], attempt_log=_log()) is None
    _control(monkeypatch)
    assert L.narrower_after_overshoot(st, "gf_term_cap", 1200, 2310, ["oc_GF"],
                                      predict=lambda k, v: ["oc_GF"], attempt_log=_log()) is None


def _write_attempt_log(rows):
    O.ATTEMPT_LOG.parent.mkdir(parents=True, exist_ok=True)
    O.ATTEMPT_LOG.write_text(json.dumps({"attempts": rows}), encoding="utf-8")


# Shape of the live A126089 rows: term cap at 2310, the 3420 trial cycle
# timing out at the 8 s budget, then back on the 2310 term cap.
TERM_ROW = {"id": "oc_GF", "cycle_id": "later", "status": "holds_on_range",
            "planned": 2310, "verified_depth": 2309, "cap_reason": "term_cap", "cap_value": 2310}


def test_flat_baseline_opens_narrowed_trial_instead_of_skipping(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _fake_eligibility(monkeypatch, opens={"gf_term_cap": "oc_GF"})
    _write_attempt_log(_log()["attempts"] + [TERM_ROW])
    st = _prime_zero()
    st["evidence"] = [_failed_gf()]
    findings = [{"kind": "depth_at_physical_cap", "evidence": {}, "suggest": [("gf_term_cap", "up")]}]
    prop = SH.propose_trial(findings, state=st, cycle_id="c")
    assert prop is not None and prop["knob"] == "gf_term_cap"
    assert prop["to"] == 1755 and prop["exploratory"] is True
    assert prop["predicted_targets"] == ["oc_GF"]
    assert prop["narrowed_after_overshoot"] == {"failed_to": 2310, "cap_reason": "time_cap"}
    assert prop["window"] == 6  # full window, scored strictly better as before
    st = SH.start_trial(prop, state=st, cycle_id="c")
    start = [e for e in st["evidence"] if e["event"] == "trial_start"][-1]
    assert start["narrowed_after_overshoot"]["cap_reason"] == "time_cap"


def test_flat_baseline_still_skips_plain_repeat(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _fake_eligibility(monkeypatch, opens={"gf_term_cap": "oc_GF"})
    _write_attempt_log([TERM_ROW])  # failure was not an overshoot
    st = _prime_zero()
    st["evidence"] = [_failed_gf()]
    findings = [{"kind": "depth_at_physical_cap", "evidence": {}, "suggest": [("gf_term_cap", "up")]}]
    assert SH.propose_trial(findings, state=st, cycle_id="c") is None
    assert st["trial_skip"]["reason"] == "no_signal_baseline"


# --- 72: cap-ladder diminishing returns -----------------------------------

def _adopt(knob="fast_term_cap", targets=("oc_FAST",), passes=528):
    rows = [{"cycle_id": "x", "oracle_passes": passes}]
    return {"event": "adopt", "knob": knob, "predicted_targets": list(targets),
            "baseline_metrics": rows, "trial_metrics": rows}


def test_ladder_needs_two_consecutive_same_target_adopts_with_flat_passes():
    assert not L.ladder_state({"evidence": [_adopt()]}, "fast_term_cap", ["oc_FAST"])["active"]
    st = {"evidence": [_adopt(), _adopt()]}
    assert L.ladder_state(st, "fast_term_cap", ["oc_FAST"])["active"]
    assert not L.ladder_state(st, "fast_term_cap", ["oc_OTHER"])["active"]
    moved = {"evidence": [_adopt(passes=520), _adopt(passes=528)]}
    assert not L.ladder_state(moved, "fast_term_cap", ["oc_FAST"])["active"]
    broken = {"evidence": [_adopt(), _adopt("gf_term_cap"), _adopt()]}
    assert not L.ladder_state(broken, "fast_term_cap", ["oc_FAST"])["active"]
    # non-adopt closes in between do not break the ladder
    mixed = {"evidence": [_adopt(), {"event": "trial_inconclusive"}, _adopt()]}
    assert L.ladder_state(mixed, "fast_term_cap", ["oc_FAST"])["active"]


def _trial(**kw):
    t = {"knob": "fast_term_cap", "predicted_targets": ["oc_FAST"],
         "baseline_metrics": [{"oracle_passes": 528, "new_oracle_targets": 0}],
         "trial_metrics": [{"oracle_passes": 528, "new_oracle_targets": 0, "oracle_pass_delta": 0}],
         "authored_at_start": 150, "target_depths_at_start": {"oc_FAST": 10, "oc_B": 5}}
    t.update(kw)
    return t


def test_marginal_value_reasons():
    assert L.marginal_value(_trial(), authored_now=150, depths_now={"oc_FAST": 40, "oc_B": 5}) == []
    assert L.marginal_value(_trial(), authored_now=149, depths_now={}) == ["freed_slots"]
    assert L.marginal_value(_trial(), authored_now=150, depths_now={"oc_B": 6}) == ["second_target_depth"]
    t = _trial(trial_metrics=[{"oracle_passes": 528, "new_oracle_targets": 1, "oracle_pass_delta": 1}])
    assert L.marginal_value(t, authored_now=150, depths_now={}) == ["oracle_pass_delta", "new_oracle_targets"]


def test_adopt_on_ladder_without_marginal_value_is_inconclusive(monkeypatch):
    monkeypatch.setattr(L, "marginal_value", lambda trial, **k: [])
    st = {"evidence": [_adopt(), _adopt()]}
    t = _trial()
    assert L.apply_diminishing_returns(st, t, "adopt", None) == ("inconclusive", "diminishing_returns")
    assert t["ladder"]["active"] and t["ladder"]["adopts"] == 2


def test_adopt_on_ladder_with_marginal_value_stays_adopt(monkeypatch):
    monkeypatch.setattr(L, "marginal_value", lambda trial, **k: ["freed_slots"])
    st = {"evidence": [_adopt(), _adopt()]}
    assert L.apply_diminishing_returns(st, _trial(), "adopt", None) == ("adopt", None)


def test_diminishing_returns_never_loosens(monkeypatch):
    monkeypatch.setattr(L, "marginal_value", lambda trial, **k: ["freed_slots"])
    st = {"evidence": [_adopt(), _adopt()]}
    for d in ("revert", "inconclusive"):
        assert L.apply_diminishing_returns(st, _trial(), d, "r") == (d, "r")
    assert L.apply_diminishing_returns({"evidence": [_adopt()]}, _trial(), "adopt", None) == ("adopt", None)


def test_diminishing_returns_off_on_control(monkeypatch):
    _control(monkeypatch)
    monkeypatch.setattr(L, "marginal_value", lambda trial, **k: [])
    st = {"evidence": [_adopt(), _adopt()]}
    assert L.apply_diminishing_returns(st, _trial(), "adopt", None) == ("adopt", None)


def test_ladder_knob_goes_behind_other_candidates(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _fake_eligibility(monkeypatch)
    st = _prime_zero()
    prop = SH.propose_trial(CAP_FINDINGS + [{"kind": "x", "suggest": [("gf_term_cap", "up")]}],
                            state=st, cycle_id="c")
    assert prop["knob"] == "fast_term_cap"  # baseline order
    st = _prime_zero()
    st["evidence"] = [_adopt(), _adopt()]
    prop = SH.propose_trial(CAP_FINDINGS + [{"kind": "x", "suggest": [("gf_term_cap", "up")]}],
                            state=st, cycle_id="c")
    assert prop["knob"] == "gf_term_cap"  # budget shifted off the flat ladder


# --- 73c: empty-pool refill comes from the target generator, cap held ----

def test_skip_records_supply_outcome(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(SH, "eligible_target_ids", lambda stall_state=None: set())
    _prime_zero()
    monkeypatch.setattr(SH, "maybe_supply_oracle_targets", lambda *a, **k: {
        "invited": True, "reason": "at_authored_cap", "n": 150, "cap": 150, "authored": []})
    monkeypatch.setattr(SH, "diagnose", lambda *a, **k: [dict(f) for f in CAP_FINDINGS])
    SH.run_cycle("c9", metrics=_metric("c9"))
    skip = SH.load_state()["trial_skip"]
    assert skip["supply"]["reason"] == "at_authored_cap"
    assert skip["supply"]["cap"] == 150 and skip["supply"]["authored"] == 0
