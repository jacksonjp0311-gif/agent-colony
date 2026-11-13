"""Hive move-selection for empty_perturb_pool. No colony imports required.

Pathfinder yields. Improver proposes add_family_rotation. Surveyor
proposes a cap trial only when holds sit at a physical cap. Nobody
maps this finding to add_skip_rule already_held_range. The Wilson
700 permille gate is unchanged.
"""
from __future__ import annotations

import hive.ops as FA
import hive.library as FL
import hive.swarm as SL
from hive.bitwork import WILSON_ACCEPT_PERMILLE, Router


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(FL, "LIBRARY_LOG", tmp_path / "fix_library.jsonl")
    monkeypatch.setattr(FL, "LIBRARY_SNAPSHOT", tmp_path / "swarm_library.json")
    monkeypatch.setattr(SL, "STATE_PATH", tmp_path / "swarm_learn.json")
    monkeypatch.setattr(SL, "EVENT_LOG", tmp_path / "swarm_learn.jsonl")
    monkeypatch.setattr(SL, "RULES_PATH", tmp_path / "swarm_rules.json")


def _finding(*, caps=True, families=("algebraic", "pattern")):
    ev = {
        "exit_reason": "no_candidates",
        "session_targets": [],
        "timeout_count": 3,
        "unused_families": list(families),
    }
    suggest = []
    if caps:
        ev["cap_holds"] = [{"id": "oc_example", "cap_reason": "term_cap"}]
        ev["suggest"] = [("fast_term_cap", "up")]
        suggest = [("fast_term_cap", "up")]
    return {"kind": "empty_perturb_pool", "evidence": ev, "suggest": suggest}


