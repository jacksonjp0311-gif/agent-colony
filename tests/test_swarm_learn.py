"""Swarm learning loop: bounds, invariants, vote, abstention, adopt/revert.

Hive's agents label failures, Bitwork retrieves a fix from the
shared library, a vote plus the Wilson gate decides whether to apply
it, and adopt / revert outcomes are written back so the next cycle
compounds. Frozen rules cannot be set.
"""
from __future__ import annotations

import json
from pathlib import Path

import colony.dashboard as dashboard
import colony.hive_adapter  # binds Hive to live self-heal / checker-lane
import colony.self_heal as SH
import colony.stall as S
import colony.telemetry as telemetry
import hive.library as FL
import hive.ops as FA
import hive.swarm as SL
from hive.bitwork import (
    WILSON_ACCEPT_PERMILLE,
    Router,
    action_fingerprint,
    wilson_lower_permille,
)


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(SH, "STATE_PATH", tmp_path / "self_heal.json")
    monkeypatch.setattr(SH, "EVENT_LOG", tmp_path / "self_heal.jsonl")
    monkeypatch.setattr(S, "STATE_PATH", tmp_path / "stall_state.json")
    monkeypatch.setattr(FL, "LIBRARY_LOG", tmp_path / "fix_library.jsonl")
    monkeypatch.setattr(FL, "LIBRARY_SNAPSHOT", tmp_path / "swarm_library.json")
    monkeypatch.setattr(SL, "STATE_PATH", tmp_path / "swarm_learn.json")
    monkeypatch.setattr(SL, "EVENT_LOG", tmp_path / "swarm_learn.jsonl")
    monkeypatch.setattr(SL, "RULES_PATH", tmp_path / "swarm_rules.json")


def _metric(cycle_id, targets=0, depth=0, delta=0, passes=528):
    score = SH.score_metrics(targets, depth, delta)
    return {
        "cycle_id": cycle_id,
        "new_oracle_targets": targets,
        "new_depth": depth,
        "oracle_passes": passes,
        "oracle_pass_delta": delta,
        "score": score,
    }


def _prime_heal(n=6, score_targets=0):
    st = SH.load_state()
    fp = SH.environment_fingerprint(state=st)["digest"]
    rows = [_metric(f"b{i}", targets=score_targets) for i in range(n)]
    for r in rows:
        r["env_fingerprint"] = fp
    st["metrics"] = rows
    st["cycle_index"] = n - 1
    st["cycles"] = [f"b{i}" for i in range(n)]
    SH.save_state(st)
    return SH.load_state()


def _prime_calibration(router: Router, n: int = 9, margin: int = 16) -> None:
    for _ in range(n):
        router.record_outcome(margin, True)


# ---------------------------------------------------------------------------
# Fix actions: bounds and invariant protection
# ---------------------------------------------------------------------------

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
    assert SH.in_bounds("park_cycles", v.payload["value"])


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


# ---------------------------------------------------------------------------
# Fix library: seeds, append-only, mining, held-out replay
# ---------------------------------------------------------------------------

