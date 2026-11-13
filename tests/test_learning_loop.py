"""Colony-wide learning loop: method cards, twin gate, shadows, control."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import colony.learning_loop as LL
import hive.ops as HO
import hive.swarm as swarm


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    log = tmp_path / "learning_loop.jsonl"
    state = tmp_path / "learning_loop.json"
    md = tmp_path / "LEARNING.md"
    cards = tmp_path / "method_cards.jsonl"
    monkeypatch.setenv("COLONY_LEARNING_LOG", str(log))
    monkeypatch.setenv("COLONY_LEARNING_STATE", str(state))
    monkeypatch.setenv("COLONY_LEARNING_MD", str(md))
    monkeypatch.setenv("COLONY_METHOD_CARDS", str(cards))
    monkeypatch.setattr(LL, "self_mod_ok", lambda: True)
    # Do not read the live twin scoreboard during unit tests.
    monkeypatch.setattr(LL, "load_twin_arms", lambda: (None, None))
    return {"log": log, "state": state, "md": md, "cards": cards, "tmp": tmp_path}


def _card(cid, method, op):
    return {
        "id": cid,
        "method": method,
        "op": op,
        "evidence": "curriculum learning",
        "source": {"arxiv_id": "2401.00001", "title": "A method", "url": ""},
    }


def test_next_card_is_legal_and_skips_tried(isolated):
    cards = [
        _card("card_aaa", "curriculum", {"op": "set_knob", "name": "curriculum_pace", "direction": "up"}),
        _card("card_bbb", "retry", {"op": "set_knob", "name": "retry_policy_cycles", "direction": "up"}),
    ]
    first = LL.next_card_proposal([], cards=cards)
    assert first is not None
    assert first["card_id"] == "card_aaa"
    ok, reason, _ = LL._validate_action(first["action"])
    assert ok, reason
    # After recording a try, the next untried card is offered.
    st = LL.load_state()
    LL.note_proposal(first, cycle_id="c1", state=st, write=True)
    second = LL.next_card_proposal([], cards=cards, state=LL.load_state())
    assert second is not None
    assert second["card_id"] == "card_bbb"


def test_illegal_and_invariant_ops_rejected(isolated):
    evil = _card("card_evil", "exec", {"op": "exec", "code": "raise SystemExit"})
    inv = _card("card_inv", "oracle", {"op": "set_knob", "name": "P_gate", "direction": "down"})
    # Unknown op is not legal.
    ok, reason, _ = LL._validate_action(evil["op"])
    assert not ok
    prop = LL.next_card_proposal([], cards=[evil, inv])
    assert prop is None


def test_prefer_card_matching_failure_knob(isolated):
    cards = [
        _card("card_aaa", "curriculum", {"op": "set_knob", "name": "curriculum_pace", "direction": "up"}),
        _card("card_park", "park", {"op": "set_knob", "name": "park_cycles", "direction": "up"}),
    ]
    findings = [{"kind": "dead_end_streak", "knob": "park_cycles", "suggest": [("park_cycles", "up")]}]
    prop = LL.next_card_proposal(findings, cards=cards)
    assert prop["card_id"] == "card_park"


def test_attach_card_findings_adds_method_card(isolated):
    cards = [
        _card("card_aaa", "curriculum", {"op": "set_knob", "name": "curriculum_pace", "direction": "up"}),
    ]
    out = LL.attach_card_findings(
        [{"kind": "flat_passes", "evidence": {}}],
        cycle_id="c1",
        cards=cards,
    )
    kinds = [f["kind"] for f in out]
    assert "flat_passes" in kinds
    assert "method_card" in kinds
    mc = next(f for f in out if f["kind"] == "method_card")
    assert mc["card_id"] == "card_aaa"
    assert mc["card_action"]["op"] == "set_knob"
    assert mc["applied_to_live_oracle"] is False


def test_hive_improver_proposes_card_action(isolated):
    """Improver prefers a legal method-card action and Hive validates it."""
    finding = {
        "kind": "method_card",
        "card_action": {"op": "set_knob", "name": "desk_budget", "direction": "up"},
        "card_id": "card_aaa",
        "suggest": [("desk_budget", "up")],
        "evidence": {"card_id": "card_aaa"},
    }
    action = swarm._action_for_role("improver", finding, None)
    assert action is not None
    assert action["op"] == "set_knob"
    assert action["name"] == "desk_budget"
    v = HO.validate(action)
    assert v.ok, getattr(v, "reason", "")


def test_decide_keep_requires_both_gates(isolated):
    # Self-heal not better → no keep, even if treatment leads.
    d = LL.decide_keep(
        trial_score=1.0, baseline_score=2.0,
        treatment={"oracle_passes": 530, "verified_depth_sum": 9300, "fitness": 0.9},
        control={"oracle_passes": 528, "verified_depth_sum": 9228, "fitness": 0.85},
    )
    assert d["keep"] is False
    assert d["reason"] == "self_heal_not_better"
    # Self-heal better, twin tied on passes and depth → fitness-only is not a keep.
    d = LL.decide_keep(
        trial_score=2.0, baseline_score=0.0,
        treatment={"oracle_passes": 528, "verified_depth_sum": 9228, "fitness": 0.90},
        control={"oracle_passes": 528, "verified_depth_sum": 9228, "fitness": 0.85},
    )
    assert d["keep"] is False
    assert d["reason"] == "twin_not_better"
    assert d["self_heal_helped"] is True
    # Both: more Oracle passes, and trial > baseline.
    d = LL.decide_keep(
        trial_score=2.0, baseline_score=0.0,
        treatment={"oracle_passes": 529, "verified_depth_sum": 9228, "fitness": 0.85},
        control={"oracle_passes": 528, "verified_depth_sum": 9228, "fitness": 0.85},
    )
    assert d["keep"] is True
    assert d["reason"] == "kept"
    # Missing control fails closed.
    d = LL.decide_keep(
        trial_score=2.0, baseline_score=0.0,
        treatment={"oracle_passes": 529, "verified_depth_sum": 9228},
        control=None,
    )
    assert d["keep"] is False
    assert d["reason"] == "twin_unavailable"
    # Equal is not strictly better; depth lead with tied passes is a keep.
    d = LL.decide_keep(
        trial_score=2.0, baseline_score=1.0,
        treatment={"oracle_passes": 528, "verified_depth_sum": 9300, "fitness": 0.85},
        control={"oracle_passes": 528, "verified_depth_sum": 9228, "fitness": 0.85},
    )
    assert d["keep"] is True
    assert d["twin"]["reason"] == "verified_depth"


def test_labeled_examples_update_card_and_family_rates(isolated):
    st = LL.load_state()
    LL.record_example(
        {"outcome": "kept", "card_id": "card_aaa", "method": "curriculum",
         "action": {"op": "set_knob", "name": "curriculum_pace", "direction": "up"},
         "cycle_id": "c1", "baseline_score": 0, "trial_score": 2, "id": "e1"},
        state=st, write=True,
    )
    LL.record_example(
        {"outcome": "reverted", "card_id": "card_aaa", "method": "curriculum",
         "action": {"op": "set_knob", "name": "curriculum_pace", "direction": "up"},
         "cycle_id": "c2", "baseline_score": 2, "trial_score": 0, "id": "e2"},
        state=st, write=True,
    )
    st = LL.load_state()
    card = st["cards"]["card_aaa"]
    assert card["n"] == 2
    assert card["kept"] == 1
    assert card["reverted"] == 1
    assert card["keep_rate_permille"] == 500
    fam = st["families"]["set_knob:curriculum_pace"]
    assert fam["n"] == 2
    assert fam["kept"] == 1
    # Idempotent: same id is not counted twice.
    LL.record_example(
        {"outcome": "kept", "card_id": "card_aaa", "method": "curriculum",
         "action": {"op": "set_knob", "name": "curriculum_pace"},
         "id": "e1"},
        state=st, write=True,
    )
    st = LL.load_state()
    assert st["cards"]["card_aaa"]["n"] == 2
    assert isolated["log"].exists()
    lines = isolated["log"].read_text().strip().splitlines()
    assert len(lines) == 2


def test_harvest_provisional_then_twin_keep_and_revert(isolated):
    evidence = [{
        "event": "adopt",
        "id": "heal1",
        "knob": "desk_budget",
        "direction": "up",
        "to": 3,
        "from": 2,
        "trial_score": 2.0,
        "baseline_score": 0.0,
        "cycle_id": "c1",
        "card_id": "card_aaa",
        "method": "budget",
    }]
    st = LL.load_state()
    LL.note_proposal(
        {"card_id": "card_aaa", "method": "budget",
         "action": {"op": "set_knob", "name": "desk_budget", "direction": "up"}},
        cycle_id="c1", state=st, write=False,
    )
    # No twin snapshot → provisional, not kept.
    rows = LL.harvest_outcomes(
        "c1", state=st, evidence=evidence,
        treatment=None, control=None, write=True,
    )
    assert rows and rows[0]["outcome"] == "provisional_adopt"
    st = LL.load_state()
    assert st["n_kept"] == 0
    assert len(st["twin_pending"]) == 1
    # Twin: treatment leads on passes → kept.
    judged = LL.judge_twin_pending(
        treatment={"oracle_passes": 529, "verified_depth_sum": 9228, "fitness": 0.86},
        control={"oracle_passes": 528, "verified_depth_sum": 9228, "fitness": 0.86},
        state=st, write=True,
    )
    assert judged and judged[0]["outcome"] == "kept"
    st = LL.load_state()
    assert st["n_kept"] == 1
    assert st["twin_pending"] == []
    # A second adopt whose twin is tied is a twin-revert, not a keep.
    ev2 = [{**evidence[0], "id": "heal2", "cycle_id": "c2"}]
    st = LL.load_state()
    rows = LL.harvest_outcomes(
        "c2", state=st, evidence=ev2,
        treatment={"oracle_passes": 528, "verified_depth_sum": 9228, "fitness": 0.9},
        control={"oracle_passes": 528, "verified_depth_sum": 9228, "fitness": 0.8},
        write=True,
    )
    assert rows[0]["outcome"] == "reverted_twin"
    st = LL.load_state()
    assert st["n_reverted"] == 1
    assert st["n_kept"] == 1


def test_shadow_score_counts_resolved(isolated):
    hive_state = {
        "shadows": [
            {"id": "s1", "resolved": True, "correct": True},
            {"id": "s2", "resolved": True, "correct": False},
            {"id": "s3", "resolved": False},
        ]
    }
    s = LL.score_shadows(hive_state)
    assert s["resolved"] == 2
    assert s["correct"] == 1
    assert s["incorrect"] == 1
    assert s["pending"] == 1
    assert s["accuracy_permille"] == 500


def test_control_is_noop(isolated, monkeypatch):
    monkeypatch.setattr(LL, "self_mod_ok", lambda: False)
    cards = [_card("card_aaa", "curriculum", {"op": "set_knob", "name": "curriculum_pace", "direction": "up"})]
    assert LL.next_card_proposal([], cards=cards) is None
    out = LL.attach_card_findings([{"kind": "flat_passes"}], cards=cards)
    assert all(f.get("kind") != "method_card" for f in out)
    result = LL.run_cycle("c1")
    assert result["ran"] is False
    assert result["reason"] == "control_arm"
    assert not isolated["log"].exists()
    assert not isolated["state"].exists()


def test_pytest_does_not_write_repo(tmp_path, monkeypatch):
    """Un-isolated paths under the repo must not be written during pytest."""
    # The fixture is NOT used: default paths are in the repo.
    monkeypatch.delenv("COLONY_LEARNING_LOG", raising=False)
    monkeypatch.delenv("COLONY_LEARNING_STATE", raising=False)
    monkeypatch.delenv("COLONY_LEARNING_MD", raising=False)
    # PYTEST_CURRENT_TEST is already set by pytest.
    assert LL._pytest_would_write_repo(LL.log_path()) is True
    assert LL._pytest_would_write_repo(LL.state_path()) is True
    before_log = LL.log_path().exists()
    before_state = LL.state_path().exists()
    before_md = LL.markdown_path().exists()
    st = LL._empty_state()
    LL.record_example(
        {"outcome": "kept", "card_id": "card_should_not_land", "action": {"op": "set_knob", "name": "desk_budget"},
         "id": "no-write"},
        state=st, write=True,
    )
    LL.write_markdown(st)
    assert LL.log_path().exists() == before_log
    assert LL.state_path().exists() == before_state
    assert LL.markdown_path().exists() == before_md


def test_evil_payload_is_not_executed(isolated):
    """A card that tries to carry code is refused; nothing is exec'd."""
    ran = {"hit": False}

    def _boom(*a, **k):
        ran["hit"] = True
        raise AssertionError("must not execute")

    # If any path tried to exec/eval the payload, the test would fail.
    cards = [_card("card_x", "evil", {"op": "exec", "code": "import os; os.system('true')"})]
    prop = LL.next_card_proposal([], cards=cards)
    assert prop is None
    assert ran["hit"] is False


