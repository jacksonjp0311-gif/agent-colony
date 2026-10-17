"""Athanor v2.5 conservative adaptive drift tolerance (James Jackson's ATHANOR), report-only."""
from __future__ import annotations

import json
import math

import pytest

from colony.athanor_coherence import (
    ADAPTIVE_PROFILES,
    CoherenceGovernor,
    delta_phi,
    drift_tolerance,
    edit_trajectory,
    scheduled_tolerance,
    structural_distance,
)
import colony.trust.athanor_v27 as G

CONS = ADAPTIVE_PROFILES["selfmod/adaptive@1.1.0"]
TSP = ADAPTIVE_PROFILES["tsp/adaptive@1.1.0"]


@pytest.fixture
def gstate(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "STATE", tmp_path / "athanor_v27.json")
    monkeypatch.delenv("COLONY_ATHANOR_GATE", raising=False)
    return tmp_path / "athanor_v27.json"


def test_profiles_match_athanor_registry():
    assert CONS == {"gamma": 6.0, "threshold_h7": 0.75, "refine_floor": 0.50, "adaptive_power": 3.0,
                    "adaptive_basis": "best", "adaptive_cap": 6.0, "adaptive_floor": 0.7,
                    "adaptive_halflife": 50}
    assert TSP["threshold_h7"] == 0.78 and TSP["adaptive_halflife"] is None
    assert ADAPTIVE_PROFILES["colony/fixed@1.0.0"]["gamma"] is None


def test_drift_tolerance_formula():
    assert drift_tolerance(0.25, 1.0, None) == 1.0
    # e = 0.5: 6 * 0.5**3 = 0.75 -> above floor 0.7
    assert drift_tolerance(0.25, 1.0, 6.0, 3.0, 0.7, 6.0) == pytest.approx(0.75)
    assert drift_tolerance(0.0001, 1.0, 6.0, 3.0, 0.7, 6.0) == 0.7      # floor
    assert drift_tolerance(4.0, 1.0, 6.0, 3.0, 0.7, 6.0) == 6.0         # cap
    assert drift_tolerance(math.inf, 1.0, 6.0, 3.0, 0.7, 6.0) == 0.7    # broken self: no slack


def test_scheduled_tolerance_basis_and_halflife():
    # basis best uses best_err2, not cur
    assert scheduled_tolerance(4.0, 0.25, 1.0, 0, 6.0, CONS) == pytest.approx(0.75)
    # half-life 50: slack above the floor halves every 50 steps
    t0 = scheduled_tolerance(1.0, 1.0, 1.0, 0, 6.0, CONS)
    t50 = scheduled_tolerance(1.0, 1.0, 1.0, 50, 6.0, CONS)
    assert t0 == 6.0 and t50 == pytest.approx(0.7 + (6.0 - 0.7) / 2)
    assert scheduled_tolerance(1.0, 1.0, 1.0, 500, 6.0, TSP) == 6.0      # no decay
    assert scheduled_tolerance(1.0, 1.0, 1.0, 9, None, CONS) == 1.0


def test_edit_trajectory_dphi_is_norm_of_each_step():
    traj = edit_trajectory([0.3, 0.0, 4.0], 0.2, tol=0.5, structure_weight=0.5)
    d = delta_phi(traj)
    assert d == pytest.approx([math.hypot(0.6, 0.1), 0.1, math.hypot(8.0, 0.1)])
    assert edit_trajectory([math.inf], 0.0)[-1][0] == 1e3


def test_structural_distance():
    a = "def f(x):\n    return x + 1\n"
    assert structural_distance(a, a) == 0.0
    d = structural_distance(a, "def f(x):\n    return x * 2 - 1\n")
    assert 0.0 < d <= 1.0


def test_behaviour_drift_rules():
    before = {"score": 0.8, "checks": {"a": True, "b": True, "c": True}}
    after = {"score": 0.81, "checks": {"a": True, "b": False, "d": True}}
    beh = G.behaviour_drift(before, after)
    # a same, b flips, c lost, d added passing, then score |0.01|/0.10
    assert beh[:4] == [0.0, 1.0, 1.0, 0.0] and beh[4] == pytest.approx(0.1)


def _checks(n, flip=0):
    b = {f"c{i}": True for i in range(n)}
    a = {f"c{i}": (i >= flip) for i in range(n)}
    return b, a


def test_one_flip_in_forty_approves_many_flips_do_not():
    b, a = _checks(40, flip=1)
    r = G.assess_change(before={"score": 0.9, "checks": b}, after={"score": 0.9, "checks": a})
    assert r["verdict"] == "APPROVE" and r["n_probes"] == 41
    b, a = _checks(40, flip=15)
    r = G.assess_change(before={"score": 0.9, "checks": b}, after={"score": 0.9, "checks": a})
    assert r["verdict"] in ("REFINE", "REJECT")


def test_conservative_is_stricter_than_fixed_gate():
    # every probe drifts 0.3: fixed tol 1 -> C = 0.769 >= 0.70; conservative tol 0.7 -> 0.3/0.7 = 0.43,
    # C = 0.70 < 0.75. Same ΔΦ -> C -> H7 math, only the tolerance and tau differ.
    beh = [0.3] * 10
    fixed = G.profile_verdict("colony/fixed@1.0.0", beh, 0.0, e_cur=0.1, e_best=0.1, step=0)
    cons = G.profile_verdict("selfmod/adaptive@1.1.0", beh, 0.0, e_cur=0.1, e_best=0.1, step=0)
    assert fixed["verdict"] == "APPROVE" and fixed["tol"] == 1.0
    assert cons["verdict"] == "REJECT" and cons["tol"] == 0.7
    # the live colony governor gives the same verdict on the same trajectory
    assert CoherenceGovernor().verify_trajectory(edit_trajectory(beh)).verdict == "APPROVE"


def test_shadow_schedule_tightens_and_never_blocks(gstate):
    b, a = _checks(10, flip=8)
    r1 = G.gate_desk_change(before={"score": 0.5, "checks": b}, after={"score": 0.5, "checks": a},
                            tentative_keep=True)
    assert r1["verdict"] != "APPROVE" and r1["would_block"] and r1["block"] is False
    assert r1["would_block_by_profile"]["selfmod/adaptive@1.1.0"]
    r2 = G.gate_desk_change(before={"score": 0.3, "checks": b}, after={"score": 0.3, "checks": b})
    st = json.loads(gstate.read_text())
    assert st["schedule"]["step"] == 2 and st["schedule"]["best_e"] == pytest.approx(0.5)  # best only tightens
    assert r2["e_best"] == pytest.approx(0.5) and r2["verdict"] == "APPROVE" and not r2["would_block"]
    assert set(r2["profiles"]) == set(ADAPTIVE_PROFILES)
    assert st["totals"]["profile:selfmod/adaptive@1.1.0:would_block_keep"] == 1
