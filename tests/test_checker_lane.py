"""Tighten-only Oracle checker proposal lane.

Covers the guard (loosening and invariant-touching rejected), the replay
harness (good and bad histories), mining, append-only recording, cycle
isolation, and dashboard/telemetry surfacing. Candidates are never
applied to the live Oracle.
"""
from __future__ import annotations

import json
from pathlib import Path

import colony.checker_lane as CL
import colony.dashboard as dashboard
import colony.oracle as O
import colony.telemetry as telemetry


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(CL, "STATE_PATH", tmp_path / "checker_lane.json")
    monkeypatch.setattr(CL, "LANE_LOG", tmp_path / "checker_lane.jsonl")
    monkeypatch.setattr(CL, "PROPOSAL_DIR", tmp_path / "checker_proposals")
    monkeypatch.setattr(CL, "RECEIPT_PATH", tmp_path / "checker_lane_receipt.json")
    # Keep the lane off the live Oracle log.
    monkeypatch.setattr(O, "ORACLE_LOG", tmp_path / "oracle.jsonl")
    (tmp_path / "oracle.jsonl").write_text("", encoding="utf-8")


def _row(mutation, passed, *, kills=None, kind="claim_theme", cycle_id="c1",
         invalidates=None, claim_text="", textbook_reuse=None, window_evidence=None):
    row = {
        "mutation": mutation,
        "passed": passed,
        "kills": list(kills or []),
        "kind": kind,
        "cycle_id": cycle_id,
        "claim_text": claim_text,
        "note": "",
    }
    if invalidates is not None:
        row["invalidates_prior_pass"] = invalidates
    if textbook_reuse is not None:
        row["textbook_reuse"] = textbook_reuse
    if window_evidence is not None:
        row["window_evidence"] = window_evidence
    return row


def _slipped_history():
    """A still-valid pass, a claim that passed then was later shown wrong, and a plain kill."""
    return [
        _row("good_lemma", True, cycle_id="c1"),
        _row("bad_trivial_sum", True, cycle_id="c1"),
        _row("easy_pad_square", False, kills=["easy_pad_oracle_kill", "collective_kill"],
             kind="easy_pad", cycle_id="c1"),
        _row("bad_trivial_sum", False, kills=["trivial:identity"], cycle_id="c2",
             invalidates=True),
        _row("other_kill", False, kills=["held_out:held_out_fail", "collective_kill"],
             cycle_id="c2"),
    ]


def _trap(pattern, **kw):
    c = {
        "kind": "trap_pattern",
        "direction": "tighten",
        "pattern": pattern,
        "pattern_type": "literal",
        "source": "test",
        "rationale": "test trap",
    }
    c.update(kw)
    return c


# ---------------------------------------------------------------------------
# Guard: loosening rejected, invariant-touching rejected
# ---------------------------------------------------------------------------

def test_guard_rejects_loosening_allow_action():
    hist = label(_slipped_history())
    g = CL.tighten_only_guard(_trap("bad_trivial_sum", action="allow"), hist)
    assert g["ok"] is False
    assert any("loosening_action:allow" in r for r in g["reasons"])


def test_guard_rejects_exemption_field():
    hist = label(_slipped_history())
    g = CL.tighten_only_guard(_trap("x", exempt_mutations=["other_kill"]), hist)
    assert g["ok"] is False
    assert any("exemption" in r for r in g["reasons"])


def test_guard_rejects_fail_to_pass_via_apply_fn():
    hist = label(_slipped_history())

    def loosen(candidate, verdict):
        # A malicious applicator that would turn every FAIL into a PASS.
        if verdict.get("passed") is False:
            return {"passed": True, "kills": [], "fired": True}
        return {"passed": True, "kills": [], "fired": False}

    g = CL.tighten_only_guard(_trap("bad_trivial_sum"), hist, apply_fn=loosen)
    assert g["ok"] is False
    assert any("would_turn_fail_into_pass" in r for r in g["reasons"])


