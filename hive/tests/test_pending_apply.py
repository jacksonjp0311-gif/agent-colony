"""Item 56: a Wilson-passing apply deferred for confounded_baseline stays
pending and is re-checked on the first clean 6-cycle window.

The Wilson 95% 700‰ gate is unchanged. A pending decision is never
auto-applied: a fresh vote must still pass, and the baseline window
must be unconfounded. Merges are not held.
"""
from __future__ import annotations

import hive.swarm as SL
from hive.bitwork import WILSON_ACCEPT_PERMILLE, Router


def _winner(fp="set_knob:direction=up:name=park_cycles", name="park_cycles", label="dead_end_streak"):
    return SL.Proposal(
        role="improver",
        label=label,
        action={"op": "set_knob", "name": name, "direction": "up"},
        fingerprint=fp,
        symptom="stall",
        ok=True,
    )


def _accepted(winner, lower=901, margin=189, n=4):
    return SL.VoteResult(
        winner, False, "accepted", {winner.fingerprint: n},
        lower, margin, n, 0, 1, n, None,
    )


def _abstain(winner=None, lower=500, margin=10):
    return SL.VoteResult(
        winner, True, "wilson_abstain", {},
        lower, margin, 1, 0, 1, 1, None,
    )


def _stub_cycle(monkeypatch, *, vote_result, start_result, confounded=True):
    monkeypatch.setattr(SL, "observe", lambda cycle_id="": [{"kind": "dead_end_streak", "evidence": {}}])
    monkeypatch.setattr(SL, "swarm_propose", lambda *a, **k: [vote_result.winner] if vote_result.winner else [])
    monkeypatch.setattr(SL, "vote", lambda *a, **k: vote_result)
    monkeypatch.setattr(SL, "start_knob_trial", lambda *a, **k: dict(start_result))
    monkeypatch.setattr(SL, "start_rule_trial", lambda *a, **k: dict(start_result))
    monkeypatch.setattr(SL, "_window_is_confounded", lambda: confounded)
    # Skip teaching/mining side effects that need a live library.
    monkeypatch.setattr(SL, "harvest_self_heal_outcomes", lambda *a, **k: [])
    monkeypatch.setattr("hive.library.mine_all", lambda **k: [])


def test_wilson_gate_unchanged():
    assert WILSON_ACCEPT_PERMILLE == 700
    from hive.bitwork import wilson_lower_permille
    assert wilson_lower_permille(9, 9) == 700
    assert wilson_lower_permille(8, 8) < 700


def test_confounded_defer_stores_pending(tmp_path, monkeypatch):
    w = _winner()
    _stub_cycle(
        monkeypatch,
        vote_result=_accepted(w),
        start_result={"ok": False, "reason": "confounded_baseline"},
        confounded=True,
    )
    out = SL.run_cycle("c1")
    assert out["ok"] is True
    pending = out["pending_apply"]
    assert pending is not None
    assert pending["fingerprint"] == w.fingerprint
    assert pending["deferred_count"] == 1
    assert pending["wilson_gate"] == 700
    st = SL.load_state()
    assert st["pending_apply"]["fingerprint"] == w.fingerprint
    assert st["pending_apply"]["first_deferred_cycle"] == "c1"
    ev = [e for e in st["evidence"] if e.get("event") == "apply_deferred"]
    assert ev and ev[-1]["reason"] == "confounded_baseline"
    assert ev[-1]["deferred_count"] == 1
    assert ev[-1]["wilson_gate"] == 700
    # Did not auto-apply.
    assert not any(e.get("event") == "trial_start" for e in st["evidence"])


def test_later_confound_increments_count_keeps_original(tmp_path, monkeypatch):
    w = _winner()
    _stub_cycle(
        monkeypatch,
        vote_result=_accepted(w),
        start_result={"ok": False, "reason": "confounded_baseline"},
        confounded=True,
    )
    SL.run_cycle("c1")
    SL.run_cycle("c2")
    # A different winner while still confounded does not replace the pending.
    other = _winner(fp="set_knob:direction=up:name=fast_term_cap", name="fast_term_cap")
    _stub_cycle(
        monkeypatch,
        vote_result=_accepted(other),
        start_result={"ok": False, "reason": "confounded_baseline"},
        confounded=True,
    )
    out = SL.run_cycle("c3")
    pending = out["pending_apply"]
    assert pending["fingerprint"] == w.fingerprint
    assert pending["deferred_count"] == 3
    assert pending["first_deferred_cycle"] == "c1"
    assert pending["last_deferred_cycle"] == "c3"


def test_clean_window_same_vote_applies_and_clears(tmp_path, monkeypatch):
    w = _winner()
    _stub_cycle(
        monkeypatch,
        vote_result=_accepted(w),
        start_result={"ok": False, "reason": "confounded_baseline"},
        confounded=True,
    )
    SL.run_cycle("c1")
    SL.run_cycle("c2")
    _stub_cycle(
        monkeypatch,
        vote_result=_accepted(w, lower=901, margin=189),
        start_result={"ok": True, "reason": "trial_started", "via": "self_heal"},
        confounded=False,
    )
    out = SL.run_cycle("c3")
    assert out["started"]["ok"] is True
    assert out["started"]["deferred_count"] == 2
    assert out["pending_apply"] is None
    st = SL.load_state()
    assert st["pending_apply"] is None
    starts = [e for e in st["evidence"] if e.get("event") == "trial_start"]
    assert len(starts) == 1
    assert starts[0]["deferred_count"] == 2
    assert starts[0]["pending_resolved"] is True
    assert starts[0]["fingerprint"] == w.fingerprint
    assert starts[0]["wilson_gate"] == 700
    assert starts[0]["lower_permille"] == 901


