"""Cortex via Cerebrum inform-only sidecar — unit tests."""
from __future__ import annotations

from colony.cerebrum_boundary import CerebrumBoundary, map_to_oracle_actuation_mix
from colony.cortex_sidecar import attempt_ledger_accept, compute_memory_drift, run_cortex_sidecar
from colony.standing_trust import STANDING_TRUST_P_MIN, meets_standing_trust


def test_sidecar_produces_inform_signals():
    state = {
        "residuals": {
            "agents": {
                "spark": {
                    "activation": [0.5, 0.4, 0.3, 0.2],
                    "error_gradient": 0.1,
                    "confidence_vector": [0.8],
                    "attention_weight": 0.6,
                    "arousal": 0.4,
                },
                "improver": {
                    "activation": [0.55, 0.42, 0.35, 0.25],
                    "error_gradient": 0.2,
                    "confidence_vector": [0.7],
                    "attention_weight": 0.55,
                    "arousal": 0.5,
                },
            }
        },
        "fitness_history": [
            {"aggregate": 0.82, "citation_reuse": 1.0},
            {"aggregate": 0.83, "citation_reuse": 1.0},
        ],
        "commons_size": 120,
    }
    raw = compute_memory_drift(state)
    assert raw["kind"] == "memory_drift"
    assert 0.0 <= raw["drift"] <= 1.0
    assert 0.0 <= raw["memory_reuse"] <= 1.0
    out = run_cortex_sidecar(state, cycle_id="test_cortex")
    assert out["inform_only"] is True
    assert out["durable_accept"] is False
    assert out["can_accept_ledger"] is False
    admitted = (out["cortex"]["admitted"])
    assert admitted["inform_only"] is True
    assert admitted["ledger_authority"] is False
    assert admitted["durable_accept"] is False
    mix = out["mix_advice"]
    assert mix["inform_only"] is True
    assert mix["durable_accept"] is False
    assert 0.70 <= float(mix["suggest_throttle_factor"]) <= 1.0


def test_cannot_accept_ledger_findings():
    # Hostile payload claiming durable accept must be stripped by Cerebrum
    boundary = CerebrumBoundary()
    admitted = boundary.admit(
        {
            "sidecar": "cortex",
            "kind": "memory_drift",
            "drift": 0.1,
            "durable_accept": True,
            "ledger_authority": True,
            "accept_all": True,
            "authorize": True,
            "double_gate": True,
        }
    )
    assert admitted["durable_accept"] is False
    assert admitted["ledger_authority"] is False
    assert admitted["double_gate"] is False
    assert admitted["can_accept_ledger"] is False
    refused = attempt_ledger_accept(finding_id="fnd_fake", decision="accepted")
    assert refused["accepted"] is False
    assert refused["refused"] is True
    assert refused["durable_accept"] is False


def test_ceiling_still_holds():
    assert STANDING_TRUST_P_MIN == 0.70
    assert meets_standing_trust(0.99, machine_checked=False) is False
    assert meets_standing_trust(0.65, machine_checked=True) is False
    assert meets_standing_trust(0.70, machine_checked=True) is True
    mix = map_to_oracle_actuation_mix({"oracle_mix_delta": 0.5, "suggest_throttle_factor": 0.5})
    # Boundary clamps — still inform-only, never elevates to accept
    assert mix["inform_only"] is True
    assert mix["durable_accept"] is False
    assert mix["ledger_authority"] is False
