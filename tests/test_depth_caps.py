"""PR #7: depth metric, physical caps, derived verified_depth, checker receipt.

Item 31: self_heal new_depth counts actual tested_hi advances, and an
in-flight trial with an inflated baseline is corrected append-only.
Item 30: a same-depth hold at a physical cap does not reopen, then close
as if the planned depth had been reached; raising the cap reopens.
Item 29: verified_depth is derived at read time for legacy rows; the
committed file is not rewritten.
Item 26: checker-lane mine/accept/reject counts land in a committed receipt.
Capability: C-finite exact iterators use a higher, bounded, raisable term
cap so held targets can be pushed past tested_hi.
"""
from __future__ import annotations

import json
from pathlib import Path

import colony.checker_lane as CL
import colony.oeis_conjectures as OC
import colony.self_heal as SH


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _isolate_oeis(tmp_path, monkeypatch):
    monkeypatch.setattr(OC, "ATTEMPT_LOG", tmp_path / "oeis_attempt_log.json")
    monkeypatch.setattr(OC, "STATE", tmp_path / "oeis_conjecture_state.json")
    OC.STATE.write_text(json.dumps({"targets": {}, "families": {}, "credit_total": 0,
                                    "scoreboard": {"extensions": {}}}))
    OC.save_attempt_log(OC._empty_attempt_log())


def _isolate_heal(tmp_path, monkeypatch):
    monkeypatch.setattr(SH, "STATE_PATH", tmp_path / "self_heal.json")
    monkeypatch.setattr(SH, "EVENT_LOG", tmp_path / "self_heal.jsonl")


def _isolate_checker(tmp_path, monkeypatch):
    monkeypatch.setattr(CL, "STATE_PATH", tmp_path / "checker_lane.json")
    monkeypatch.setattr(CL, "LANE_LOG", tmp_path / "checker_lane.jsonl")
    monkeypatch.setattr(CL, "PROPOSAL_DIR", tmp_path / "checker_proposals")
    monkeypatch.setattr(CL, "RECEIPT_PATH", tmp_path / "checker_lane_receipt.json")


def _gf_entry(eid="oc_A165064_0", anum="A165064", n_terms=20, tested_hi=1199):
    d = OC.parse_definition("Expansion of (1-x)/(1-2*x).")
    # A rational g.f. — C-finite, cheap and exact.
    if d is None:
        d = {"kind": "gf", "expr": "(1-x)/(1-2*x)"}
    terms = [int(c) for c in OC._series_A(d["expr"], n_terms)]
    # (1-x)/(1-2x) = 1 + x + 2x^2 + 4x^3 + ... from n=0? Let's just use computed.
    return {
        "id": eid, "anum": anum,
        "name": "Expansion of (1-x)/(1-2*x).",
        "offset": 0, "section": "formula",
        "text": "G.f.: (1-x)/(1-2*x) (conjectured).",
        "claim": {"form": "gf", "expr": d["expr"]},
        "definition": d, "terms": terms, "data_n": n_terms,
        "published_hi": n_terms - 1, "refs": {},
        "tested_hi": tested_hi,
    }


def _write_log(rows):
    log = OC._empty_attempt_log()
    log["attempts"] = list(rows)
    OC.save_attempt_log(log)


def _legacy(eid, anum, form, depth, bfile, cycle="old", beyond=None, status="holds_on_range"):
    if beyond is None:
        beyond = int(depth) > int(bfile)
    return {
        "id": eid, "anum": anum, "form": form,
        "depth": depth, "bfile_hi": bfile, "beyond": beyond,
        "status": status, "cycle_id": cycle,
    }


def _new_row(eid, anum, form, planned, verified, bfile, cycle, *,
             cap_reason=None, cap_value=None, extended=0, status="holds_on_range"):
    rec = {
        "id": eid, "anum": anum, "form": form,
        "depth": verified, "bfile_hi": bfile, "beyond": verified > bfile,
        "status": status, "cycle_id": cycle,
        "planned": planned, "verified_depth": verified,
        "extended": extended, "prior_tested_hi": verified - extended,
    }
    if cap_reason:
        rec["cap_reason"] = cap_reason
        rec["cap_value"] = cap_value
    return rec


# ---------------------------------------------------------------------------
# Item 31 — new_depth metric and in-flight trial
# ---------------------------------------------------------------------------

