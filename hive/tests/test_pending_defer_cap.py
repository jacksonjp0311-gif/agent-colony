"""Item 120: pending-apply deferral record + cap (shadow lane, never applied). No colony imports."""
from __future__ import annotations

import hive.swarm as SL
from hive.bitwork import WILSON_ACCEPT_PERMILLE
from hive.tests.test_pending_apply import _accepted, _abstain, _stub_cycle, _winner


def _run(monkeypatch, cid, reason, env="envA", confounded=False, vote=None):
    w = _winner()
    _stub_cycle(monkeypatch, vote_result=vote or _accepted(w),
                start_result={"ok": False, "reason": reason}, confounded=confounded)
    monkeypatch.setattr(SL, "_current_env_digest", lambda: env)
    return SL.run_cycle(cid)


def test_deferral_record_tracks_the_current_digest_not_only_the_first(monkeypatch):
    _run(monkeypatch, "c1", "confounded_baseline", env="envA", confounded=True)
    _run(monkeypatch, "c2", "confounded_baseline", env="envB", confounded=True)
    out = _run(monkeypatch, "c3", "no_signal_baseline", env="envC")
    p = out["pending_apply"]
    assert p["deferred_under"] == "envA"                  # unchanged meaning: first deferral
    assert p["last_deferred_under"] == "envC"             # item 120: where it really is now
    assert p["deferred_under_changes"] == 2
    assert p["deferred_reasons"] == {"confounded_baseline": 2, "no_signal_baseline": 1}


def test_confound_and_reservation_waits_are_never_capped(monkeypatch):
    for i in range(SL.PENDING_DEFER_CAP + 3):
        out = _run(monkeypatch, f"c{i}", "confounded_baseline", confounded=True)
    for i in range(SL.PENDING_DEFER_CAP + 3):
        out = _run(monkeypatch, f"r{i}", "self_heal_trial_running", confounded=True)
    assert out["pending_apply"] is not None
    assert not [e for e in SL.load_state()["evidence"] if e.get("event") == "pending_apply_shadowed"]


def test_no_signal_cap_moves_to_shadow_lane_and_never_applies(monkeypatch):
    for i in range(SL.PENDING_DEFER_CAP):
        out = _run(monkeypatch, f"c{i}", "no_signal_baseline")
    st = SL.load_state()
    assert st["pending_apply"] is None and out["pending_apply"] is None
    ev = [e for e in st["evidence"] if e.get("event") == "pending_apply_shadowed"]
    assert len(ev) == 1 and ev[0]["same_digest_deferrals"] == SL.PENDING_DEFER_CAP
    assert ev[0]["applied"] is False and ev[0]["wilson_gate"] == WILSON_ACCEPT_PERMILLE == 700
    sh = [s for s in st["shadows"] if s.get("via") == "pending_defer_cap"]
    assert len(sh) == 1 and sh[0]["resolved"] is False and sh[0]["source"] == "shadow"
    assert st["pending_capped"]["env_digest"] == "envA"
    assert int(st.get("applied_count") or 0) == 0 and not st.get("trial")
    # same action, same digest: not re-pended, no second shadow row
    _run(monkeypatch, "c9", "no_signal_baseline")
    st = SL.load_state()
    assert st["pending_apply"] is None
    assert st["evidence"][-1]["event"] == "apply_deferred" and st["evidence"][-1]["capped"] is True
    assert len([s for s in st["shadows"] if s.get("via") == "pending_defer_cap"]) == 1
    # environment changed: the action may wait again
    out = _run(monkeypatch, "c10", "no_signal_baseline", env="envB")
    assert out["pending_apply"] is not None and SL.load_state()["pending_capped"] is None


def test_cap_counts_across_drop_and_recreate_under_one_digest(monkeypatch):
    _run(monkeypatch, "c1", "no_signal_baseline")
    _run(monkeypatch, "c2", "no_signal_baseline")
    # a clean-window abstain drops the pending (item 56) ...
    _run(monkeypatch, "c3", "no_signal_baseline", vote=_abstain(_winner()))
    assert SL.load_state()["pending_apply"] is None
    # ... and the next accepted vote re-creates it: the same-digest count carries on
    _run(monkeypatch, "c4", "no_signal_baseline")
    st = SL.load_state()
    assert st["pending_apply"] is None
    assert [e for e in st["evidence"] if e.get("event") == "pending_apply_shadowed"]


def test_switch_off_and_control_keep_old_behaviour(monkeypatch):
    monkeypatch.setenv("HIVE_PENDING_DEFER_CAP", "off")
    for i in range(SL.PENDING_DEFER_CAP + 2):
        out = _run(monkeypatch, f"c{i}", "no_signal_baseline")
    p = out["pending_apply"]
    assert p is not None and p["deferred_count"] == SL.PENDING_DEFER_CAP + 2
    assert "last_deferred_under" not in p and "pending_defer_ledger" not in SL.load_state()
    monkeypatch.delenv("HIVE_PENDING_DEFER_CAP")
    monkeypatch.setenv("COLONY_ARM", "control")
    assert not SL._pending_defer_cap_enabled()