def test_pathfinder_yields_on_empty_pool(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    FL.ensure_seeded()
    router = FL.train_router()
    p = SL.propose_for_role("pathfinder", [_finding()], router)
    assert p is None


def test_improver_proposes_family_rotation(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    FL.ensure_seeded()
    router = FL.train_router()
    p = SL.propose_for_role("improver", [_finding()], router)
    assert p is not None
    assert p.ok
    assert p.action["op"] == "add_family_rotation"
    assert p.action["family"] in FA.KNOWN_FAMILIES
    assert p.action["family"] == "algebraic"  # first unused from evidence, deterministic
    assert p.label == "empty_perturb_pool"


def test_surveyor_proposes_cap_raise_when_holds_at_cap(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    FL.ensure_seeded()
    router = FL.train_router()
    p = SL.propose_for_role("surveyor", [_finding(caps=True)], router)
    assert p is not None
    assert p.ok
    assert p.action["op"] == "set_knob"
    assert p.action["name"] == "fast_term_cap"
    assert p.action["direction"] == "up"


def test_surveyor_yields_when_no_cap_holds(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    FL.ensure_seeded()
    router = FL.train_router()
    p = SL.propose_for_role("surveyor", [_finding(caps=False)], router)
    assert p is None


def test_nobody_proposes_already_held_skip(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    FL.ensure_seeded()
    router = FL.train_router()
    proposals = SL.swarm_propose([_finding()], router)
    fps = [p.fingerprint for p in proposals]
    assert all("already_held_range" not in fp for fp in fps)
    assert all(p.action.get("op") != "add_skip_rule" for p in proposals)
    roles = {p.role for p in proposals}
    assert "pathfinder" not in roles
    assert "improver" in roles


def test_archivist_refuses_retrieved_skip_on_empty_pool(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    FL.ensure_seeded()
    router = FL.train_router()
    # Even if retrieval would return the old skip, the archivist must drop it.
    p = SL.propose_for_role("archivist", [_finding()], router)
    if p is not None:
        assert p.action.get("op") != "add_skip_rule"
        assert "already_held_range" not in (p.fingerprint or "")


def test_spent_picks_still_maps_to_skip(tmp_path, monkeypatch):
    """The original no_progress_perturb (session had targets) is unchanged."""
    _isolate(tmp_path, monkeypatch)
    FL.ensure_seeded()
    router = FL.train_router()
    finding = {
        "kind": "no_progress_perturb",
        "evidence": {
            "exit_reason": "timeout",
            "session_targets": ["oc_X"],
            "timeout_count": 1,
        },
    }
    p = SL.propose_for_role("pathfinder", [finding], router)
    assert p is not None
    assert p.action["op"] == "add_skip_rule"
    assert p.action["target_kind"] == "already_held_range"


def test_corrective_hist_seed_is_negative_and_original_is_untouched(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    FL.ensure_seeded()
    rows = {r["id"]: r for r in FL.seed_patterns()}
    assert "seed:pr4:hist-no-candidates-skip" in rows
    assert rows["seed:pr4:hist-no-candidates-skip"]["outcome"] == "positive"
    assert "seed:pr4:hist-no-candidates-skip:p" in rows
    assert rows["seed:pr4:hist-no-candidates-skip:p"]["outcome"] == "positive"
    assert "seed:pr4:hist-no-candidates-skip:corrective" in rows
    corr = rows["seed:pr4:hist-no-candidates-skip:corrective"]
    assert corr["outcome"] == "negative"
    assert corr["label"] == "empty_perturb_pool"
    assert corr["evidence"]["corrects"] == "seed:pr4:hist-no-candidates-skip"
    assert "seed:pr4:hist-no-candidates-skip:p:corrective" in rows
    assert rows["seed:pr4:hist-no-candidates-skip:p:corrective"]["outcome"] == "negative"


def test_wilson_gate_unchanged():
    assert WILSON_ACCEPT_PERMILLE == 700
    assert SL.WILSON_ACCEPT_PERMILLE == 700


def test_improver_prefers_legal_method_card_action():
    """A method-card action in the closed set is what improver proposes."""
    from hive import swarm
    from hive import ops as HO
    finding = {
        "kind": "method_card",
        "card_action": {"op": "set_knob", "name": "desk_budget", "direction": "up"},
        "suggest": [("desk_budget", "up")],
        "evidence": {"card_id": "card_test"},
    }
    action = swarm._action_for_role("improver", finding, None)
    assert action is not None
    assert action["op"] == "set_knob"
    assert action["name"] == "desk_budget"
    v = HO.validate(action)
    assert v.ok, getattr(v, "reason", "")


def test_improver_rejects_card_action_outside_role_ops():
    from hive import swarm
    finding = {
        "kind": "method_card",
        "card_action": {"op": "exec", "code": "print(1)"},
        "evidence": {},
    }
    action = swarm._action_for_role("improver", finding, None)
    # exec is not in the improver op set, so the card is ignored and
    # the usual fallback (preferred knob) may still fire.
    if action is not None:
        assert action.get("op") != "exec"


def _card_finding():
    return {
        "kind": "method_card",
        "card_id": "mc_testcard12",
        "method": "Practice easier cases first.",
        "card_action": {"op": "set_knob", "name": "curriculum_pace", "direction": "up"},
        "suggest": [("curriculum_pace", "up")],
        "evidence": {"card_id": "mc_testcard12", "method": "Practice easier cases first."},
    }


def _dead_end_finding():
    return {
        "kind": "dead_end_streak",
        "evidence": {"streak": 4},
    }


def test_improver_proposes_method_card_ahead_of_earlier_failure(tmp_path, monkeypatch):
    """A method_card finding reaches the vote even if a failure is listed first."""
    _isolate(tmp_path, monkeypatch)
    FL.ensure_seeded()
    router = FL.train_router()
    findings = [_dead_end_finding(), _finding(), _card_finding()]
    p = SL.propose_for_role("improver", findings, router)
    assert p is not None
    assert p.ok
    assert p.label == "method_card"
    assert p.action["op"] == "set_knob"
    assert p.action["name"] == "curriculum_pace"
    assert p.card_id == "mc_testcard12"
    assert p.method == "Practice easier cases first."
    d = p.as_dict()
    assert d["card_id"] == "mc_testcard12"
    # Other roles still propose from their own findings — the card
    # competes in the vote; it does not silence them.
    surveyor = SL.propose_for_role("surveyor", [_finding(caps=True), _card_finding()], router)
    assert surveyor is not None
    assert surveyor.label == "empty_perturb_pool"
    assert surveyor.action["name"] == "fast_term_cap"


def test_improver_falls_back_when_no_method_card(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    FL.ensure_seeded()
    router = FL.train_router()
    p = SL.propose_for_role("improver", [_finding()], router)
    assert p is not None
    assert p.label == "empty_perturb_pool"
    assert p.action["op"] == "add_family_rotation"
    assert p.card_id == ""