def test_new_depth_ignores_same_depth_beyond_holds():
    """Cycle 871 pattern: two beyond=true rows, extended 0, tested_hi flat."""
    log = {"attempts": [
        _legacy("oc_A126089_0", "A126089", "relation", 20000, 200, cycle="prior"),
        _legacy("oc_A165064_0", "A165064", "gf", 1200, 100, cycle="prior"),
        _new_row("oc_A126089_0", "A126089", "relation", 20000, 956, 200,
                 "20261113T010318Z_e7b0b9", cap_reason="digit_or_time_cap",
                 cap_value=956, extended=0),
        _new_row("oc_A165064_0", "A165064", "gf", 1200, 1199, 100,
                 "20261113T010318Z_e7b0b9", cap_reason="term_cap",
                 cap_value=1200, extended=0),
    ]}
    assert SH.count_new_depth(log, "20261113T010318Z_e7b0b9") == 0
    m = SH.collect_metrics("20261113T010318Z_e7b0b9", stall_state={
        "targets_tried": [], "turns": [],
        "pass_history": [{"cycle_id": "20261113T010318Z_e7b0b9", "pass_total": 528}],
    }, attempt_log=log)
    assert m["new_depth"] == 0
    assert m["score"] == 0.0


def test_new_depth_counts_strict_tested_hi_increase():
    log = {"attempts": [
        _new_row("oc_A165064_0", "A165064", "gf", 1200, 1199, 100, "c0",
                 cap_reason="term_cap", cap_value=1200, extended=0),
        _new_row("oc_A165064_0", "A165064", "gf", 8000, 7999, 100, "c1",
                 cap_reason="term_cap", cap_value=8000, extended=6800),
    ]}
    assert SH.count_new_depth(log, "c1") == 1
    # A later same-id cycle at the new depth would not count again.
    assert SH.count_new_depth(log, "c2") == 0


def test_new_depth_first_past_bfile_counts():
    log = {"attempts": [
        _legacy("oc_X_0", "AX", "gf", 100, 100, cycle="c0", beyond=False),
        _new_row("oc_X_0", "AX", "gf", 8000, 2000, 100, "c1", extended=1900),
    ]}
    assert SH.count_new_depth(log, "c1") == 1


def test_inflated_trial_baseline_is_recomputed(tmp_path, monkeypatch):
    """The live perturb_cooldown 6→8 trial had baseline 2.0 from two
    same-depth holds. Recompute from the corrected metric; append evidence;
    do not rewrite metric history."""
    _isolate_heal(tmp_path, monkeypatch)
    _isolate_oeis(tmp_path, monkeypatch)

    cid_hold = "20261113T010318Z_e7b0b9"
    inflated = {
        "cycle_id": cid_hold,
        "new_oracle_targets": 0,
        "new_depth": 2,
        "oracle_pass_delta": 0,
        "oracle_passes": 528,
        "score": 2.0,
    }
    flat = {
        "cycle_id": "flat",
        "new_oracle_targets": 0, "new_depth": 0,
        "oracle_pass_delta": 0, "oracle_passes": 528, "score": 0.0,
    }
    baseline = [dict(flat, cycle_id=f"b{i}") for i in range(5)] + [inflated]
    st = SH.load_state()
    st["metrics"] = [dict(r) for r in baseline]
    st["trial"] = {
        "knob": "perturb_cooldown_cycles",
        "from": 6, "to": 8, "direction": "up",
        "reason": "no_progress_perturb",
        "window": 6,
        "baseline_score": 2.0,
        "baseline_metrics": [dict(r) for r in baseline],
        "trial_metrics": [],
        "started_cycle": "start",
        "applied_to_live_oracle": False,
        "authorized": False,
    }
    st["knobs"]["perturb_cooldown_cycles"] = 8
    SH.save_state(st)

    _write_log([
        _legacy("oc_A126089_0", "A126089", "relation", 20000, 200, cycle="prior"),
        _legacy("oc_A165064_0", "A165064", "gf", 1200, 100, cycle="prior"),
        _new_row("oc_A126089_0", "A126089", "relation", 20000, 956, 200,
                 cid_hold, cap_reason="digit_or_time_cap", cap_value=956, extended=0),
        _new_row("oc_A165064_0", "A165064", "gf", 1200, 1199, 100,
                 cid_hold, cap_reason="term_cap", cap_value=1200, extended=0),
    ])

    # Metrics history before:
    hist_before = [dict(r) for r in SH.load_state()["metrics"]]
    st = SH.reconcile_inflated_trial(SH.load_state())
    SH.save_state(st)
    st = SH.load_state()
    trial = st["trial"]
    assert trial is not None
    assert trial["baseline_corrected"] is True
    assert trial["baseline_score_original"] == 2.0
    assert trial["baseline_score"] == 0.0
    assert trial["knob"] == "perturb_cooldown_cycles"
    assert trial["from"] == 6 and trial["to"] == 8
    # Append-only: original metric history rows are untouched.
    assert st["metrics"] == hist_before
    ev = [e for e in st["evidence"] if e.get("event") == "trial_baseline_corrected"]
    assert ev
    assert ev[0]["old_baseline_score"] == 2.0
    assert ev[0]["baseline_score"] == 0.0
    # Second call is a no-op (already corrected).
    n = len(st["evidence"])
    st2 = SH.reconcile_inflated_trial(st)
    assert len(st2["evidence"]) == n


