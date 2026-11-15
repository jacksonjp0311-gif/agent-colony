"""Item 76: a deep-check timeout never regresses depth; a term-cap raise
that the time cap would stop becomes a coupled trial; every predicted
target of an open trial is attempted in the trial window.

Hermetic: state, attempt log and reports live under tmp_path (conftest
live-state guard). Rows mirror the live A126089 shape (e.g.f. series, gf
2865 term cap, 12.4 s time cap). Gates unchanged: Oracle, P >= 0.70, the
150 cap, Wilson, the 6-cycle window, strictly better and the triviality
filter are not touched; authorize stays false; the control arm is a no-op.
"""
from __future__ import annotations

import json

import colony.arm as arm
import colony.oeis_conjectures as O
import colony.self_heal as SH
import colony.self_heal_coupled as C
from tests.test_exploratory_trials import _isolate, _prime_zero

EGF = {"kind": "egf", "expr": "(1-2*x)*sqrt(1-4*x)"}  # A126089's definition
T = "oc_GF"


def _terms(n):
    return O.extend(EGF, 0, [], n, seconds=60)


def _entry(stored=20, tested_hi=None):
    e = {"id": T, "anum": "A126089", "offset": 0, "terms": _terms(stored), "data_n": 10, "text": "rec",
         "published_hi": stored - 1, "definition": dict(EGF),
         "claim": {"form": "relation", "parts": ["(-n+4)*a(n)+2*(2*n-5)*(n-3)*a(n-1)", "0"],
                   "rels": ["="], "mod": None, "n0": None}}
    if tested_hi is not None:
        e["tested_hi"] = tested_hi
    return e


def _control(monkeypatch):
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: False)


def _write_log(rows):
    O.ATTEMPT_LOG.parent.mkdir(parents=True, exist_ok=True)
    O.ATTEMPT_LOG.write_text(json.dumps({"attempts": rows}), encoding="utf-8")


# --- (a) a timeout keeps the verified prefix --------------------------------

def test_extend_time_cap_keeps_prefix():
    full = _terms(80)
    info: dict = {}
    cut = O.extend(EGF, 0, full[:20], 120, seconds=0.0, info=info)
    assert len(cut) == 21 and info["cap_reason"] == "time_cap"  # the old drop
    info = {}
    kept = O.extend(EGF, 0, full[:20], 120, seconds=0.0, info=info, keep_hi=60)
    assert info["cap_reason"] == "time_cap"  # time still binds past the prefix
    assert len(kept) == 61 and kept == _terms(61)  # n = 0..60 kept
    assert info.get("elapsed_s") is not None


def test_attempt_disprove_timeout_keeps_prior_depth(monkeypatch):
    monkeypatch.setattr(O, "DEEP_SECONDS", 0.0)
    e = _entry()
    old = O.attempt_disprove(e, None, fetch=False)
    assert old["status"] == "holds_on_range" and old["range"][1] <= 20
    r = O.attempt_disprove(e, 60, fetch=False)
    assert r["status"] == "holds_on_range"
    assert r["range"][1] >= 60 and r["cap_reason"] == "time_cap"
    assert r["extended"] >= 0 and "deep_elapsed_s" in r


def test_attempt_disprove_reads_prior_from_entry(monkeypatch):
    monkeypatch.setattr(O, "DEEP_SECONDS", 0.0)
    r = O.attempt_disprove(_entry(tested_hi=50), None, fetch=False)
    assert r["range"][1] >= 50


def test_remember_attempt_floors_verified_depth_append_only():
    prior = {"id": T, "cycle_id": "c0", "planned": 2865, "verified_depth": 2864,
             "cap_reason": "term_cap", "cap_value": 2865}
    _write_log([dict(prior)])
    e = _entry(tested_hi=2864)
    timed_out = {"action": "attempt_disprove", "status": "holds_on_range", "range": [1, 75],
                 "deep_terms": 76, "cap_reason": "time_cap", "cap_value": 12.4}
    O.remember_attempt(e, [timed_out], "c1", planned=3975)
    rows = json.loads(O.ATTEMPT_LOG.read_text())["attempts"]
    assert rows[0] == prior  # earlier rows untouched (append-only)
    row = rows[-1]
    assert row["verified_depth"] == 2864 and row["depth"] == 2864
    assert row["attempt_verified_depth"] == 75 and row["verified_depth_floor"] == "prior_tested_hi"
    assert row["cap_reason"] == "time_cap" and row["planned"] == 3975 and row["extended"] == 0


def test_remember_attempt_does_not_floor_a_counterexample():
    _write_log([])
    bad = {"action": "attempt_disprove", "status": "counterexample_verified", "range": [1, 75]}
    O.remember_attempt(_entry(tested_hi=2864), [bad], "c1", planned=3975)
    row = json.loads(O.ATTEMPT_LOG.read_text())["attempts"][-1]
    assert row["verified_depth"] == 75 and "verified_depth_floor" not in row


