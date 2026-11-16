"""Item 104: one exclusive experiment reservation (self-build / self-heal / Hive rule), fail closed,
Hive keeps a Wilson-passing winner deferred by the reservation as pending_apply (gate unchanged),
and blueprint verdicts flag windows another trial shared (flag only)."""
from __future__ import annotations

import json

import pytest

import colony.experiment_reservation as R


@pytest.fixture
def files(tmp_path):
    ps = {s: tmp_path / f"{s}.json" for s in R.SLOTS}
    return ps


def _put(path, trial):
    path.write_text(json.dumps({"trial": trial}))


def test_free_when_nobody_holds(files):
    assert R.check("self_heal", paths=files)["ok"] is True


def test_refuses_when_another_slot_holds(files):
    _put(files["self_build"], {"blueprint": {"id": "bp_x"}})
    r = R.check("self_heal", paths=files)
    assert r["ok"] is False and r["reason"] == "self_build_trial_open" and r["holder"] == "self_build"
    assert R.check("self_build", paths=files)["ok"] is True   # own slot does not block itself
    _put(files["hive_rule"], {"fingerprint": "f"})
    assert R.check("self_build", paths=files)["reason"] == "hive_rule_trial_open"


def test_in_memory_state_overrides_file(files):
    _put(files["self_heal"], {"knob": "x"})
    assert R.check("self_build", paths=files)["ok"] is False
    assert R.check("self_build", paths=files, states={"self_heal": {"trial": None}})["ok"] is True


def test_unreadable_state_fails_closed(files):
    files["hive_rule"].write_text("{not json")
    r = R.check("self_heal", paths=files)
    assert r["ok"] is False and r["reason"] == "reservation_unreadable"
    files["hive_rule"].write_text("[1, 2]")
    assert R.check("self_heal", paths=files)["reason"] == "reservation_unreadable"


def test_holders_fn_raising_fails_closed():
    def boom(**k):
        raise RuntimeError("x")
    assert R.check("self_heal", holders_fn=boom)["reason"] == "reservation_unreadable"


def test_switch_off_and_control_arm(files, monkeypatch):
    _put(files["self_build"], {"blueprint": {}})
    monkeypatch.setenv("COLONY_EXPERIMENT_RESERVATION", "off")
    assert R.check("self_heal", paths=files) == {"ok": True, "reason": "reservation_off", "requester": "self_heal"}
    monkeypatch.delenv("COLONY_EXPERIMENT_RESERVATION")
    monkeypatch.setenv("COLONY_ARM", "control")
    assert R.check("self_heal", paths=files)["reason"] == "reservation_off"


def test_self_heal_start_trial_refuses_while_blueprint_trial_open(tmp_path, monkeypatch):
    import colony.self_build as SB
    import colony.self_heal as SH
    monkeypatch.setattr(SB, "STATE_PATH", tmp_path / "self_build.json")
    _put(tmp_path / "self_build.json", {"blueprint": {"id": "bp_x"}})
    st = SH.load_state()
    knob = next(iter(SH.KNOB_SPECS))
    out = SH.start_trial({"knob": knob, "from": SH.current_knob(knob), "to": SH.current_knob(knob)},
                         state=st, cycle_id="c1")
    assert not out.get("trial")
    assert out["trial_skip"]["reason"] == "self_build_trial_open"


def test_hive_knob_trial_refused_by_reservation(monkeypatch):
    import hive.swarm as SL
    from hive import host
    monkeypatch.setattr(SL, "_heal_busy", lambda: False)
    monkeypatch.setattr(host, "experiment_holder", lambda req: "self_build_trial_open")
    p = SL.Proposal(role="improver", label="dead_end_streak",
                    action={"op": "set_knob", "name": "park_cycles", "direction": "up"},
                    fingerprint="set_knob:direction=up:name=park_cycles", symptom="stall", ok=True)
    assert SL.start_knob_trial(p, cycle_id="c1", state={}) == {"ok": False, "reason": "self_build_trial_open"}
    assert SL.start_rule_trial(p, cycle_id="c1", state={})["reason"] == "self_build_trial_open"


def test_hive_host_hook_standalone_and_failing():
    from hive import host
    import types
    saved = host._heal
    try:
        host.bind(heal=None)
        assert host.experiment_holder("self_heal") is None
        host.bind(heal=types.SimpleNamespace(experiment_holder=lambda r: (_ for _ in ()).throw(OSError())))
        assert host.experiment_holder("self_heal") == "reservation_unreadable"
    finally:
        host.bind(heal=saved)


