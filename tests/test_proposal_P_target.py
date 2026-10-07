"""P_oracle uses the real Oracle verdict on the proposal's target lemma (not its title)."""
from __future__ import annotations

import json

import colony.standing_trust as ST
from colony.standing_trust import (
    STANDING_TRUST_P_MIN,
    compute_proposal_P,
    meets_standing_trust,
    resolve_proposal_target,
    target_oracle_verdict,
)

TITLE = "Chain `adversarial_hockey_deep` citing Some paper"
ACTION = "seek_enable:adversarial_hockey_deep"


def _row(mutation, *, passed, cycle_id, credit=None, sense_pass=None, kind="hard_enable"):
    return {
        "mutation": mutation,
        "kind": kind,
        "passed": passed,
        "fitness_credit": passed if credit is None else credit,
        "cycle_id": cycle_id,
        "sense": {"sense_pass": passed if sense_pass is None else sense_pass},
        "hear": {"bus_ok": False},
        "kills": [] if passed else ["held_out:held_out_fail"],
    }


def _log(tmp_path, monkeypatch, rows):
    path = tmp_path / "oracle.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    monkeypatch.setattr(ST, "ORACLE_LOG", path)
    return path


def _P(**kw):
    return compute_proposal_P(
        mutation=TITLE, action=ACTION, fingerprint="", novelty={"textbook_reuse": 0.0},
        bench_delta=None, lesson_consistency=1.0, **kw,
    )


def test_resolves_target_from_structured_fields():
    assert resolve_proposal_target(action=ACTION, mutation=TITLE) == "adversarial_hockey_deep"
    # title-only backtick also resolves when it names a real catalog entry
    assert resolve_proposal_target(action="", mutation=TITLE) == "adversarial_hockey_deep"
    # free text / unknown names never resolve
    assert resolve_proposal_target(action="mandate:cite", mutation="Deepen compute-useful math") == ""
    assert resolve_proposal_target(action="seek_enable:not_a_real_lemma_xyz", mutation="x") == ""


def test_resolved_pass_gets_real_credit(tmp_path, monkeypatch):
    # Title-text rows (process kills) must not drag the target's real pass down
    _log(tmp_path, monkeypatch, [
        _row("adversarial_hockey_deep", passed=True, cycle_id="c1"),
        _row(TITLE, passed=False, cycle_id="c1", kind="process"),
    ])
    P, terms = _P(cycle_id="c1")
    assert terms["P_oracle"] == 1.0
    assert terms["P_oracle_target_resolved"] == 1.0
    assert P == round(0.35 + 0.25 + 0.25 * 0.5 + 0.15, 4)
    assert meets_standing_trust(P, machine_checked=True)


def test_resolved_kill_scores_low(tmp_path, monkeypatch):
    _log(tmp_path, monkeypatch, [
        _row("adversarial_hockey_deep", passed=True, cycle_id="c0"),
        _row("adversarial_hockey_deep", passed=False, cycle_id="c0b"),  # latest = kill
    ])
    P, terms = _P(cycle_id="c1")
    assert terms["P_oracle"] == 0.0
    assert P < STANDING_TRUST_P_MIN


def test_stale_pass_is_not_credit(tmp_path, monkeypatch):
    _log(tmp_path, monkeypatch, [_row("adversarial_hockey_deep", passed=True, cycle_id="old")])
    assert target_oracle_verdict("adversarial_hockey_deep", cycle_id="new") is None
    P, terms = _P(cycle_id="new")
    assert terms["P_oracle"] == 0.0
    assert terms["P_oracle_target_resolved"] == 0.0
    assert P < STANDING_TRUST_P_MIN


def test_pass_without_credit_is_half(tmp_path, monkeypatch):
    _log(tmp_path, monkeypatch, [_row("adversarial_hockey_deep", passed=True, cycle_id="c1", credit=False)])
    _P_, terms = _P(cycle_id="c1")
    assert terms["P_oracle"] == 0.5


