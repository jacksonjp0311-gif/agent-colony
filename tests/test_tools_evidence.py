"""Tests for the optional evidence-gated evolution tools."""
import json
from pathlib import Path
import tempfile
import shutil

import pytest

from colony.tools.evidence_graph import append_node, query_by_type, GRAPH_LOG
from colony.tools.statistical_keep_gate import should_accept, record_outcome, HISTORY
from colony.tools.invariant_contracts import (
    check_verified_depth_contract,
    check_no_overlap,
    check_frontier_safe,
)


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


def test_statistical_keep_gate_with_history(tmp_path, monkeypatch):
    hist = tmp_path / "hist.jsonl"
    monkeypatch.setattr("colony.tools.statistical_keep_gate.HISTORY", hist)
    # write some false accepts
    for _ in range(10):
        record_outcome(0.05, True)
    for _ in range(90):
        record_outcome(0.1, True)
    # rate of low-delta accepts is low
    assert should_accept(0.1) is True


def test_invariant_contracts():
    assert check_verified_depth_contract({"independent_path_recorded": True}) is True
    assert check_verified_depth_contract({}) is False
    assert check_no_overlap("exp1", {"exp2"}) is True
    assert check_no_overlap("exp1", {"exp1"}) is False
    assert check_frontier_safe(True, True) is True
    assert check_frontier_safe(True, False) is False
    assert check_frontier_safe(False, False) is True