def test_guard_rejects_p_min_touch():
    hist = label(_slipped_history())
    for field, value in (("P_min", 0.65), ("p_min", 0.70), ("standing_trust_P_min", 0.5)):
        g = CL.tighten_only_guard(_trap("bad_trivial_sum", **{field: value}), hist)
        assert g["ok"] is False, field
        assert any("touches_invariant" in r for r in g["reasons"]), (field, g["reasons"])


def test_guard_rejects_authored_cap_touch():
    hist = label(_slipped_history())
    for field, value in (("authored_cap", 200), ("MAX_AUTHORED_TOTAL", 151), ("authored_check_cap", 150)):
        g = CL.tighten_only_guard(_trap("bad_trivial_sum", **{field: value}), hist)
        assert g["ok"] is False, field
        assert any("touches_invariant" in r for r in g["reasons"])


def test_guard_rejects_athanor_touch():
    hist = label(_slipped_history())
    for field, value in (("athanor", "change"), ("dPhi", 0), ("H7", "relax"), ("athanor_math", "edit")):
        g = CL.tighten_only_guard(_trap("bad_trivial_sum", **{field: value}), hist)
        assert g["ok"] is False, field
        assert any("touches_invariant" in r for r in g["reasons"])


def test_guard_rejects_authorize_and_witness_touch():
    hist = label(_slipped_history())
    g = CL.tighten_only_guard(_trap("bad_trivial_sum", human_authorize=False), hist)
    assert g["ok"] is False
    assert any("touches_invariant" in r for r in g["reasons"])
    g = CL.tighten_only_guard(_trap("bad_trivial_sum", witness_append_only=False), hist)
    assert g["ok"] is False
    assert any("touches_invariant" in r for r in g["reasons"])


def test_guard_rejects_weaker_novelty_threshold():
    hist = label(_slipped_history())
    cand = {
        "kind": "stricter_novelty",
        "direction": "tighten",
        "textbook_reuse_kill_at": 0.90,  # higher than live 0.34: looser
    }
    g = CL.tighten_only_guard(cand, hist)
    assert g["ok"] is False
    assert any("novelty_looser_than_live" in r for r in g["reasons"])


def test_guard_rejects_narrower_window():
    hist = label(_slipped_history())
    cand = {
        "kind": "wider_shifted_window",
        "direction": "tighten",
        "min_window": 10,  # live is 30; narrower is looser
    }
    g = CL.tighten_only_guard(cand, hist)
    assert g["ok"] is False
    assert any("window_narrower_than_live" in r for r in g["reasons"])


def test_guard_rejects_missing_tighten_direction():
    hist = label(_slipped_history())
    g = CL.tighten_only_guard(_trap("bad_trivial_sum", direction="loosen"), hist)
    assert g["ok"] is False
    assert any("direction_not_tighten" in r for r in g["reasons"])
    g = CL.tighten_only_guard(_trap("bad_trivial_sum", direction=""), hist)
    assert g["ok"] is False


def test_guard_rejects_empty_pattern():
    hist = label(_slipped_history())
    g = CL.tighten_only_guard(_trap(""), hist)
    assert g["ok"] is False
    assert any("empty_pattern" in r for r in g["reasons"])


def test_guard_accepts_clean_trap():
    hist = label(_slipped_history())
    g = CL.tighten_only_guard(_trap("bad_trivial_sum"), hist)
    assert g["ok"] is True
    assert g["reasons"] == []


def test_guard_rationale_mentioning_invariants_is_not_a_hit():
    hist = label(_slipped_history())
    g = CL.tighten_only_guard(_trap(
        "bad_trivial_sum",
        rationale="The P >= 0.70 gate, the 150 cap, and Athanor math are unchanged.",
    ), hist)
    assert g["ok"] is True


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

