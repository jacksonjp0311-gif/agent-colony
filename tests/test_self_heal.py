"""Self-healing policy loop: bounds, invariants, adopt/revert, quarantine.

The colony may only change its own search and healing knobs, and only
when a trial measurably helps. The Oracle, the P ≥ 0.70 gate, the 150
cap, Athanor math, authorize, and the witness are not knobs.
"""
from __future__ import annotations

import json
from pathlib import Path

import colony.dashboard as dashboard
import colony.self_heal as SH
import colony.stall as S
import colony.telemetry as telemetry


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(SH, "STATE_PATH", tmp_path / "self_heal.json")
    monkeypatch.setattr(SH, "EVENT_LOG", tmp_path / "self_heal.jsonl")
    monkeypatch.setattr(S, "STATE_PATH", tmp_path / "stall_state.json")


def _metric(cycle_id, targets=0, depth=0, delta=0, passes=528):
    score = SH.score_metrics(targets, depth, delta)
    return {
        "cycle_id": cycle_id,
        "new_oracle_targets": targets,
        "new_depth": depth,
        "oracle_passes": passes,
        "oracle_pass_delta": delta,
        "score": score,
    }


def _prime_baseline(n=6, score_targets=0):
    """Write n flat baseline metric rows and return the state."""
    st = SH.load_state()
    fp = SH.environment_fingerprint(state=st)["digest"]
    rows = [_metric(f"b{i}", targets=score_targets) for i in range(n)]
    for r in rows:
        r["env_fingerprint"] = fp
    st["metrics"] = rows
    st["cycle_index"] = n - 1
    st["cycles"] = [f"b{i}" for i in range(n)]
    SH.save_state(st)
    return SH.load_state()


# ---------------------------------------------------------------------------
# Bounds and invariants
# ---------------------------------------------------------------------------

def test_every_knob_has_hard_bounds():
    assert SH.KNOB_SPECS
    for name, spec in SH.KNOB_SPECS.items():
        assert spec.lo < spec.hi, name
        assert spec.lo <= spec.default <= spec.hi, name
        assert spec.kind in ("int", "float")
        assert SH.in_bounds(name, spec.default)
        assert SH.in_bounds(name, spec.lo)
        assert SH.in_bounds(name, spec.hi)
        mid = (spec.lo + spec.hi) / 2
        assert SH.clamp(name, mid) == SH._cast(spec, mid) or SH.in_bounds(name, SH.clamp(name, mid))


