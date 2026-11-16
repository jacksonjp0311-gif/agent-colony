"""Item 89: append-only failure modes for self-changes and blueprints; the generator reads them back."""
from __future__ import annotations

import json

import pytest

import colony.failure_modes as FM
import colony.self_build as SB
import colony.self_heal as SH
from tests.test_self_build import FakeOEIS, NO_EV, _ctx, _row, paths  # noqa: F401


@pytest.fixture(autouse=True)
def _self_mod(monkeypatch):
    monkeypatch.delenv("COLONY_ARM", raising=False)
    monkeypatch.setenv("COLONY_SELF_MOD", "on")


def _rows():
    return FM.load()


def test_reverted_blueprint_logs_metric_reference_and_amount():
    close = {"outcome": "reverted", "cycle_id": "c9", "blueprint": "bp_x", "operator": "add",
             "verdict": {"keep": False, "reason": "not_better_than_baseline",
                         "trial_gain": [0.0, 3.0], "baseline_gain": [1.0, 0.0]}}
    row = FM.log_blueprint(close, components=["oeis_extra_pass"])
    assert row["mode"] == "reverted:not_better_than_baseline"
    assert row["lost"][0] == {"metric": "oracle_passes", "against": "baseline", "by": -1.0}
    assert row["metrics"]["verified_depth_sum"]["trial_gain_vs_twin"] == 3.0
    assert _rows()[-1]["subject"]["components"] == ["oeis_extra_pass"]


def test_blueprint_losing_to_twin_on_depth_only():
    row = FM.blueprint_row({"outcome": "reverted", "verdict": {"reason": "not_better_than_twin",
                                                              "trial_gain": [0.0, -2.0], "baseline_gain": [-1.0, 0.0]}})
    assert {"metric": "verified_depth_sum", "against": "twin", "by": -2.0} in row["lost"]
    assert all(x["against"] != "baseline" for x in row["lost"])


def test_kept_blueprint_writes_nothing():
    assert FM.log_blueprint({"outcome": "kept", "verdict": {"keep": True}}) is None
    assert _rows() == []


def test_log_is_append_only():
    FM.append({"kind": "blueprint", "mode": "a"})
    first = FM.LOG.read_text()
    FM.append({"kind": "blueprint", "mode": "b"})
    assert FM.LOG.read_text().startswith(first) and len(_rows()) == 2


def test_control_arm_writes_and_penalizes_nothing(monkeypatch):
    monkeypatch.setenv("COLONY_ARM", "control")
    assert FM.append({"kind": "x"}) is None and not FM.LOG.exists()
    assert FM.component_penalty("oeis_extra_pass", {"oeis_extra_pass": 5}) == 1.0
    assert FM.heal_repeat_failures("k", "up", [{"kind": "self_heal", "outcome": "reverted",
                                                "subject": {"knob": "k", "direction": "up"}}]) == 0


def test_only_real_losses_penalize_components():
    rows = [{"kind": "blueprint", "outcome": "reverted", "subject": {"components": ["a"]}},
            {"kind": "blueprint", "outcome": "inconclusive", "subject": {"components": ["b"]}},
            {"kind": "blueprint", "outcome": "voided", "subject": {"components": ["b"]}}]
    losses = FM.component_losses(rows)
    assert losses == {"a": 1}
    assert FM.component_penalty("a", losses) < 1.0 == FM.component_penalty("b", losses)


def test_generator_moves_off_a_component_that_lost(paths):
    st = SB.empty_state()
    base = [bp["added"][0]["component"] for bp in SB.candidates(st, NO_EV) if bp["operator"] == "add"]
    top = base[0]
    for _ in range(3):
        FM.append({"kind": "blueprint", "outcome": "reverted", "subject": {"components": [top]}})
    after = [bp["added"][0]["component"] for bp in SB.candidates(st, NO_EV) if bp["operator"] == "add"]
    assert after[0] != top and after.index(top) > base.index(top)


