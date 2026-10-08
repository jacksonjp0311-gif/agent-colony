"""actuation's fp mirror must not wipe the desk's exploration distribution."""
from __future__ import annotations

import json


def test_param_experiment_preserves_exploration_distribution(tmp_path, monkeypatch):
    import colony.actuation as A
    import colony.exploration_budget as B

    monkeypatch.setattr(A, "ROOT", tmp_path)
    monkeypatch.setattr(A, "ACT_STATE", tmp_path / "actuation.json")
    monkeypatch.setattr(A, "ACT_LOG", tmp_path / "actuation.jsonl")
    budget_path = tmp_path / "society" / "systems" / "exploration_budget.json"
    monkeypatch.setattr(B, "BUDGET_PATH", budget_path)
    monkeypatch.setattr(B, "HISTORY", tmp_path / "conjecture_history.jsonl")

    B.record_outcome("easy_pad_square_again", "revert", kind="easy_pad")
    before = json.loads(budget_path.read_text())
    assert before["revert_penalties"] == {"easy_pad_square_again": 1}
    assert before["mutate_distribution"]

    row = A.act_param_experiment(
        state_data={}, cycle_id="c1", actor="t", residual_magnitude=0.9, confidence=0.95,
        peer_consensus=3, motivating_signal={"kind": "oracle_easy_pad"}, hypothesis="h",
    )
    assert row.get("executed") is True
    after = json.loads(budget_path.read_text())
    assert after["fp"] == row["result"]["after"]
    assert after["last_outcome"]["cycle_id"] == "c1"
    for k in ("mutate_distribution", "revert_penalties", "keep_rewards"):
        assert after[k] == before[k]
