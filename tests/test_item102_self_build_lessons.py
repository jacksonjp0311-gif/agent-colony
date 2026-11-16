"""Item 102: self-build learns from its own reverted blueprints (no duplicate re-adds, desk lesson)."""
from __future__ import annotations

from colony import self_build as SB
from colony import self_build_lessons as L

LOG = [
    {"event": "blueprint_trial_open", "blueprint": "b1", "operator": "add",
     "added": [{"component": "oeis_extra_pass", "n": 1}]},
    {"event": "blueprint_trial_close", "blueprint": "b1", "outcome": "reverted"},
    {"event": "blueprint_trial_open", "blueprint": "b2", "operator": "add",
     "added": [{"component": "oeis_swarm_improvers", "n": 1}]},
    {"event": "blueprint_trial_close", "blueprint": "b2", "outcome": "reverted"},
    {"event": "blueprint_trial_open", "blueprint": "b3", "operator": "add",
     "added": [{"component": "oeis_consensus_vote", "n": 1}]},
    {"event": "blueprint_trial_void", "blueprint": "b3", "outcome": "voided"},
    {"event": "blueprint_trial_open", "blueprint": "b4", "operator": "add",
     "added": [{"component": "frontier_extra_batch", "n": 1}]},
    {"event": "blueprint_trial_close", "blueprint": "b4", "outcome": "kept"},
]
STATE = {"active": {"id": "bp_x", "steps": [{"component": "frontier_extra_batch", "n": 1}]}, "tried": {},
         "macros": {}, "component_stats": {}, "operator_stats": {}}


def test_reverted_and_desk_losses_from_log():
    les = L.lessons(LOG)
    assert les["reverted"] == {"oeis_extra_pass": 1, "oeis_swarm_improvers": 1}
    assert les["desk_losses"] == {"oeis": 2}


EV = {"oeis_beyond_bfile": {"boost": 2.0}, "new_data_extra_push": {"boost": 1.5}}


def _cands(monkeypatch, mode):
    monkeypatch.delenv("COLONY_ARM", raising=False)
    monkeypatch.setenv("COLONY_SELF_BUILD_LESSONS", mode)
    monkeypatch.setattr(L, "lessons", lambda rows=None: {"reverted": {"oeis_extra_pass": 1, "oeis_swarm_improvers": 1},
                                                         "desk_losses": {"oeis": 2}})
    return SB.candidates(STATE, EV)


def _added(bp):
    return {a["component"] for a in bp.get("added") or []}


def test_no_readd_of_reverted_components_in_any_form(monkeypatch):
    on = _cands(monkeypatch, "live")
    assert not any(_added(bp) & {"oeis_extra_pass", "oeis_swarm_improvers"} for bp in on)
    off = _cands(monkeypatch, "off")
    assert any("oeis_swarm_improvers" in _added(bp) for bp in off)


def test_desk_lesson_puts_other_desk_first(monkeypatch):
    on = _cands(monkeypatch, "live")
    assert "new_data_extra_push" in _added(on[0])
    off = _cands(monkeypatch, "off")
    assert any(c.startswith("oeis_") for c in _added(off[0]))


def test_control_arm_off(monkeypatch):
    monkeypatch.setenv("COLONY_ARM", "control")
    assert L.enabled() is False


def test_macro_expansion_blocked():
    les = {"reverted": {"oeis_extra_pass": 1}, "desk_losses": {"oeis": 1}}
    macros = {"m1": {"steps": [{"component": "oeis_extra_pass", "n": 1}]}}
    assert L.blocked([{"component": "m1"}], les, macros) is True
    assert L.desk_factor("m1", les, SB.COMPONENTS, macros) == 1 / 1.5