def test_blueprint_close_and_void_write_failure_rows(paths, monkeypatch):
    board = {"history": [_row(5, 100, 5, 100)] * 3}
    ctx = _ctx(oeis=FakeOEIS(menu=[]), free=1)
    monkeypatch.setattr(SB, "code_fingerprint", lambda: "a")
    SB.run_cycle("c0", ctx=ctx, board=board, heal={}, ev=NO_EV)
    monkeypatch.setattr(SB, "code_fingerprint", lambda: "b")
    SB.run_cycle("c1", ctx=ctx, board=board, heal={}, ev=NO_EV)
    r = [x for x in _rows() if x["kind"] == "blueprint"][-1]
    assert r["mode"] == "voided:code_changed_in_window" and r["subject"]["components"]


def test_self_test_rejections_are_logged(paths):
    out = SB.run_cycle("c", ctx=_ctx(oeis=FakeOEIS(menu=[]), free=0), board={"history": []}, heal={}, ev=NO_EV)
    assert out["rejected"]
    r = [x for x in _rows() if x["kind"] == "blueprint_self_test"][-1]
    assert r["n_rejected"] == len(out["rejected"]) and r["by_reason"]


def test_heal_revert_row_names_metric_and_check():
    ev = {"event": "revert", "id": "ev1", "cycle_id": "c", "knob": "gf_term_cap", "direction": "up",
          "from": 4000, "to": 3149, "reason": "x", "decision_requested": "adopt",
          "trial_score": 1.0, "baseline_score": 2.0,
          "trial_metrics": [{"oracle_pass_delta": 0, "depth": 5}], "baseline_metrics": [{"oracle_pass_delta": 1, "depth": 5}]}
    row = FM.heal_row(ev)
    assert row["mode"] == "reverted:did_not_improve"
    assert row["lost"][0] == {"metric": "score", "against": "baseline", "by": -1.0}
    assert {"metric": "oracle_pass_delta", "against": "baseline", "by": -1.0} in row["lost"]
    assert FM.heal_row({"event": "adopt"}) is None


def test_self_heal_run_cycle_logs_its_closed_trial(monkeypatch):
    st = SH.load_state()
    ev = {"event": "revert", "id": "ev_t", "knob": "k", "direction": "up", "reason": "did_not_improve",
          "trial_metrics": [], "baseline_metrics": []}

    def close(state, cycle_id):
        state.setdefault("evidence", []).append(dict(ev))
        state["trial"] = None
        return state
    st["trial"] = {"knob": "k", "env_fingerprint": "x"}
    SH.save_state(st)
    monkeypatch.setattr(SH, "trial_fingerprint_mismatch", lambda trial, state=None: (False, "x", "x"))
    monkeypatch.setattr(SH, "maybe_close_trial", close)
    monkeypatch.setattr(SH, "propose_trial", lambda *a, **k: None)
    SH.run_cycle("c1", metrics={}, stall_state={}, findings=[])
    rows = [r for r in _rows() if r["kind"] == "self_heal"]
    assert rows and rows[-1]["subject"]["evidence_id"] == "ev_t"


def test_heal_order_prefers_untried_failure_mode():
    rows = [{"kind": "self_heal", "outcome": "reverted", "subject": {"knob": "a", "direction": "up"}}] * 2
    assert FM.heal_repeat_failures("a", "up", rows) == 2
    assert FM.heal_repeat_failures("a", "down", rows) == 0


def test_summary_counts_modes_and_lost_metrics():
    FM.log_blueprint({"outcome": "reverted", "verdict": {"reason": "not_better_than_twin",
                                                         "trial_gain": [-1, 0], "baseline_gain": [-2, 0]}})
    s = FM.summary()
    assert s["modes"]["blueprint"] == {"reverted:not_better_than_twin": 1}
    assert s["lost"] == {"oracle_passes<twin": 1}
    json.dumps(s)