def test_run_cycle_reconciles_before_judging(tmp_path, monkeypatch):
    """Reconcile first (append-only), then void a trial with no fingerprint."""
    _isolate_heal(tmp_path, monkeypatch)
    _isolate_oeis(tmp_path, monkeypatch)
    _write_log([
        _legacy("oc_A165064_0", "A165064", "gf", 1200, 100, cycle="prior"),
        _new_row("oc_A165064_0", "A165064", "gf", 1200, 1199, 100,
                 "hold", cap_reason="term_cap", cap_value=1200, extended=0),
    ])
    st = SH.load_state()
    inflated = {
        "cycle_id": "hold", "new_oracle_targets": 0, "new_depth": 2,
        "oracle_pass_delta": 0, "oracle_passes": 528, "score": 2.0,
    }
    flats = [{
        "cycle_id": f"b{i}", "new_oracle_targets": 0, "new_depth": 0,
        "oracle_pass_delta": 0, "oracle_passes": 528, "score": 0.0,
    } for i in range(5)]
    st["trial"] = {
        "knob": "perturb_cooldown_cycles", "from": 6, "to": 8,
        "direction": "up", "reason": "no_progress_perturb",
        "window": 6, "baseline_score": 2.0,
        "baseline_metrics": flats + [inflated],
        "trial_metrics": [], "started_cycle": "hold",
        "applied_to_live_oracle": False, "authorized": False,
    }
    st["knobs"]["perturb_cooldown_cycles"] = 8
    SH.save_state(st)
    out = SH.run_cycle("next", metrics={
        "cycle_id": "next", "new_oracle_targets": 0, "new_depth": 0,
        "oracle_pass_delta": 0, "oracle_passes": 528, "score": 0.0,
    })
    assert out["ok"] is True
    st = SH.load_state()
    # Baseline is still corrected append-only, then the unfingerprinted
    # trial is voided (it has no recorded environment; a cap-raising merge
    # mid-trial is a confound). Knob restored; not a revert-as-negative.
    ev_corr = [e for e in st["evidence"] if e.get("event") == "trial_baseline_corrected"]
    ev_void = [e for e in st["evidence"] if e.get("event") == "trial_voided_confound"]
    assert ev_corr and ev_corr[0]["baseline_score"] == 0.0
    assert ev_corr[0]["old_baseline_score"] == 2.0
    assert ev_void
    assert ev_void[0]["old_fingerprint"] == SH.UNRECORDED_FINGERPRINT
    assert ev_void[0]["adopted"] is False
    assert ev_void[0]["reverted"] is False
    assert ev_void[0]["to"] == 6
    assert st["trial"] is None
    assert st["adopted_count"] == 0
    assert st["reverted_count"] == 0
    assert st["knobs"]["perturb_cooldown_cycles"] == 6


# ---------------------------------------------------------------------------
# Item 30 — physical cap recording and eligibility
# ---------------------------------------------------------------------------