def test_scoreboard_extension_never_moves_down():
    state = {"scoreboard": {"counterexamples": {}, "proofs": {}, "extensions": {
        T: {"anum": "A126089", "bfile_hi": 200, "to": 2864, "check": "exact"}}}}
    O._score(state, _entry(), [{"action": "attempt_disprove", "status": "holds_on_range",
                                "range": [1, 300], "bfile_hi": 200}])
    assert state["scoreboard"]["extensions"][T]["to"] == 2864


# --- (b) prefer a coupled trial when the time cap would bind ---------------

TERM_2865 = {"id": T, "status": "holds_on_range", "planned": 2865, "verified_depth": 2864,
             "cap_reason": "term_cap", "cap_value": 2865}
TIME_2588 = {"id": T, "status": "holds_on_range", "planned": 2588, "verified_depth": 75,
             "cap_reason": "time_cap", "cap_value": 8.0}
TIME_3975 = {"id": T, "status": "holds_on_range", "planned": 3975, "verified_depth": 2864,
             "attempt_verified_depth": 75, "cap_reason": "time_cap", "cap_value": 12.4}
FINDINGS = [{"kind": "depth_at_physical_cap", "evidence": {}, "suggest": [("gf_term_cap", "up")]}]


def _eligibility(monkeypatch):
    monkeypatch.setattr(SH, "eligible_target_ids",
                        lambda stall_state=None: {T} if "gf_terms" in O._CAP_OVERRIDES else set())


def _setup(tmp_path, monkeypatch, rows, *, evidence=(), gf=2865, ds=12.4):
    _isolate(tmp_path, monkeypatch)
    _eligibility(monkeypatch)
    _write_log(rows)
    st = _prime_zero()
    SH._apply_knob(st, "gf_term_cap", gf)
    SH._apply_knob(st, "deep_seconds", ds)
    st["evidence"] = list(evidence)
    SH.save_state(st)
    return SH.load_state()


def test_time_needed_and_fit():
    log = {"attempts": [dict(TIME_2588, cycle_id="a"), dict(TERM_2865, cycle_id="b")]}
    need = C.time_needed(T, "gf_term_cap", 3975, attempt_log=log)
    assert need > 16.0  # 8 s * (3975/2588)^3
    fit = C.fit_term_to_time(T, "gf_term_cap", 2865, 3975, 16.0, attempt_log=log)
    assert 2865 < fit < 3975
    assert C.time_needed(T, "gf_term_cap", fit, attempt_log=log) <= 16.0 * C.TIME_FIT_MARGIN + 1e-6
    # no time-capped row: no estimate, raise unchanged
    assert C.time_needed(T, "gf_term_cap", 3975, attempt_log={"attempts": [TERM_2865]}) is None
    # measured elapsed time is used when it is larger than the cap value
    log2 = {"attempts": [dict(TIME_3975, deep_elapsed_s=28.0)]}
    assert round(C.time_needed(T, "gf_term_cap", 3975, attempt_log=log2), 1) == 28.0


def test_single_term_raise_becomes_coupled(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch, [dict(TIME_2588, cycle_id="a"), dict(TERM_2865, cycle_id="b")])
    prop = SH.propose_trial(FINDINGS, state=st, cycle_id="c")
    assert prop is not None and prop["knob"] == "gf_term_cap" and prop["from"] == 2865
    assert prop["coupled"]["knob"] == "deep_seconds" and prop["coupled"]["from"] == 12.4
    assert prop["coupled"]["to"] > 12.4 and prop["coupled"]["to"] <= SH.KNOB_SPECS["deep_seconds"].hi
    assert prop["predicted_targets"] == [T] and prop["exploratory"] is True
    assert prop["coupled_time_risk"]["target"] == T
    assert prop["window"] == 6 and prop["authorized"] is False
    st = SH.start_trial(prop, state=st, cycle_id="c")
    assert st["knobs"]["deep_seconds"] == prop["coupled"]["to"]
    assert st["knobs"]["gf_term_cap"] == prop["to"]


def test_no_time_risk_keeps_single_raise(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch, [dict(TERM_2865, cycle_id="b")])
    prop = SH.propose_trial(FINDINGS, state=st, cycle_id="c")
    assert prop is not None and "coupled" not in prop


def test_time_risk_with_deep_seconds_on_cooldown_defers(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch, [dict(TIME_2588, cycle_id="a"), dict(TERM_2865, cycle_id="b")])
    st["knob_last_trial"] = {"deep_seconds": {"direction": "up", "cycle_index": st["cycle_index"]}}
    prop = SH.propose_trial(FINDINGS, state=st, cycle_id="c")
    assert prop is None or prop["knob"] != "gf_term_cap"


def _failed_gf_3975():
    return {"id": "ev_gf3975", "event": "trial_inconclusive", "knob": "gf_term_cap", "from": 3975,
            "to": 2865, "exploratory": True, "predicted_targets": [T], "started_cycle": "t0",
            "trial_metrics": [{"cycle_id": "t1"}]}


