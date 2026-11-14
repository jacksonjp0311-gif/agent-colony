"""Item 63: predict only targets whose cap_reason the knob actually binds."""
from __future__ import annotations

import colony.oeis_conjectures as O
import colony.self_heal as SH

from test_exploratory_trials import (
    CAP_FINDINGS, _isolate, _prime_zero, _fake_eligibility,
)


def test_knobs_for_cap_reason_families():
    assert O.knobs_for_cap_reason("digit_or_time_cap") == frozenset({"deep_digits", "deep_seconds"})
    assert O.knobs_for_cap_reason("time_cap") == frozenset({"deep_seconds"})
    assert O.knobs_for_cap_reason("digit_cap") == frozenset({"deep_digits"})
    assert O.knobs_for_cap_reason("term_cap", row={"cap_value": 1200}) == frozenset({"gf_term_cap"})
    assert O.knobs_for_cap_reason("term_cap", row={"cap_value": 8000}) == frozenset({"fast_term_cap"})
    assert O.knobs_for_cap_reason("term_cap", row={"cap_value": 20000}) == frozenset({"deep_term_cap"})
    assert O.knobs_for_cap_reason("ref_limited") == frozenset()
    assert O.knobs_for_cap_reason("") == frozenset()


def test_term_cap_knob_follows_evaluator_not_just_value():
    gf = {"claim": {"form": "gf"}, "definition": {"kind": "gf"}}
    assert O.term_cap_knob_for(gf) == "gf_term_cap"
    rec = {"definition": {"kind": "rec"}, "claim": {"form": "rec"}}
    # A non-C-finite rec uses the deep term cap (fast_cfinite_available is False).
    assert O.term_cap_knob_for(rec) == "deep_term_cap"


def _log_for(tid, reason, value):
    return {"attempts": [{
        "id": tid, "status": "holds_on_range",
        "cap_reason": reason, "cap_value": value, "verified_depth": value,
    }]}


def _eligible_under_any_cap(monkeypatch, tid="oc_A126089_0"):
    """Reproduce the eligibility leak: any cap override appears to free tid."""
    def ids(stall_state=None):
        return {tid} if O._CAP_OVERRIDES else set()
    monkeypatch.setattr(SH, "eligible_target_ids", ids)


def test_predictor_drops_mismatched_digit_or_time_target(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _eligible_under_any_cap(monkeypatch)
    monkeypatch.setattr(O, "load_attempt_log", lambda **k: _log_for("oc_A126089_0", "digit_or_time_cap", 956))
    assert SH.predicted_new_targets("gf_term_cap", 2310) == []
    assert SH.predicted_new_targets("fast_term_cap", 10700) == []
    assert SH.predicted_new_targets("deep_term_cap", 30000) == []
    assert SH.predicted_new_targets("deep_seconds", 9.8) == ["oc_A126089_0"]
    assert SH.predicted_new_targets("deep_digits", 6500) == ["oc_A126089_0"]


def test_predictor_matches_term_cap_to_the_binding_term_knob(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _eligible_under_any_cap(monkeypatch, "oc_A165064_0")
    monkeypatch.setattr(O, "load_attempt_log", lambda **k: _log_for("oc_A165064_0", "term_cap", 8000))
    assert SH.predicted_new_targets("fast_term_cap", 10700) == ["oc_A165064_0"]
    assert SH.predicted_new_targets("gf_term_cap", 2310) == []
    assert SH.predicted_new_targets("deep_seconds", 9.8) == []


def test_target_with_no_attempt_row_still_predicted(tmp_path, monkeypatch):
    """No recorded cap_reason: do not over-filter a brand-new eligible id."""
    _isolate(tmp_path, monkeypatch)
    _fake_eligibility(monkeypatch)
    monkeypatch.setattr(O, "load_attempt_log", lambda **k: {"attempts": []})
    assert SH.predicted_new_targets("fast_term_cap", 10700) == ["oc_FAST"]


def test_propose_prefers_knob_that_binds_the_capped_target(tmp_path, monkeypatch):
    """A depth_at_physical_cap finding that names the wrong term knob still
    opens the matching digit/time knob when that is what can move the hold.
    """
    _isolate(tmp_path, monkeypatch)
    _eligible_under_any_cap(monkeypatch)
    monkeypatch.setattr(O, "load_attempt_log", lambda **k: _log_for("oc_A126089_0", "time_cap", 8.0))
    st = _prime_zero()
    findings = [
        {"kind": "depth_at_physical_cap", "evidence": {}, "suggest": [("gf_term_cap", "up")]},
    ]
    prop = SH.propose_trial(findings, state=st, cycle_id="c")
    assert prop is not None
    assert prop["knob"] == "deep_seconds"
    assert prop["predicted_targets"] == ["oc_A126089_0"]
    assert prop["exploratory"] is True