def test_clean_window_abstain_drops_pending_no_apply(tmp_path, monkeypatch):
    w = _winner()
    _stub_cycle(
        monkeypatch,
        vote_result=_accepted(w),
        start_result={"ok": False, "reason": "confounded_baseline"},
        confounded=True,
    )
    SL.run_cycle("c1")
    _stub_cycle(
        monkeypatch,
        vote_result=_abstain(w),
        start_result={"ok": False, "reason": "should_not_be_called"},
        confounded=False,
    )
    # start_* must not be invoked on abstain.
    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("start must not run when the fresh vote fails the gate")

    monkeypatch.setattr(SL, "start_knob_trial", _boom)
    monkeypatch.setattr(SL, "start_rule_trial", _boom)
    out = SL.run_cycle("c2")
    assert called["n"] == 0
    assert out["pending_apply"] is None
    st = SL.load_state()
    assert st["pending_apply"] is None
    drops = [e for e in st["evidence"] if e.get("event") == "pending_apply_dropped"]
    assert drops and drops[-1]["reason"] == "vote_failed_gate"
    assert drops[-1]["pending_deferred_count"] == 1
    assert drops[-1]["wilson_gate"] == 700
    assert not any(e.get("event") == "trial_start" for e in st["evidence"])


def test_clean_window_different_winner_drops_and_may_apply_new(tmp_path, monkeypatch):
    w = _winner()
    other = _winner(fp="set_knob:direction=up:name=fast_term_cap", name="fast_term_cap")
    _stub_cycle(
        monkeypatch,
        vote_result=_accepted(w),
        start_result={"ok": False, "reason": "confounded_baseline"},
        confounded=True,
    )
    SL.run_cycle("c1")
    _stub_cycle(
        monkeypatch,
        vote_result=_accepted(other, lower=901, margin=249),
        start_result={"ok": True, "reason": "trial_started", "via": "self_heal"},
        confounded=False,
    )
    out = SL.run_cycle("c2")
    assert out["started"]["ok"] is True
    assert out["started"]["deferred_count"] == 0  # this is a new decision
    assert out["pending_apply"] is None
    st = SL.load_state()
    drops = [e for e in st["evidence"] if e.get("event") == "pending_apply_dropped"]
    assert drops and drops[-1]["reason"] == "vote_changed"
    assert drops[-1]["pending_fingerprint"] == w.fingerprint
    starts = [e for e in st["evidence"] if e.get("event") == "trial_start"]
    assert starts[-1]["fingerprint"] == other.fingerprint
    assert starts[-1]["wilson_gate"] == 700


def test_abstain_while_confounded_keeps_pending(tmp_path, monkeypatch):
    w = _winner()
    _stub_cycle(
        monkeypatch,
        vote_result=_accepted(w),
        start_result={"ok": False, "reason": "confounded_baseline"},
        confounded=True,
    )
    SL.run_cycle("c1")
    _stub_cycle(
        monkeypatch,
        vote_result=_abstain(w),
        start_result={"ok": False, "reason": "unused"},
        confounded=True,
    )
    out = SL.run_cycle("c2")
    assert out["pending_apply"] is not None
    assert out["pending_apply"]["fingerprint"] == w.fingerprint
    assert out["pending_apply"]["deferred_count"] == 1  # not incremented on abstain
    st = SL.load_state()
    assert st["pending_apply"]["fingerprint"] == w.fingerprint
    assert not any(e.get("event") == "pending_apply_dropped" for e in st["evidence"])


def test_pending_not_applied_without_clean_window(tmp_path, monkeypatch):
    """Even a still-passing vote is not applied while the window is confounded."""
    w = _winner()
    _stub_cycle(
        monkeypatch,
        vote_result=_accepted(w),
        start_result={"ok": False, "reason": "confounded_baseline"},
        confounded=True,
    )
    SL.run_cycle("c1")
    out = SL.run_cycle("c2")
    assert out["pending_apply"]["deferred_count"] == 2
    assert out.get("started", {}).get("ok") is not True
    st = SL.load_state()
    assert st["pending_apply"] is not None
    assert not any(e.get("event") == "trial_start" for e in st["evidence"])


def test_visibility_reports_pending(tmp_path, monkeypatch):
    w = _winner()
    _stub_cycle(
        monkeypatch,
        vote_result=_accepted(w),
        start_result={"ok": False, "reason": "confounded_baseline"},
        confounded=True,
    )
    SL.run_cycle("c1")
    vis = SL.visibility()
    assert vis["swarm_pending_apply"]["deferred_count"] == 1
    assert vis["swarm_pending_apply"]["fingerprint"] == w.fingerprint
    text = SL.format_visibility(vis)
    assert "pending" in text
    assert "deferred 1" in text
    assert WILSON_ACCEPT_PERMILLE == 700
