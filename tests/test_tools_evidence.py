"""Tests for the optional evidence-gated evolution tools."""
import pytest
from colony.tools.evidence_graph import append_node, query_by_type
from colony.tools.statistical_keep_gate import should_accept, record_outcome
from colony.tools.invariant_contracts import check_verified_depth_contract, check_no_overlap, check_frontier_safe
from colony.tools.ablation_harness import run_ablation
from colony.tools.method_composition import compose, ALLOWED_OPS
from colony.tools.prospective_grading import grade_method
from colony.tools.novelty_filter import is_novel, signature
from colony.tools.hunter_persistence import persist_hit
from colony.tools.reward_isolation import can_award_credit


def test_evidence_graph_append_and_query(tmp_path, monkeypatch):
    monkeypatch.setattr("colony.tools.evidence_graph.GRAPH_LOG", tmp_path / "graph.jsonl")
    nid = append_node("counterexample", {"claim": "test", "value": 42})
    assert nid.startswith("counterexample:")
    results = query_by_type("counterexample")
    assert len(results) == 1
    assert results[0]["payload"]["value"] == 42


def test_statistical_keep_gate_cold_start(tmp_path, monkeypatch):
    monkeypatch.setattr("colony.tools.statistical_keep_gate.HISTORY", tmp_path / "hist.jsonl")
    assert should_accept(0.1) is True
    assert should_accept(0.001) is False


def test_invariant_contracts():
    assert check_verified_depth_contract({"independent_path_recorded": True}) is True
    assert check_verified_depth_contract({}) is False
    assert check_no_overlap("exp1", {"exp2"}) is True
    assert check_no_overlap("exp1", {"exp1"}) is False
    assert check_frontier_safe(True, True) is True
    assert check_frontier_safe(True, False) is False


def test_ablation_harness():
    def with_fn():
        return {"oracle_passes": 5, "verified_depth": 10}
    def without_fn():
        return {"oracle_passes": 3, "verified_depth": 8}
    delta = run_ablation("bus", with_fn, without_fn)
    assert delta["delta_passes"] == 2
    assert delta["factor"] == "bus"


def test_method_composition():
    m = compose(["modular_search", "residue_check"], {"window": 100})
    assert m["oracle_compatible"] is True
    assert "modular_search" in m["ops"]
    with pytest.raises(ValueError):
        compose(["bad_op"])


def test_prospective_grading():
    m = {"oracle_compatible": True, "ops": ["a", "b"]}
    score = grade_method(m, 0.3)
    assert 0.5 < score <= 1.0


def test_novelty_filter():
    claim = {"ops": ["modular_search"]}
    sig = signature(claim)
    assert is_novel(claim, [sig, sig]) is False
    assert is_novel(claim, []) is True


def test_hunter_persistence(tmp_path, monkeypatch):
    monkeypatch.setattr("colony.tools.evidence_graph.GRAPH_LOG", tmp_path / "graph.jsonl")
    nid = persist_hit("claim-1", {"n": 123, "fails": True})
    assert "counterexample_hit" in nid


def test_reward_isolation():
    good = {"independent_path_recorded": True}
    assert can_award_credit(good, False, True) is True
    assert can_award_credit({}, False, True) is False
    assert can_award_credit(good, True, False) is False


def test_learning_loop_optional_hook():
    from colony.learning_loop import decide_keep, _optional_evidence_tools
    signals = _optional_evidence_tools({"independent_path_recorded": True}, 0.04)
    assert signals.get("tools_available") is True
    r = decide_keep(
        trial_score=1.2,
        baseline_score=1.0,
        treatment={"oracle_passes": 3, "verified_depth_sum": 6},
        control={"oracle_passes": 2, "verified_depth_sum": 5},
    )
    assert r["keep"] is True
    assert "twin" in r


def test_swarm_facade_and_adapter():
    from colony.hive_adapter import query_tools
    r = query_tools({"action": "record", "claim": {"id": "swarm-test"}})
    assert r["ok"] is True
    assert "graph_id" in r
    g = query_tools({"action": "gate", "delta": 0.04})
    assert g["ok"] is True
    assert "accept" in g
    c = query_tools({"action": "compose", "ops": ["modular_search"]})
    assert c["ok"] is True
    n = query_tools({"action": "novel", "claim": {"ops": ["residue_check"]}})
    assert n["ok"] is True


def test_sensory_memory_connective():
    from colony.tools.sensory_surface import sense
    from colony.tools.memory_organ import remember, recall
    from colony.tools.connective import pulse, route_to_swarm
    from colony.hive_adapter import query_tools

    snap = sense("test")
    assert snap["ok"] is True
    assert "sensors" in snap["channels"]

    mid = remember("test_kind", {"value": 1}, rate="working")
    assert mid.startswith("mem:")
    items = recall(kind="test_kind")
    assert any(i["id"] == mid for i in items)

    p = pulse("cycle-test")
    assert p["ok"] is True
    assert "memory_id" in p

    r = route_to_swarm({"action": "sense", "query": "x"})
    assert r["ok"] is True

    q = query_tools({"action": "sense", "query": "swarm"})
    assert q.get("ok") is True
    q2 = query_tools({"action": "pulse", "cycle": "c1"})
    assert q2.get("ok") is True


def test_existing_signals_via_facade():
    from colony.hive_adapter import query_tools
    s = query_tools({"action": "sensors"})
    assert s["ok"] is True
    assert "trends" in s
    f = query_tools({"action": "failures", "limit": 1})
    assert f["ok"] is True
    a = query_tools({"action": "athanor"})
    assert a["ok"] is True
    r = query_tools({"action": "residuals"})
    assert r["ok"] is True


def test_evolutionary_bias_fail_open():
    import hive.swarm as s
    pen = s._failure_penalty("nonexistent_knob_xyz")
    assert isinstance(pen, int)
    assert pen <= 0
    # Existing fingerprint that has failed should be non-positive
    pen2 = s._failure_penalty("park_cycles")
    assert pen2 <= 0
