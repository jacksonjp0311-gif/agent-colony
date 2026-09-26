"""Colony integration smoke — compile + governor + external array hooks."""
from __future__ import annotations

import importlib


def test_imports_compile():
    for mod in (
        "colony.athanor_coherence",
        "colony.pulsemesh_feeds",
        "colony.external_array",
        "colony.residuals",
        "colony.actuation",
        "colony.oracle",
        "colony.authorize",
        "colony.debate_multihop",
        "colony.emergence.growth",
    ):
        importlib.import_module(mod)


def test_governor_persist_and_oracle_untouched():
    from colony.athanor_coherence import CoherenceGovernor, persist_verdict
    from colony.oracle import counts as oracle_counts

    before = dict(oracle_counts())
    agents = {
        "spark": {
            "activation": [0.4, 0.4, 0.4, 0.4],
            "error_gradient": 0.05,
            "confidence_vector": [0.7],
            "attention_weight": 0.5,
            "arousal": 0.3,
        },
        "improver": {
            "activation": [0.41, 0.39, 0.4, 0.42],
            "error_gradient": 0.06,
            "confidence_vector": [0.68],
            "attention_weight": 0.52,
            "arousal": 0.32,
        },
        "geometer": {
            "activation": [0.42, 0.4, 0.38, 0.41],
            "error_gradient": 0.04,
            "confidence_vector": [0.72],
            "attention_weight": 0.51,
            "arousal": 0.31,
        },
        "scribe": {
            "activation": [0.4, 0.41, 0.39, 0.4],
            "error_gradient": 0.05,
            "confidence_vector": [0.7],
            "attention_weight": 0.5,
            "arousal": 0.3,
        },
    }
    v = CoherenceGovernor().verify_residuals(agents)
    snap = persist_verdict(v, cycle_id="smoke_spark3")
    assert snap["latest"]["inform_only"] is True
    assert snap["latest"]["durable_accept"] is False
    after = dict(oracle_counts())
    # Governor must not mutate Oracle counters
    assert before.get("passes") == after.get("passes")
    assert before.get("kills") == after.get("kills")


def test_actuation_gate_still_requires_human_authorize_ceiling():
    """Sanity: standing trust P_min stays 0.70; athanor does not accept-all."""
    from colony.standing_trust import STANDING_TRUST_P_MIN, meets_standing_trust

    assert STANDING_TRUST_P_MIN == 0.70
    assert meets_standing_trust(0.99, machine_checked=False) is False
    assert meets_standing_trust(0.65, machine_checked=True) is False
    assert meets_standing_trust(0.70, machine_checked=True) is True
