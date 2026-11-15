"""Item 78: the cobind check in front of every cap trial; time-bound retire.

Rows mirror live A126089 after adopt #11 (6:11 PM ET Nov 15): depth 3148 at
gf 3149 / deep_digits 11647 / deep_seconds 16.0 (its KnobSpec ceiling),
measured series times 14.5-15.8 s at planned 3149 and 37.5 s at 4259.
Hermetic (tmp_path). Gates unchanged; authorize false; control arm no-op.
"""
from __future__ import annotations

import json

import colony.arm as arm
import colony.oeis_conjectures as O
import colony.self_heal as SH
import colony.self_heal_cobind as B
import colony.self_heal_coupled as C
from tests.test_exploratory_trials import _isolate, _prime_zero

T = "oc_GF"


def _row(cid, planned, verified, reason, value, **kw):
    r = {"id": T, "status": "holds_on_range", "cycle_id": cid, "planned": planned,
         "verified_depth": verified, "cap_reason": reason, "cap_value": value, "fast_cfinite": False}
    r.update(kw)
    return r


DIGITS = [_row("d1", 2310, 1853, "digit_cap", 6350), _row("d2", 2310, 2200, "digit_cap", 7700),
          _row("d3", 2865, 2540, "digit_cap", 9050)]
AFTER_ADOPT = DIGITS + [
    _row("a1", 3149, 3148, "term_cap", 3149, deep_elapsed_s=14.51),
    _row("a2", 3149, 3148, "term_cap", 3149, deep_elapsed_s=15.79),
]
FINDINGS = [{"kind": "depth_at_physical_cap", "evidence": {}, "suggest": [("gf_term_cap", "up")]}]


def _write_log(rows):
    O.ATTEMPT_LOG.parent.mkdir(parents=True, exist_ok=True)
    O.ATTEMPT_LOG.write_text(json.dumps({"attempts": rows}), encoding="utf-8")


def _setup(tmp_path, monkeypatch, rows, *, gf=3149, digits=11647, ds=16.0, evidence=None):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(SH, "eligible_target_ids",
                        lambda stall_state=None: {T} if "gf_terms" in O._CAP_OVERRIDES else set())
    _write_log(rows)
    st = _prime_zero()
    SH._apply_knob(st, "gf_term_cap", gf)
    SH._apply_knob(st, "deep_digits", digits)
    SH._apply_knob(st, "deep_seconds", ds)
    st["evidence"] = list(evidence if evidence is not None else [
        {"id": "ev_a", "event": "adopt", "knob": "gf_term_cap", "from": 2865, "to": 3149,
         "predicted_targets": [T]}])
    SH.save_state(st)
    return SH.load_state()


def _control(monkeypatch):
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: False)


# --- measured time model ------------------------------------------------------

def test_measured_series_time_is_used():
    log = {"attempts": AFTER_ADOPT}
    pts = C.time_points(T, log)
    assert pts[0] == (3149.0, 15.79, 1.0)  # newest first, no margin on measured rows
    assert 3149 < B.time_limit(T, 16.0, log) < 3175
    need = C.time_needed(T, "gf_term_cap", 4259, attempt_log=log)
    assert 35 < need < 45  # live measured 37.5 s at planned 4259
    # without measured rows the item-76 lower-bound rows still apply
    old = {"attempts": [_row("t", 3975, 75, "time_cap", 16.0)]}
    assert C.time_points(T, old) == [(3975.0, 16.0, C.TIME_FIT_MARGIN)]


# --- (2) time binds at the deep_seconds ceiling --------------------------------

def test_time_bound_at_ceiling_retires_target(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch, AFTER_ADOPT)
    assert B.retire_time_bound(st, [T], cycle_id="c") == [T]
    assert C.compute_bound(st, T)
    ev = [e for e in st["evidence"] if e["event"] == "target_retired"][-1]
    assert ev["reason"] == "compute_bound" and ev["detail"] == "time_cap_at_deep_seconds_ceiling"
    assert ev["knobs"] == {"deep_seconds": 16.0} and ev["authorized"] is False
    assert B.retire_time_bound(st, [T], cycle_id="c2") == []  # once
    assert C.refresh_compute_bound(st, "c3") == []  # ds cannot rise past its ceiling


def test_no_retire_below_ceiling_or_with_headroom(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch, AFTER_ADOPT, ds=12.4)
    assert B.retire_time_bound(st, [T], cycle_id="c") == []
    fast = DIGITS + [_row("a1", 3149, 3148, "term_cap", 3149, deep_elapsed_s=6.0)]
    st = _setup(tmp_path, monkeypatch, fast)
    assert B.retire_time_bound(st, [T], cycle_id="c") == []