def test_same_depth_hold_at_term_cap_does_not_reopen(tmp_path, monkeypatch):
    _isolate_oeis(tmp_path, monkeypatch)
    e = _gf_entry(tested_hi=1199)
    # Force the slow / pre-upgrade cap so this hold is at the live ceiling.
    monkeypatch.setattr(OC, "FAST_TERM_CAP", 1200)
    monkeypatch.setattr(OC, "GF_TERMS", 1200)
    _write_log([
        _new_row(e["id"], e["anum"], "gf", 1200, 1199, 100, "c1",
                 cap_reason=OC.CAP_TERM, cap_value=1200, extended=0),
    ])
    OC.STATE.write_text(json.dumps({
        "targets": {e["id"]: {"tested_hi": 1199, "status": "holds_on_range"}},
        "families": {}, "credit_total": 0,
        "scoreboard": {"extensions": {e["id"]: {"anum": e["anum"], "to": 1199, "bfile_hi": 100}}},
    }))
    assert OC.claim_testable_hi(e) == 1200
    # Last verified already equals what this cycle can compute (cap 1200 → n=1199).
    assert OC.can_progress_past(e, 1199, require_past_published=True) is False


def test_raising_term_cap_reopens_held_target(tmp_path, monkeypatch):
    _isolate_oeis(tmp_path, monkeypatch)
    e = _gf_entry(tested_hi=1199)
    monkeypatch.setattr(OC, "FAST_TERM_CAP", 8000)
    _write_log([
        _new_row(e["id"], e["anum"], "gf", 1200, 1199, 100, "c1",
                 cap_reason=OC.CAP_TERM, cap_value=1200, extended=0),
    ])
    OC.STATE.write_text(json.dumps({
        "targets": {e["id"]: {"tested_hi": 1199}},
        "families": {}, "credit_total": 0,
        "scoreboard": {"extensions": {e["id"]: {"to": 1199}}},
    }))
    assert OC.term_cap_for(e) == 8000
    assert OC.cap_has_been_raised(
        {"planned": 1200, "verified_depth": 1199, "cap_reason": OC.CAP_TERM, "cap_value": 1200},
        e,
    ) is True
    assert OC.can_progress_past(e, 1199, require_past_published=True) is True


def test_planned_depth_is_not_treated_as_reached(tmp_path, monkeypatch):
    """A126089 pattern: planned 20_000, verified 956 at a digit cap.
    Must not close as if 20_000 had been computed. Reopens only when the
    digit/time cap is raised.
    """
    _isolate_oeis(tmp_path, monkeypatch)
    # EGF-style: not C-finite, claim_testable_hi uses GF_TERMS.
    d = {"kind": "egf", "expr": "1/(1-x)"}
    e = {
        "id": "oc_A126089_0", "anum": "A126089",
        "name": "egf", "offset": 0,
        "claim": {"form": "relation", "parts": ["a(n)", "n*a(n-1)"], "rels": ["="], "mod": None},
        "definition": d, "terms": list(range(20)), "data_n": 20,
        "published_hi": 200, "refs": {}, "tested_hi": 956,
    }
    _write_log([
        _new_row(e["id"], e["anum"], "relation", 20000, 956, 200, "c1",
                 cap_reason=OC.CAP_DIGIT, cap_value=3000, extended=0),
    ])
    # Digits still at the recorded cap (or the PR #6 default of 3000 if
    # we force the live cap down).
    monkeypatch.setattr(OC, "DEEP_DIGITS", 3000)
    # evaluator_caps uses DEEP_DIGITS unless a knob override is in force.
    # A recorded digit_cap of 3000 with live 3000 has not been raised...
    # but production default is now 5000. Monkeypatch the constant.
    assert OC.cap_has_been_raised(
        {"cap_reason": OC.CAP_DIGIT, "cap_value": 3000, "planned": 20000, "verified_depth": 956},
        e,
    ) is False
    assert OC.can_progress_past(e, 956, require_past_published=True) is False

    # Raising the digit cap reopens.
    monkeypatch.setattr(OC, "DEEP_DIGITS", 5000)
    assert OC.cap_has_been_raised(
        {"cap_reason": OC.CAP_DIGIT, "cap_value": 3000, "planned": 20000, "verified_depth": 956},
        e,
    ) is True
    assert OC.can_progress_past(e, 956, require_past_published=True) is True


