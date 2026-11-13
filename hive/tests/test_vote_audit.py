"""Every Hive gate decision records the vote numbers needed to audit it.

apply_deferred used to store only action, fingerprint, and reason, so
the first live gate-pass (run 43364882065) could not be checked from
the committed snapshot. abstain already had margin, lower_permille,
tallies, n_votes, and winner; trial_start had margin and
lower_permille only. All four outcomes — pass (trial_start), abstain,
apply, and deferred — now write the same audit fields, including
bucket and runner-up. The Wilson 95% gate and the 700 permille
threshold are unchanged.
"""
from __future__ import annotations

import hive.swarm as SL
from hive.bitwork import (
    WILSON_ACCEPT_PERMILLE,
    Router,
    margin_bucket,
)

AUDIT_FIELDS = (
    "margin",
    "lower_permille",
    "bucket",
    "bucket_n",
    "tallies",
    "n_votes",
    "winner",
    "runner_up",
)


def _prime_calibration(router: Router, n: int = 9, margin: int = 16) -> None:
    for _ in range(n):
        router.record_outcome(margin, True)


def _scored_pair(router: Router):
    a = SL.Proposal(
        role="improver", label="repeated_targets",
        action={"op": "set_knob", "name": "park_cycles", "direction": "up"},
        fingerprint="set_knob:direction=up:name=park_cycles",
        symptom="stall loop same targets",
    )
    b = SL.Proposal(
        role="pathfinder", label="repeated_targets",
        action={"op": "set_knob", "name": "park_cycles", "direction": "up"},
        fingerprint="set_knob:direction=up:name=park_cycles",
        symptom="stall loop same targets",
    )
    c = SL.Proposal(
        role="surveyor", label="repeated_targets",
        action={"op": "set_knob", "name": "unused_menu_cycles", "direction": "up"},
        fingerprint="set_knob:direction=up:name=unused_menu_cycles",
        symptom="stall loop same targets",
    )
    _prime_calibration(router)
    router.learn(
        "stall loop same targets", "repeated_targets",
        "set_knob:direction=up:name=park_cycles", proto_key="s1",
    )
    for p in (a, b, c):
        p.match = router.score_action(p.symptom, p.fingerprint)
    if a.match is not None:
        _prime_calibration(router, margin=a.match.margin)
        a.match = router.score_action(a.symptom, a.fingerprint)
        b.match = router.score_action(b.symptom, b.fingerprint)
        c.match = router.score_action(c.symptom, c.fingerprint)
    return a, b, c


def _assert_audit(rec: dict) -> None:
    for field in AUDIT_FIELDS:
        assert field in rec, f"missing audit field {field} on {rec.get('event')}"
    assert rec["wilson_gate"] == WILSON_ACCEPT_PERMILLE
    assert WILSON_ACCEPT_PERMILLE == 700
    assert isinstance(rec["margin"], int)
    assert isinstance(rec["lower_permille"], int)
    assert isinstance(rec["bucket"], int)
    assert isinstance(rec["tallies"], dict)
    assert isinstance(rec["n_votes"], int)
    if rec["margin"] > 0:
        assert rec["bucket"] == margin_bucket(rec["margin"])


def test_vote_fills_bucket_and_runner_up():
    router = Router()
    a, b, c = _scored_pair(router)
    result = SL.vote([a, b, c], router)
    assert result.abstained is False
    assert result.reason == "accepted"
    assert result.winner is not None
    assert result.winner.fingerprint == "set_knob:direction=up:name=park_cycles"
    assert result.runner_up is not None
    assert result.runner_up.fingerprint == "set_knob:direction=up:name=unused_menu_cycles"
    assert result.bucket == margin_bucket(result.margin)
    assert result.lower_permille >= WILSON_ACCEPT_PERMILLE
    fields = SL.vote_audit_fields(result)
    _assert_audit({**fields, "event": "vote"})
    assert fields["winner"]["fingerprint"] == result.winner.fingerprint
    assert fields["runner_up"]["fingerprint"] == result.runner_up.fingerprint
    # Gate is not loosened.
    assert fields["wilson_gate"] == 700


