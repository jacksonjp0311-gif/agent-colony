"""hunt_shadow.json history holds counts only (no churn)."""
from __future__ import annotations

import json

import colony.hunt_shadow as HS


def test_history_is_counts_only(tmp_path, monkeypatch):
    monkeypatch.setattr(HS, "STATE", tmp_path / "h.json")
    (tmp_path / "h.json").write_text(json.dumps({"history": [
        {"cycle_id": "old", "drop_out_of_bar": ["a", "b"], "enter_bar": [], "near_misses": {"x": ["m"]}}]}))
    summ = {"ts": "t", "cycle_id": "c1", "n_meet_bar_actual": 3, "n_meet_bar_shadow": 0, "n_unknown_claims": 2,
            "drop_out_of_bar": ["imp_1", "imp_2", "imp_3"], "enter_bar": [], "guidance": {"mode": "live"},
            "near_misses": {"oracle_rows": 4, "shifted_window_failures": ["q"], "single_reason_kills": []}}
    HS.record(summ)
    hist = json.loads((tmp_path / "h.json").read_text())["history"]
    assert hist[0]["drop_out_of_bar"] == 2 and hist[0]["near_misses"]["x"] == 1
    assert hist[1]["drop_out_of_bar"] == 3 and hist[1]["guidance_mode"] == "live"
    assert all(not isinstance(v, list) for h in hist for v in h.values())