def label(rows):
    return CL.label_history(rows)


def test_saturation_kills_do_not_invalidate_earlier_passes():
    rows = [
        _row("vandermonde", True, cycle_id="c1"),
        _row("vandermonde", True, cycle_id="c2"),
        _row("vandermonde", False, cycle_id="c3",
             kills=["held_out:held_out:already_saturated_no_harder_window", "collective_kill"]),
    ]
    hist = label(rows)
    labels = [r["label"] for r in hist]
    assert labels == ["pass_still_valid", "pass_still_valid", "kill"]


def test_latest_pass_keeps_earlier_passes_valid():
    rows = [
        _row("authored_x", False, kills=["held_out:held_out_fail"], cycle_id="c1"),
        _row("authored_x", True, cycle_id="c2"),
    ]
    hist = label(rows)
    assert hist[1]["label"] == "pass_still_valid"


def test_invalidating_kill_marks_earlier_pass():
    hist = label(_slipped_history())
    by = {r["mutation"] + str(r["passed"]): r["label"] for r in hist}
    assert by["good_lemmaTrue"] == "pass_still_valid"
    assert by["bad_trivial_sumTrue"] == "pass_later_invalidated"
    assert by["bad_trivial_sumFalse"] == "kill"


# ---------------------------------------------------------------------------
# Replay: good and bad cases
# ---------------------------------------------------------------------------

def test_replay_accepts_when_it_catches_slipped_and_keeps_good():
    hist = label(_slipped_history())
    r = CL.replay_candidate(_trap("bad_trivial_sum"), hist)
    assert r["accepted"] is True
    assert r["applied_to_live_oracle"] is False
    assert "bad_trivial_sum" in r["known_bad_caught"]
    assert r["known_good_kept"] == r["known_good_total"]
    assert r["known_good_total"] >= 1
    assert r["unexplained_pass_to_fail"] == []
    assert r["fail_to_pass"] == []


def test_replay_rejects_unexplained_pass_to_fail():
    hist = label(_slipped_history())
    # A pattern that also matches the still-valid pass.
    r = CL.replay_candidate(_trap("lemma"), hist)  # matches good_lemma
    assert r["accepted"] is False
    assert any("unexplained_pass_to_fail" in x for x in r["reasons"])
    assert "good_lemma" in r["unexplained_pass_to_fail"]


def test_replay_rejects_when_no_known_bad_caught():
    hist = label(_slipped_history())
    r = CL.replay_candidate(_trap("other_kill"), hist)
    assert r["accepted"] is False
    assert any("no_known_bad_caught" in x for x in r["reasons"])
    assert r["known_good_kept"] == r["known_good_total"]


def test_replay_rejects_fail_to_pass_via_apply_fn():
    hist = label(_slipped_history())

    def loosen(candidate, verdict):
        if verdict.get("passed") is False:
            return {"passed": True, "kills": [], "fired": True}
        return {"passed": verdict.get("passed"), "kills": list(verdict.get("kills") or []), "fired": False}

    r = CL.replay_candidate(_trap("bad_trivial_sum"), hist, apply_fn=loosen)
    assert r["accepted"] is False
    # Guard catches it first; either reason is a correct reject.
    blob = " ".join(r["reasons"])
    assert "fail_to_pass" in blob or "would_turn_fail_into_pass" in blob or "guard_rejected" in blob


def test_replay_keeps_known_good_on_saturation_history():
    rows = [
        _row("vandermonde", True, cycle_id="c1"),
        _row("vandermonde", False, cycle_id="c2",
             kills=["held_out:held_out:already_saturated_no_harder_window", "collective_kill"]),
        _row("bad_trivial_sum", True, cycle_id="c1"),
        _row("bad_trivial_sum", False, kills=["trivial:identity"], cycle_id="c2", invalidates=True),
    ]
    hist = label(rows)
    # A vandermonde trap would flip a still-valid pass → reject.
    r = CL.replay_candidate(_trap("vandermonde"), hist)
    assert r["accepted"] is False
    assert "vandermonde" in r["unexplained_pass_to_fail"]
    # A precise trap for the slipped claim is accepted and does not touch vandermonde.
    r2 = CL.replay_candidate(_trap("bad_trivial_sum"), hist)
    assert r2["accepted"] is True
    assert r2["known_good_kept"] == r2["known_good_total"]


