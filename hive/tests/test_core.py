"""Hive core tests: ops, library, vote, teach. No colony imports."""
from __future__ import annotations

import hive.ops as FA
import hive.library as FL
import hive.swarm as SL
from hive import host
from hive.bitwork import (
    WILSON_ACCEPT_PERMILLE,
    Router,
    wilson_lower_permille,
)


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(FL, "LIBRARY_LOG", tmp_path / "fix_library.jsonl")
    monkeypatch.setattr(SL, "STATE_PATH", tmp_path / "swarm_learn.json")
    monkeypatch.setattr(SL, "EVENT_LOG", tmp_path / "swarm_learn.jsonl")
    monkeypatch.setattr(SL, "RULES_PATH", tmp_path / "swarm_rules.json")


def _prime_calibration(router: Router, n: int = 9, margin: int = 16) -> None:
    for _ in range(n):
        router.record_outcome(margin, True)


def test_every_op_is_in_the_closed_vocabulary():
    assert FA.OPS == frozenset({
        "set_knob", "add_skip_rule", "add_park_rule", "reorder_desk",
        "add_family_rotation", "mark_ceiling", "add_triviality_candidate",
    })


def test_set_knob_rejects_invariants_and_out_of_bounds(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    for name in (
        "oracle_p", "p_min", "authored_cap", "athanor", "witness",
        "human_authorize", "human_guide", "w_targets", "standing_trust",
        "live_oracle", "delta_phi",
    ):
        v = FA.validate({"op": "set_knob", "name": name, "direction": "down"})
        assert v.ok is False, name
        assert v.reason in ("invariant", "unknown_or_invariant_knob"), (name, v.reason)
    v = FA.validate({"op": "set_knob", "name": "park_cycles", "value": 999})
    assert v.ok is False
    assert v.reason == "out_of_bounds"
    v = FA.validate({"op": "set_knob", "name": "park_cycles", "direction": "up"})
    assert v.ok is True
    assert v.payload["name"] == "park_cycles"
    assert host.heal_in_bounds("park_cycles", v.payload["value"])


def test_skip_park_family_desk_ceiling_bounds():
    assert FA.validate({"op": "add_skip_rule"}).ok is False
    assert FA.validate({"op": "add_skip_rule", "target_kind": "empty_label", "cycles": 0}).ok is False
    assert FA.validate({"op": "add_skip_rule", "target_kind": "empty_label", "cycles": 8}).ok is True
    assert FA.validate({"op": "add_park_rule", "target_kind": "dead_end", "cycles": 2}).ok is False
    assert FA.validate({"op": "add_park_rule", "chain": "proof:7", "cycles": 12}).ok is True
    assert FA.validate({"op": "add_family_rotation", "family": "not-a-family"}).ok is False
    assert FA.validate({"op": "add_family_rotation", "family": "goldbach"}).ok is True
    assert FA.validate({"op": "reorder_desk", "order": ["conjecture", "mystery"]}).ok is False
    assert FA.validate({"op": "reorder_desk", "order": ["conjecture", "hunt"]}).ok is True
    assert FA.validate({"op": "reorder_desk", "order": ["conjecture", "conjecture"]}).ok is False
    assert FA.validate({"op": "mark_ceiling", "target": "A165064"}).ok is False
    assert FA.validate({"op": "mark_ceiling", "target": "A165064", "depth": 1200}).ok is True
    # Invariant fragments cannot hide in a target or reason.
    assert FA.validate({"op": "mark_ceiling", "target": "oracle_p", "depth": 10}).ok is False
    assert FA.validate({
        "op": "mark_ceiling", "target": "A1", "depth": 10, "reason": "lower_athanor",
    }).ok is False


def test_unknown_op_and_triviality_routed_to_checker():
    assert FA.validate({"op": "rewrite_oracle", "value": 0}).ok is False
    v = FA.validate({
        "op": "add_triviality_candidate",
        "pattern": "textbook identity restated",
        "pattern_type": "literal",
    })
    assert v.ok is True
    assert v.payload["routed_to"] == "checker_lane"
    assert v.payload["applied_to_live_oracle"] is False
    # Empty or invariant-touching patterns are rejected.
    assert FA.validate({"op": "add_triviality_candidate", "pattern": ""}).ok is False
    assert FA.validate({
        "op": "add_triviality_candidate", "pattern": "loosen oracle_threshold",
    }).ok is False


def test_touches_invariant_covers_fragments():
    assert FA.touches_invariant("p_min")
    assert FA.touches_invariant("Pmin")
    assert FA.touches_invariant("live_oracle")
    assert FA.touches_invariant("human_guide")
    assert not FA.touches_invariant("park_cycles")
    assert not FA.touches_invariant("fast_term_cap")


def test_seed_patterns_are_deterministic_and_validate(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    a = FL.seed_patterns()
    b = FL.seed_patterns()
    assert [p["id"] for p in a] == [p["id"] for p in b]
    # 14 positive + 14 paraphrases + 2 negative invariant examples.
    assert len(a) == 30
    positives = [p for p in a if p["outcome"] == "positive"]
    negatives = [p for p in a if p["outcome"] == "negative"]
    assert len(positives) == 28
    assert len(negatives) == 2
    for p in positives:
        v = FA.validate(p["action"])
        assert v.ok is True, (p["id"], v.reason)
    for p in negatives:
        v = FA.validate(p["action"])
        assert v.ok is False
        assert "invariant" in v.reason or "unknown" in v.reason


def test_library_is_append_only(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    written = FL.ensure_seeded()
    assert len(written) == 30
    # A second seed write adds nothing (same ids).
    again = FL.ensure_seeded()
    assert again == []
    rows = FL.load_records()
    assert len(rows) == 30
    # Appending a new record grows the log; existing ids are refused.
    extra = FL.append_record({
        "id": "live:example:1",
        "source": "self_heal",
        "kind": "fix",
        "label": "repeated_targets",
        "symptom": "a live adopt of park_cycles after a stall loop",
        "action": {"op": "set_knob", "name": "park_cycles", "direction": "up"},
        "outcome": "positive",
    })
    assert extra is not None
    assert FL.append_record({"id": "live:example:1", "symptom": "changed"}) is None
    rows = FL.load_records()
    assert len(rows) == 31
    # The original first line is unchanged (append-only, no rewrite).
    first = FL.load_records()[0]
    assert first["id"] == written[0]["id"]
    assert first["symptom"] == written[0]["symptom"]


def test_held_out_replay_accuracy_on_seeds(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    FL.ensure_seeded()
    router = FL.train_router()
    cases = FL.held_out_cases()
    assert len(cases) == 28
    result = router.replay_accuracy(cases, hold_out=True)
    # Raw top-1: every paraphrase retrieves its sibling's action.
    assert result["n"] == 28
    assert result["correct"] == 28
    assert result["accuracy_permille"] == 1000
    assert result["lower_permille"] == wilson_lower_permille(28, 28)
    assert result["lower_permille"] >= WILSON_ACCEPT_PERMILLE
    # The live Wilson *gate* still abstains: calibration buckets are empty.
    assert result["abstained"] == 28
    hit = router.classify(cases[0][0])
    assert hit is not None
    assert hit.abstained is True
    assert hit.accepted is False


def test_train_router_is_deterministic(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    FL.ensure_seeded()
    a = FL.train_router()
    b = FL.train_router()
    assert a.library_size() == b.library_size()
    text = "the evaluator hit a built-in term cap depth at physical cap"
    assert a.classify(text).action_key == b.classify(text).action_key
    assert a.classify(text).score == b.classify(text).score


def test_swarm_vote_majority_and_tie_break():
    router = Router()
    # Two roles agree, one disagrees. Majority wins.
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
    # Prime the gate so a win can be accepted.
    _prime_calibration(router)
    # Score the agreeing action so the winner carries a passing match.
    router.learn(
        "stall loop same targets", "repeated_targets",
        "set_knob:direction=up:name=park_cycles", proto_key="s1",
    )
    # Re-score after calibration (learn doesn't set accepted on old matches).
    for p in (a, b, c):
        p.match = router.score_action(p.symptom, p.fingerprint)
    # Force the winner's match to use the primed bucket by recording
    # against whatever margin score_action produced, then re-score.
    if a.match is not None:
        _prime_calibration(router, margin=a.match.margin)
        a.match = router.score_action(a.symptom, a.fingerprint)
        b.match = router.score_action(b.symptom, b.fingerprint)
    result = SL.vote([a, b, c], router)
    assert result.winner is not None
    assert result.winner.fingerprint == "set_knob:direction=up:name=park_cycles"
    assert result.tallies[result.winner.fingerprint] == 2
    assert result.abstained is False
    assert result.reason == "accepted"
    assert result.lower_permille >= WILSON_ACCEPT_PERMILLE


def test_wilson_gate_abstains_when_uncalibrated():
    router = Router()
    p = SL.Proposal(
        role="improver", label="repeated_targets",
        action={"op": "set_knob", "name": "park_cycles", "direction": "up"},
        fingerprint="set_knob:direction=up:name=park_cycles",
        symptom="stall loop",
    )
    result = SL.vote([p], router)
    assert result.abstained is True
    assert result.reason == "wilson_abstain"
    assert result.lower_permille < WILSON_ACCEPT_PERMILLE
    assert result.winner is not None  # the winner is known, just not applied


def test_legislator_vetoes_invariant_proposals():
    router = Router()
    _prime_calibration(router)
    bad = SL.Proposal(
        role="improver", label="invariant_touch",
        action={"op": "set_knob", "name": "oracle_p", "direction": "down"},
        fingerprint="set_knob:direction=down:name=oracle_p",
        symptom="lower the oracle threshold",
        ok=True,
    )
    result = SL.vote([bad], router)
    assert result.winner is None
    assert result.abstained is True
    assert result.n_vetoes == 1
    assert result.reason == "no_legal_proposal"


def test_teach_from_adopt_and_revert_compounds(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    FL.ensure_seeded()
    router = FL.train_router()
    before = router.library_size()
    adopt = {
        "event": "adopt",
        "id": "ev-adopt-1",
        "cycle_id": "c10",
        "knob": "fast_term_cap",
        "direction": "up",
        "to": 10000,
        "from": 8000,
        "reason": "depth_at_physical_cap",
        "label": "depth_at_physical_cap",
        "symptom": "evaluator hit a new physical cap on a held algebraic target",
        "baseline_score": 0.0,
        "trial_score": 2.0,
        "helped": True,
    }
    written = SL.teach_from_event(router, adopt)
    assert written is not None
    assert written["outcome"] == "positive"
    assert router.library_size() == before + 1
    # A second write of the same id does not grow the library.
    assert SL.teach_from_event(router, adopt) is None
    assert router.library_size() == before + 1
    revert = {
        "event": "revert",
        "id": "ev-rev-1",
        "cycle_id": "c11",
        "knob": "perturb_epsilon",
        "direction": "up",
        "reason": "flat_passes",
        "label": "flat_passes",
        "symptom": "raising epsilon did not produce new oracle-reaching targets",
        "baseline_score": 1.0,
        "trial_score": 1.0,
        "helped": False,
    }
    written_r = SL.teach_from_event(router, revert)
    assert written_r is not None
    assert written_r["outcome"] == "negative"
    assert router.library_size() == before + 2
    # The reverted action is stored as a negative prototype.
    negs = [p for p in router.prototypes if p.polarity == "negative"]
    assert any(p.source_id == written_r["id"] for p in negs)


def test_at_most_one_action_per_cycle_constant():
    assert SL.MAX_ACTIONS_PER_CYCLE == 1
    assert SL.MAX_ACTIONS_PER_CYCLE <= 2


def test_run_cycle_seeds_library_and_abstains_early(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    # No findings: still seeds the library and reports a learning-curve point.
    out = SL.run_cycle("c0")
    assert out["ok"] is True
    assert out["applied_to_live_oracle"] is False
    assert out["authorized"] is False
    assert out["library_size"] >= 28
    assert FL.load_records()
    vis = SL.visibility()
    assert vis["swarm_library_size"] >= 28
    assert vis["swarm_replay_accuracy_permille"] == 1000
    assert vis["swarm_max_actions_per_cycle"] == 1
    assert vis["swarm_roles"] == list(SL.SWARM_ROLES)
    # With findings but an uncalibrated gate, the cycle abstains.
    finding = {"kind": "repeated_targets", "evidence": {"targets": ["A1"], "cycles_with_tries": ["c0"]}}
    monkeypatch.setattr(SL, "observe", lambda cycle_id="": [finding])
    out2 = SL.run_cycle("c1")
    assert out2["ok"] is True
    vote = out2.get("vote")
    # May be None if observe was used after trial state; otherwise abstain.
    if vote is not None:
        assert vote["abstained"] is True
    st = SL.load_state()
    assert st["abstained_count"] >= 1
    assert st["applied_count"] == 0


def test_on_cycle_swallows_exceptions(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    def _boom(*a, **k):
        raise RuntimeError("swarm failed")

    monkeypatch.setattr(SL, "run_cycle", _boom)
    out = SL.on_cycle("c1")
    assert out["ok"] is False
    assert "RuntimeError" in out["error"]
    assert out["applied_to_live_oracle"] is False
    assert out["authorized"] is False


def test_learning_curve_fields(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    FL.ensure_seeded()
    st = SL.load_state()
    st["adopted_count"] = 2
    st["reverted_count"] = 1
    st["first_seen"] = {"repeated_targets": {"cycle_id": "c0", "index": 2}}
    st["first_adopted"] = {"repeated_targets": {"cycle_id": "c5", "index": 7}}
    router = FL.train_router()
    point = SL.learning_curve_point(router, st, cycle_id="c5")
    assert point["library_size"] == router.library_size()
    assert point["replay_accuracy_permille"] == 1000
    assert point["adopt_rate_permille"] == 666  # 2/3
    assert point["time_to_fix"]["n"] == 1
    assert point["time_to_fix"]["mean"] == 5
    assert point["time_to_fix"]["by_kind"]["repeated_targets"] == 5
    assert point["applied_to_live_oracle"] is False


def test_format_visibility_plain_wording(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    line = SL.format_visibility()
    for banned in ("conscious", "consciousness", "breakthrough", "AGI", "sentient"):
        assert banned.lower() not in line.lower()


def test_voided_trial_is_not_taught(tmp_path, monkeypatch):
    """A trial_voided_confound event is neither a positive nor a negative example."""
    from hive.bitwork import Router
    import hive.library as FL
    import hive.swarm as SL
    monkeypatch.setattr(FL, "LIBRARY_LOG", tmp_path / "fix_library.jsonl")
    router = Router()
    ev = {
        "event": "trial_voided_confound",
        "id": "void1",
        "cycle_id": "c1",
        "knob": "perturb_cooldown_cycles",
        "from": 8, "to": 6, "direction": "up",
        "reason": "environment_changed",
        "adopted": False, "reverted": False,
        "baseline_score": 0.0, "trial_score": 2.0,
    }
    assert SL.teach_from_event(router, ev) is None
    ev_rule = dict(ev, via="swarm_rule", action={"op": "add_park_rule", "target_kind": "dead_end", "cycles": 12}, knob=None)
    assert SL.teach_from_event(router, ev_rule) is None
    assert FL.load_records() == []
    assert router.library_size() == 0