def test_desks_expose_bounded_knobs():
    from hive.ops import KNOWN_DESKS
    from colony.self_heal import KNOB_SPECS
    registry = LL.desk_knobs()
    for desk in KNOWN_DESKS:
        assert desk in registry, f"{desk} has no bounded knobs"
        assert registry[desk], f"{desk} empty"
    ok, missing = LL.knobs_are_bounded(KNOB_SPECS)
    assert ok, missing


def test_run_cycle_fail_soft(isolated, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("nope")
    monkeypatch.setattr(LL, "load_state", _boom)
    result = LL.run_cycle("c1")
    assert result["ran"] is False
    assert result["reason"].startswith("error:")


def test_render_markdown_and_dashboard_are_plain_english(isolated):
    st = LL.load_state()
    LL.record_example(
        {"outcome": "kept", "card_id": "card_aaa", "method": "curriculum pacing",
         "action": {"op": "set_knob", "name": "curriculum_pace"},
         "cycle_id": "c1", "baseline_score": 0, "trial_score": 2, "id": "e1"},
        state=st, write=True,
    )
    st = LL.load_state()
    st["shadow"] = {"pending": 1, "resolved": 2, "correct": 1, "accuracy_permille": 500}
    md = LL.render_markdown(st)
    assert "Method cards tried" in md
    assert "Kept" in md
    assert "Reverted" in md
    assert "card_aaa" in md
    assert "Not AGI" in md
    html = LL.dashboard_section(st)
    assert "Method cards tried, kept, reverted" in html
    assert "card_aaa" in html
    vis = LL.format_visibility(st)
    assert "kept" in vis and "reverted" in vis
    LL.write_markdown(st)
    assert isolated["md"].exists()
    assert "curriculum pacing" in isolated["md"].read_text()


def test_card_proposal_from_hive_result(isolated):
    from colony.hive_adapter import card_proposal_from_result
    result = {
        "proposals": [
            {"role": "surveyor", "label": "depth_at_physical_cap",
             "action": {"op": "set_knob", "name": "fast_term_cap", "direction": "up"},
             "card_id": ""},
            {"role": "improver", "label": "method_card",
             "action": {"op": "set_knob", "name": "curriculum_pace", "direction": "up"},
             "card_id": "mc_8efa602cd2c2", "method": "curriculum",
             "fingerprint": "fp1"},
        ]
    }
    card = card_proposal_from_result(result)
    assert card is not None
    assert card["card_id"] == "mc_8efa602cd2c2"
    assert card["action"]["name"] == "curriculum_pace"
    assert card_proposal_from_result({"proposals": []}) is None
    assert card_proposal_from_result(None) is None


def test_adapter_on_cycle_passes_proposal(isolated, monkeypatch):
    """hive_adapter.on_cycle forwards the card proposal to learning_loop."""
    import colony.hive_adapter as HA
    seen = {}

    def _swarm(cycle_id=""):
        return {
            "ok": True,
            "proposals": [{
                "role": "improver", "label": "method_card",
                "action": {"op": "set_knob", "name": "curriculum_pace", "direction": "up"},
                "card_id": "mc_abc", "method": "curriculum",
                "fingerprint": "fp",
            }],
        }

    def _ll(cycle_id="", proposal=None, **k):
        seen["cycle_id"] = cycle_id
        seen["proposal"] = proposal
        return {"ran": True, "got": proposal}

    monkeypatch.setattr(HA, "hive_learning_enabled", lambda: True)
    monkeypatch.setattr(HA.swarm, "on_cycle", _swarm)
    import colony.learning_loop as LLmod
    monkeypatch.setattr(LLmod, "on_cycle", _ll)
    # hive_adapter imports _ll inside the function; patch the module it imports
    import sys
    monkeypatch.setitem(sys.modules, "colony.learning_loop", LLmod)
    out = HA.on_cycle("c1")
    assert seen["cycle_id"] == "c1"
    assert seen["proposal"] is not None
    assert seen["proposal"]["card_id"] == "mc_abc"
    assert out["learning_loop"]["got"]["card_id"] == "mc_abc"


def test_evolve_workflow_adds_learning_md_and_live_state():
    from pathlib import Path
    text = Path(".github/workflows/colony-evolve.yml").read_text(encoding="utf-8")
    assert "society/LEARNING.md" in text
    assert "data/society_state.live.json" in text
    assert "data/society_state.segments.json" in text
    # Frozen snapshot is still added, never rewritten by this change.
    assert "git add data/society_state.json" in text


def test_note_hive_deferral_and_visibility(isolated):
    import colony.learning_loop as LL
    from hive.bitwork import WILSON_ACCEPT_PERMILLE
    pending = {
        "fingerprint": "set_knob:direction=up:name=park_cycles",
        "label": "dead_end_streak",
        "action": {"op": "set_knob", "name": "park_cycles", "direction": "up"},
        "deferred_count": 4,
        "deferred_under": "abc123",
        "wilson_gate": WILSON_ACCEPT_PERMILLE,
    }
    row = LL.note_hive_deferral(pending, cycle_id="c4")
    assert row is not None
    assert row["event"] == "hive_deferred"
    assert row["deferred_count"] == 4
    # Same count is not logged twice.
    assert LL.note_hive_deferral(pending, cycle_id="c5") is None
    st = LL.load_state()
    assert st["last_hive_deferral"]["deferred_count"] == 4
    vis = LL.format_visibility(st)
    assert "deferred 4 times" in vis
    md = LL.render_markdown(st)
    assert "deferred **4** times" in md
    assert "Wilson 700" in md
    assert WILSON_ACCEPT_PERMILLE == 700


def test_run_cycle_records_pending_apply(isolated, monkeypatch):
    import colony.learning_loop as LL
    monkeypatch.setattr(LL, "harvest_outcomes", lambda *a, **k: [])
    monkeypatch.setattr(LL, "judge_twin_pending", lambda *a, **k: [])
    monkeypatch.setattr(LL, "score_shadows", lambda *a, **k: {"pending": 0, "resolved": 0})
    out = LL.run_cycle(
        "c1",
        proposal={"card_id": "mc_8efa602cd2c2", "method": "curriculum",
                  "action": {"op": "set_knob", "name": "curriculum_pace", "direction": "up"},
                  "fingerprint": "set_knob:direction=up:name=curriculum_pace"},
        pending_apply={
            "fingerprint": "set_knob:direction=up:name=curriculum_pace",
            "label": "method_card",
            "card_id": "mc_8efa602cd2c2",
            "deferred_count": 2,
            "deferred_under": "fpX",
        },
    )
    assert out["ran"] is True
    assert out["deferred"]["deferred_count"] == 2
    st = LL.load_state()
    proposed = st["pending"][-1]
    assert proposed["card_id"] == "mc_8efa602cd2c2"
    assert proposed["deferred_count"] == 2
    log = LL.load_log()
    ev = [r for r in log if r.get("event") == "hive_deferred"]
    assert ev and ev[-1]["deferred_count"] == 2


def test_adapter_forwards_pending_apply(isolated, monkeypatch):
    import colony.hive_adapter as HA
    import colony.learning_loop as LLmod
    seen = {}

    def _swarm(cycle_id=""):
        return {
            "ok": True,
            "proposals": [{
                "role": "improver", "label": "method_card",
                "action": {"op": "set_knob", "name": "curriculum_pace", "direction": "up"},
                "card_id": "mc_abc", "method": "curriculum",
                "fingerprint": "fp",
            }],
            "pending_apply": {
                "fingerprint": "fp",
                "deferred_count": 3,
                "card_id": "mc_abc",
                "label": "method_card",
            },
        }

    def _ll(cycle_id="", proposal=None, pending_apply=None, **k):
        seen["proposal"] = proposal
        seen["pending_apply"] = pending_apply
        return {"ran": True, "deferred": pending_apply}

    monkeypatch.setattr(HA, "hive_learning_enabled", lambda: True)
    monkeypatch.setattr(HA.swarm, "on_cycle", _swarm)
    monkeypatch.setattr(LLmod, "on_cycle", _ll)
    import sys
    monkeypatch.setitem(sys.modules, "colony.learning_loop", LLmod)
    out = HA.on_cycle("c1")
    assert seen["pending_apply"]["deferred_count"] == 3
    assert seen["proposal"]["card_id"] == "mc_abc"
    assert out["learning_loop"]["deferred"]["deferred_count"] == 3