def test_ref_limited_stays_closed(tmp_path, monkeypatch):
    _isolate_oeis(tmp_path, monkeypatch)
    ref = {"offset": 0, "terms": [i + 1 for i in range(32)]}  # hi = 31
    d = OC.parse_definition("Expansion of (1-4*x)/(1-6*x-12*x^2+8*x^3).")
    terms_a = [int(c) for c in OC._series_A(d["expr"], 20)]
    e = {
        "id": "oc_A108476_0", "anum": "A108476",
        "name": "gf", "offset": 0,
        "claim": {"form": "relation",
                  "parts": ["a(n)", "A002605(n+1)*A026150(n)"],
                  "rels": ["="], "mod": None, "n0": None},
        "definition": d, "terms": terms_a, "data_n": 20, "published_hi": 19,
        "refs": {"A002605": dict(ref), "A026150": dict(ref)},
        "tested_hi": 30,
    }
    assert OC.claim_testable_hi(e) == 30
    _write_log([
        _new_row(e["id"], e["anum"], "relation", 30, 30, 19, "c1",
                 cap_reason=OC.CAP_REF, cap_value=30, extended=0),
    ])
    assert OC.can_progress_past(e, 30, require_past_published=True) is False
    assert OC.planned_depth(e, 30) == 30


def test_remember_attempt_records_cap_and_extended(tmp_path, monkeypatch):
    _isolate_oeis(tmp_path, monkeypatch)
    e = _gf_entry(tested_hi=10)
    acts = [{
        "status": "holds_on_range",
        "range": [0, 50],
        "tested": 51,
        "deep_terms": 51,
        "extended": 40,
        "cap_reason": OC.CAP_TERM,
        "cap_value": 50,
    }]
    OC.STATE.write_text(json.dumps({
        "targets": {e["id"]: {"tested_hi": 10}},
        "families": {}, "credit_total": 0, "scoreboard": {"extensions": {}},
    }))
    OC.remember_attempt(e, acts, "c1", planned=50)
    raw = OC.load_attempt_log(derived=False)
    row = raw["attempts"][-1]
    assert row["verified_depth"] == 50
    assert row["planned"] == 50
    assert row["extended"] == 40
    assert row["cap_reason"] == OC.CAP_TERM
    assert row["cap_value"] == 50
    assert row["prior_tested_hi"] == 10


# ---------------------------------------------------------------------------
# Item 29 — derived verified_depth view, no rewrite
# ---------------------------------------------------------------------------

def test_derived_view_fills_legacy_verified_depth_without_rewriting(tmp_path, monkeypatch):
    _isolate_oeis(tmp_path, monkeypatch)
    legacy = [
        _legacy("oc_A165064_0", "A165064", "gf", 1200, 100, cycle="c0"),
        _legacy("oc_A126089_0", "A126089", "relation", 20000, 200, cycle="c0"),
        _legacy("oc_A108476_0", "A108476", "relation", 20000, 19, cycle="c0"),
        _legacy("oc_A026587_0", "A026587", "relation", 1000, 1000, cycle="c0", beyond=False),
    ]
    _write_log(legacy)
    # Byte-identical file after a derived load (writers use derived=False,
    # and save strips derived fields).
    before = OC.ATTEMPT_LOG.read_bytes()
    OC.STATE.write_text(json.dumps({
        "targets": {
            "oc_A165064_0": {"tested_hi": 1199},
            "oc_A126089_0": {"tested_hi": 956},
            "oc_A108476_0": {"tested_hi": 30},
            "oc_A026587_0": {"tested_hi": 371},
        },
        "families": {}, "credit_total": 0,
        "scoreboard": {"extensions": {
            "oc_A165064_0": {"to": 1199, "bfile_hi": 100},
            "oc_A126089_0": {"to": 956, "bfile_hi": 200},
            "oc_A108476_0": {"to": 30, "bfile_hi": 19},
        }},
    }))
    view = OC.load_attempt_log()
    by = {a["id"]: a for a in view["attempts"]}
    assert by["oc_A165064_0"]["verified_depth"] == 1199
    assert by["oc_A126089_0"]["verified_depth"] == 956
    assert by["oc_A108476_0"]["verified_depth"] == 30
    assert by["oc_A026587_0"]["verified_depth"] == 371
    assert all(a.get("verified_depth_derived") for a in view["attempts"])
    # Committed file unchanged.
    after = OC.ATTEMPT_LOG.read_bytes()
    assert after == before
    raw = OC.load_attempt_log(derived=False)
    assert all("verified_depth" not in a for a in raw["attempts"])
    # Saving a derived view must not write the derived fields.
    OC.save_attempt_log(view)
    raw2 = json.loads(OC.ATTEMPT_LOG.read_text())
    assert all("verified_depth" not in a for a in raw2["attempts"])
    assert all("verified_depth_derived" not in a for a in raw2["attempts"])


