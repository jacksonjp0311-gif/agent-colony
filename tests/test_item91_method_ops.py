"""Item 91: method cards become Hive-testable method ops (deterministic, no outside model).

The Wilson 700 gate, its calibration and the trial rules are untouched: a method op is an
``unknown``-outcome library record Bitwork can retrieve; only a real trial outcome teaches.
"""
from __future__ import annotations

import json

import pytest

import colony.arm as arm
from colony import method_ops as M
from hive import library as FL
from hive.bitwork import WILSON_ACCEPT_PERMILLE

CARDS = [
    {"id": "mc_a", "concept": "stochastic_search", "method": "Perturb more widely (annealing).",
     "op": {"op": "set_knob", "name": "perturb_epsilon", "direction": "up"}},
    {"id": "mc_b", "concept": "stochastic_search", "method": "Annealing again.",
     "op": {"op": "set_knob", "name": "perturb_epsilon", "direction": "up"}},
    {"id": "mc_c", "method": "Look further back.",  # pre-concept card: inferred from the knob
     "op": {"op": "set_knob", "name": "unused_menu_cycles", "direction": "up"}},
    {"id": "mc_bad", "concept": "stochastic_search", "method": "x",
     "op": {"op": "set_knob", "name": "oracle_p", "direction": "down"}},  # invariant: rejected
    {"id": "mc_unmapped", "concept": "consciousness", "method": "y",
     "op": {"op": "set_knob", "name": "stall_cycles", "direction": "down"}},  # no class: skipped
]


def test_records_are_deterministic_valid_and_deduped():
    recs = M.method_op_records(CARDS)
    assert recs == M.method_op_records(CARDS)
    ids = [r["id"] for r in recs]
    assert ids == ["method_op:no_progress_perturb:set_knob:perturb_epsilon:up",
                   "method_op:repeated_targets:set_knob:unused_menu_cycles:up"]
    assert recs[0]["evidence"]["card_ids"] == ["mc_a", "mc_b"]
    for r in recs:
        assert r["outcome"] == "unknown" and r["source"] == "method_card"


def test_live_cards_all_convert():
    cards = M.load_cards()
    if not cards:
        pytest.skip("no cards in this checkout")
    recs = M.method_op_records(cards)
    assert recs and all(r["action"]["op"] == "set_knob" for r in recs)


def test_install_is_append_only_idempotent_and_control_noop(tmp_path, monkeypatch):
    lib = tmp_path / "fix_library.jsonl"
    lib.write_text(json.dumps({"id": "keep_me", "kind": "fix"}) + "\n")
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: False)
    assert M.install(cards=CARDS, path=lib) == []
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: True)
    first = M.install(cards=CARDS, path=lib)
    assert len(first) == 2
    assert M.install(cards=CARDS, path=lib) == []
    lines = lib.read_text().splitlines()
    assert json.loads(lines[0])["id"] == "keep_me" and len(lines) == 3


def test_method_ops_never_enter_wilson_calibration_and_are_retrievable():
    seeds = FL.seed_patterns()
    recs = [FL.canonicalize(r) for r in M.method_op_records(CARDS)]
    # replay calibration only uses positive records: unchanged by method ops
    assert FL.held_out_cases(seeds + recs) == FL.held_out_cases(seeds)
    rtr = FL.train_router(seeds + recs)
    key = recs[1]["action_key"]
    m = rtr.score_action(FL.feature_text(recs[1]), key)
    assert m is not None and m.action_key == key  # Bitwork can now retrieve the card op
    assert WILSON_ACCEPT_PERMILLE == 700  # gate unchanged


def test_evolve_entry_on_cycle_installs_ops_and_logs_picks(monkeypatch):
    """Evolve calls hive_adapter.on_cycle (not run_cycle): both hooks must run there."""
    import colony.hive_adapter as HA
    calls = []
    monkeypatch.setattr(HA, "hive_learning_enabled", lambda: True)
    monkeypatch.setattr(HA, "_before_hive", lambda: calls.append("before"))
    monkeypatch.setattr(HA, "_after_hive", lambda r: calls.append(("after", r.get("cycle_id"))))
    monkeypatch.setattr(HA.swarm, "on_cycle", lambda cid: {"ok": True, "cycle_id": cid})
    HA.on_cycle("c9")
    assert calls[:2] == ["before", ("after", "c9")]
    monkeypatch.setattr(HA, "hive_learning_enabled", lambda: False)
    calls.clear()
    HA.on_cycle("c10")
    assert calls == []  # control arm: no hooks
