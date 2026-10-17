"""Athanor 3.0.0 pieces (James Jackson's ATHANOR): Governor.judge adapter shape + memory-capped run."""
from __future__ import annotations

import json
import math

import pytest

from colony.athanor_coherence import GOVERNOR_BIG, Governor
import colony.trust.athanor_gate as G
from test_challenger import _desk, art, sandbox  # noqa: F401


def test_judge_rules_match_athanor_3():
    gov = Governor(lambda p: p, scale=0.1)
    same = gov.judge([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    assert same["verdict"] == "APPROVE" and same["h7"] == 1.0 and same["probes"] == 3
    # drift limit 1/τ − 1 ≈ 0.4286 × scale: 0.04 coherent, 0.05 not
    assert gov.judge([0.0] * 4, [0.04] * 4)["verdict"] == "APPROVE"
    assert gov.judge([0.0] * 4, [0.05] * 4)["verdict"] == "REJECT"
    mixed = gov.judge([0.0] * 10, [0.0] * 6 + [1.0] * 4)        # H7 0.6 -> REFINE band
    assert mixed["verdict"] == "REFINE" and mixed["h7"] == pytest.approx(0.6)
    crash = gov.judge([1.0, 2.0], [1.0, math.nan])             # non-finite candidate => BIG drift
    assert crash["verdict"] == "REJECT" and crash["probe_failed"] and crash["dphi_max"] == GOVERNOR_BIG
    # tolerance widens the limit
    assert gov.judge([0.0] * 4, [0.05] * 4, tolerance=2.0)["verdict"] == "APPROVE"
    with pytest.raises(ValueError):
        gov.judge([1.0], [1.0, 2.0])


def test_check_runs_first_and_raising_check_rejects():
    calls = []
    gov = Governor(lambda p: calls.append(p) or [0.0], check=lambda p: 1 / 0)
    d = gov.judge("cur", "cand")
    assert d["verdict"] == "REJECT" and d["valid"] is False and calls == []
    assert Governor(lambda p: [0.0], check=lambda p: True).judge("a", "b")["valid"] is True


def test_parity_with_athanor_3_governor_when_installed():
    athanor = pytest.importorskip("athanor")
    if not hasattr(athanor, "Governor"):
        pytest.skip("athanor < 3.0")
    import numpy as np
    rng = np.random.default_rng(3)
    for _ in range(25):
        cur = rng.normal(size=12).tolist()
        new = (np.array(cur) + rng.normal(scale=rng.uniform(0.01, 0.3), size=12)).tolist()
        theirs = athanor.Governor(lambda p: p, scale=0.1).judge(cur, new, tolerance=0.7).as_dict()
        ours = Governor(lambda p: p, scale=0.1).judge(cur, new, tolerance=0.7)
        assert ours["verdict"] == theirs["verdict"] and ours["h7"] == pytest.approx(theirs["h7"], abs=1e-6)
        assert ours["dphi_mean"] == pytest.approx(theirs["dphi_mean"], rel=1e-5)


IMPL_OK = '''
def run_basic_checks():
    return {"a": True, "b": 1 + 1 == 2}
def run_hard_checks():
    return {"h": True}
'''
IMPL_OOM = '''
def run_basic_checks():
    x = []
    while True:
        x.append(bytearray(64 * 1024 * 1024))
def run_hard_checks():
    return {}
'''
IMPL_LOOP = '''
def run_basic_checks():
    while True:
        pass
def run_hard_checks():
    return {}
'''


def test_guarded_run_passes_good_impl():
    g = G.guarded_run(IMPL_OK)
    assert g["passed"] and g["n_basic"] == 2 and g["n_hard"] == 1 and g["n_pass"] == 3


def test_guarded_run_caps_memory():
    g = G.guarded_run(IMPL_OOM, memory_bytes=512 * 1024 ** 2)
    assert not g["passed"] and g["reason"].startswith("MemoryError")


def test_guarded_run_times_out():
    g = G.guarded_run(IMPL_LOOP, timeout_s=1.0)
    assert not g["passed"] and g["reason"].startswith("timeout")


def test_pre_bench_guard_only_on_colony_impl(tmp_path, monkeypatch):
    monkeypatch.delenv("COLONY_ATHANOR_GATE", raising=False)
    assert G.pre_bench_guard(new_src=IMPL_OK, target_impl=tmp_path / "lemma_impl.py") is None
    monkeypatch.setattr(G, "GUARDED_IMPL", tmp_path / "lemma_impl.py")
    g = G.pre_bench_guard(new_src=IMPL_OK, target_impl=tmp_path / "lemma_impl.py")
    assert g["passed"] and g["block"] is False
    monkeypatch.setenv("COLONY_ATHANOR_GATE", "off")
    assert G.pre_bench_guard(new_src=IMPL_OK, target_impl=tmp_path / "lemma_impl.py") is None


def test_failed_guard_is_a_hard_validity_reject_in_shadow(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "STATE", tmp_path / "s.json")
    monkeypatch.delenv("COLONY_ATHANOR_GATE", raising=False)
    snap = {"score": 0.9, "checks": {"a": True}}
    row = G.gate_desk_change(before=snap, after=snap, tentative_keep=True,
                             guard={"ran": True, "passed": False, "reason": "MemoryError: x"})
    assert row["verdict"] == "REJECT" and "guarded run" in row["reason"] and row["validity_passed"] is False
    assert row["would_block"] and row["block"] is False
    tot = json.loads((tmp_path / "s.json").read_text())["totals"]
    assert tot["guard_failed"] == 1 and tot["validity_failed"] == 1


def test_desk_runs_guard_before_bench_and_keeps_in_shadow(sandbox, tmp_path, monkeypatch):
    import colony.novelty_gate as NG
    import colony.oracle as O

    class V:
        passed = True
        fitness_credit = True
        kills: list = []

    monkeypatch.setattr(G, "STATE", tmp_path / "s.json")
    monkeypatch.delenv("COLONY_ATHANOR_GATE", raising=False)
    order = []
    monkeypatch.setattr(G, "guarded_run", lambda src, **k: order.append("guard") or
                        {"ran": True, "passed": False, "reason": "MemoryError: capped"})
    monkeypatch.setattr(O, "gate_keep", lambda **k: ("keep", V()))
    monkeypatch.setattr(NG, "evaluate", lambda **k: {"novel_to_commons": True, "kills": []})
    D, impl = _desk(monkeypatch, sandbox, art(odd=False), "odd_sum")
    monkeypatch.setattr(G, "GUARDED_IMPL", impl)
    benches = iter([{"score": 0.8, "ok": True, "n_hard_pass": 1}, {"score": 0.9, "ok": True, "n_hard_pass": 2}])
    monkeypatch.setattr(D, "run_lemma_bench", lambda: order.append("bench") or next(benches))
    r = D.improve_once(cycle_id="cycG")
    assert order == ["bench", "guard", "bench"]       # before-bench, guard, then in-process bench
    assert r.decision == "keep"                         # shadow: decision unchanged
    row = json.loads((tmp_path / "s.json").read_text())["rows"][-1]
    assert row["guard"]["passed"] is False and row["would_block"] and not row["block"]
