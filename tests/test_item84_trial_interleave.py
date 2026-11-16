"""Item 84: time-limited blueprint trials, code-change void, self-heal / self-build turn taking."""
from __future__ import annotations

import json

import pytest

import colony.self_build as SB
import colony.self_heal as SH
from tests.test_self_build import FakeOEIS, NO_EV, _ctx, _row, paths  # noqa: F401


def _open(board, ctx, heal=None):
    return SB.run_cycle("20261116T000000Z_a", ctx=ctx, board=board, heal=heal or {}, ev=NO_EV)


def _cid(i):
    return f"20261116T{i:06d}Z_x"


def test_trial_closes_inconclusive_after_one_window_plus_grace(paths):
    board = {"history": [_row(5, 100, 5, 100)]}
    ctx = _ctx(oeis=FakeOEIS(menu=[]), free=1)
    assert _open(board, ctx)["opened"]
    closed = None
    for i in range(1, SB.TRIAL_MAX_CYCLES + 1):
        out = SB.run_cycle(_cid(i), ctx=ctx, board=board, heal={}, ev=NO_EV)
        if out["closed"]:
            closed, at = out["closed"], i
            break
    assert closed["outcome"] == "inconclusive" and at == SB.TRIAL_MAX_CYCLES == SB.WINDOW_CYCLES + 3
    assert SB.load_state()["active"]["id"] == "bp_default"


def test_code_change_in_window_voids_without_credit(paths, monkeypatch):
    _st, log = paths
    board = {"history": [_row(5, 100, 5, 100)] * 3}
    ctx = _ctx(oeis=FakeOEIS(menu=[]), free=1)
    monkeypatch.setattr(SB, "code_fingerprint", lambda: "fp_a")
    _open(board, ctx)
    board["history"] += [_row(9, 200, 5, 100)] * 3   # would look like a big gain
    monkeypatch.setattr(SB, "code_fingerprint", lambda: "fp_b")
    out = SB.run_cycle(_cid(1), ctx=ctx, board=board, heal={}, ev=NO_EV)
    assert out["closed"]["outcome"] == "voided" and out["closed"]["reason"] == "code_changed_in_window"
    st = SB.load_state()
    assert st["active"]["id"] == "bp_default" and st["kept_count"] == 0 and st["voided_count"] == 1
    assert not st["tried"]  # a voided blueprint may be proposed again
    assert json.loads(log.read_text().splitlines()[-1])["event"] == "blueprint_trial_void"


def test_legacy_open_trial_without_fingerprint_is_voided(paths):
    st = SB.empty_state()
    st["trial"] = {"blueprint": {"id": "bp_x", "steps": []}, "opened_cycle_id": "c0", "opened_cycle_index": 0}
    row = SB._close(st, {"history": []}, "c1", write=False, log_path=None)
    assert row["outcome"] == "voided" and row["reason"] == "no_code_fingerprint_at_open"


def test_self_heal_gets_the_next_turn_then_self_build(paths):
    board = {"history": [_row(5, 100, 5, 100)] * 3}
    ctx = _ctx(oeis=FakeOEIS(menu=[]), free=1)
    st = SB.empty_state()
    st["trial"] = {"blueprint": {"id": "bp_x", "steps": [], "signature": "x"}, "opened_cycle_id": _cid(0),
                   "code_fp": SB.code_fingerprint(), "opened_cycle_index": 0, "open_row": 0, "window_rows": 1,
                   "baseline_gain": [0, 0]}
    st["cycle_index"] = SB.WINDOW_CYCLES
    SB.save_state(st)
    out = SB.run_cycle(_cid(10), ctx=ctx, board=board, heal={}, ev=NO_EV)
    assert out["closed"] and out["opened"] is None and out["last_skip"]["reason"] == "self_heal_turn"
    # self-heal has not run its proposer yet: still its turn
    out = SB.run_cycle(_cid(11), ctx=ctx, board=board, heal={"last_propose_cycle": _cid(9)}, ev=NO_EV)
    assert out["opened"] is None and out["last_skip"]["reason"] == "self_heal_turn"
    # self-heal took its turn (proposed nothing): self-build proposes the next blueprint
    out = SB.run_cycle(_cid(12), ctx=ctx, board=board, heal={"last_propose_cycle": _cid(12)}, ev=NO_EV)
    assert out["opened"] is not None


def test_no_deadlock_when_both_wait(paths):
    st = SB.load_state()
    st["heal_turn"] = {"cycle_id": _cid(5)}
    SB.save_state(st)
    out = SB.run_cycle(_cid(6), ctx=_ctx(oeis=FakeOEIS(menu=[]), free=1), board={"history": []},
                       heal={"build_turn": {"cycle_id": _cid(5)}}, ev=NO_EV)
    assert out["last_skip"] is None or out["last_skip"].get("reason") != "self_heal_turn"


def test_build_turn_pending_rules(paths):
    heal = {"build_turn": {"cycle_id": _cid(5)}}
    assert SB.build_turn_pending(heal) is True
    st = SB.load_state()
    st["last_propose_cycle"] = _cid(5)
    SB.save_state(st)
    assert SB.build_turn_pending(heal) is False
    assert SB.build_turn_pending({}) is False


def test_self_heal_yields_one_turn_after_its_trial_ends(monkeypatch):
    monkeypatch.setattr(SB, "blocks_self_heal", lambda state=None: False)
    monkeypatch.setattr(SB, "build_turn_pending", lambda heal_state, state=None: bool(heal_state.get("build_turn")))
    called = []
    monkeypatch.setattr(SH, "propose_trial", lambda *a, **k: called.append(1))
    st = SH.load_state()
    st["build_turn"] = {"cycle_id": "c0"}
    SH.save_state(st)
    out = SH.run_cycle("c1", metrics={}, stall_state={}, findings=[])
    assert not called and out["trial_skip"]["reason"] == "self_build_turn"
    monkeypatch.setattr(SB, "build_turn_pending", lambda heal_state, state=None: False)
    out = SH.run_cycle("c2", metrics={}, stall_state={}, findings=[])
    assert called and SH.load_state()["last_propose_cycle"] == "c2" and not SH.load_state().get("build_turn")


def test_control_arm_unchanged(paths, monkeypatch):
    monkeypatch.setenv("COLONY_ARM", "control")
    assert SB.build_turn_pending({"build_turn": {"cycle_id": "c"}}) is False
    assert SB.run_cycle("c", ctx=_ctx(free=1), board={}, heal={}, ev=NO_EV)["skipped"]


def test_state_keys_written_by_self_heal_survive_reload():
    st = SH.load_state()
    st.update({"build_turn": {"cycle_id": "c"}, "last_propose_cycle": "c",
               "zero_prediction_skips": {"count": 2}, "co_binding_caps": {"t": 1},
               "retirement_audits": [{"x": 1}], "retirement_audit_sig": "s"})
    SH.save_state(st)
    back = SH.load_state()
    for k in ("build_turn", "last_propose_cycle", "zero_prediction_skips", "co_binding_caps",
              "retirement_audits", "retirement_audit_sig"):
        assert back[k] == st[k]


def test_gf_trial_not_reopened_once_target_is_compute_bound():
    from colony.self_heal_coupled import compute_bound
    st = SH.load_state()
    st["compute_bound_targets"] = {"oc_A126089_0": {"reason": "time_bound"}}
    assert compute_bound(st, "oc_A126089_0")