def test_abstain_evidence_has_full_audit_fields(tmp_path, monkeypatch):
    router = Router()
    # Uncalibrated: Wilson gate abstains.
    p = SL.Proposal(
        role="improver", label="repeated_targets",
        action={"op": "set_knob", "name": "park_cycles", "direction": "up"},
        fingerprint="set_knob:direction=up:name=park_cycles",
        symptom="stall loop",
    )
    result = SL.vote([p], router)
    assert result.reason == "wilson_abstain"
    st = SL._empty_state()
    ev = SL.append_evidence(st, {
        **SL.vote_audit_fields(result),
        "event": "abstain",
        "cycle_id": "c0",
        "reason": result.reason,
    })
    _assert_audit(ev)
    assert ev["event"] == "abstain"
    assert ev["reason"] == "wilson_abstain"
    assert ev["winner"] is not None
    assert ev["winner"]["fingerprint"] == p.fingerprint


def test_apply_deferred_records_the_same_vote_fields(tmp_path, monkeypatch):
    """The case item 43 caught: a gate-pass that then deferred."""
    router = Router()
    a, b, c = _scored_pair(router)
    result = SL.vote([a, b, c], router)
    assert result.abstained is False
    assert result.reason == "accepted"
    st = SL._empty_state()
    ev = SL.append_evidence(st, {
        **SL.vote_audit_fields(result),
        "event": "apply_deferred",
        "cycle_id": "c1",
        "reason": "confounded_baseline",
        "vote_reason": result.reason,
        "fingerprint": result.winner.fingerprint,
        "action": result.winner.action,
    })
    _assert_audit(ev)
    assert ev["event"] == "apply_deferred"
    assert ev["reason"] == "confounded_baseline"
    assert ev["vote_reason"] == "accepted"
    assert ev["margin"] == result.margin
    assert ev["lower_permille"] == result.lower_permille
    assert ev["bucket"] == result.bucket
    assert ev["tallies"] == result.tallies
    assert ev["n_votes"] == result.n_votes
    assert ev["winner"]["fingerprint"] == result.winner.fingerprint
    assert ev["runner_up"]["fingerprint"] == result.runner_up.fingerprint
    # The numbers that were missing from the live run are present.
    assert ev["margin"] > 0
    assert ev["lower_permille"] >= WILSON_ACCEPT_PERMILLE


def test_run_cycle_deferred_and_abstain_write_audit_fields(tmp_path, monkeypatch):
    """End-to-end: a live cycle that defers still records the vote."""
    finding = {
        "kind": "no_progress_perturb",
        "evidence": {
            "exit_reason": "no_candidates",
            "exit_cycle": "20261113T015301Z_759b6f",
            "session_targets": [],
            "timeout_count": 2,
        },
    }
    monkeypatch.setattr(SL, "observe", lambda cycle_id="": [finding])

    def _defer(proposal, cycle_id="", state=None):
        return {"ok": False, "reason": "confounded_baseline"}

    monkeypatch.setattr(SL, "start_knob_trial", _defer)
    monkeypatch.setattr(SL, "start_rule_trial", _defer)

    # Seed + calibrate first (no findings), then a findings cycle.
    monkeypatch.setattr(SL, "observe", lambda cycle_id="": [])
    out0 = SL.run_cycle("c0")
    assert out0["ok"] is True
    monkeypatch.setattr(SL, "observe", lambda cycle_id="": [finding])
    out1 = SL.run_cycle("c1")
    assert out1["ok"] is True
    st = SL.load_state()
    events = [e for e in (st.get("evidence") or []) if e.get("cycle_id") == "c1"]
    assert events, "expected a gate decision on the findings cycle"
    for ev in events:
        if ev.get("event") in {"abstain", "apply_deferred", "trial_start"}:
            _assert_audit(ev)
    deferred = [e for e in events if e.get("event") == "apply_deferred"]
    abstained = [e for e in events if e.get("event") == "abstain"]
    started = [e for e in events if e.get("event") == "trial_start"]
    # One of the three must have happened; if the vote passed, it is
    # deferred because start_* is stubbed. If it abstained, that is
    # also fully audited.
    assert deferred or abstained or started
    if deferred:
        ev = deferred[0]
        assert ev["reason"] == "confounded_baseline"
        assert ev["margin"] > 0
        assert ev["winner"] is not None
        assert ev["bucket"] == margin_bucket(ev["margin"])
    if started:
        ev = started[0]
        assert ev["margin"] >= 0
        assert ev["winner"] is not None


def test_wilson_threshold_unchanged():
    assert WILSON_ACCEPT_PERMILLE == 700
    from hive.bitwork import wilson_lower_permille
    # 9/9 is the documented edge: lower bound == 700, just accepted.
    assert wilson_lower_permille(9, 9) == 700
    assert wilson_lower_permille(8, 8) < 700