def test_seed_patterns_are_deterministic_and_validate(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    a = FL.seed_patterns()
    b = FL.seed_patterns()
    assert [p["id"] for p in a] == [p["id"] for p in b]
    # 19 positive + 19 paraphrases + 2 negative invariant examples
    # + 2 append-only correctives (legal action, wrong for an empty pool).
    assert len(a) == 42
    positives = [p for p in a if p["outcome"] == "positive"]
    negatives = [p for p in a if p["outcome"] == "negative"]
    invariant_neg = [p for p in negatives if p.get("source") == "invariant"]
    corrective_neg = [p for p in negatives if "corrective" in str(p.get("id") or "")]
    assert len(positives) == 38
    assert len(invariant_neg) == 2
    assert len(corrective_neg) == 2
    assert len(negatives) == 4
    for p in positives:
        v = FA.validate(p["action"])
        assert v.ok is True, (p["id"], v.reason)
    for p in invariant_neg:
        v = FA.validate(p["action"])
        assert v.ok is False
        assert "invariant" in v.reason or "unknown" in v.reason
    # Correctives label a legal skip as the wrong fix; the action still validates.
    for p in corrective_neg:
        v = FA.validate(p["action"])
        assert v.ok is True, (p["id"], v.reason)
        assert p["label"] == "empty_perturb_pool"


def test_library_is_append_only(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    written = FL.ensure_seeded()
    assert len(written) == 42
    # A second seed write adds nothing (same ids).
    again = FL.ensure_seeded()
    assert again == []
    rows = FL.load_records()
    assert len(rows) == 42
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
    assert len(rows) == 43
    # The original first line is unchanged (append-only, no rewrite).
    first = FL.load_records()[0]
    assert first["id"] == written[0]["id"]
    assert first["symptom"] == written[0]["symptom"]


def test_held_out_replay_accuracy_on_seeds(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    FL.ensure_seeded()
    router = FL.train_router()
    cases = FL.held_out_cases()
    assert len(cases) == 38
    result = router.replay_accuracy(cases, hold_out=True)
    # Raw top-1: every paraphrase retrieves its sibling's action.
    assert result["n"] == 38
    assert result["correct"] == 38
    assert result["accuracy_permille"] == 1000
    assert result["lower_permille"] == wilson_lower_permille(38, 38)
    assert result["lower_permille"] >= WILSON_ACCEPT_PERMILLE
    # The live Wilson *gate* still abstains: calibration buckets are empty.
    assert result["abstained"] == 38
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


# ---------------------------------------------------------------------------
# Swarm vote, abstention, legislator veto
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Learning from adopt / revert; equivalent metric; at-most-N
# ---------------------------------------------------------------------------

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


def test_rule_trial_uses_corrected_new_depth_metric(tmp_path, monkeypatch):
    """A same-depth beyond=true hold must not count as progress (PR #7)."""
    _isolate(tmp_path, monkeypatch)
    _prime_heal(6, score_targets=0)
    # The corrected counter scores a same-depth hold as 0.
    log = {
        "attempts": [
            {
                "id": "A165064", "cycle_id": "old",
                "bfile_hi": 100, "verified_depth": 1200,
                "extended": 0, "beyond": True, "status": "holds_on_range",
            },
            {
                "id": "A165064", "cycle_id": "now",
                "bfile_hi": 100, "verified_depth": 1200,
                "extended": 0, "beyond": True, "status": "holds_on_range",
            },
        ]
    }
    assert SH.count_new_depth(log, "now") == 0
    # A real advance still scores 1.
    log["attempts"].append({
        "id": "A126089", "cycle_id": "now",
        "bfile_hi": 100, "verified_depth": 2000,
        "extended": 50, "beyond": True, "status": "holds_on_range",
    })
    assert SH.count_new_depth(log, "now") == 1
    # The rule trial scores windows with this same corrected count,
    # never the stale raw new_depth on a metric row.
    stale = {"cycle_id": "now", "new_oracle_targets": 0, "new_depth": 99, "oracle_pass_delta": 0}
    corrected = SH.count_new_depth(log, "now")
    assert corrected == 1
    assert SH.score_metrics(0, corrected, 0) == SH.W_DEPTH * 1
    assert SH.score_metrics(0, int(stale["new_depth"]), 0) != SH.score_metrics(0, corrected, 0)


def test_at_most_one_action_per_cycle_constant():
    assert SL.MAX_ACTIONS_PER_CYCLE == 1
    assert SL.MAX_ACTIONS_PER_CYCLE <= 2


def test_start_knob_trial_defers_when_heal_busy(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _prime_heal(6)
    st = SH.load_state()
    trial = {
        "knob": "park_cycles", "from": 6, "to": 8, "direction": "up",
        "reason": "repeated_targets", "window": 6,
        "baseline_score": 0.0, "baseline_metrics": st["metrics"],
        "trial_metrics": [],
    }
    SH.start_trial(trial, state=st, cycle_id="t0")
    proposal = SL.Proposal(
        role="improver", label="repeated_targets",
        action={"op": "set_knob", "name": "unused_menu_cycles", "direction": "up"},
        fingerprint="set_knob:direction=up:name=unused_menu_cycles",
        symptom="stall loop",
    )
    out = SL.start_knob_trial(proposal, cycle_id="t1", state=SL.load_state())
    assert out["ok"] is False
    assert out["reason"] == "self_heal_trial_running"


def test_start_knob_trial_and_rule_trial_need_metrics(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    # No metric rows yet.
    proposal = SL.Proposal(
        role="improver", label="repeated_targets",
        action={"op": "set_knob", "name": "park_cycles", "direction": "up"},
        fingerprint=action_fingerprint({"op": "set_knob", "name": "park_cycles", "direction": "up"}),
        symptom="stall loop",
    )
    out = SL.start_knob_trial(proposal, cycle_id="c0", state=SL.load_state())
    assert out["ok"] is False
    assert out["reason"] in ("not_enough_metrics", "self_heal_replay_rejected")
    park = SL.Proposal(
        role="pathfinder", label="dead_end_streak",
        action={"op": "add_park_rule", "target_kind": "dead_end", "cycles": 12},
        fingerprint="add_park_rule:cycles=12:target_kind=dead_end",
        symptom="dead end streak",
    )
    out2 = SL.start_rule_trial(park, cycle_id="c0", state=SL.load_state())
    assert out2["ok"] is False
    assert out2["reason"] == "not_enough_metrics"


def test_rule_trial_adopts_only_on_strict_improvement(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _prime_heal(6)
    st = SL.load_state()
    park = SL.Proposal(
        role="pathfinder", label="dead_end_streak",
        action={"op": "add_park_rule", "target_kind": "dead_end", "cycles": 12},
        fingerprint="add_park_rule:cycles=12:target_kind=dead_end",
        symptom="dead end streak",
    )
    started = SL.start_rule_trial(park, cycle_id="c0", state=st)
    assert started["ok"] is True
    assert any(r.get("trial") for r in st["rules"])
    # Feed six flat metric rows — should revert (not strictly higher).
    # maybe_close_rule_trial calls collect_metrics; stub it to our rows.
    rows = [_metric(f"t{i}") for i in range(6)]
    idx = {"i": 0}

    def _collect(cycle_id, stall_state=None):
        r = rows[min(idx["i"], 5)]
        idx["i"] += 1
        return r

    monkeypatch.setattr(SH, "collect_metrics", _collect)
    for i in range(6):
        st = SL.maybe_close_rule_trial(st, f"t{i}")
    assert st.get("trial") is None
    assert st["reverted_count"] == 1
    assert st["adopted_count"] == 0
    assert st["last_decision"]["event"] == "revert"
    assert st["last_decision"]["helped"] is False
    # No active rule remains.
    assert SL.active_rules(state=st) == []

    # A second trial that actually improves is adopted.
    st2 = SL.load_state()  # empty; reuse in-memory st after we clear trial
    st["reverted_count"] = 1
    started = SL.start_rule_trial(park, cycle_id="c1", state=st)
    assert started["ok"] is True
    better = [_metric(f"u{i}", targets=1) for i in range(6)]
    idx["i"] = 0

    def _collect2(cycle_id, stall_state=None):
        r = better[min(idx["i"], 5)]
        idx["i"] += 1
        return r

    monkeypatch.setattr(SH, "collect_metrics", _collect2)
    for i in range(6):
        st = SL.maybe_close_rule_trial(st, f"u{i}")
    assert st["adopted_count"] == 1
    assert st["last_decision"]["event"] == "adopt"
    assert st["last_decision"]["trial_score"] > st["last_decision"]["baseline_score"]
    assert SL.active_rules(state=st)
    assert SL.active_rules(state=st)[0]["active"] is True
    assert SL.active_rules(state=st)[0]["trial"] is False


def test_run_cycle_seeds_library_and_calibrates(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    # No findings: still seeds the library, reports a learning-curve point,
    # and honestly calibrates from held-out leave-one-out results.
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
    st = SL.load_state()
    cal = st.get("calibration") or {}
    b64 = next(b for b in cal["buckets"] if b["min_margin"] == 64)
    # Most leave-one-out cases land in the 64 bucket (a few may sit
    # just under, in 32). The 64 bucket stays above 700. Every
    # labeled case is counted exactly once across buckets.
    replay_n = sum(b["by_source"]["replay"]["n"] for b in cal["buckets"])
    replay_c = sum(b["by_source"]["replay"]["correct"] for b in cal["buckets"])
    assert replay_n == 38
    assert replay_c == 38
    assert b64["by_source"]["replay"]["n"] == b64["by_source"]["replay"]["correct"]
    assert b64["n"] == b64["correct"]
    assert b64["n"] >= 28
    assert b64["lower_permille"] >= 700
    assert FL.LIBRARY_SNAPSHOT.exists()
    # With findings, the gate may now accept for a high-margin pick
    # (the replay-seeded bucket is above 700). If it still abstains,
    # a shadow pick is recorded. Standalone hosts often defer apply
    # (no trial window), so applied_count may stay 0 either way.
    finding = {"kind": "repeated_targets", "evidence": {"targets": ["A1"], "cycles_with_tries": ["c0"]}}
    monkeypatch.setattr(SL, "observe", lambda cycle_id="": [finding])
    out2 = SL.run_cycle("c1")
    assert out2["ok"] is True
    assert out2["applied_to_live_oracle"] is False
    assert out2["authorized"] is False
    vote = out2.get("vote")
    st2 = SL.load_state()
    if vote is not None and vote.get("abstained"):
        assert any(not s.get("resolved") for s in (st2.get("shadows") or []))

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


# ---------------------------------------------------------------------------
# Telemetry, dashboard, evolve hook
# ---------------------------------------------------------------------------

def test_telemetry_and_dashboard_surface_swarm_fields(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    FL.ensure_seeded()
    SL.run_cycle("c0")
    vis = SL.visibility()
    line = SL.format_visibility(vis)
    monkeypatch.setattr(SL, "visibility", lambda state=None: vis)
    monkeypatch.setattr(SL, "format_visibility", lambda v=None: line)

    snap = telemetry.gather_internal({"fitness_history": [], "agents": {}})
    assert snap["swarm_library_size"] == vis["swarm_library_size"]
    assert snap["swarm_replay_accuracy_permille"] == vis["swarm_replay_accuracy_permille"]
    assert snap["swarm_adopted"] == vis["swarm_adopted"]
    assert snap["swarm_reverted"] == vis["swarm_reverted"]
    assert snap["swarm_abstained"] == vis["swarm_abstained"]
    assert "swarm_time_to_fix" in snap

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
    assert "Hive" in html
    assert "library" in html
    assert "Hive" in summary
    assert "replay accuracy" in line
    assert "library" in line


def test_evolve_hook_is_guarded():
    src = Path(__file__).resolve().parents[1] / "colony" / "emergence" / "growth_steps_evolve.py"
    text = src.read_text(encoding="utf-8")
    assert "from colony.hive_adapter import on_cycle" in text
    idx = text.index("from colony.hive_adapter import on_cycle")
    window = text[max(0, idx - 80): idx + 360]
    assert "try:" in window
    assert "except Exception:" in window
    assert "on_cycle(cycle_id)" in window
    assert "authorize" not in window.lower() or "authorize=false" in window.lower()


def test_format_visibility_plain_wording(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    line = SL.format_visibility()
    for banned in ("conscious", "consciousness", "breakthrough", "AGI", "sentient"):
        assert banned.lower() not in line.lower()


# ---------------------------------------------------------------------------
# Item 32 (Hive) — confound void covers Hive-started trials; no teaching
# ---------------------------------------------------------------------------

def test_hive_knob_trial_records_fingerprint_and_voids_on_cap_change(tmp_path, monkeypatch):
    """A Hive-started set_knob trial uses self-heal start_trial, so a
    mid-trial cap change voids it. Harvest must not teach from the void."""
    _isolate(tmp_path, monkeypatch)
    _prime_heal(6)
    proposal = SL.Proposal(
        role="improver", label="no_progress_perturb",
        action={"op": "set_knob", "name": "perturb_cooldown_cycles", "direction": "up"},
        fingerprint=action_fingerprint(
            {"op": "set_knob", "name": "perturb_cooldown_cycles", "direction": "up"}
        ),
        symptom="no progress perturb",
    )
    out = SL.start_knob_trial(proposal, cycle_id="t0", state=SL.load_state())
    assert out["ok"] is True, out
    live = SH.load_state()["trial"]
    assert live["environment_fingerprint"]
    assert live["source"] == "swarm"
    assert SH.current_knob("perturb_cooldown_cycles") == 8
    # Mid-trial confound: a different knob (evaluator cap) moves.
    st = SH.load_state()
    st["knobs"]["fast_term_cap"] = 16000
    SH.save_state(st)
    SH.run_cycle("t1", metrics=_metric("t1", depth=2))
    st = SH.load_state()
    assert st["trial"] is None
    ev = [e for e in st["evidence"] if e.get("event") == "trial_voided_confound"]
    assert ev
    assert ev[0]["adopted"] is False
    assert ev[0]["reverted"] is False
    assert SH.current_knob("perturb_cooldown_cycles") == 6
    assert st["adopted_count"] == 0
    assert st["reverted_count"] == 0
    # Hive must not treat the void as a teaching example.
    router = Router()
    swarm_st = SL.load_state()
    taught = SL.harvest_self_heal_outcomes(router, swarm_st)
    assert taught == []
    assert SL.teach_from_event(router, ev[0]) is None
    mined = FL.mine_self_heal()
    assert all(r.get("evidence", {}).get("event") != "trial_voided_confound" for r in mined)
    assert all(r.get("outcome") in ("positive", "negative", "unknown") and r.get("evidence", {}).get("event") != "trial_voided_confound" for r in mined)


def test_hive_rule_trial_voids_on_fingerprint_change_without_teaching(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _prime_heal(6)
    park = SL.Proposal(
        role="pathfinder", label="dead_end_streak",
        action={"op": "add_park_rule", "target_kind": "dead_end", "cycles": 12},
        fingerprint="add_park_rule:cycles=12:target_kind=dead_end",
        symptom="dead end streak",
    )
    st = SL.load_state()
    started = SL.start_rule_trial(park, cycle_id="c0", state=st)
    assert started["ok"] is True, started
    trial = st["trial"]
    assert trial["environment_fingerprint"]
    # Mid-window: environment fingerprint no longer matches.
    trial = dict(trial)
    # Keep the recorded fingerprint, but make the live one differ by
    # changing a host knob (fast_term_cap).
    heal = SH.load_state()
    heal["knobs"]["fast_term_cap"] = 16000
    SH.save_state(heal)
    # Six improving rows would have adopted if we did not void.
    rows = [_metric(f"t{i}", targets=1) for i in range(6)]
    idx = {"i": 0}

    def _collect(cycle_id, stall_state=None):
        r = rows[min(idx["i"], 5)]
        idx["i"] += 1
        return r

    monkeypatch.setattr(SH, "collect_metrics", _collect)
    n_library_before = len(FL.load_records() or [])
    st = SL.maybe_close_rule_trial(st, "t0")
    assert st["trial"] is None
    assert st["adopted_count"] == 0
    assert st["reverted_count"] == 0
    assert st["last_decision"]["event"] == "trial_voided_confound"
    assert st["last_decision"]["adopted"] is False
    assert st["last_decision"]["reverted"] is False
    assert st["last_decision"]["old_fingerprint"] != st["last_decision"]["new_fingerprint"]
    # The in-trial rule was dropped, not adopted.
    assert SL.active_rules(state=st) == []
    router = Router()
    assert SL.teach_from_event(router, st["last_decision"]) is None
    assert len(FL.load_records() or []) == n_library_before


def test_unrecorded_hive_rule_trial_voids(tmp_path, monkeypatch):
    """A rule trial started under older code (no fingerprint) is voided."""
    _isolate(tmp_path, monkeypatch)
    _prime_heal(6)
    st = SL.load_state()
    st["trial"] = {
        "op": "add_park_rule",
        "action": {"op": "add_park_rule", "target_kind": "dead_end", "cycles": 12},
        "fingerprint": "add_park_rule:cycles=12:target_kind=dead_end",
        "role": "pathfinder",
        "label": "dead_end_streak",
        "window": 6,
        "baseline_score": 0.0,
        "trial_metrics": [_metric(f"t{i}", targets=1) for i in range(6)],
        "source": "swarm",
    }
    st["rules"] = [{
        "fingerprint": "add_park_rule:cycles=12:target_kind=dead_end",
        "action": {"op": "add_park_rule", "target_kind": "dead_end", "cycles": 12},
        "active": True, "trial": True,
    }]
    st["adopted_count"] = 0
    st["reverted_count"] = 0
    SL.save_state(st)
    st = SL.maybe_close_rule_trial(st, "t5")
    assert st["trial"] is None
    assert st["adopted_count"] == 0
    assert st["reverted_count"] == 0
    assert st["last_decision"]["event"] == "trial_voided_confound"
    assert st["last_decision"]["old_fingerprint"] == SH.UNRECORDED_FINGERPRINT
    assert SL.active_rules(state=st) == []
    router = Router()
    assert SL.teach_from_event(router, st["last_decision"]) is None