def test_set_knob_rejects_out_of_bounds(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    r = SH.set_knob("park_cycles", 999)
    assert r["ok"] is False
    assert r["reason"] == "out_of_bounds"
    r2 = SH.set_knob("park_cycles", 1)
    assert r2["ok"] is False
    r3 = SH.set_knob("perturb_epsilon", 0.0)
    assert r3["ok"] is False
    r4 = SH.set_knob("park_cycles", 8)
    assert r4["ok"] is True
    assert r4["value"] == 8


def test_clamp_projects_onto_bounds():
    assert SH.clamp("park_cycles", 100) == SH.KNOB_SPECS["park_cycles"].hi
    assert SH.clamp("park_cycles", -3) == SH.KNOB_SPECS["park_cycles"].lo
    assert SH.clamp("step_size", 0.99) == SH.KNOB_SPECS["step_size"].hi


def test_invariants_are_untouchable(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    forbidden = [
        "p_min", "P_min", "standing_trust_p_min", "authorize_p",
        "authored_cap", "max_authored_total", "authored_check_cap",
        "athanor", "delta_phi", "dphi", "h7", "athanor_math",
        "authorize", "human_authorize", "witness", "rewrite_witness",
        "oracle_threshold", "w_targets", "w_depth", "w_passes",
    ]
    for name in forbidden:
        assert SH.is_invariant_name(name), name
        assert SH.active_knob(name) is None
        r = SH.set_knob(name, 0)
        assert r["ok"] is False, name
        assert SH.stepped_value(name, "up") is None
        try:
            SH.clamp(name, 1)
            assert False, f"clamp should have raised for {name}"
        except ValueError:
            pass


def test_defaults_file_cannot_widen_bounds_or_add_invariants(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    fake = tmp_path / "defaults.json"
    fake.write_text(json.dumps({
        "knobs": {
            "park_cycles": {"default": 6, "lo": 1, "hi": 1000},
            "p_min": {"default": 0.5, "lo": 0.1, "hi": 1.0},
            "perturb_epsilon": {"default": 0.99},  # out of code bounds
        }
    }), encoding="utf-8")
    monkeypatch.setattr(SH, "DEFAULTS_PATH", fake)
    defaults = SH.default_knobs()
    assert "p_min" not in defaults
    # Out-of-bounds file default is ignored; code default is used.
    assert defaults["perturb_epsilon"] == SH.KNOB_SPECS["perturb_epsilon"].default
    # Widened file bounds cannot be used: in_bounds still uses code.
    assert not SH.in_bounds("park_cycles", 1000)
    assert SH.KNOB_SPECS["park_cycles"].hi == 18


def test_load_state_drops_invariant_and_oob_knobs(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    SH.STATE_PATH.write_text(json.dumps({
        "knobs": {"park_cycles": 8, "p_min": 0.5, "perturb_epsilon": 9.0, "authorize": True},
        "evidence": [],
    }), encoding="utf-8")
    st = SH.load_state()
    assert st["knobs"]["park_cycles"] == 8
    assert "p_min" not in st["knobs"]
    assert "authorize" not in st["knobs"]
    assert st["knobs"]["perturb_epsilon"] == SH.KNOB_SPECS["perturb_epsilon"].default


def test_defaults_match_stall_constants():
    assert SH.KNOB_SPECS["park_cycles"].default == S.PARK_CYCLES
    assert SH.KNOB_SPECS["block_streak_to_park"].default == S.BLOCK_STREAK_TO_PARK
    assert SH.KNOB_SPECS["stall_cycles"].default == S.STALL_CYCLES
    assert SH.KNOB_SPECS["stall_dead_end_cycles"].default == S.STALL_DEAD_END_CYCLES
    assert SH.KNOB_SPECS["perturb_max_cycles"].default == S.PERTURB_MAX_CYCLES
    assert SH.KNOB_SPECS["perturb_epsilon"].default == S.PERTURB_EPSILON
    assert SH.KNOB_SPECS["perturb_wide_epsilon"].default == S.PERTURB_WIDE_EPSILON
    assert SH.KNOB_SPECS["perturb_min_targets"].default == S.PERTURB_MIN_TARGETS
    assert SH.KNOB_SPECS["perturb_cooldown_cycles"].default == S.PERTURB_COOLDOWN_CYCLES
    assert SH.KNOB_SPECS["perturb_zero_pick_cycles"].default == S.PERTURB_ZERO_PICK_CYCLES
    assert SH.KNOB_SPECS["unused_menu_cycles"].default == S.UNUSED_MENU_CYCLES


def test_metric_weights_are_fixed():
    assert SH.score_metrics(1, 1, 1) == SH.W_TARGETS + SH.W_DEPTH + SH.W_PASSES
    assert SH.score_metrics(2, 0, 1) == 2 * SH.W_TARGETS + SH.W_PASSES
    assert SH.score_metrics(0, 0, -1) == -SH.W_PASSES
    # A drop in passes scores worse than a flat window.
    assert SH.score_metrics(0, 0, -1) < SH.score_metrics(0, 0, 0)


# ---------------------------------------------------------------------------
# Adopt / revert
# ---------------------------------------------------------------------------

def test_adopt_when_trial_beats_baseline(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _prime_baseline(6, score_targets=0)
    st = SH.load_state()
    trial = {
        "knob": "perturb_cooldown_cycles",
        "from": 6,
        "to": 9,
        "direction": "up",
        "reason": "no_progress_perturb",
        "window": 6,
        "baseline_score": 0.0,
        "baseline_metrics": st["metrics"],
        "trial_metrics": [],
        "started_cycle": "b5",
        "started_index": 5,
    }
    SH.start_trial(trial, state=st, cycle_id="t0")
    # Six trial cycles that each found a new Oracle-reaching target.
    for i in range(6):
        out = SH.run_cycle(f"t{i+1}", metrics=_metric(f"t{i+1}", targets=1))
    assert out["ok"]
    vis = SH.visibility()
    assert vis["self_changes_adopted"] == 1
    assert vis["self_changes_reverted"] == 0
    assert vis["last_self_change"]["event"] == "adopt"
    assert vis["last_self_change"]["knob"] == "perturb_cooldown_cycles"
    assert vis["last_self_change"]["to"] == 9
    assert vis["last_self_change"]["trial_score"] > vis["last_self_change"]["baseline_score"]
    assert SH.current_knob("perturb_cooldown_cycles") == 9
    # Evidence is on disk with the numbers.
    ev = [e for e in SH.load_state()["evidence"] if e["event"] == "adopt"]
    assert len(ev) == 1
    assert ev[0]["baseline_score"] == 0.0
    assert ev[0]["trial_score"] == 6.0
    assert ev[0]["authorized"] is False
    assert ev[0]["applied_to_live_oracle"] is False


def test_revert_when_trial_does_not_help(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _prime_baseline(6, score_targets=1)  # baseline already scoring
    st = SH.load_state()
    baseline = SH.window_score(st["metrics"][-6:])
    assert baseline == 6.0
    trial = {
        "knob": "unused_menu_cycles",
        "from": 20,
        "to": 24,
        "direction": "up",
        "reason": "repeated_targets",
        "window": 6,
        "baseline_score": baseline,
        "baseline_metrics": st["metrics"][-6:],
        "trial_metrics": [],
    }
    SH.start_trial(trial, state=st, cycle_id="t0")
    assert SH.current_knob("unused_menu_cycles") == 24
    for i in range(6):
        out = SH.run_cycle(f"t{i+1}", metrics=_metric(f"t{i+1}", targets=0))
    vis = SH.visibility()
    assert vis["self_changes_adopted"] == 0
    assert vis["self_changes_reverted"] == 1
    assert vis["last_self_change"]["event"] == "revert"
    assert vis["last_self_change"]["helped"] is False
    # Restored.
    assert SH.current_knob("unused_menu_cycles") == 20


def test_tie_reverts(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _prime_baseline(6, score_targets=1)
    st = SH.load_state()
    trial = {
        "knob": "park_cycles",
        "from": 6,
        "to": 8,
        "direction": "up",
        "reason": "dead_end_streak",
        "window": 6,
        "baseline_score": 6.0,
        "baseline_metrics": st["metrics"][-6:],
        "trial_metrics": [],
    }
    SH.start_trial(trial, state=st, cycle_id="t0")
    for i in range(6):
        SH.run_cycle(f"t{i+1}", metrics=_metric(f"t{i+1}", targets=1))
    vis = SH.visibility()
    assert vis["self_changes_reverted"] == 1
    assert vis["self_changes_adopted"] == 0
    assert SH.current_knob("park_cycles") == 6


def test_no_trial_until_baseline_window_is_full(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    findings = [{"kind": "flat_passes", "evidence": {"stall_cycles": 8, "threshold": 6}}]
    out = SH.run_cycle("c1", metrics=_metric("c1"), findings=findings)
    assert out["trial_started"] is False
    assert out["trial"] is None
    # Five more (total 6) — the 6th can start a trial (baseline is those 6).
    for i in range(2, 6):
        out = SH.run_cycle(f"c{i}", metrics=_metric(f"c{i}"), findings=findings)
        assert out["trial_started"] is False
    out = SH.run_cycle("c6", metrics=_metric("c6"), findings=findings)
    assert out["trial_started"] is True
    assert out["trial"]["knob"] in (
        "perturb_epsilon", "unused_menu_cycles", "perturb_max_cycles",
    )


def test_one_trial_at_a_time(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _prime_baseline(6)
    findings = [{"kind": "flat_passes", "evidence": {}}]
    out1 = SH.run_cycle("c7", metrics=_metric("c7"), findings=findings)
    assert out1["trial_started"] is True
    out2 = SH.run_cycle("c8", metrics=_metric("c8"), findings=findings)
    assert out2["trial_started"] is False
    assert out2["trial"]["knob"] == out1["trial"]["knob"]


def test_replay_rejects_already_reverted_change(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    ev = [{
        "event": "revert",
        "knob": "perturb_cooldown_cycles",
        "from": 6,
        "to": 9,
        "direction": "up",
    }]
    r = SH.replay_proposal("perturb_cooldown_cycles", 6, 9, direction="up", evidence=ev)
    assert r["accepted"] is False
    assert "already_reverted_same_change" in r["reasons"]
    r2 = SH.replay_proposal("perturb_cooldown_cycles", 6, 10, direction="up", evidence=ev)
    # Different target: not an exact repeat. Online trial may still decide.
    assert r2["accepted"] is True
    r3 = SH.replay_proposal("p_min", 0.7, 0.8, direction="up", evidence=[])
    assert r3["accepted"] is False


def test_evidence_is_append_only(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st = SH.load_state()
    e1 = SH.append_evidence(st, {"event": "adopt", "knob": "park_cycles", "from": 6, "to": 8})
    SH.save_state(st)
    first_id = e1["id"]
    # Try to rewrite the first event through save_state.
    st2 = SH.load_state()
    st2["evidence"] = [{"id": first_id, "event": "adopt", "knob": "TAMPERED", "from": 0, "to": 0}]
    SH.save_state(st2)
    st3 = SH.load_state()
    by_id = {e["id"]: e for e in st3["evidence"]}
    assert by_id[first_id]["knob"] == "park_cycles"
    assert by_id[first_id]["to"] == 8
    # A new event is appended.
    SH.append_evidence(st3, {"event": "revert", "knob": "park_cycles", "from": 8, "to": 6})
    SH.save_state(st3)
    ids = [e["id"] for e in SH.load_state()["evidence"]]
    assert first_id in ids
    assert len(ids) == 2
    # jsonl also only grew.
    lines = SH.EVENT_LOG.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 2
    assert "TAMPERED" not in SH.EVENT_LOG.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Recursion (meta knobs) is bounded
# ---------------------------------------------------------------------------

def test_step_size_and_evaluation_window_are_bounded_knobs(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert "step_size" in SH.KNOB_SPECS
    assert "evaluation_window" in SH.KNOB_SPECS
    assert SH.KNOB_SPECS["step_size"].group == "meta"
    assert SH.KNOB_SPECS["evaluation_window"].group == "meta"
    # Repeated "up" steps cannot escape the max.
    v = SH.KNOB_SPECS["step_size"].default
    for _ in range(40):
        nxt = SH.stepped_value("step_size", "up", current=v, step_size=0.4)
        if nxt is None:
            break
        v = nxt
    assert v == SH.KNOB_SPECS["step_size"].hi
    w = SH.KNOB_SPECS["evaluation_window"].default
    for _ in range(40):
        nxt = SH.stepped_value("evaluation_window", "up", current=w, step_size=0.4)
        if nxt is None:
            break
        w = nxt
    assert w == SH.KNOB_SPECS["evaluation_window"].hi
    # Same for down.
    v = SH.KNOB_SPECS["step_size"].default
    for _ in range(40):
        nxt = SH.stepped_value("step_size", "down", current=v, step_size=0.4)
        if nxt is None:
            break
        v = nxt
    assert v == SH.KNOB_SPECS["step_size"].lo


def test_meta_knob_follows_the_same_evidence_rule(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _prime_baseline(6, score_targets=0)
    findings = [{"kind": "high_revert_rate", "evidence": {"recent_trials": 4, "reverts": 3}}]
    out = SH.run_cycle("c7", metrics=_metric("c7"), findings=findings)
    assert out["trial_started"] is True
    assert out["trial"]["knob"] in ("step_size", "evaluation_window")
    # A helpful trial adopts it.
    knob = out["trial"]["knob"]
    target = out["trial"]["to"]
    for i in range(6):
        SH.run_cycle(f"u{i}", metrics=_metric(f"u{i}", targets=1), findings=[])
    vis = SH.visibility()
    assert vis["self_changes_adopted"] == 1
    assert vis["last_self_change"]["knob"] == knob
    assert SH.current_knob(knob) == target


def test_epsilon_pair_stays_legal(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st = SH.load_state()
    # Setting epsilon above current wide raises wide (or is kept legal).
    r = SH.set_knob("perturb_epsilon", 0.6, state=st)
    assert r["ok"] is True
    knobs = r["state"]["knobs"]
    assert knobs["perturb_wide_epsilon"] >= knobs["perturb_epsilon"]
    assert SH.in_bounds("perturb_wide_epsilon", knobs["perturb_wide_epsilon"])


# ---------------------------------------------------------------------------
# Quarantine
# ---------------------------------------------------------------------------

def test_quarantine_after_threshold_and_expires(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st = SH.load_state()
    st["cycle_index"] = 10
    SH.save_state(st)
    # Default threshold is 2.
    r1 = SH.note_failure("stall_perturb", RuntimeError("boom1"), "c1")
    assert r1["recorded"] is True
    assert r1["quarantined"] is False
    assert SH.is_quarantined("stall_perturb") is False
    r2 = SH.note_failure("stall_perturb", RuntimeError("boom2"), "c2")
    assert r2["quarantined"] is True
    assert SH.is_quarantined("stall_perturb") is True
    steps = SH.quarantined_steps()
    assert any(s["step"] == "stall_perturb" for s in steps)
    # Advance past the quarantine window.
    st = SH.load_state()
    q_cycles = int(SH.current_knob("quarantine_cycles"))
    st["cycle_index"] = 10 + q_cycles
    SH.expire_quarantines(st)
    SH.save_state(st)
    assert SH.is_quarantined("stall_perturb") is False
    assert SH.quarantined_steps() == []


def test_cannot_quarantine_protected_gates(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    for name in (
        "trust_gate", "trust_gate_pre", "oracle", "oracle_check",
        "authorize", "athanor", "witness", "p_gate", "standing_trust",
        "human_guide",
    ):
        assert SH.is_protected_step(name), name
        r = SH.note_failure(name, RuntimeError("nope"), "c1")
        assert r["protected"] is True
        assert r["quarantined"] is False
        assert r["recorded"] is False
        assert SH.is_quarantined(name) is False
        # run_step must not swallow a protected failure.
        def _boom():
            raise RuntimeError("gate failed")
        try:
            SH.run_step(name, _boom, cycle_id="c1")
            assert False, f"protected step {name} should propagate"
        except RuntimeError as exc:
            assert "gate failed" in str(exc)


def test_run_step_skips_quarantined_and_records_throws(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st = SH.load_state()
    st["cycle_index"] = 3
    st["quarantine"] = {"oeis_idle": {"until_index": 10, "reason": "test"}}
    SH.save_state(st)
    called = []
    out = SH.run_step("oeis_idle", lambda: called.append(1), cycle_id="c")
    assert out["skipped"] is True
    assert out["quarantined"] is True
    assert called == []
    # A throw on a free optional step is recorded, not raised.
    out2 = SH.run_step("checker_lane", lambda: (_ for _ in ()).throw(ValueError("x")), cycle_id="c")
    assert out2["ok"] is False
    assert "ValueError" in out2["error"]
    assert SH.load_state()["failures"]


def test_run_step_never_silences_a_gate(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    ran = []
    out = SH.run_step("trust_gate", lambda: ran.append("ok") or "passed", cycle_id="c")
    assert out["ok"] is True
    assert out["protected"] is True
    assert out["result"] == "passed"


# ---------------------------------------------------------------------------
# Diagnosis, stall wiring, visibility
# ---------------------------------------------------------------------------

def test_diagnose_repeated_targets(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    stall = {
        "cycles": ["c1", "c2", "c3"],
        "targets_tried": [
            {"cycle_id": "c1", "targets": ["oc_A1_0"]},
            {"cycle_id": "c2", "targets": ["oc_A1_0"]},
            {"cycle_id": "c3", "targets": ["oc_A1_0"]},
        ],
        "perturb": {},
        "turns": [],
        "stall_cycles": 0,
    }
    findings = SH.diagnose("c3", stall_state=stall, heal_state=SH.load_state())
    kinds = [f["kind"] for f in findings]
    assert "repeated_targets" in kinds
    ev = next(f["evidence"] for f in findings if f["kind"] == "repeated_targets")
    assert ev["distinct_targets_last_3"] == 1


def test_diagnose_no_progress_perturb(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    stall = {
        "cycles": ["c1"],
        "targets_tried": [],
        "turns": [],
        "stall_cycles": 0,
        "perturb": {
            "active": False,
            "exit_reason": "timeout",
            "session_progress": False,
            "session_targets": ["oc_X"],
            "timeout_count": 1,
        },
    }
    findings = SH.diagnose("c1", stall_state=stall, heal_state=SH.load_state())
    assert any(f["kind"] == "no_progress_perturb" for f in findings)


def test_stall_reads_policy_override(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    # No override: stall uses its own constant (and monkeypatches still work).
    assert S._policy("park_cycles", S.PARK_CYCLES) == S.PARK_CYCLES
    monkeypatch.setattr(S, "PARK_CYCLES", 4)
    assert S._policy("park_cycles", S.PARK_CYCLES) == 4
    monkeypatch.setattr(S, "PARK_CYCLES", 6)
    # An adopted override is honoured.
    st = SH.load_state()
    r = SH.set_knob("park_cycles", 10, state=st)
    assert r["ok"]
    SH.save_state(r["state"])
    assert SH.active_knob("park_cycles") == 10
    assert S._policy("park_cycles", S.PARK_CYCLES) == 10
    # assess_stall uses the policy stall_cycles when overridden.
    st2 = SH.load_state()
    SH.set_knob("stall_cycles", 4, state=st2)
    SH.save_state(st2)
    # 4 flat snapshots should now trip STALL (default is 6).
    S.save_state({
        **S._empty_state(),
        "pass_history": [{"cycle_id": f"c{i}", "pass_total": 528} for i in range(4)],
        "cycles": [f"c{i}" for i in range(4)],
        "turns": [{"cycle_id": f"c{i}", "kind": "oeis", "name": "t", "outcome": "pass"} for i in range(4)],
    })
    report = S.assess_stall()
    assert report["on"] is True
    assert report["reason"] == "flat_passes"


def test_family_rotation_reads_policy(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    import colony.oeis_conjectures as OC
    assert OC._rotation_penalty() == 0.85
    st = SH.load_state()
    SH.set_knob("family_rotation_penalty", 0.6, state=st)
    SH.save_state(st)
    assert OC._rotation_penalty() == 0.6


def test_visibility_and_format(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    line = SH.format_visibility()
    assert "self_changes_adopted 0" in line
    assert "self_changes_reverted 0" in line
    assert "last_self_change none" in line
    assert "quarantined steps: none" in line
    vis = SH.visibility()
    assert vis["self_changes_adopted"] == 0
    assert vis["self_changes_reverted"] == 0
    assert vis["last_self_change"] is None
    assert vis["quarantined_steps"] == []


def test_telemetry_and_dashboard_surface_fields(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _prime_baseline(6)
    st = SH.load_state()
    trial = {
        "knob": "perturb_cooldown_cycles",
        "from": 6, "to": 9, "direction": "up",
        "reason": "no_progress_perturb", "window": 6,
        "baseline_score": 0.0, "baseline_metrics": st["metrics"],
        "trial_metrics": [],
    }
    SH.start_trial(trial, state=st, cycle_id="t0")
    for i in range(6):
        SH.run_cycle(f"t{i+1}", metrics=_metric(f"t{i+1}", targets=1))
    vis = SH.visibility()
    line = SH.format_visibility(vis)
    monkeypatch.setattr(SH, "visibility", lambda state=None: vis)
    monkeypatch.setattr(SH, "format_visibility", lambda v=None: line)

    snap = telemetry.gather_internal({"fitness_history": [], "agents": {}})
    assert snap["self_changes_adopted"] == 1
    assert snap["self_changes_reverted"] == 0
    assert snap["last_self_change"]["event"] == "adopt"
    assert snap["quarantined_steps"] == []

    data = tmp_path / "data"
    data.mkdir()
    (tmp_path / "society").mkdir(exist_ok=True)
    (data / "society_state.json").write_text(json.dumps({
        "cycle_count": 1,
        "fitness_history": [{"cycle_id": "c1", "aggregate": 1}],
        "agents": {},
        "roles": {},
        "tribute_mandate": {"active_ask": "watch"},
    }), encoding="utf-8")
    dashboard.refresh_dashboard(tmp_path)
    html = (tmp_path / "society" / "DASHBOARD.html").read_text(encoding="utf-8")
    summary = (tmp_path / "society" / "WITNESS_SUMMARY.md").read_text(encoding="utf-8")
    assert "Self-heal" in html
    assert "self_changes_adopted" in html
    assert "self_changes_adopted 1" in html
    assert "Self-heal" in summary
    assert "self_changes_adopted" in summary


def test_on_cycle_swallows_exceptions(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    def _boom(*a, **k):
        raise RuntimeError("diagnosed fail")

    monkeypatch.setattr(SH, "run_cycle", _boom)
    out = SH.on_cycle("c1")
    assert out["ok"] is False
    assert "RuntimeError" in out["error"]
    assert out["applied_to_live_oracle"] is False
    assert out["authorized"] is False


def test_evolve_hook_is_guarded():
    src = Path(__file__).resolve().parents[1] / "colony" / "emergence" / "growth_steps_evolve.py"
    text = src.read_text(encoding="utf-8")
    assert "from colony.self_heal import on_cycle" in text
    idx = text.index("from colony.self_heal import on_cycle")
    window = text[max(0, idx - 80): idx + 320]
    assert "try:" in window
    assert "except Exception:" in window
    assert "on_cycle(cycle_id)" in window
    assert "authorize" not in window.lower() or "authorize=false" in window.lower()


def test_does_not_write_human_guide_or_oracle(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    src = Path(__file__).resolve().parents[1] / "colony" / "self_heal.py"
    text = src.read_text(encoding="utf-8")
    assert "write_human_guide" not in text
    assert "ORACLE_LOG" not in text
    # A full adopt cycle leaves the Oracle log untouched.
    oracle = tmp_path / "oracle.jsonl"
    oracle.write_text("", encoding="utf-8")
    import colony.oracle as O
    monkeypatch.setattr(O, "ORACLE_LOG", oracle)
    _prime_baseline(6)
    findings = [{"kind": "flat_passes", "evidence": {}}]
    SH.run_cycle("c7", metrics=_metric("c7"), findings=findings)
    for i in range(6):
        SH.run_cycle(f"u{i}", metrics=_metric(f"u{i}", targets=1), findings=[])
    assert oracle.read_text(encoding="utf-8") == ""


def test_collect_metrics_from_stall_and_attempts(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    stall = {
        "targets_tried": [
            {"cycle_id": "c0", "targets": ["old"]},
            {"cycle_id": "c1", "targets": ["new_a", "old"]},
        ],
        "turns": [
            {"cycle_id": "c1", "name": "new_a", "outcome": "kill"},
            {"cycle_id": "c1", "name": "new_b", "outcome": "pass"},
            {"cycle_id": "c1", "name": "parked", "outcome": "skip"},
        ],
        "pass_history": [
            {"cycle_id": "c0", "pass_total": 528},
            {"cycle_id": "c1", "pass_total": 529},
        ],
    }
    log = {"attempts": [
        # Real depth advance this cycle: first past-b-file hold, no prior.
        {"cycle_id": "c1", "beyond": True, "id": "oc_A1",
         "planned": 8000, "verified_depth": 2000, "depth": 2000,
         "bfile_hi": 100, "extended": 1900, "status": "holds_on_range"},
        # Published-range hold: not new depth.
        {"cycle_id": "c1", "beyond": False, "id": "oc_A2",
         "planned": 45, "verified_depth": 45, "depth": 45,
         "bfile_hi": 45, "extended": 0, "status": "holds_on_range"},
        # Earlier cycle, ignored.
        {"cycle_id": "c0", "beyond": True, "id": "oc_A3",
         "planned": 500, "verified_depth": 500, "depth": 500,
         "bfile_hi": 100, "extended": 400, "status": "holds_on_range"},
    ]}
    m = SH.collect_metrics("c1", stall_state=stall, attempt_log=log)
    # new_a (tried + oracle) and new_b (oracle only) are new; old is not; skip is not.
    assert m["new_oracle_targets"] == 2
    assert m["new_depth"] == 1
    assert m["oracle_passes"] == 529
    assert m["oracle_pass_delta"] == 1
    assert m["score"] == SH.score_metrics(2, 1, 1)

# ---------------------------------------------------------------------------
# Item 32 — environment fingerprint and confound void
# ---------------------------------------------------------------------------

def test_fingerprint_stable_and_ignores_trialled_knob(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st = SH.load_state()
    a = SH.environment_fingerprint(state=st)
    b = SH.environment_fingerprint(state=st)
    assert a["digest"] == b["digest"]
    assert a["code"]
    assert a["knobs"]
    # Changing only the trialled knob does not change the trial fingerprint.
    st["knobs"]["perturb_cooldown_cycles"] = 8
    c = SH.environment_fingerprint(exclude_knob="perturb_cooldown_cycles", state=st)
    d = SH.environment_fingerprint(exclude_knob="perturb_cooldown_cycles", state=SH.load_state())
    assert c["digest"] == d["digest"]
    assert "perturb_cooldown_cycles" not in c["knobs"]


def test_fingerprint_changes_when_a_cap_knob_moves(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    st = SH.load_state()
    before = SH.environment_fingerprint(exclude_knob="perturb_cooldown_cycles", state=st)
    st["knobs"]["fast_term_cap"] = 16000
    after = SH.environment_fingerprint(exclude_knob="perturb_cooldown_cycles", state=st)
    assert before["digest"] != after["digest"]
    assert before["knobs"]["fast_term_cap"] != after["knobs"]["fast_term_cap"]
    # Code digest is unchanged; only the cap moved.
    assert before["code"] == after["code"]


def test_start_trial_records_fingerprint(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _prime_baseline(6)
    st = SH.load_state()
    trial = {
        "knob": "perturb_cooldown_cycles", "from": 6, "to": 8,
        "direction": "up", "reason": "no_progress_perturb",
        "window": 6, "baseline_score": 0.0,
        "baseline_metrics": st["metrics"], "trial_metrics": [],
    }
    SH.start_trial(trial, state=st, cycle_id="t0")
    live = SH.load_state()["trial"]
    assert live["environment_fingerprint"]
    ev = [e for e in SH.load_state()["evidence"] if e["event"] == "trial_start"]
    assert ev[0]["environment_fingerprint"] == live["environment_fingerprint"]
    # The recorded digest matches the live environment excluding the trialled knob.
    fp = SH.environment_fingerprint(exclude_knob="perturb_cooldown_cycles", state=SH.load_state())
    assert live["environment_fingerprint"] == fp["digest"]


def test_cap_change_mid_trial_voids_no_adopt_no_revert(tmp_path, monkeypatch):
    """A raised evaluator cap mid-trial is a confound: void, restore knob,
    do not adopt, do not count a revert-as-negative."""
    _isolate(tmp_path, monkeypatch)
    _prime_baseline(6)
    st = SH.load_state()
    trial = {
        "knob": "perturb_cooldown_cycles", "from": 6, "to": 8,
        "direction": "up", "reason": "no_progress_perturb",
        "window": 6, "baseline_score": 0.0,
        "baseline_metrics": st["metrics"], "trial_metrics": [],
        "started_cycle": "b5",
    }
    SH.start_trial(trial, state=st, cycle_id="t0")
    assert SH.current_knob("perturb_cooldown_cycles") == 8
    # Three scoring cycles that would, if they finished the window, adopt.
    for i in range(3):
        out = SH.run_cycle(f"t{i+1}", metrics=_metric(f"t{i+1}", depth=2))
        assert out["trial"] is not None
    # Mid-trial: a different knob (the evaluator cap) moves, as PR #7 did.
    st = SH.load_state()
    st["knobs"]["fast_term_cap"] = 16000
    SH.save_state(st)
    evidence_before = list(SH.load_state()["evidence"])
    ids_before = [e["id"] for e in evidence_before]
    out = SH.run_cycle("t4", metrics=_metric("t4", depth=2))
    st = SH.load_state()
    assert out["trial"] is None
    assert st["trial"] is None
    ev = [e for e in st["evidence"] if e["event"] == "trial_voided_confound"]
    assert len(ev) == 1
    assert ev[0]["knob"] == "perturb_cooldown_cycles"
    assert ev[0]["old_fingerprint"]
    assert ev[0]["new_fingerprint"]
    assert ev[0]["old_fingerprint"] != ev[0]["new_fingerprint"]
    assert ev[0]["old_fingerprint"] != SH.UNRECORDED_FINGERPRINT
    assert ev[0]["reason"] == "environment_changed"
    assert ev[0]["adopted"] is False
    assert ev[0]["reverted"] is False
    assert ev[0]["to"] == 6
    assert ev[0]["from"] == 8
    # Knob restored; not counted as a failed trial.
    assert SH.current_knob("perturb_cooldown_cycles") == 6
    assert st["adopted_count"] == 0
    assert st["reverted_count"] == 0
    assert vis_event_is_void()
    # Append-only: earlier events are untouched.
    by_id = {e["id"]: e for e in st["evidence"]}
    for eid in ids_before:
        assert by_id[eid]["event"] == next(e["event"] for e in evidence_before if e["id"] == eid)
    # A void is not a revert: the same change may be retried after a clean baseline.
    replay = SH.replay_proposal("perturb_cooldown_cycles", 6, 8, direction="up",
                                evidence=list(st["evidence"]))
    assert replay["accepted"] is True


def vis_event_is_void():
    vis = SH.visibility()
    assert vis["last_self_change"]["event"] == "trial_voided_confound"
    assert vis["self_changes_adopted"] == 0
    assert vis["self_changes_reverted"] == 0
    return True


def test_inflight_pr7_trial_voids_instead_of_adopting(tmp_path, monkeypatch):
    """Replica of the live perturb_cooldown 6→8 trial after PR #7.

    Baseline was corrected to 0.0; cycle 874 scored real new_depth=2 from
    raised caps, not from the cooldown knob. 3 of 6 trial metrics already
    total 2.0, so the next run would adopt. The trial has no fingerprint
    (it started under older code) and must void.
    """
    _isolate(tmp_path, monkeypatch)
    st = SH.load_state()
    baseline = [_metric(f"b{i}") for i in range(6)]
    for r in baseline:
        r["new_depth"] = 0
        r["score"] = 0.0
    trial_rows = [
        _metric("20261113T014648Z_b2870e", depth=2),
        _metric("20261113T015010Z_6a67d4"),
        _metric("20261113T015301Z_759b6f"),
    ]
    st["metrics"] = baseline + trial_rows
    st["knobs"]["perturb_cooldown_cycles"] = 8
    st["trial"] = {
        "knob": "perturb_cooldown_cycles",
        "from": 6, "to": 8, "direction": "up",
        "reason": "no_progress_perturb",
        "window": 6,
        "baseline_score": 0.0,
        "baseline_score_original": 2.0,
        "baseline_corrected": True,
        "baseline_metrics": [dict(r) for r in baseline],
        "trial_metrics": [dict(r) for r in trial_rows],
        "started_cycle": "20261113T010908Z_57af80",
        "started_index": 5,
        "applied_to_live_oracle": False,
        "authorized": False,
        # No environment_fingerprint: started before this mechanism existed.
    }
    st["adopted_count"] = 0
    st["reverted_count"] = 0
    SH.save_state(st)
    # Three more zero-score cycles would complete the window at trial_score=2.0
    # vs baseline 0.0 and adopt, if we did not void.
    out = SH.run_cycle("20261113T020000Z_next", metrics=_metric("20261113T020000Z_next"))
    st = SH.load_state()
    assert out["ok"] is True
    assert st["trial"] is None
    ev = [e for e in st["evidence"] if e.get("event") == "trial_voided_confound"]
    assert ev
    assert ev[0]["old_fingerprint"] == SH.UNRECORDED_FINGERPRINT
    assert ev[0]["new_fingerprint"]
    assert ev[0]["reason"] == "unrecorded_environment"
    assert ev[0]["adopted"] is False
    assert ev[0]["reverted"] is False
    assert ev[0]["knob"] == "perturb_cooldown_cycles"
    assert ev[0]["to"] == 6
    assert SH.current_knob("perturb_cooldown_cycles") == 6
    assert st["adopted_count"] == 0
    assert st["reverted_count"] == 0
    # History of the trial is preserved on the event, not rewritten away.
    assert len(ev[0]["trial_metrics"]) == 3
    assert ev[0]["trial_metrics"][0]["new_depth"] == 2
    assert ev[0]["baseline_score"] == 0.0


def test_voided_trial_does_not_adopt_even_if_window_is_full(tmp_path, monkeypatch):
    """maybe_close_trial must void, not adopt, a confounded complete window."""
    _isolate(tmp_path, monkeypatch)
    st = SH.load_state()
    rows = [_metric(f"t{i}", depth=1) for i in range(6)]
    st["knobs"]["perturb_cooldown_cycles"] = 8
    st["trial"] = {
        "knob": "perturb_cooldown_cycles", "from": 6, "to": 8,
        "direction": "up", "reason": "no_progress_perturb",
        "window": 6, "baseline_score": 0.0,
        "baseline_metrics": [_metric(f"b{i}") for i in range(6)],
        "trial_metrics": rows,
    }
    # No fingerprint, and a full window that beats baseline.
    SH.save_state(st)
    st = SH.maybe_close_trial(SH.load_state(), "t5")
    assert st["trial"] is None
    assert st["adopted_count"] == 0
    assert st["reverted_count"] == 0
    assert st["knobs"]["perturb_cooldown_cycles"] == 6
    ev = [e for e in st["evidence"] if e["event"] == "trial_voided_confound"]
    assert ev
    assert ev[0]["adopted"] is False


def test_fresh_baseline_required_after_void(tmp_path, monkeypatch):
    """After a void, a new trial waits for a full same-fingerprint window.

    Confounded metrics (the cap-driven new_depth=2 row, or unfingerprinted
    history) must not become the next baseline.
    """
    _isolate(tmp_path, monkeypatch)
    findings = [{"kind": "no_progress_perturb", "evidence": {"timeout_count": 1}}]
    # Six unfingerprinted (legacy) metrics — not a clean baseline.
    st = SH.load_state()
    st["metrics"] = [_metric(f"old{i}", depth=2 if i == 0 else 0) for i in range(6)]
    # First is the confounded cap-driven gain.
    SH.save_state(st)
    out = SH.run_cycle("n1", metrics=_metric("n1"), findings=findings)
    assert out["trial_started"] is False
    assert out["trial"] is None
    # n2–n5: last-6 window still contains at least one unfingerprinted row.
    for i in range(2, 6):
        out = SH.run_cycle(f"n{i}", metrics=_metric(f"n{i}"), findings=findings)
        assert out["trial_started"] is False, i
    # n6: last 6 are all new, same-fingerprint cycles.
    out = SH.run_cycle("n6", metrics=_metric("n6"), findings=findings)
    started = out["trial_started"]
    assert started is True
    # The new baseline does not include the confounded new_depth=2.
    trial = out["trial"]
    assert trial["baseline_score"] == 0.0
    assert all(int(r.get("new_depth") or 0) == 0 for r in trial["baseline_metrics"])
    assert all(r.get("env_fingerprint") for r in trial["baseline_metrics"])
    assert trial["environment_fingerprint"]


def test_code_fingerprint_change_voids_trial(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _prime_baseline(6)
    st = SH.load_state()
    trial = {
        "knob": "park_cycles", "from": 6, "to": 8,
        "direction": "up", "reason": "dead_end_streak",
        "window": 6, "baseline_score": 0.0,
        "baseline_metrics": st["metrics"], "trial_metrics": [],
    }
    SH.start_trial(trial, state=st, cycle_id="t0")
    monkeypatch.setattr(SH, "_colony_file_digest", lambda: "deadbeef" * 8)
    # Clear any module cache confusion: the function is patched.
    out = SH.run_cycle("t1", metrics=_metric("t1", targets=1))
    st = SH.load_state()
    assert st["trial"] is None
    ev = [e for e in st["evidence"] if e["event"] == "trial_voided_confound"]
    assert ev
    assert ev[0]["reason"] == "environment_changed"
    assert ev[0]["old_fingerprint"] != ev[0]["new_fingerprint"]
    assert SH.current_knob("park_cycles") == 6
    assert st["reverted_count"] == 0
    assert st["adopted_count"] == 0
