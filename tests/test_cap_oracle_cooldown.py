"""Cap raise waits for an Oracle pass. Close path must not raise."""
import colony.self_heal as SH


def test_close_with_predicted_does_not_raise():
    st = {
        "trial": {
            "knob": "gf_term_cap",
            "from": 100,
            "to": 200,
            "direction": "up",
            "predicted_targets": ["t1"],
            "predicted_depth_gain": 10,
            "trial_metrics": [{"oracle_pass_delta": 1, "new_depth": 10}],
            "baseline_score": 0,
            "pre_trial_depths": {"t1": 0},
            "current_depths": {"t1": 10},
        },
        "knobs": {"gf_term_cap": 200},
        "cap_adopt": {},
        "evidence": [],
    }
    out = SH._close_trial(st, "c", "adopt")
    # The bug was an UnboundLocalError here. Close must finish.
    assert out.get("trial") is None


def test_prior_no_pass_blocks_depth_only():
    st = {
        "trial": {
            "knob": "gf_term_cap",
            "from": 200,
            "to": 300,
            "direction": "up",
            "predicted_targets": ["t1"],
            "predicted_depth_gain": 40,
            "trial_metrics": [{"oracle_pass_delta": 0, "new_depth": 40}],
            "baseline_score": 0,
        },
        "knobs": {"gf_term_cap": 300},
        "cap_adopt": {"gf_term_cap": {"oracle_passes": 626, "no_new_passes": True}},
        "evidence": [],
    }
    out = SH._close_trial(st, "c", "adopt")
    # Depth alone does not adopt when the prior raise produced no passes.
    assert int(out.get("adopted_count") or 0) == 0
    assert out.get("trial") is None


def test_cap_blocked_until_oracle_moves(monkeypatch):
    monkeypatch.setattr("colony.oracle.counts", lambda: {"passes": 626})
    st = {"cap_adopt": {"gf_term_cap": {"oracle_passes": 626}}}
    assert SH._cap_raise_blocked(st, "gf_term_cap") == "cap_awaiting_oracle"
    monkeypatch.setattr("colony.oracle.counts", lambda: {"passes": 627})
    assert SH._cap_raise_blocked(st, "gf_term_cap") is None
