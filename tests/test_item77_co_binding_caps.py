"""Item 77: co-binding caps (term cap + deep_digits [+ deep_seconds]).

Rows mirror the live A126089 shape at 4:20 PM ET Nov 15: depth 2864 held by
gf_term_cap 2865 and the 10400-digit cap together (digit rows at
1853/6350, 2200/7700, 2540/9050), with time caps recorded at planned 2588
and 3975. Hermetic: state and attempt log under tmp_path. Gates unchanged
(Oracle, P >= 0.70, 150 cap, Wilson, 6-cycle window, strictly better,
triviality filter, Athanor); authorize false; control arm a no-op.
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
         "verified_depth": verified, "cap_reason": reason, "cap_value": value}
    r.update(kw)
    return r


ROWS = [
    _row("d1", 2310, 1853, "digit_cap", 6350),
    _row("d2", 2310, 2200, "digit_cap", 7700),
    _row("t1", 2588, 75, "time_cap", 8.0),
    _row("d3", 2865, 2540, "digit_cap", 9050),
    _row("g1", 2865, 2864, "term_cap", 2865),
    _row("t2", 3975, 75, "time_cap", 12.4),
    _row("t3", 3975, 75, "time_cap", 16.0),
]
FINDINGS = [{"kind": "depth_at_physical_cap", "evidence": {},
             "suggest": [("gf_term_cap", "up"), ("deep_digits", "up"), ("deep_seconds", "up")]}]


def _write_log(rows):
    O.ATTEMPT_LOG.parent.mkdir(parents=True, exist_ok=True)
    O.ATTEMPT_LOG.write_text(json.dumps({"attempts": rows}), encoding="utf-8")


def _recent_trial_evidence():
    return [{"id": "ev_v", "event": "trial_voided_confound", "knob": "gf_term_cap", "from": 3975, "to": 2865,
             "predicted_targets": [T]},
            {"id": "ev_s", "event": "trial_start", "knob": "gf_term_cap", "from": 2865, "to": 3975,
             "predicted_targets": [T]}]


def _eligible():
    return {T} if "gf_terms" in O._CAP_OVERRIDES else set()


def _setup(tmp_path, monkeypatch, rows=ROWS, evidence=None):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(SH, "eligible_target_ids", lambda stall_state=None: _eligible())
    _write_log(rows)
    st = _prime_zero()
    SH._apply_knob(st, "gf_term_cap", 2865)
    SH._apply_knob(st, "deep_digits", 10400)
    SH._apply_knob(st, "deep_seconds", 12.4)
    st["evidence"] = list(_recent_trial_evidence() if evidence is None else evidence)
    SH.save_state(st)
    return SH.load_state()


def _control(monkeypatch):
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: False)


# --- why the item-76 dry run did not open ------------------------------------

def _entry():
    return {"id": T, "anum": "A126089", "offset": 0, "terms": list(range(1, 76)), "published_hi": 200,
            "definition": {"kind": "egf", "expr": "(1-2*x)*sqrt(1-4*x)"}, "tested_hi": 2864,
            "claim": {"form": "relation", "parts": ["a(n)", "0"], "rels": ["="], "mod": None, "n0": None}}


def test_deeper_plan_time_cap_does_not_close_target(monkeypatch):
    monkeypatch.setattr(O, "claim_testable_hi", lambda e: 20000)
    e = _entry()
    log = {"attempts": [_row("g1", 2865, 2864, "term_cap", 2865), _row("t3", 3975, 75, "time_cap", 16.0)]}
    with O.cap_override("gf_term_cap", 3149):
        # Old rule: reachable = 75 from the 3975 row, so never eligible (ds at its 16 s ceiling).
        assert O.can_progress_past(e, 2864, log) is True
    with O.cap_override("gf_term_cap", 3975):
        assert O.can_progress_past(e, 2864, log) is False  # same plan, same time cap: still closed


# --- (2) digit-growth model ----------------------------------------------------

def test_digit_model_from_recent_rows():
    log = {"attempts": ROWS}
    m = B.digit_model(T, log)
    assert [p[0] for p in m.pts] == [1853, 2200, 2540]
    assert 3.9 < m.slope < 4.2
    assert 2860 < m.n_at(10400) < 2890  # live: the 10400-digit cap binds near n = 2875
    assert m.digits_at(3148) > m.digits_at(2864) > 10000
    one = B.DigitModel([(2540.0, 9050.0)])
    assert abs(one.n_at(10400) - 10400 / (9050 / 2540)) < 1e-6
    assert B.digit_model(T, {"attempts": [ROWS[4]]}) is None


def test_simulate_singles_negligible_triple_wins(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch)
    sim = B.simulate(st, T)
    assert sim["depth"] == 2864
    assert set(sim["binding_now"]) >= {"term_cap", "digit_cap"}
    bar = B.negligible_gain(2864)
    singles = [c for c in sim["candidates"] if len(c["knobs"]) == 1]
    assert singles and all(c["gain"] < bar for c in singles)
    best = max(sim["candidates"], key=lambda c: c["gain"])
    assert set(best["knobs"]) == {"gf_term_cap", "deep_digits", "deep_seconds"}
    assert best["gain"] > 200
    v = best["values"]
    assert v["deep_seconds"] <= SH.KNOB_SPECS["deep_seconds"].hi
    assert v["deep_digits"] <= SH.KNOB_SPECS["deep_digits"].hi
    assert 2865 < v["gf_term_cap"] < 3975  # narrowed to fit the 16 s ceiling


# --- (1) one coupled trial over co-binding caps --------------------------------

def test_proposal_is_one_triple_trial(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch)
    prop = SH.propose_trial(FINDINGS, state=st, cycle_id="c")
    assert prop is not None and prop["knob"] == "gf_term_cap" and prop["from"] == 2865
    assert prop["coupled"]["knob"] == "deep_digits" and prop["coupled"]["to"] > 10400
    assert [c["knob"] for c in prop["coupled_more"]] == ["deep_seconds"]
    assert prop["coupled_more"][0]["to"] <= 16.0
    assert prop["predicted_targets"] == [T] and prop["exploratory"] is True
    assert prop["cobind"]["predicted_gain"] > prop["cobind"]["best_single_gain"]
    assert prop["window"] == 6 and prop["authorized"] is False
    st = SH.start_trial(prop, state=st, cycle_id="c")
    k = st["knobs"]
    assert k["gf_term_cap"] == prop["to"] and k["deep_digits"] == prop["coupled"]["to"]
    assert k["deep_seconds"] == prop["coupled_more"][0]["to"]
    start = [e for e in st["evidence"] if e["event"] == "trial_start"][-1]
    assert start["coupled_more"][0]["knob"] == "deep_seconds" and start["cobind"]["target"] == T
    assert SH.trial_fingerprint_mismatch(st["trial"], state=st)[0] is False
    for knob in ("gf_term_cap", "deep_digits", "deep_seconds"):
        assert SH._knob_on_cooldown(st, knob, "up")
    assert SH.propose_trial(FINDINGS, state=st, cycle_id="c2") is None  # single slot


def test_not_adopted_reverts_all_together_and_retires(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch)
    prop = SH.propose_trial(FINDINGS, state=st, cycle_id="c")
    st = SH.start_trial(prop, state=st, cycle_id="c")
    st = SH._close_trial(st, "c6", "inconclusive", reason="no_signal")
    k = st["knobs"]
    assert (k["gf_term_cap"], k["deep_digits"], k["deep_seconds"]) == (2865, 10400, 12.4)
    assert C.compute_bound(st, T)
    ret = [e for e in st["evidence"] if e["event"] == "target_retired"][-1]
    assert set(ret["knobs"]) == {"gf_term_cap", "deep_digits", "deep_seconds"}
    assert st["knob_last_trial"]["deep_seconds"].get("closed_index") is not None


def test_void_reverts_all_together(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch)
    st = SH.start_trial(SH.propose_trial(FINDINGS, state=st, cycle_id="c"), state=st, cycle_id="c")
    st = SH.void_trial_for_confound(st, "c2", old_fingerprint="a", new_fingerprint="b")
    k = st["knobs"]
    assert (k["gf_term_cap"], k["deep_digits"], k["deep_seconds"]) == (2865, 10400, 12.4)
    assert st["evidence"][-1]["coupled_more"][0]["knob"] == "deep_seconds"


def test_adopt_keeps_all(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch)
    prop = SH.propose_trial(FINDINGS, state=st, cycle_id="c")
    st = SH.start_trial(prop, state=st, cycle_id="c")
    import colony.self_heal_score as SS
    monkeypatch.setattr(SS, "refresh_trial_scores", lambda trial: None)
    st["trial"]["predicted_depth_gain"] = 284
    st = SH._close_trial(st, "c6", "adopt")
    assert st["evidence"][-1]["event"] == "adopt"
    assert st["knobs"]["deep_digits"] == prop["coupled"]["to"]
    assert st["knobs"]["deep_seconds"] == prop["coupled_more"][0]["to"]


def test_retired_or_cooldown_knob_left_out(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch)
    st["retired_cap_knobs"] = {"deep_seconds": {"value": 16.0, "ceiling": 16.0}}
    sim = B.simulate(st, T)
    assert all("deep_seconds" not in c["knobs"] for c in sim["candidates"])
    st = _setup(tmp_path, monkeypatch)
    st["knob_last_trial"] = {"deep_digits": {"direction": "up", "cycle_index": st["cycle_index"]}}
    assert all("deep_digits" not in c["knobs"] for c in B.simulate(st, T)["candidates"])


def test_failed_combo_not_repeated(tmp_path, monkeypatch):
    failed = {"event": "trial_inconclusive", "knob": "gf_term_cap", "from": 3149, "to": 2865,
              "predicted_targets": [T], "coupled": {"knob": "deep_digits"},
              "coupled_more": [{"knob": "deep_seconds"}]}
    st = _setup(tmp_path, monkeypatch, evidence=_recent_trial_evidence() + [failed])
    prop = B.cobind_proposal(st, [T], eligible=_eligible)
    assert prop is None or set([prop["knob"], prop["coupled"]["knob"]]
                               + [c["knob"] for c in prop.get("coupled_more") or []]) != \
        {"gf_term_cap", "deep_digits", "deep_seconds"}


def test_no_digit_evidence_leaves_items_74_76(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch, rows=[r for r in ROWS if r["cap_reason"] != "digit_cap"])
    assert B.cobind_proposal(st, [T], eligible=_eligible) is None


def test_single_with_real_gain_not_replaced(tmp_path, monkeypatch):
    # digits far from binding: a plain gf raise already gains a lot
    rows = [_row("d1", 2310, 1853, "digit_cap", 6350), _row("g1", 2310, 2309, "term_cap", 2310)]
    st = _setup(tmp_path, monkeypatch, rows=rows)
    SH._apply_knob(st, "gf_term_cap", 2310)
    SH._apply_knob(st, "deep_digits", 12000)
    assert B.cobind_proposal(st, [T], eligible=_eligible) is None


def test_ineligible_under_override_no_proposal(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch)
    assert B.cobind_proposal(st, [T], eligible=lambda: set()) is None


def test_control_arm_noop(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch)
    _control(monkeypatch)
    assert B.cobind_proposal(st, [T], eligible=_eligible) is None
    assert B.note_zero_prediction_skip(st, "c", [{"knob": "gf_term_cap", "predicted": []}]) is None
    assert SH.propose_trial(FINDINGS, state=st, cycle_id="c") is None


# --- (3) co_binding_caps finding --------------------------------------------

def test_co_binding_finding_after_six_zero_skips(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch)
    zero = [{"knob": "gf_term_cap", "to": 3975, "predicted": []},
            {"knob": "deep_digits", "to": 11750, "predicted": []}]
    for i in range(5):
        assert B.note_zero_prediction_skip(st, f"s{i}", zero) is None
    ev = B.note_zero_prediction_skip(st, "s5", zero)
    assert ev["event"] == "finding" and ev["kind"] == "co_binding_caps"
    assert ev["zero_prediction_skips"] == 6 and ev["authorized"] is False
    tgt = ev["targets"][0]
    assert tgt["target"] == T and {"term_cap", "digit_cap"} <= set(tgt["binding_caps"])
    n = len(st["evidence"])
    assert B.note_zero_prediction_skip(st, "s6", zero) is None  # once per streak
    assert len(st["evidence"]) == n
    # a candidate with a prediction resets the streak
    B.note_zero_prediction_skip(st, "s7", [{"knob": "gf_term_cap", "predicted": [T]}])
    assert st["zero_prediction_skips"]["count"] == 0
    jsonl = SH.EVENT_LOG.read_text().splitlines()
    assert any('"co_binding_caps"' in ln for ln in jsonl)  # append-only event log


def test_skip_path_counts_zero_predictions(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(B, "cobind_proposal", lambda *a, **k: None)
    monkeypatch.setattr(SH, "eligible_target_ids", lambda stall_state=None: set())
    for i in range(6):
        SH.propose_trial(FINDINGS, state=st, cycle_id=f"s{i}")
        st["cycle_index"] = int(st.get("cycle_index") or 0) + 1
    assert st["trial_skip"]["reason"] == "no_signal_baseline"
    assert st["zero_prediction_skips"]["count"] >= 6
    assert st.get("co_binding_caps", {}).get("targets")