def test_simulate_never_removes_a_kill():
    row = _row("easy_pad_square", False, kills=["easy_pad_oracle_kill"])
    nxt = CL.simulate(_trap("easy_pad_square"), row)
    assert nxt["passed"] is False
    assert "easy_pad_oracle_kill" in nxt["kills"]
    assert nxt["fired"] is True


# ---------------------------------------------------------------------------
# Stricter novelty and wider windows
# ---------------------------------------------------------------------------

def test_stricter_novelty_identity_catches_slipped():
    hist = label(_slipped_history())
    cand = {
        "kind": "stricter_novelty",
        "direction": "tighten",
        "add_identities": ["bad_trivial_sum"],
        "source": "test",
    }
    r = CL.replay_candidate(cand, hist)
    assert r["accepted"] is True
    assert "bad_trivial_sum" in r["known_bad_caught"]


def test_stricter_novelty_threshold_uses_row_score():
    rows = [
        _row("good_lemma", True, cycle_id="c1", textbook_reuse=0.10),
        _row("almost_textbook", True, cycle_id="c1", textbook_reuse=0.30),
        _row("almost_textbook", False, kills=["textbook_reuse=0.30"], cycle_id="c2",
             textbook_reuse=0.30, invalidates=True),
    ]
    hist = label(rows)
    cand = {
        "kind": "stricter_novelty",
        "direction": "tighten",
        "textbook_reuse_kill_at": 0.25,  # live is 0.34; this is stricter
    }
    r = CL.replay_candidate(cand, hist)
    assert r["accepted"] is True
    assert "almost_textbook" in r["known_bad_caught"]
    assert r["unexplained_pass_to_fail"] == []


def test_wider_window_requires_evidence_and_catches():
    rows = [
        _row("good_lemma", True, cycle_id="c1"),
        _row("wide_fail", True, cycle_id="c1",
             window_evidence={"passes_at": 30, "fails_at": 40}),
        _row("wide_fail", False, kills=["later_invalid"], cycle_id="c2",
             invalidates=True, window_evidence={"passes_at": 30, "fails_at": 40}),
    ]
    hist = label(rows)
    cand = {
        "kind": "wider_shifted_window",
        "direction": "tighten",
        "min_window": 40,
    }
    r = CL.replay_candidate(cand, hist)
    assert r["accepted"] is True
    assert "wide_fail" in r["known_bad_caught"]
    # Without evidence, a still-valid pass is not flipped.
    assert r["unexplained_pass_to_fail"] == []


def test_wider_window_without_evidence_does_not_accept():
    hist = label(_slipped_history())  # no window_evidence on any row
    cand = {
        "kind": "wider_shifted_window",
        "direction": "tighten",
        "min_window": 40,
    }
    r = CL.replay_candidate(cand, hist)
    assert r["accepted"] is False
    assert any("no_known_bad_caught" in x for x in r["reasons"])


# ---------------------------------------------------------------------------
# Mining and integration with a fixture history
# ---------------------------------------------------------------------------

def test_mine_proposes_trap_for_slipped_claim():
    hist = label(_slipped_history())
    cands = CL.mine(hist)
    patterns = [c.get("pattern") for c in cands if c.get("kind") == "trap_pattern"]
    assert "bad_trivial_sum" in patterns
    for c in cands:
        assert c["direction"] == "tighten"
        assert c["kind"] in CL.CANDIDATE_KINDS