def test_timeout_follow_up_is_coupled_despite_term_cooldown(tmp_path, monkeypatch):
    rows = [dict(TIME_2588, cycle_id="a"), dict(TERM_2865, cycle_id="b"), dict(TIME_3975, cycle_id="t0"),
            dict(TERM_2865, cycle_id="t2")]
    st = _setup(tmp_path, monkeypatch, rows, evidence=[_failed_gf_3975()])
    # the failed single-knob trial just closed: gf_term_cap is on cooldown
    st["knob_last_trial"] = {"gf_term_cap": {"direction": "up", "cycle_index": st["cycle_index"],
                                             "closed_index": st["cycle_index"]}}
    prop = SH.propose_trial(FINDINGS, state=st, cycle_id="c")
    assert prop is not None and prop["knob"] == "gf_term_cap"
    assert prop["coupled"]["knob"] == "deep_seconds" and prop["coupled"]["to"] > 12.4
    assert 2865 < prop["to"] <= 3975
    assert prop["predicted_targets"] == [T]


def test_time_risk_control_arm_noop(tmp_path, monkeypatch):
    st = _setup(tmp_path, monkeypatch, [dict(TIME_2588, cycle_id="a"), dict(TERM_2865, cycle_id="b")])
    _control(monkeypatch)
    assert C.time_risk_coupled(st, "gf_term_cap", 2865, 3975, [T]) is None
    assert SH.propose_trial(FINDINGS, state=st, cycle_id="c") is None


# --- (c) every predicted target is attempted in the trial window -----------

def _open_trial(tmp_path, monkeypatch, rows, metrics=("w1",)):
    _isolate(tmp_path, monkeypatch)
    _write_log(rows)
    st = _prime_zero()
    st["trial"] = {"knob": "gf_term_cap", "from": 2865, "to": 3148, "predicted_targets": [T],
                   "started_cycle": "s0", "trial_metrics": [{"cycle_id": c} for c in metrics],
                   "authorized": False}
    SH.save_state(st)
    return SH.load_state()


def test_untried_predicted_target_is_scheduled(tmp_path, monkeypatch):
    st = _open_trial(tmp_path, monkeypatch, [dict(TIME_3975, cycle_id="s0")])
    # the start-cycle attempt does not count as a retry in the window
    assert SH.trial_targets_to_retry(st, "w1") == [T]
    assert SH.trial_targets_to_retry(st, "s0") == []


def test_attempted_target_is_not_rescheduled(tmp_path, monkeypatch):
    st = _open_trial(tmp_path, monkeypatch, [dict(TERM_2865, cycle_id="w1")], metrics=("w1", "w2"))
    assert SH.trial_targets_to_retry(st, "w2") == []


def test_retry_runs_once_and_records_evidence(tmp_path, monkeypatch):
    st = _open_trial(tmp_path, monkeypatch, [])
    calls = []

    def runner(cid, tids):
        calls.append((cid, list(tids)))
        rows = json.loads(O.ATTEMPT_LOG.read_text())["attempts"]
        rows.append(dict(TERM_2865, cycle_id=cid))
        _write_log(rows)
        return {"chosen": [{"id": t} for t in tids]}

    out = SH.retry_trial_targets("w1", state=st, runner=runner)
    assert calls == [("w1", [T])] and out["retried"] == [T]
    assert out["authorized"] is False and out["applied_to_live_oracle"] is False
    ev = SH.load_state()["evidence"][-1]
    assert ev["event"] == "trial_target_retry" and ev["targets"] == [T] and ev["authorized"] is False
    # attempted now: the next cycle does not retry again
    st = SH.load_state()
    st["trial"]["trial_metrics"].append({"cycle_id": "w2"})
    assert SH.retry_trial_targets("w2", state=st, runner=runner)["retried"] == []
    assert len(calls) == 1


def test_no_trial_or_control_arm_no_retry(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert SH.trial_targets_to_retry(_prime_zero(), "w1") == []
    st = _open_trial(tmp_path, monkeypatch, [])
    _control(monkeypatch)
    assert SH.trial_targets_to_retry(st, "w1") == []
    assert SH.retry_trial_targets("w1", state=st, runner=lambda *a: 1 / 0)["retried"] == []


def test_run_cycle_only_ids_attempts_exactly_those(tmp_path, monkeypatch):
    monkeypatch.setattr(O, "REPORT", tmp_path / "report.json")
    monkeypatch.setattr(O, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(O, "mode", lambda: "shadow")
    other = dict(_entry(), id="oc_OTHER")
    monkeypatch.setattr(O, "load_menu", lambda: [other, _entry()])
    seen = []

    def fake(e, prior_hi=None, fetch=True):
        seen.append(e["id"])
        return {"action": "attempt_disprove", "id": e["id"], "anum": e["anum"], "status": "holds_on_range",
                "range": [1, 19], "bfile_hi": 19, "data_hi": 9, "tested": 19, "deep_terms": 20}
    monkeypatch.setattr(O, "attempt_disprove", fake)
    _write_log([])
    rep = O.run_cycle("w1", fetch=False, beyond_bfile=True, only_ids=[T], purpose="trial_predicted_retry")
    assert seen == [T] and [c["id"] for c in rep["chosen"]] == [T]
    assert rep["purpose"] == "trial_predicted_retry"
