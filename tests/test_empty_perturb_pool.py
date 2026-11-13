"""Empty-pool diagnosis, non-stickiness, cap suggestions, authoring invite.

Queue items 46–51: a distinct empty_perturb_pool finding, a supply path
that stays inside the 150 authored-check cap, and has_eligible only
counting real Oracle-reachable alternatives. Gates are unchanged.
"""
from __future__ import annotations

import colony.self_heal as SH
import colony.stall as S
import colony.authoring as AU


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(SH, "STATE_PATH", tmp_path / "self_heal.json")
    monkeypatch.setattr(SH, "EVENT_LOG", tmp_path / "self_heal.jsonl")
    monkeypatch.setattr(S, "STATE_PATH", tmp_path / "stall_state.json")


def _empty_exit(cycle_id="exit0", pass_total=528, blocked=True):
    st = S._empty_state()
    st["cycles"] = [cycle_id, "c1", "c2"]
    st["pass_history"] = [{"cycle_id": cycle_id, "pass_total": pass_total},
                          {"cycle_id": "c1", "pass_total": pass_total},
                          {"cycle_id": "c2", "pass_total": pass_total}]
    st["stall_cycles"] = 10
    st["perturb"] = {
        "active": False,
        "exit_reason": "no_candidates",
        "exit_cycle": cycle_id,
        "session_progress": False,
        "session_targets": [],
        "timeout_count": 3,
        "no_candidates_pass_total": pass_total if blocked else None,
        "cooldown_until": -1,
        "strategy": "mutate",
    }
    return st