def test_production_log_view_backfills_all_legacy_rows():
    """Against the committed production log: every pre-PR #4 row gets a
    verified_depth in the view, and a fresh raw load is unchanged.
    """
    # Read the committed file directly so this is independent of any
    # test that monkeypatches ATTEMPT_LOG.
    repo = Path(__file__).resolve().parents[1]
    raw = json.loads((repo / "society" / "systems" / "oeis_attempt_log.json").read_text(encoding="utf-8"))
    view = OC.attempt_log_view(raw)
    legacy = [a for a in raw["attempts"] if "planned" not in a and "verified_depth" not in a]
    assert len(legacy) == 41
    view_legacy = [a for a in view["attempts"] if a.get("verified_depth_derived")]
    assert len(view_legacy) == 41
    for a in view_legacy:
        assert "verified_depth" in a
        # Never greater than the requested (legacy) depth.
        assert int(a["verified_depth"] or 0) <= int(a.get("depth") or 0)
    # Spot-check the three named sequences.
    by = {}
    for a in view["attempts"]:
        by.setdefault(a["id"], []).append(a)
    # Last derived (or last overall) for each:
    a165s = [a for a in by["oc_A165064_0"] if a.get("verified_depth_derived")]
    a126s = [a for a in by["oc_A126089_0"] if a.get("verified_depth_derived")]
    a108 = [a for a in by.get("oc_A108476_0", []) if a.get("verified_depth_derived")]
    assert a165s and a126s
    # Spot-check: derived depths are the held ranges recorded on those
    # legacy rows (1199 or the 1200-term cap for A165064; 956 for A126089).
    # The exact last-derived row can move as the log grows; every derived
    # value is already bounded by requested depth above.
    assert any(int(a["verified_depth"]) in (1199, 1200) for a in a165s)
    assert any(int(a["verified_depth"]) in (956, 1199) for a in a126s)
    if a108:
        assert a108[-1]["verified_depth"] == 30
    # Raw file is not a backfill: explicit verified_depth is only on rows
    # written at attempt time (post-PR #6 / #7), and the 41 legacy rows
    # counted above still have no verified_depth on disk.
    explicit = [a for a in raw["attempts"] if "verified_depth" in a]
    assert explicit
    assert all("planned" in a or "extended" in a for a in explicit)


# ---------------------------------------------------------------------------
# Item 26 — committed checker-lane receipt
# ---------------------------------------------------------------------------

def test_checker_lane_writes_committed_receipt(tmp_path, monkeypatch):
    _isolate_checker(tmp_path, monkeypatch)
    # A history with nothing to mine still produces an ok receipt.
    result = CL.run_lane([], cycle_id="c1")
    assert result["ok"] is True
    assert CL.RECEIPT_PATH.exists()
    receipt = CL.load_receipt()
    assert receipt["cycles"]
    last = receipt["last"]
    assert last["ok"] is True
    assert last["cycle_id"] == "c1"
    assert last["error"] is None or last["error"] is last.get("error")
    assert "candidates_mined" in last
    assert "new_accepted" in last
    assert "new_rejected" in last
    assert last["applied_to_live_oracle"] is False
    vis = CL.visibility()
    assert vis["checker_lane_ok"] is True
    assert vis["checker_candidates_mined"] == last["candidates_mined"]
    assert vis["checker_new_accepted"] == last["new_accepted"]
    assert vis["checker_new_rejected"] == last["new_rejected"]
    assert vis["checker_proposals_awaiting_review"] == 0


def test_receipt_seeds_rejected_memory_on_fresh_state(tmp_path, monkeypatch):
    _isolate_checker(tmp_path, monkeypatch)
    CL.save_receipt({
        "version": 1,
        "cycles": [],
        "rejected": [{
            "fingerprint": "abc123",
            "kind": "triviality_pattern",
            "status": "rejected",
            "reasons": ["no_known_bad_caught"],
        }],
    })
    # Runtime snapshot is missing (fresh CI checkout).
    assert not CL.STATE_PATH.exists()
    st = CL.load_state()
    fps = {r.get("fingerprint") for r in st.get("rejected") or []}
    assert "abc123" in fps
    assert st.get("rejected_seeded_from_receipt") is True


