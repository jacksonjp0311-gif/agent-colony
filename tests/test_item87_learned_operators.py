"""Item 87: wider blueprint mutation operators and generator weights learned from kept / reverted trials."""
from __future__ import annotations

import pytest

import colony.self_build as SB
import colony.self_heal as SH
from tests.test_self_build import NO_EV, paths  # noqa: F401


@pytest.fixture(autouse=True)
def _self_mod(monkeypatch):
    monkeypatch.delenv("COLONY_ARM", raising=False)
    monkeypatch.setenv("COLONY_SELF_MOD", "on")


def _active(*names):
    st = SB.empty_state()
    st["active"] = SB.make_blueprint([{"component": n, "n": 1} for n in names])
    return st


def test_new_operators_replace_jump_pair_are_generated():
    st = _active("oeis_extra_pass")
    ops = {c["operator"] for c in SB.candidates(st, NO_EV)}
    assert {"replace", "jump", "pair"} <= ops
    for c in SB.candidates(st, NO_EV):
        ok, why = SB.validate(c, st["macros"])
        assert ok, why


def test_pair_combines_two_different_desks():
    for c in SB.candidates(SB.empty_state(), NO_EV):
        if c["operator"] == "pair":
            a, b = (SB.COMPONENTS[s["component"]]["plan"] for s in c["added"])
            assert a is not b


def test_pair_never_outranks_its_weaker_half():
    cands = SB.candidates(SB.empty_state(), NO_EV)
    w = {c["added"][0]["component"]: c["weight"] for c in cands if c["operator"] == "add" and c["steps"][0]["n"] == 1}
    for c in cands:
        if c["operator"] == "pair":
            assert c["weight"] <= min(w[s["component"]] for s in c["added"]) + 1e-12


def test_operator_weights_learned_from_outcomes():
    assert SB.operator_factor("add", {}) == pytest.approx(1.0)
    good = SB.operator_factor("swap", {"swap": {"tried": 4, "kept": 4}})
    bad = SB.operator_factor("swap", {"swap": {"tried": 4, "kept": 0}})
    assert good > SB.OPERATOR_PRIOR["swap"] > bad


def test_learned_weights_reorder_candidates():
    st = _active("oeis_extra_pass", "oeis_replay_buffer")
    base = [c["operator"] for c in SB.candidates(st, NO_EV)]
    st["operator_stats"] = {"add": {"tried": 6, "kept": 0, "reverted": 6},
                            "remove": {"tried": 6, "kept": 6, "reverted": 0}}
    after = [c["operator"] for c in SB.candidates(st, NO_EV)]
    assert after.index("remove") < base.index("remove")
    assert after[0] != "add"


def test_operator_stats_rebuilt_from_log_ignore_inconclusive_and_void():
    rows = [{"event": "blueprint_trial_open", "blueprint": "b1", "operator": "add"},
            {"event": "blueprint_trial_close", "blueprint": "b1", "outcome": "kept"},
            {"event": "blueprint_trial_open", "blueprint": "b2", "operator": "add"},
            {"event": "blueprint_trial_close", "blueprint": "b2", "outcome": "reverted", "operator": "add"},
            {"event": "blueprint_trial_open", "blueprint": "b3", "operator": "swap"},
            {"event": "blueprint_trial_close", "blueprint": "b3", "outcome": "inconclusive"},
            {"event": "blueprint_trial_open", "blueprint": "b4", "operator": "pair"},
            {"event": "blueprint_trial_void", "blueprint": "b4", "outcome": "voided"}]
    st = SB.operator_stats_from_log(rows)
    assert st["add"] == {"tried": 2, "kept": 1, "reverted": 1}
    assert st.get("swap", {"tried": 0})["tried"] == 0 and st.get("pair", {"tried": 0})["tried"] == 0


def test_close_updates_operator_stats(paths):
    st = SB.empty_state()
    bp = SB.make_blueprint([{"component": "oeis_extra_pass", "n": 1}], operator="pair")
    bp["added"] = bp["steps"]
    st["trial"] = {"blueprint": bp, "opened_cycle_index": 0, "open_row": 0, "window_rows": 1,
                   "baseline_gain": [0, 0]}
    st["cycle_index"] = SB.WINDOW_CYCLES
    board = {"history": [{"paired": True, "treatment": {"oracle_passes": 1, "verified_depth_sum": 1},
                          "control": {"oracle_passes": 1, "verified_depth_sum": 1}}] * 2}
    SB._close(st, board, "c", write=False, log_path=None)
    assert st["operator_stats"]["pair"] == {"tried": 1, "kept": 0, "reverted": 1}


def test_self_heal_learned_move_rates_from_evidence(monkeypatch):
    st = {"evidence": [{"event": "adopt", "knob": "k", "direction": "up"},
                       {"event": "adopt", "knob": "k", "direction": "up"},
                       {"event": "revert", "knob": "k", "direction": "down"},
                       {"event": "trial_inconclusive", "knob": "j", "direction": "up"}]}
    r = SH.learned_move_rates(st)
    assert r[("k", "up")] == pytest.approx(0.75) and r[("k", "down")] == pytest.approx(1 / 3)
    assert ("j", "up") not in r
    monkeypatch.setenv("COLONY_ARM", "control")
    assert SH.learned_move_rates(st) == {}
