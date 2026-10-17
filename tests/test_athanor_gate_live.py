"""Athanor gate LIVE mode (COLONY_ATHANOR_GATE=live) and flag-back: shadow/off restore old behaviour."""
from __future__ import annotations

import json

import pytest

import colony.trust.athanor_gate as G
from test_challenger import _desk, art, sandbox  # noqa: F401


class V:
    passed = True
    fitness_credit = True
    kills: list = []


def _run(monkeypatch, sandbox, tmp_path, mode, after_checks, *, guard=None):
    import colony.novelty_gate as NG
    import colony.oracle as O
    if mode is None:
        monkeypatch.delenv("COLONY_ATHANOR_GATE", raising=False)
    else:
        monkeypatch.setenv("COLONY_ATHANOR_GATE", mode)
    monkeypatch.setattr(G, "STATE", tmp_path / f"s_{mode}.json")
    oracle_calls = []
    verdict = V()
    monkeypatch.setattr(O, "gate_keep", lambda **k: oracle_calls.append(k) or ("keep", verdict))
    monkeypatch.setattr(NG, "evaluate", lambda **k: {"novel_to_commons": True, "kills": []})
    D, impl = _desk(monkeypatch, sandbox, art(odd=False), "odd_sum")
    benched = []
    before = {"score": 0.8, "ok": True, "n_hard_pass": 1, "checks": {f"c{i}": True for i in range(10)}}
    after = {"score": 0.9, "ok": True, "n_hard_pass": 2, "checks": after_checks}
    benches = iter([before, after])
    monkeypatch.setattr(D, "run_lemma_bench", lambda: benched.append(1) or next(benches))
    if guard is not None:
        monkeypatch.setattr(G, "GUARDED_IMPL", impl)
        monkeypatch.setattr(G, "guarded_run", lambda src, **k: dict(guard))
    r = D.improve_once(cycle_id=f"cyc_{mode}")
    return r, impl, oracle_calls, verdict, benched


# 8 of 10 checks flip: Athanor REJECTs this change under every profile
FLIPPY = {**{f"c{i}": False for i in range(8)}, "c8": True, "c9": True}
CALM = {**{f"c{i}": True for i in range(10)}, "odd_sum": True}


def test_live_blocks_unapproved_keep_and_leaves_oracle_alone(sandbox, tmp_path, monkeypatch):
    r, impl, calls, verdict, _ = _run(monkeypatch, sandbox, tmp_path, "live", FLIPPY)
    assert r.decision == "revert" and "athanor_gate=BLOCK" in r.note
    assert len(calls) == 1 and verdict.passed is True          # Oracle ran once, its verdict untouched
    assert '("odd_sum", lambda: all(check_odd_sum(n) for n in range(0, 20)), False)' in impl.read_text()
    st = json.loads((tmp_path / "s_live.json").read_text())
    assert st["totals"]["blocked_keep_live"] == 1 and st["rows"][-1]["block"] is True


@pytest.mark.parametrize("mode", [None, "shadow", "off"])
def test_flag_back_restores_old_behaviour(sandbox, tmp_path, monkeypatch, mode):
    r, impl, calls, verdict, _ = _run(monkeypatch, sandbox, tmp_path, mode, FLIPPY)
    assert r.decision == "keep" and "athanor_gate" not in r.note
    assert '("odd_sum", lambda: all(check_odd_sum(n) for n in range(0, 20)), True)' in impl.read_text()
    assert (tmp_path / f"s_{mode}.json").exists() is (mode != "off")   # off: no assessment at all


def test_live_approves_calm_change(sandbox, tmp_path, monkeypatch):
    r, *_ = _run(monkeypatch, sandbox, tmp_path, "live", CALM)
    assert r.decision == "keep" and "athanor_gate" not in r.note


def test_live_failed_guard_skips_in_process_bench_and_reverts(sandbox, tmp_path, monkeypatch):
    r, impl, calls, _v, benched = _run(monkeypatch, sandbox, tmp_path, "live", CALM,
                                       guard={"ran": True, "passed": False, "reason": "MemoryError: capped"})
    assert len(benched) == 1                       # only the before-bench; candidate never ran in-process
    assert r.decision == "revert" and "athanor_gate=BLOCK (guarded run" in r.note
    assert '("odd_sum", lambda: all(check_odd_sum(n) for n in range(0, 20)), False)' in impl.read_text()


def test_shadow_failed_guard_still_benches_and_keeps(sandbox, tmp_path, monkeypatch):
    r, impl, calls, _v, benched = _run(monkeypatch, sandbox, tmp_path, "shadow", CALM,
                                       guard={"ran": True, "passed": False, "reason": "MemoryError: capped"})
    assert len(benched) == 2 and r.decision == "keep"


def test_live_assessment_error_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("COLONY_ATHANOR_GATE", "live")
    monkeypatch.setattr(G, "STATE", tmp_path / "s.json")
    monkeypatch.setattr(G, "assess_change", lambda **k: 1 / 0)
    row = G.gate_desk_change(before={}, after={}, tentative_keep=True)
    assert row["verdict"] == "ERROR" and row["block"] is True
