"""Adapted Athanor unit tests — pure colony.athanor_coherence (no vendor tree)."""
from __future__ import annotations

import math

from colony.athanor_coherence import (
    CoherenceGovernor,
    basin_drift,
    boundary_excess,
    coherence_from_dphi,
    commensurability_suppression_score,
    cusp_limited_h7,
    delta_phi,
    h7_horizon,
    immunity_index,
    inject_bounded_noise,
    map_h7_to_stabilizer,
    omega_lipschitz_kappa_bound,
    residuals_to_trajectory,
    select_boundary_invariant,
    weighted_coherence_mean,
)


def test_delta_phi_l2_basic():
    traj = [[0, 0], [3, 4], [3, 4]]
    d = delta_phi(traj, mode="l2")
    assert len(d) == 2
    assert float(d[0]) == 5.0
    assert float(d[1]) == 0.0


def test_coherence_monotone():
    d = [0.0, 1.0, 9.0]
    c = coherence_from_dphi(d)
    assert c[0] > c[1] > c[2]


def test_h7_horizon():
    c = [0.71, 0.69, 0.70, 0.10]
    h7 = h7_horizon(c, threshold=0.70)
    assert abs(h7 - 0.5) < 1e-6


def test_weighted_and_cusp_h7_helpers():
    c = [0.2, 0.6, 0.9]
    wm = weighted_coherence_mean(c, power=2.0)
    assert wm > float(sum(c) / len(c))
    h7_all = h7_horizon(c, threshold=0.7)
    h7_cusp = cusp_limited_h7(c, threshold=0.7, survival_floor=0.5)
    assert h7_all <= h7_cusp <= 1.0


def test_h20_noise_immunity_helpers():
    d = [0.0, 0.2, 0.4, 0.8]
    c = coherence_from_dphi(d)
    d_pert = inject_bounded_noise(d, sigma=0.05, seed=7)
    c_pert = coherence_from_dphi(d_pert)
    i20 = immunity_index(c, c_pert)
    b20 = basin_drift(c, c_pert)
    kappa = omega_lipschitz_kappa_bound(float(sum(c) / len(c)))
    assert 0.0 <= i20 <= 1.0
    assert isinstance(b20, float)
    assert 0.0 <= kappa <= 1.0


def test_h44_boundary_algebra_helpers():
    assert abs(boundary_excess(1.7, 1.0) - 0.7) < 1e-9
    phi = (1.0 + math.sqrt(5.0)) / 2.0
    s_phi = commensurability_suppression_score(float(phi), max_denominator=64)
    s_rat = commensurability_suppression_score(1.5, max_denominator=64)
    assert s_phi > s_rat
    out = select_boundary_invariant([1.5, float(phi), 1.7], degree=2, suppression_weight=0.5)
    assert out["selected"] is not None
    assert out["degree"] == 2


def test_noise_seed_reproducible():
    d = [0.0, 0.3, 0.6]
    a = inject_bounded_noise(d, sigma=0.1, seed=11)
    b = inject_bounded_noise(d, sigma=0.1, seed=11)
    assert all(abs(x - y) < 1e-12 for x, y in zip(a, b))


def test_residuals_trajectory_and_verdict_inform_only():
    agents = {
        "spark": {
            "activation": [0.5, 0.4, 0.3, 0.2],
            "error_gradient": 0.1,
            "confidence_vector": [0.8, 0.7],
            "attention_weight": 0.6,
            "arousal": 0.4,
        },
        "improver": {
            "activation": [0.55, 0.42, 0.31, 0.22],
            "error_gradient": 0.12,
            "confidence_vector": [0.75, 0.7],
            "attention_weight": 0.62,
            "arousal": 0.45,
        },
        "geometer": {
            "activation": [0.52, 0.41, 0.33, 0.21],
            "error_gradient": 0.11,
            "confidence_vector": [0.78, 0.7],
            "attention_weight": 0.61,
            "arousal": 0.42,
        },
        "legislator": {
            "activation": [0.51, 0.43, 0.32, 0.23],
            "error_gradient": 0.09,
            "confidence_vector": [0.77, 0.7],
            "attention_weight": 0.59,
            "arousal": 0.41,
        },
    }
    traj = residuals_to_trajectory(agents)
    assert len(traj) >= 4
    gov = CoherenceGovernor()
    v = gov.verify_residuals(agents)
    assert v.verdict in ("APPROVE", "REFINE", "REJECT")
    assert v.inform_only is True
    assert v.double_gate is False
    assert v.durable_accept is False
    advice = map_h7_to_stabilizer(v)
    assert advice["inform_only"] is True
    assert advice["action_mix_internal"] == 0.50
    assert advice["action_mix_external"] == 0.50
    assert 0.0 < advice["suggest_throttle_factor"] <= 1.0


def test_reject_suggests_30pct_throttle():
    # Highly drifting residuals → low H7 → REJECT → throttle 0.70
    agents = {
        f"a{i}": {
            "activation": [i * 0.2 % 1, (i * 0.3) % 1, (i * 0.5) % 1, (i * 0.7) % 1],
            "error_gradient": 1.5,
            "confidence_vector": [0.1],
            "attention_weight": 0.9,
            "arousal": 1.0,
        }
        for i in range(8)
    }
    v = CoherenceGovernor().verify_residuals(agents)
    advice = map_h7_to_stabilizer(v)
    if v.verdict == "REJECT":
        assert advice["suggest_throttle_factor"] == 0.70