def test_diagnose_empty_pool_on_exit_cycle(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    stall = _empty_exit("c1")
    findings = SH.diagnose("c1", stall_state=stall, heal_state=SH.load_state())
    kinds = [f["kind"] for f in findings]
    assert "empty_perturb_pool" in kinds
    assert "no_progress_perturb" not in kinds
    ev = next(f["evidence"] for f in findings if f["kind"] == "empty_perturb_pool")
    assert ev["exit_reason"] == "no_candidates"
    assert ev["session_targets"] == []


def test_diagnose_empty_pool_while_blocked_not_on_exit_cycle(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    stall = _empty_exit("old_exit", blocked=True)
    # Same pass total, no eligible targets: item 33 still blocks.
    monkeypatch.setattr(S, "has_eligible_progress_target", lambda state=None: False)
    findings = SH.diagnose("later", stall_state=stall, heal_state=SH.load_state())
    kinds = [f["kind"] for f in findings]
    assert "empty_perturb_pool" in kinds
    assert "no_progress_perturb" not in kinds


def test_diagnose_empty_pool_is_not_sticky_once_unblocked(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    stall = _empty_exit("old_exit", pass_total=528, blocked=True)
    # Passes moved: item 33 no longer blocks.
    stall["pass_history"][-1]["pass_total"] = 529
    monkeypatch.setattr(S, "has_eligible_progress_target", lambda state=None: False)
    findings = SH.diagnose("later", stall_state=stall, heal_state=SH.load_state())
    kinds = [f["kind"] for f in findings]
    assert "empty_perturb_pool" not in kinds
    assert "no_progress_perturb" not in kinds


def test_spent_picks_still_diagnosed_as_no_progress(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    stall = _empty_exit("c1")
    stall["perturb"]["session_targets"] = ["oc_X"]
    stall["perturb"]["exit_reason"] = "timeout"
    findings = SH.diagnose("c1", stall_state=stall, heal_state=SH.load_state())
    kinds = [f["kind"] for f in findings]
    assert "no_progress_perturb" in kinds
    assert "empty_perturb_pool" not in kinds


def test_empty_pool_suggests_caps_only_when_holds_at_caps(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(SH, "_empty_pool_cap_suggestions", lambda: (
        [{"id": "oc_example", "cap_reason": "term_cap", "cap_value": 8000}],
        [("fast_term_cap", "up"), ("gf_term_cap", "up")],
    ))
    stall = _empty_exit("c1")
    findings = SH.diagnose("c1", stall_state=stall, heal_state=SH.load_state())
    f = next(x for x in findings if x["kind"] == "empty_perturb_pool")
    assert f["suggest"][0] == ("fast_term_cap", "up")
    assert f["evidence"]["cap_holds"][0]["cap_reason"] == "term_cap"

    monkeypatch.setattr(SH, "_empty_pool_cap_suggestions", lambda: ([], []))
    findings2 = SH.diagnose("c1", stall_state=stall, heal_state=SH.load_state())
    f2 = next(x for x in findings2 if x["kind"] == "empty_perturb_pool")
    assert f2["suggest"] == []


def test_maybe_supply_invites_authoring_under_the_cap(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    called = {}

    def _author(*, max_new=1, cycle_id="", write=True):
        called["max_new"] = max_new
        called["cycle_id"] = cycle_id
        called["write"] = write
        return [{"name": "authored_demo", "accepted": True}]

    monkeypatch.setattr(AU, "author_checks", _author)
    monkeypatch.setattr(AU, "authored_count", lambda: 12)
    monkeypatch.setattr(SH, "authored_check_counts", lambda: {"n": 12, "cap": 150, "room": True})
    findings = [{"kind": "empty_perturb_pool", "evidence": {"authoring_room": True}}]
    out = SH.maybe_supply_oracle_targets("c9", findings=findings)
    assert out["invited"] is True
    assert called["max_new"] == 1
    assert called["write"] is True
    assert out["authored"][0]["name"] == "authored_demo"
    assert out["cap"] == 150


def test_maybe_supply_does_not_author_at_the_150_cap(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    def _author(**kwargs):
        raise AssertionError("must not author at the cap")

    monkeypatch.setattr(AU, "author_checks", _author)
    monkeypatch.setattr(AU, "authored_count", lambda: 150)
    findings = [{"kind": "empty_perturb_pool"}]
    out = SH.maybe_supply_oracle_targets("c9", findings=findings)
    assert out["invited"] is False
    assert out["reason"] == "at_authored_cap"
    assert out["cap"] == 150
    assert out["authored"] == []


def test_maybe_supply_silent_without_the_finding(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(AU, "author_checks", lambda **k: (_ for _ in ()).throw(AssertionError("no")))
    out = SH.maybe_supply_oracle_targets("c9", findings=[{"kind": "flat_passes"}])
    assert out["invited"] is False
    assert out["reason"] == "no_finding"


def test_authored_cap_constant_unchanged():
    assert AU.MAX_AUTHORED_TOTAL == 150
    assert AU.MAX_AUTHORED_PER_CYCLE == 1


def test_has_eligible_still_false_on_empty_oeis_pool(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(S, "oracle_reachable_alternatives", lambda state=None: [])
    assert S.has_eligible_progress_target() is False


def test_has_eligible_true_for_a_real_progressable_alternative(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(S, "oracle_reachable_alternatives", lambda state=None: [
        {"id": "oc_new", "can_progress": True, "source": "oeis"},
    ])
    assert S.has_eligible_progress_target() is True
    # Invented or non-progressing rows are ignored.
    monkeypatch.setattr(S, "oracle_reachable_alternatives", lambda state=None: [
        {"id": "shape:congruence", "can_progress": False},
        {"id": "", "can_progress": True},
    ])
    assert S.has_eligible_progress_target() is False


def test_diagnose_suggestions_for_empty_pool_are_not_a_cooldown():
    # After the 6→8 cooldown revert, this finding must not default to
    # another cooldown trial.
    assert SH.DIAGNOSIS_SUGGESTIONS.get("empty_perturb_pool") == []


def _timeout_exit(cycle_id="exitT", pass_total=528, entered="enter0", progress=True, active=False):
    st = S._empty_state()
    st["cycles"] = [entered, "c1", cycle_id]
    st["pass_history"] = [
        {"cycle_id": entered, "pass_total": pass_total},
        {"cycle_id": "c1", "pass_total": pass_total},
        {"cycle_id": cycle_id, "pass_total": pass_total},
    ]
    st["stall_cycles"] = 10
    st["perturb"] = {
        "active": active,
        "exit_reason": "timeout",
        "exit_cycle": cycle_id,
        "entered_at": entered,
        "session_progress": progress,
        "session_targets": ["oc_A174783_0", "oc_A212205_0"],
        "timeout_count": 4,
        "cycles_in_mode": 9,
        "cooldown_until": -1,
        "strategy": "explore",
    }
    return st


def test_diagnose_timeout_flat_passes_invites_supply_even_with_depth(tmp_path, monkeypatch):
    """Timeout/dead-end with depth progress but flat Oracle passes is a supply cue."""
    _isolate(tmp_path, monkeypatch)
    stall = _timeout_exit("cT", progress=True)
    findings = SH.diagnose("cT", stall_state=stall, heal_state=SH.load_state())
    kinds = [f["kind"] for f in findings]
    assert "perturb_ended_no_oracle" in kinds
    ev = next(f["evidence"] for f in findings if f["kind"] == "perturb_ended_no_oracle")
    assert ev["exit_reason"] == "timeout"
    assert ev["oracle_pass_delta"] == 0
    # Not sticky: later cycles do not re-emit.
    later = SH.diagnose("cLater", stall_state=stall, heal_state=SH.load_state())
    assert "perturb_ended_no_oracle" not in [f["kind"] for f in later]


def test_diagnose_timeout_with_new_passes_does_not_invite(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    stall = _timeout_exit("cT", pass_total=528, progress=True)
    stall["pass_history"][-1]["pass_total"] = 529
    findings = SH.diagnose("cT", stall_state=stall, heal_state=SH.load_state())
    assert "perturb_ended_no_oracle" not in [f["kind"] for f in findings]


def test_diagnose_dead_end_exit_flat_passes_invites(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    stall = _timeout_exit("cD", progress=True)
    stall["perturb"]["exit_reason"] = "dead_end_turns"
    findings = SH.diagnose("cD", stall_state=stall, heal_state=SH.load_state())
    assert "perturb_ended_no_oracle" in [f["kind"] for f in findings]


def test_maybe_supply_authors_on_timeout_finding(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    called = {}

    def _gen(**kwargs):
        called["max_new"] = kwargs.get("max_new")
        called["write"] = kwargs.get("write")
        return [{"name": "authored_mut_demo", "accepted": True}]

    import colony.target_generator as TG
    monkeypatch.setattr(TG, "author_targets", _gen)
    monkeypatch.setattr(AU, "authored_count", lambda: 101)
    findings = [{"kind": "perturb_ended_no_oracle", "evidence": {"exit_reason": "timeout"}}]
    out = SH.maybe_supply_oracle_targets("cT", findings=findings)
    assert out["invited"] is True
    assert out["reason"] == "generated"
    assert out["authored"][0]["name"] == "authored_mut_demo"
    assert called["max_new"] == 1
    assert called["write"] is True
    assert out["cap"] == 150


def test_maybe_supply_timeout_still_respects_150_cap(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    def _boom(**kwargs):
        raise AssertionError("must not author at the cap")

    import colony.target_generator as TG
    monkeypatch.setattr(TG, "author_targets", _boom)
    monkeypatch.setattr(AU, "author_checks", _boom)
    monkeypatch.setattr(AU, "authored_count", lambda: 150)
    out = SH.maybe_supply_oracle_targets("cT", findings=[{"kind": "perturb_ended_no_oracle"}])
    assert out["invited"] is False
    assert out["reason"] == "at_authored_cap"
    assert out["cap"] == 150
    assert out["authored"] == []
