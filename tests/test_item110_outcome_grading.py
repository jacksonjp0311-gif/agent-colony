"""Item 110: Hive predictions graded by measured outcome (HIVE_OUTCOME_GRADING)."""
from __future__ import annotations

import json

import hive.outcome_grading as OG
import hive.swarm as SL
from hive.bitwork import WILSON_ACCEPT_PERMILLE


def _heal(*rows):
    return [dict(r) for r in rows]


def _shadow(sid, ts, knob, margin=40, direction="up"):
    return {"id": sid, "ts": ts, "cycle_id": "", "label": "x", "margin": margin,
            "action": {"op": "set_knob", "name": knob, "direction": direction},
            "fingerprint": f"set_knob:direction={direction}:name={knob}:value=1", "resolved": False}


def _start(knob, ts):
    return {"event": "trial_start", "knob": knob, "direction": "up", "ts": ts}


def _close(event, knob, ts, eid):
    return {"event": event, "knob": knob, "direction": "up", "ts": ts, "id": eid}


def test_gate_constant_unchanged():
    assert WILSON_ACCEPT_PERMILLE == 700


def test_adopt_after_prediction_is_correct_and_revert_is_wrong():
    st = {"shadows": [_shadow("a", "2026-01-01T00:00:00Z", "k1"), _shadow("b", "2026-01-01T00:00:00Z", "k2")]}
    trials = OG.collect_trials(_heal(
        _start("k1", "2026-01-01T01:00:00Z"), _close("adopt", "k1", "2026-01-01T03:00:00Z", "t1"),
        _start("k2", "2026-01-01T01:00:00Z"), _close("revert", "k2", "2026-01-01T03:00:00Z", "t2"),
    ))
    r = OG.grade(OG.collect_predictions(st), trials)
    assert (r["n_graded"], r["n_correct"], r["n_wrong"]) == (2, 1, 1)


def test_no_foreknowledge_trial_started_before_prediction_abstains():
    st = {"shadows": [_shadow("a", "2026-01-01T02:00:00Z", "k1")]}
    trials = OG.collect_trials(_heal(
        _start("k1", "2026-01-01T01:00:00Z"), _close("adopt", "k1", "2026-01-01T03:00:00Z", "t1")))
    r = OG.grade(OG.collect_predictions(st), trials)
    assert r["n_graded"] == 0 and r["n_abstain"] == 1


def test_voided_or_missing_trial_gives_no_credit():
    st = {"shadows": [_shadow("a", "2026-01-01T00:00:00Z", "k1"), _shadow("b", "2026-01-01T00:00:00Z", "k9")]}
    trials = OG.collect_trials(_heal(
        _start("k1", "2026-01-01T01:00:00Z"),
        {"event": "trial_voided_confound", "knob": "k1", "direction": "up", "ts": "2026-01-01T02:00:00Z"}))
    r = OG.grade(OG.collect_predictions(st), trials)
    assert r["n_graded"] == 0 and r["units"] == []


def test_direction_must_match():
    st = {"shadows": [_shadow("a", "2026-01-01T00:00:00Z", "k1", direction="down")]}
    trials = OG.collect_trials(_heal(
        _start("k1", "2026-01-01T01:00:00Z"), _close("adopt", "k1", "2026-01-01T03:00:00Z", "t1")))
    assert OG.grade(OG.collect_predictions(st), trials)["n_graded"] == 0


def test_repeated_predictions_collapse_to_one_unit():
    st = {"shadows": [_shadow(f"s{i}", f"2026-01-01T00:0{i}:00Z", "k1") for i in range(5)]}
    trials = OG.collect_trials(_heal(
        _start("k1", "2026-01-01T01:00:00Z"), _close("adopt", "k1", "2026-01-01T03:00:00Z", "t1")))
    r = OG.grade(OG.collect_predictions(st), trials)
    assert r["n_correct"] == 5 and len(r["units"]) == 1 and r["units"][0]["n_predictions"] == 5


def test_ledger_is_append_only_and_idempotent(tmp_path):
    path = tmp_path / "g.jsonl"
    st = {"shadows": [_shadow("a", "2026-01-01T00:00:00Z", "k1")]}
    trials = OG.collect_trials(_heal(
        _start("k1", "2026-01-01T01:00:00Z"), _close("adopt", "k1", "2026-01-01T03:00:00Z", "t1")))
    units = OG.grade(OG.collect_predictions(st), trials)["units"]
    assert len(OG.append_units(units, path)) == 1
    first = path.read_text()
    assert OG.append_units(units, path) == []
    assert path.read_text() == first


def test_switch_and_control(monkeypatch):
    monkeypatch.delenv("HIVE_OUTCOME_GRADING", raising=False)
    monkeypatch.delenv("COLONY_ARM", raising=False)
    assert OG.outcome_grading_enabled()
    monkeypatch.setenv("HIVE_OUTCOME_GRADING", "off")
    assert not OG.outcome_grading_enabled()
    monkeypatch.delenv("HIVE_OUTCOME_GRADING", raising=False)
    monkeypatch.setenv("COLONY_ARM", "control")
    assert not OG.outcome_grading_enabled()


def _cal_with_slices():
    cal = SL._empty_calibration()
    for b in cal["buckets"]:
        if b["min_margin"] == 32:
            b["by_source"]["shadow"] = {"n": 30, "correct": 0}
            b["by_source"]["replay"] = {"n": 5, "correct": 5}
    return cal


def test_totals_swap_shadow_for_outcome_only_when_on(monkeypatch):
    rows = [{"rule": OG.RULE, "margin": 40, "correct": True}]
    monkeypatch.setenv("HIVE_OUTCOME_GRADING", "off")
    cal = _cal_with_slices()
    OG.apply_to_calibration(cal, rows)
    SL._recompute_bucket_totals(cal)
    b = [x for x in cal["buckets"] if x["min_margin"] == 32][0]
    assert (b["correct"], b["n"]) == (5, 35)
    monkeypatch.delenv("HIVE_OUTCOME_GRADING", raising=False)
    monkeypatch.delenv("COLONY_ARM", raising=False)
    SL._recompute_bucket_totals(cal)
    assert (b["correct"], b["n"]) == (6, 6)
    assert b["by_source"]["shadow"] == {"n": 30, "correct": 0}  # old slice kept, not rewritten


def test_grade_outcomes_noop_when_off(monkeypatch):
    monkeypatch.setenv("HIVE_OUTCOME_GRADING", "off")
    router = SL._build_router()
    st = {"calibration": SL._empty_calibration()}
    assert SL.grade_outcomes(router, st) is None
    assert "outcome_grading" not in st


def test_grade_outcomes_writes_ledger(monkeypatch, tmp_path):
    monkeypatch.delenv("HIVE_OUTCOME_GRADING", raising=False)
    monkeypatch.delenv("COLONY_ARM", raising=False)
    monkeypatch.setattr(OG, "LEDGER_PATH", tmp_path / "g.jsonl")
    from hive import host
    ev = _heal(_start("k1", "2026-01-01T01:00:00Z"), _close("adopt", "k1", "2026-01-01T03:00:00Z", "t1"))
    monkeypatch.setattr(host, "heal_load_state", lambda: {"evidence": ev})
    router = SL._build_router()
    st = {"calibration": SL._empty_calibration(), "shadows": [_shadow("a", "2026-01-01T00:00:00Z", "k1")]}
    info = SL.grade_outcomes(router, st)
    assert info["units"] == 1 and info["units_correct"] == 1
    rows = [json.loads(x) for x in (tmp_path / "g.jsonl").read_text().splitlines()]
    assert rows[0]["trial_event"] == "adopt"