def test_proposer_moves_on_after_retire(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch, AFTER_ADOPT)
    prop = SH.propose_trial(FINDINGS, state=st, cycle_id="c")
    assert prop is None or T not in (prop.get("predicted_targets") or [])
    assert C.compute_bound(st, T)


# --- (1) cobind gate in front of every cap trial -------------------------------

def test_negligible_single_raise_is_skipped(tmp_path, monkeypatch):
    # deep_seconds below the ceiling but on cooldown: no coupled form can open,
    # and a single gf raise is held by the digit cap near n ~ 3175.
    st = _setup(tmp_path, monkeypatch, AFTER_ADOPT, ds=15.9)
    st["knob_last_trial"] = {"deep_seconds": {"direction": "up", "cycle_index": st["cycle_index"]},
                             "deep_digits": {"direction": "up", "cycle_index": st["cycle_index"]}}
    gate = B.negligible_step(st, {"gf_term_cap": 4259}, [T])
    assert gate["skipped"] == "co_binding_caps" and gate["predicted_gain"][T] < B.negligible_gain(3148)
    prop = SH.propose_trial(FINDINGS, state=st, cycle_id="c")
    assert prop is None or prop["knob"] != "gf_term_cap"
    checked = (st.get("trial_skip") or {}).get("explore_checked") or []
    gf = [c for c in checked if c["knob"] == "gf_term_cap"]
    # skipped either by the cobind gate or, first, by the item-76 time-risk deferral
    assert gf and (gf[0].get("skipped") == "co_binding_caps"
                   or gf[0].get("deferred") == "time_risk_coupled_knob_on_cooldown")


def test_gate_skips_single_without_time_risk(tmp_path, monkeypatch):
    # No time evidence at all: only the digit cap co-binds (near n ~ 3175).
    rows = DIGITS + [_row("a1", 3149, 3148, "term_cap", 3149)]
    st = _setup(tmp_path, monkeypatch, rows, ds=12.4)
    st["knob_last_trial"] = {"deep_digits": {"direction": "up", "cycle_index": st["cycle_index"]}}
    prop = SH.propose_trial(FINDINGS, state=st, cycle_id="c")
    assert prop is None or prop["knob"] != "gf_term_cap"
    checked = (st.get("trial_skip") or {}).get("explore_checked") or []
    assert any(c.get("skipped") == "co_binding_caps" and c["knob"] == "gf_term_cap" for c in checked)


def test_step_with_real_gain_passes(tmp_path, monkeypatch):
    rows = DIGITS + [_row("a1", 2310, 2309, "term_cap", 2310, deep_elapsed_s=4.0)]
    st = _setup(tmp_path, monkeypatch, rows, gf=2310, digits=12000, ds=12.4)
    assert B.negligible_step(st, {"gf_term_cap": 2865}, [T]) is None
    prop = SH.propose_trial(FINDINGS, state=st, cycle_id="c")
    assert prop is not None and prop["knob"] == "gf_term_cap"


def test_unknown_target_never_blocks(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch, AFTER_ADOPT)
    assert B.negligible_step(st, {"gf_term_cap": 4259}, ["oc_UNKNOWN"]) is None
    assert B.negligible_step(st, {"park_cycles": 8}, [T]) is None


def test_gate_counts_toward_co_binding_streak(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch, AFTER_ADOPT)
    skipped = [{"knob": "gf_term_cap", "to": 4259, "predicted": [T], "skipped": "co_binding_caps"}]
    for i in range(B.ZERO_PREDICTION_STREAK - 1):
        B.note_zero_prediction_skip(st, f"s{i}", skipped)
    assert st["zero_prediction_skips"]["count"] == B.ZERO_PREDICTION_STREAK - 1


def test_item74_coupled_form_is_gated(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch, AFTER_ADOPT, ds=15.0)
    trial = {"knob": "gf_term_cap", "to": 4259, "predicted_targets": [T],
             "coupled": {"knob": "deep_seconds", "to": 16.0}}
    assert SH._cobind_gate(st, trial)["skipped"] == "co_binding_caps"


def test_control_arm_noop(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch, AFTER_ADOPT)
    _control(monkeypatch)
    assert B.negligible_step(st, {"gf_term_cap": 4259}, [T]) is None
    assert B.retire_time_bound(st, [T], cycle_id="c") == []
    assert not C.compute_bound(st, T)