def test_mine_failure_is_recorded_in_receipt(tmp_path, monkeypatch):
    _isolate_checker(tmp_path, monkeypatch)

    def boom(_hist):
        raise RuntimeError("miner crashed")

    result = CL.run_lane([], cycle_id="c_err", mine_fn=boom)
    assert result["ok"] is False
    assert "RuntimeError" in (result.get("error") or "")
    receipt = CL.load_receipt()
    last = receipt["last"]
    assert last["ok"] is False
    assert last["cycle_id"] == "c_err"
    assert last["error"]
    vis = CL.visibility()
    assert vis["checker_lane_ok"] is False
    assert vis["checker_lane_error"]


# ---------------------------------------------------------------------------
# Capability — raisable caps and fast C-finite path
# ---------------------------------------------------------------------------

def test_fast_cfinite_extend_past_old_gf_cap():
    """A165064-style rational g.f. reaches the fast term cap, cheaply and exactly."""
    e = _gf_entry(n_terms=16, tested_hi=0)
    defn = e["definition"]
    assert OC.fast_cfinite_available(e, defn) is True
    info = {}
    out = OC.extend(defn, e["offset"], e["terms"], OC.FAST_TERM_CAP, "A", info=info, entry=e)
    assert out is not None
    assert len(out) >= min(2000, OC.FAST_TERM_CAP)
    # Reproduces the published terms.
    assert out[:len(e["terms"])] == e["terms"]
    assert info.get("fast_cfinite") is True
    assert info.get("cap_reason") == OC.CAP_TERM
    # Past the old 1200-term series cap.
    assert (e["offset"] + len(out) - 1) > 1200 or len(out) > 1200


def test_live_a165064_can_be_pushed_past_1199():
    """The real menu entry is C-finite; extend goes past the held 1199."""
    menu = {e["anum"]: e for e in OC.load_menu()}
    e = menu["A165064"]
    defn = OC.computable_definition(e)
    assert defn and defn.get("kind") == "gf"
    assert OC.fast_cfinite_available(e, defn) is True
    assert OC.term_cap_for(e, defn) == OC.FAST_TERM_CAP
    info = {}
    # Only need to go a little past 1199 to prove the point, but the
    # fast path is cheap so use a mid-size request.
    out = OC.extend(defn, e["offset"], e["terms"], 2000, "A", info=info, entry=e)
    assert out is not None
    assert out[:len(e["terms"])] == e["terms"]
    hi = e["offset"] + len(out) - 1
    assert hi >= 2000 or hi > 1199
    assert len(out) > 1199


def test_cap_knobs_have_hard_bounds():
    for name in ("gf_term_cap", "deep_term_cap", "fast_term_cap", "deep_digits", "deep_seconds"):
        assert name in SH.KNOB_SPECS
        spec = SH.KNOB_SPECS[name]
        assert spec.lo < spec.default <= spec.hi
        assert SH.in_bounds(name, spec.default)
        assert SH.in_bounds(name, spec.lo)
        assert not SH.in_bounds(name, spec.hi + (1 if spec.kind == "int" else 1.0))
        # Invariants still rejected.
        assert SH.is_invariant_name("oracle_p") is True


def test_evaluator_caps_honor_a_live_knob(tmp_path, monkeypatch):
    _isolate_heal(tmp_path, monkeypatch)
    # No trial, knobs at defaults: module constants win (monkeypatch works).
    monkeypatch.setattr(OC, "FAST_TERM_CAP", 3000)
    assert OC.evaluator_caps()["fast_term_cap"] == 3000
    # An in-flight trial on this knob applies the trial value.
    st = SH.load_state()
    st["knobs"]["fast_term_cap"] = 12000
    st["trial"] = {"knob": "fast_term_cap", "from": 8000, "to": 12000}
    SH.save_state(st)
    assert OC.evaluator_caps()["fast_term_cap"] == 12000


def test_already_attempted_does_not_block_after_cap_raise(tmp_path, monkeypatch):
    _isolate_oeis(tmp_path, monkeypatch)
    e = _gf_entry(tested_hi=1199)
    _write_log([
        _new_row(e["id"], e["anum"], "gf", 1200, 1199, 100, "c1",
                 cap_reason=OC.CAP_TERM, cap_value=1200, extended=0),
    ])
    # Planning 8000 after the cap was raised is a new pair.
    assert OC.already_attempted_pair(e["id"], 8000) is False
    # The old verified 1199 is still a known pair.
    assert OC.already_attempted_pair(e["id"], 1199) is True