def _stub(monkeypatch, SL, winner, reason):
    vr = SL.VoteResult(winner, False, "accepted", {winner.fingerprint: 4}, 901, 189, 4, 0, 1, 4, None)
    monkeypatch.setattr(SL, "observe", lambda cycle_id="": [{"kind": "dead_end_streak", "evidence": {}}])
    monkeypatch.setattr(SL, "swarm_propose", lambda *a, **k: [winner])
    monkeypatch.setattr(SL, "vote", lambda *a, **k: vr)
    monkeypatch.setattr(SL, "start_knob_trial", lambda *a, **k: {"ok": False, "reason": reason})
    monkeypatch.setattr(SL, "_window_is_confounded", lambda: True)
    monkeypatch.setattr(SL, "harvest_self_heal_outcomes", lambda *a, **k: [])
    monkeypatch.setattr("hive.library.mine_all", lambda **k: [])


@pytest.mark.parametrize("reason", ["self_heal_trial_running", "self_build_trial_open"])
def test_hive_winner_deferred_by_reservation_is_kept_pending(monkeypatch, reason):
    import hive.swarm as SL
    from hive.bitwork import WILSON_ACCEPT_PERMILLE
    w = SL.Proposal(role="improver", label="dead_end_streak",
                    action={"op": "set_knob", "name": "park_cycles", "direction": "up"},
                    fingerprint="set_knob:direction=up:name=park_cycles", symptom="stall", ok=True)
    _stub(monkeypatch, SL, w, reason)
    out = SL.run_cycle("c1")
    assert out["pending_apply"]["fingerprint"] == w.fingerprint
    assert out["pending_apply"]["wilson_gate"] == WILSON_ACCEPT_PERMILLE == 700
    st = SL.load_state()
    assert not any(e.get("event") == "trial_start" for e in st["evidence"])   # never auto-applied


def test_hive_pending_on_reservation_switch_off(monkeypatch):
    import hive.swarm as SL
    monkeypatch.setenv("HIVE_PENDING_ON_RESERVATION", "off")
    w = SL.Proposal(role="improver", label="dead_end_streak",
                    action={"op": "set_knob", "name": "park_cycles", "direction": "up"},
                    fingerprint="set_knob:direction=up:name=park_cycles", symptom="stall", ok=True)
    _stub(monkeypatch, SL, w, "self_heal_trial_running")
    assert SL.run_cycle("c1")["pending_apply"] is None


def test_cycle_ts_and_overlap():
    assert R.cycle_ts("20261116T053650Z_4fc81b") == "2026-11-16T05:36:50Z"
    assert R.cycle_ts("dry_run") is None
    ivs = [{"slot": "self_heal", "id": "k@1", "start": "2026-11-16T05:36:50Z", "end": "2026-11-16T06:16:43Z"},
           {"slot": "self_build", "id": "bp", "start": "2026-11-16T01:00:00Z", "end": "2026-11-16T01:43:45Z"}]
    got = R.overlapping("2026-11-16T05:02:56Z", "2026-11-16T05:46:16Z", ivs)
    assert [g["id"] for g in got] == ["k@1"]
    assert R.overlapping("2026-11-16T01:43:45Z", "2026-11-16T02:00:00Z", ivs) == []   # touching ends
    assert R.overlapping("2026-11-16T01:10:00Z", None, ivs, exclude_id="bp") == [ivs[0] | {"outcome": None}]


def test_trial_intervals_from_logs():
    bp = [{"event": "blueprint_trial_open", "blueprint": "bp_a", "cycle_id": "20261116T051056Z_613a12"},
          {"event": "blueprint_trial_close", "blueprint": "bp_a", "cycle_id": "20261116T055604Z_3aae26",
           "outcome": "reverted"}]
    heal = {"evidence": [{"event": "trial_voided_confound", "knob": "park_cycles",
                          "started_cycle": "20261116T053650Z_4fc81b", "cycle_id": "20261116T061643Z_252f96"}]}
    ivs = R.trial_intervals(blueprint_rows=bp, heal_state=heal, hive_state={})
    assert {i["slot"] for i in ivs} == {"self_build", "self_heal"}
    a = next(i for i in ivs if i["slot"] == "self_build")
    assert [x["id"] for x in R.overlapping(a["start"], a["end"], ivs, exclude_id="bp_a")] == \
        ["park_cycles@20261116T053650Z_4fc81b"]


def test_self_build_skips_when_reservation_refuses(monkeypatch, tmp_path):
    import colony.self_build as SB
    monkeypatch.setattr(SB, "STATE_PATH", tmp_path / "sb.json")
    monkeypatch.setattr(SB, "LOG_PATH", tmp_path / "sb.jsonl")
    monkeypatch.setattr(R, "check", lambda req, **k: {"ok": False, "reason": "hive_rule_trial_open"})
    called = []
    monkeypatch.setattr(SB, "propose", lambda *a, **k: called.append(1) or (None, []))
    out = SB.run_cycle("c", board={"history": []}, heal={}, ev={}, write=False, execute=False,
                       ctx=object())
    assert not called and out["last_skip"]["reason"] == "hive_rule_trial_open"


def test_no_gate_constant_changed():
    from hive.bitwork import WILSON_ACCEPT_PERMILLE
    import colony.self_build as SB
    assert WILSON_ACCEPT_PERMILLE == 700 and SB.WINDOW_CYCLES == 6
