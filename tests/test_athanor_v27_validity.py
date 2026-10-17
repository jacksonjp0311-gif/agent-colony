"""Athanor v2.5 validity pre-gate (James Jackson's ATHANOR), ported report-only."""
from __future__ import annotations

import json
import math

import pytest

from colony.athanor_coherence import snapshot_validity, validity_check
import colony.trust.athanor_v27 as G
from test_challenger import _desk, art, sandbox  # noqa: F401  (fixture reuse)


@pytest.fixture
def gstate(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "STATE", tmp_path / "athanor_v27.json")
    monkeypatch.delenv("COLONY_ATHANOR_GATE", raising=False)
    return tmp_path / "athanor_v27.json"


def test_validity_check_matches_athanor_rules():
    assert validity_check(lambda x: x * 2.0, [1, 2, 3]) == {
        "gate": "VALIDITY", "passed": True, "inputs": 3, "failures": 0, "first_failure": None}
    r = validity_check(lambda x: 1.0 / x, [1, 0, 2, 0])
    assert not r["passed"] and r["failures"] == 2 and r["first_failure"]["input"] == 0
    assert "ZeroDivisionError" in r["first_failure"]["output"]
    r = validity_check(lambda x: [x, math.nan], [1])
    assert not r["passed"] and r["failures"] == 1
    assert not validity_check(lambda x: math.inf, [1])["passed"]
    with pytest.raises(KeyError):  # only ArithmeticError / ValueError / TypeError count as invalid
        validity_check(lambda x: {}[x], [1])


def test_snapshot_validity():
    good = {"score": 0.9, "seconds": 0.1, "ok": True, "checks": {"basic:a": True, "hard:b": False}}
    r = snapshot_validity(good)
    assert r["passed"] and r["inputs"] == 4
    assert not snapshot_validity({**good, "score": math.nan})["passed"]
    bad = snapshot_validity({**good, "checks": {"hard:b": None}})
    assert not bad["passed"] and bad["first_failure"]["input"] == "check:hard:b"
    assert not snapshot_validity({**good, "error": "boom"})["passed"]
    assert not snapshot_validity(None)["passed"] and not snapshot_validity({})["passed"]


def test_shadow_logs_but_never_blocks(gstate):
    row = G.gate_desk_change(before={"score": 0.8}, after={"score": math.inf}, mutation="m",
                             cycle_id="c1", tentative_keep=True)
    assert row["mode"] == "shadow" and row["verdict"] == "REJECT" and row["validity_passed"] is False
    assert row["would_block"] is True and row["block"] is False
    st = json.loads(gstate.read_text())
    assert st["totals"]["validity_failed"] == 1 and st["totals"]["would_block_keep"] == 1
    ok = G.gate_desk_change(before={"score": 0.8}, after={"score": 0.9, "checks": {"x": True}},
                            tentative_keep=True)
    assert ok["verdict"] == "APPROVE" and not ok["would_block"] and not ok["block"]


def test_off_mode_does_nothing(gstate, monkeypatch):
    monkeypatch.setenv("COLONY_ATHANOR_GATE", "off")
    assert G.gate_desk_change(before={}, after={"score": math.nan}, tentative_keep=True) is None
    assert not gstate.exists()


def test_desk_keep_unchanged_when_shadow_flags_validity(sandbox, gstate, monkeypatch):
    import colony.novelty_gate as NG
    import colony.oracle as O

    class V:
        passed = True
        fitness_credit = True
        kills: list = []

    monkeypatch.setattr(O, "gate_keep", lambda **k: ("keep", V()))
    monkeypatch.setattr(NG, "evaluate", lambda **k: {"novel_to_commons": True, "kills": []})
    D, _impl = _desk(monkeypatch, sandbox, art(odd=False), "odd_sum")
    benches = iter([{"score": 0.8, "ok": True, "n_hard_pass": 1},
                    {"score": 0.9, "ok": True, "n_hard_pass": 2, "checks": {"hard:odd_sum": None}}])
    monkeypatch.setattr(D, "run_lemma_bench", lambda: next(benches))
    r = D.improve_once(cycle_id="cycV")
    assert r.decision == "keep" and "athanor_gate" not in r.note
    row = json.loads(gstate.read_text())["rows"][-1]
    assert row["mutation"] == "odd_sum" and row["would_block"] and not row["block"]