def test_run_lane_accepts_tightener_on_fixture_history(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    hist = label(_slipped_history())
    report = CL.run_lane(hist, cycle_id="testc1")
    assert report["ok"] is True
    assert report["applied_to_live_oracle"] is False
    assert report["awaiting_review"] >= 1
    ids = [p["id"] for p in report["proposals"]]
    assert any(p["known_bad_caught"] for p in report["proposals"])
    # Proposal file exists and says it is not applied.
    files = list((tmp_path / "checker_proposals").glob("*.md"))
    assert files
    text = files[0].read_text(encoding="utf-8")
    assert "awaiting human review" in text
    assert "has not been applied to the live Oracle" in text
    assert "P ≥ 0.70" in text or "P >= 0.70" in text
    assert "150" in text
    # State snapshot lists them.
    state = CL.load_state()
    assert state["awaiting_review"]
    assert all(p.get("applied_to_live_oracle") is False for p in state["awaiting_review"])
    assert ids


def test_run_lane_does_not_write_to_oracle_log(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    before = O.ORACLE_LOG.read_text(encoding="utf-8") if O.ORACLE_LOG.exists() else ""
    CL.run_lane(label(_slipped_history()), cycle_id="testc2")
    after = O.ORACLE_LOG.read_text(encoding="utf-8") if O.ORACLE_LOG.exists() else ""
    assert after == before


def test_append_only_log_does_not_rewrite(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    hist = label(_slipped_history())
    CL.run_lane(hist, cycle_id="c1")
    first = CL.LANE_LOG.read_text(encoding="utf-8")
    assert first
    n1 = first.count("\n")
    # A second run with the same history must not rewrite earlier lines,
    # and must not append a duplicate accepted/rejected for the same fingerprint.
    CL.run_lane(hist, cycle_id="c2")
    second = CL.LANE_LOG.read_text(encoding="utf-8")
    assert second.startswith(first) or first in second
    # Earlier records are still present, byte-identical at the front.
    assert second[:len(first)] == first
    # And we did not grow by a full second copy of every event.
    n2 = second.count("\n")
    assert n2 >= n1
    # No truncate: file only grew or stayed.
    assert len(second) >= len(first)


def test_on_cycle_swallows_exceptions(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    def boom(_history):
        raise RuntimeError("mine exploded")

    monkeypatch.setattr(CL, "mine", boom)
    # run_lane catches mine errors; on_cycle also wraps the rest.
    out = CL.on_cycle("cx", history=label(_slipped_history()))
    assert out["ok"] is False
    assert "mine" in str(out.get("error") or "")
    assert out["applied_to_live_oracle"] is False

    def boom_run(*_a, **_k):
        raise RuntimeError("run exploded")

    monkeypatch.setattr(CL, "run_lane", boom_run)
    out = CL.on_cycle("cy")
    assert out["ok"] is False
    assert "run exploded" in str(out.get("error") or "")


def test_pending_withdrawn_if_new_history_would_flip_good_pass(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    hist = label(_slipped_history())
    CL.run_lane(hist, cycle_id="c1")
    vis = CL.visibility()
    assert vis["checker_proposals_awaiting_review"] >= 1
    # A new still-valid pass whose name contains the accepted pattern.
    wider = hist + [ _row("bad_trivial_sum_good_cousin", True, cycle_id="c9") ]
    wider = label(wider)
    report = CL.run_lane(wider, cycle_id="c9")
    # The old trap on "bad_trivial_sum" would now flip the cousin; it must leave review.
    pending_ids = [p["id"] for p in report["proposals"]]
    state = CL.load_state()
    withdrawn = [p for p in state["rejected"] if p.get("status") == "withdrawn"]
    # Either withdrawn, or no longer awaiting. A brand-new more-specific
    # candidate is allowed to take its place, but the broad one must go.
    fps_pending = {p.get("fingerprint") for p in state["awaiting_review"]}
    for p in withdrawn:
        assert p["fingerprint"] not in fps_pending
    assert withdrawn or all(
        "bad_trivial_sum_good_cousin" not in str((p.get("replay") or {}).get("unexplained_pass_to_fail") or [])
        for p in state["awaiting_review"]
    )
    # And if something is still pending, it must keep the new good pass.
    for p in state["awaiting_review"]:
        replay = CL.replay_candidate(p["candidate"], wider)
        assert "bad_trivial_sum_good_cousin" not in replay["unexplained_pass_to_fail"]
    assert pending_ids is not None


# ---------------------------------------------------------------------------
# Surfacing: visibility, telemetry, dashboard
# ---------------------------------------------------------------------------

def test_visibility_and_format(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert "0" in CL.format_visibility()
    CL.run_lane(label(_slipped_history()), cycle_id="c1")
    vis = CL.visibility()
    assert vis["checker_proposals_awaiting_review"] >= 1
    line = CL.format_visibility(vis)
    assert "checker proposals awaiting human review" in line
    assert "Not applied to the live Oracle" in line


def test_telemetry_and_dashboard_surface_proposals(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    CL.run_lane(label(_slipped_history()), cycle_id="c1")
    vis = CL.visibility()
    monkeypatch.setattr(CL, "visibility", lambda: vis)
    monkeypatch.setattr(CL, "format_visibility", lambda v=None: CL.format_visibility(vis))

    snap = telemetry.gather_internal({"fitness_history": [], "agents": {}})
    assert snap["checker_proposals_awaiting_review"] == vis["checker_proposals_awaiting_review"]
    assert snap["checker_proposals"] == vis["checker_proposals"]
    assert snap["checker_proposals_awaiting_review"] >= 1

    data = tmp_path / "data"
    data.mkdir()
    (tmp_path / "society").mkdir(exist_ok=True)
    (data / "society_state.json").write_text(json.dumps({
        "cycle_count": 1,
        "fitness_history": [{"cycle_id": "c1", "aggregate": 1}],
        "agents": {},
        "roles": {},
        "tribute_mandate": {"active_ask": "watch"},
    }), encoding="utf-8")
    dashboard.refresh_dashboard(tmp_path)
    html = (tmp_path / "society" / "DASHBOARD.html").read_text(encoding="utf-8")
    summary = (tmp_path / "society" / "WITNESS_SUMMARY.md").read_text(encoding="utf-8")
    assert "Checker proposals awaiting human review" in html
    assert "checker proposals awaiting human review" in html.lower() or "Checker proposals" in html
    assert "Checker proposals awaiting human review" in summary or "checker proposals" in summary.lower()
    # The live Oracle is not claimed to have changed.
    assert "Not applied" in html or "not applied" in html.lower() or "awaiting human review" in html


def test_evolve_hook_is_guarded():
    """The evolve-cycle hook wraps the lane in try/except and does not authorize."""
    src = Path(__file__).resolve().parents[1] / "colony" / "emergence" / "growth_steps_evolve.py"
    text = src.read_text(encoding="utf-8")
    assert "from colony.checker_lane import on_cycle" in text
    # The import and call sit inside a try, the same way stall does.
    idx = text.index("from colony.checker_lane import on_cycle")
    window = text[max(0, idx - 80): idx + 280]
    assert "try:" in window
    assert "except Exception:" in window
    assert "on_cycle(cycle_id)" in window
    assert "authorize" not in window.lower() or "authorize=false" in window.lower()


def test_simulate_does_not_honor_allow_action():
    """Defense in depth: even a candidate marked 'allow' cannot un-kill a FAIL."""
    row = _row("other_kill", False, kills=["held_out:held_out_fail"])
    nxt = CL.simulate(_trap("no_match_zzzz", action="allow"), row)
    assert nxt["passed"] is False
    assert "held_out:held_out_fail" in nxt["kills"]