def test_unresolved_falls_back_to_legacy(tmp_path, monkeypatch):
    _log(tmp_path, monkeypatch, [_row("adversarial_hockey_deep", passed=True, cycle_id="c1")])
    P, terms = compute_proposal_P(
        mutation="Deepen compute-useful math from accepted findings",
        action="mandate:cite_accepted_compute_findings",
        novelty={"textbook_reuse": 0.0}, bench_delta=None, lesson_consistency=1.0, cycle_id="c1",
    )
    assert "P_oracle_target_resolved" not in terms
    assert terms["P_oracle"] in (0.0, 0.5, 1.0)  # legacy path, unchanged
    # explicit oracle dict still wins (legacy callers)
    P2, t2 = compute_proposal_P(
        mutation=TITLE, action=ACTION, oracle={"passed": False, "hear": {"bus_ok": True}},
        novelty={"textbook_reuse": 0.0}, bench_delta=None, lesson_consistency=1.0, cycle_id="c1",
    )
    assert t2["P_oracle"] == 0.0


def test_gate_threshold_unchanged():
    assert STANDING_TRUST_P_MIN == 0.70
    assert meets_standing_trust(0.70, machine_checked=True) is True
    assert meets_standing_trust(0.6999, machine_checked=True) is False


def test_hearing_rejected_proposal_never_queued(monkeypatch):
    from colony import hold_posture as HP

    monkeypatch.setattr(HP, "scan_new_authorize_themes", lambda ledger, lookback=400: [])
    state = {"improvement_proposals": [
        {"id": "imp_a", "status": "candidate_measured", "hearing_verdict": "reject", "P": 0.9, "title": "a"},
        {"id": "imp_b", "status": "candidate", "hearing_verdict": "accept_candidate", "P": 0.9, "title": "b"},
    ]}
    out = HP.scan_all_candidates(None, state)
    ids = [e.get("finding_id") for e in out]
    assert "imp_b" in ids and "imp_a" not in ids


def test_measured_rescore_picks_up_same_cycle_verdict(tmp_path, monkeypatch):
    """Proposal scored before the desk judges its target (fail closed), then rescored at
    measurement once the Oracle verdict on the real lemma exists."""
    from colony.fitness import EvolutionEngine

    path = _log(tmp_path, monkeypatch, [])
    P0, t0 = _P(cycle_id="c1")
    assert t0["P_oracle"] == 0.0 and P0 < STANDING_TRUST_P_MIN
    prop = {
        "id": "imp_x", "cycle_id": "c1", "title": TITLE, "action": ACTION, "fingerprint": "",
        "status": "candidate", "hearing_verdict": "accept_candidate", "P": P0, "P_terms": t0,
        "before_metrics": {"aggregate": 0.82}, "after_metrics": None,
    }
    path.write_text(json.dumps(_row("adversarial_hockey_deep", passed=True, cycle_id="c1")) + "\n")
    eng = EvolutionEngine.__new__(EvolutionEngine)
    eng.data = {"improvement_proposals": [prop]}
    eng.workshop = None
    closed = eng.close_open_proposals("c2", {"aggregate": 0.82})
    assert closed and closed[0]["P_terms"]["P_oracle"] == 1.0
    assert closed[0]["P_propose"] == P0
    # measured delta 0 → P_bench 0.3; novelty carried over (1.0)
    assert closed[0]["P"] == round(0.35 + 0.25 + 0.25 * 0.3 + 0.15 * closed[0]["P_terms"]["P_lesson"], 4)


def test_measured_rescore_killed_target_stays_below_gate(tmp_path, monkeypatch):
    from colony.fitness import EvolutionEngine

    _log(tmp_path, monkeypatch, [_row("adversarial_hockey_deep", passed=False, cycle_id="c1")])
    prop = {
        "id": "imp_y", "cycle_id": "c1", "title": TITLE, "action": ACTION, "fingerprint": "",
        "status": "candidate", "P": 0.5, "P_terms": {"P_novelty": 1.0},
        "before_metrics": {"aggregate": 0.5}, "after_metrics": None,
    }
    eng = EvolutionEngine.__new__(EvolutionEngine)
    eng.data = {"improvement_proposals": [prop]}
    eng.workshop = None
    closed = eng.close_open_proposals("c2", {"aggregate": 0.9})  # big bench rise
    assert closed[0]["P_terms"]["P_oracle"] == 0.0
    assert closed[0]["P"] < STANDING_TRUST_P_MIN
