"""Fitness and scoreboard rows carry stall visibility fields.

The fields are reporting only: they are not scored, and they do not touch
the Oracle, the 0.70 gate, or the 150 cap.
"""
from __future__ import annotations

import colony.stall as S
from colony.fitness import EvolutionEngine


class _Reg:
    def best_for(self, _skill):
        return "spark"

    def active(self):
        return {}


def test_visibility_fields_and_fitness_row():
    for i in range(6):
        S.record_pass_total(f"f{i}", 528)
        S.record_targets_tried(f"f{i}", [f"t{i}a", f"t{i}b"])
    S.enter_perturb("f5", commit_sha="s")
    vis = S.visibility()
    assert vis["stall_cycles"] == 6
    assert vis["perturb_active"] is True
    # last 3 cycles: f3, f4, f5 each with 2 targets
    assert vis["distinct_targets_tried_last_3_cycles"] >= 6
    assert "stall_cycles 6" in S.format_visibility(vis)
    assert "perturb_active True" in S.format_visibility(vis)

    evo = EvolutionEngine(state_data={}, registry=_Reg(), workshop=None)
    row = evo.record_fitness("f5", {"aggregate": 0.86, "novelty": 0.75})
    assert row["stall_cycles"] == 6
    assert row["perturb_active"] is True
    assert row["distinct_targets_tried_last_3_cycles"] >= 6
    # Not folded into the scored aggregate: the value we passed is unchanged.
    assert row["aggregate"] == 0.86


def test_visibility_clears_after_a_new_pass():
    for i in range(6):
        S.record_pass_total(f"f{i}", 528)
    S.enter_perturb("f5", commit_sha="s")
    S.on_cycle_end("up", pass_total=529, rows=[
        {"cycle_id": "up", "passed": True, "kills": [], "mutation": "fresh"},
    ])
    vis = S.visibility()
    assert vis["perturb_active"] is False
    assert vis["stall_cycles"] == 0
