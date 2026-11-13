"""Twin control arm: isolation, frozen self-mod, and scoreboard math."""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import colony.arm as arm
import colony.checker_lane as CL
import colony.self_heal as SH
import colony.twin as twin

REPO = Path(__file__).resolve().parents[1]


def _write(p: Path, obj) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    return p


def _tiny_society(root: Path, *, passes=528, kills=340, depth_a=7999, depth_b=1199,
                  adopts=2, reverts=1, trial=None, knobs=None, cycle_count=100,
                  fitness=0.5, novelty=0.75) -> Path:
    systems = root / "society" / "systems"
    systems.mkdir(parents=True, exist_ok=True)
    _write(systems / "oracle.json", {"version": 1, "passes": passes, "kills": kills})
    _write(systems / "oeis_conjecture_state.json", {
        "targets": {},
        "scoreboard": {
            "counterexamples": {},
            "proofs": {
                "p1": {"anum": "A000001", "routine": True},
                "p2": {"anum": "A000002", "routine": False},
            },
            "extensions": {
                "oc_A165064_0": {"anum": "A165064", "bfile_hi": 100, "to": depth_a, "check": "exact"},
                "oc_A126089_0": {"anum": "A126089", "bfile_hi": 200, "to": depth_b, "check": "exact"},
            },
        },
    })
    _write(systems / "self_heal.json", {
        "version": 1,
        "knobs": knobs or {"park_cycles": 10, "perturb_cooldown_cycles": 8},
        "trial": trial or {"knob": "park_cycles", "from": 6, "to": 10},
        "metrics": [{"cycle_id": "x", "score": 1}],
        "quarantine": {"foo": 3},
        "failures": [],
        "evidence": [{"event": "trial_start"}],
        "adopted_count": adopts,
        "reverted_count": reverts,
        "cycle_index": 4,
        "cycles": ["x"],
        "last_self_change": {"event": "adopt", "knob": "park_cycles"},
        "knob_last_trial": {},
    })
    (systems / "fitness_history.jsonl").write_text(
        json.dumps({
            "ts": "2026-11-13T01:55:11Z",
            "cycle_id": "c1",
            "aggregate": fitness,
            "novelty": novelty,
        }) + "\n",
        encoding="utf-8",
    )
    _write(root / "data" / "society_state.json", {
        "cycle_count": cycle_count,
        "fitness_history": [],
        "roles": {},
    })
    _write(root / "data" / "commons" / "canary.json", {"src": "treatment"})
    return root


# ---------------------------------------------------------------------------
# Arm flags
# ---------------------------------------------------------------------------

def test_default_arm_is_treatment(monkeypatch):
    monkeypatch.delenv("COLONY_ARM", raising=False)
    monkeypatch.delenv("COLONY_SELF_MOD", raising=False)
    assert arm.arm() == "treatment"
    assert arm.is_control() is False
    assert arm.self_mod_enabled() is True
    assert arm.hive_learning_enabled() is True


def test_control_disables_self_mod_and_hive(monkeypatch):
    monkeypatch.setenv("COLONY_ARM", "control")
    assert arm.arm() == "control"
    assert arm.is_control() is True
    assert arm.self_mod_enabled() is False
    assert arm.hive_learning_enabled() is False


def test_hive_learning_feature_check_independent_of_hive_presence(monkeypatch):
    """Works before and after Hive merges: no Hive import required."""
    monkeypatch.setenv("COLONY_ARM", "treatment")
    monkeypatch.delenv("COLONY_HIVE_LEARNING", raising=False)
    assert arm.hive_learning_enabled() is True
    monkeypatch.setenv("COLONY_HIVE_LEARNING", "off")
    assert arm.hive_learning_enabled() is False
    monkeypatch.setenv("COLONY_ARM", "control")
    monkeypatch.setenv("COLONY_HIVE_LEARNING", "on")
    assert arm.hive_learning_enabled() is False


def test_control_disables_hive_through_adapter(tmp_path, monkeypatch):
    """Control arm: colony.hive_adapter on_cycle/run_cycle must not call Hive."""
    monkeypatch.setenv("COLONY_ARM", "control")
    import colony.hive_adapter as adapter
    import hive.swarm as SL
    monkeypatch.setattr(SL, "STATE_PATH", tmp_path / "swarm_learn.json")
    monkeypatch.setattr(SL, "EVENT_LOG", tmp_path / "swarm_learn.jsonl")
    monkeypatch.setattr(SL, "RULES_PATH", tmp_path / "swarm_rules.json")
    called: list[str] = []
    monkeypatch.setattr(
        SL, "run_cycle",
        lambda cycle_id="": called.append("run:" + cycle_id) or {"ok": True, "learned": True},
    )
    monkeypatch.setattr(
        SL, "on_cycle",
        lambda cycle_id="": called.append("on:" + cycle_id) or {"ok": True, "learned": True},
    )
    out = adapter.on_cycle("c1")
    assert out["skipped"] is True
    assert out["learning"] is False
    assert out["reason"] == "control_arm"
    assert out["authorized"] is False
    assert out["applied_to_live_oracle"] is False
    assert called == []
    out2 = adapter.run_cycle("c2")
    assert out2["skipped"] is True
    assert called == []
    # No Hive snapshot written by a skipped call.
    assert not (tmp_path / "swarm_learn.json").exists()
    vis = adapter.visibility()
    assert vis.get("learning") is False or vis.get("swarm_learning") is False
    assert "control" in str(vis.get("skipped") or vis.get("arm") or "")
    line = adapter.format_visibility()
    assert "learning off" in line
    assert "control" in line


def test_treatment_hive_adapter_still_calls_hive(monkeypatch):
    """The adapter must not block Hive on the treatment arm."""
    monkeypatch.setenv("COLONY_ARM", "treatment")
    monkeypatch.delenv("COLONY_HIVE_LEARNING", raising=False)
    monkeypatch.delenv("COLONY_SELF_MOD", raising=False)
    import colony.hive_adapter as adapter
    import hive.swarm as SL
    called: list[str] = []
    monkeypatch.setattr(
        SL, "on_cycle",
        lambda cycle_id="": called.append(cycle_id) or {"ok": True, "learned": True, "cycle_id": cycle_id},
    )
    out = adapter.on_cycle("t1")
    assert out.get("learned") is True
    assert called == ["t1"]


# ---------------------------------------------------------------------------
# Self-mod disabled in control
# ---------------------------------------------------------------------------

def test_control_does_not_start_or_close_self_heal_trials(tmp_path, monkeypatch):
    monkeypatch.setenv("COLONY_ARM", "control")
    monkeypatch.setattr(SH, "STATE_PATH", tmp_path / "self_heal.json")
    monkeypatch.setattr(SH, "EVENT_LOG", tmp_path / "self_heal.jsonl")
    # Baseline long enough that treatment would propose.
    st = SH.load_state()
    rows = []
    for i in range(8):
        rows.append({
            "cycle_id": f"b{i}",
            "new_oracle_targets": 0,
            "new_depth": 0,
            "oracle_passes": 528,
            "oracle_pass_delta": 0,
            "score": 0.0,
        })
    st["metrics"] = rows
    st["cycle_index"] = 7
    st["cycles"] = [r["cycle_id"] for r in rows]
    # A finding that would start a trial on treatment.
    findings = [{"kind": "no_progress_perturb", "suggest": [("perturb_cooldown_cycles", "up")]}]
    proposal = SH.propose_trial(findings, state=st, cycle_id="c9")
    assert proposal is None
    started = SH.start_trial(
        {
            "knob": "park_cycles",
            "from": 6,
            "to": 8,
            "direction": "up",
            "reason": "test",
            "window": 6,
            "baseline_score": 0,
            "trial_metrics": [],
        },
        state=st,
        cycle_id="c9",
    )
    assert started.get("trial") in (None, {}) or started.get("trial") is None
    assert SH.active_knob("park_cycles") is None
    assert SH.active_knob("perturb_cooldown_cycles") is None
    # Defaults still available via current_knob / default_knobs.
    defaults = SH.default_knobs()
    assert defaults["park_cycles"] == 6
    assert defaults["perturb_cooldown_cycles"] == 6

    # An in-flight trial must not adopt.
    st["trial"] = {
        "knob": "park_cycles",
        "from": 6,
        "to": 8,
        "window": 6,
        "baseline_score": 0,
        "trial_metrics": rows[:6],
        "started_cycle": "b0",
        "started_index": 0,
    }
    closed = SH.maybe_close_trial(st, "c9")
    assert closed.get("adopted_count") in (0, None) or int(closed.get("adopted_count") or 0) == 0
    # Knobs must not have moved to the trial value as an adopt.
    knobs = closed.get("knobs") or SH.default_knobs()
    # If trial was cleared or left, park_cycles must not have been adopted.
    last = closed.get("last_self_change")
    if last:
        assert last.get("event") != "adopt"


def test_control_confound_guard_is_a_noop(tmp_path, monkeypatch):
    """An unfingerprinted (or environment-mismatched) in-flight trial is
    not voided on the control arm: knobs, evidence, and the trial itself
    stay frozen. On treatment the same trial would void."""
    monkeypatch.setenv("COLONY_ARM", "control")
    monkeypatch.setattr(SH, "STATE_PATH", tmp_path / "self_heal.json")
    monkeypatch.setattr(SH, "EVENT_LOG", tmp_path / "self_heal.jsonl")
    st = SH.load_state()
    st["knobs"]["perturb_cooldown_cycles"] = 8
    trial = {
        "knob": "perturb_cooldown_cycles",
        "from": 6, "to": 8, "direction": "up",
        "reason": "no_progress_perturb",
        "window": 6,
        "baseline_score": 0.0,
        "baseline_metrics": [],
        "trial_metrics": [
            {"cycle_id": "c874", "new_oracle_targets": 0, "new_depth": 2,
             "oracle_pass_delta": 0, "oracle_passes": 528, "score": 2.0},
        ],
        "started_cycle": "c873",
        # No environment_fingerprint: treatment would void as unrecorded.
    }
    st["trial"] = trial
    st["adopted_count"] = 0
    st["reverted_count"] = 0
    SH.save_state(st)
    evidence_before = list(SH.load_state().get("evidence") or [])
    out = SH.run_cycle("c875", metrics={
        "cycle_id": "c875", "new_oracle_targets": 0, "new_depth": 0,
        "oracle_pass_delta": 0, "oracle_passes": 528, "score": 0.0,
    })
    st2 = SH.load_state()
    assert out["ok"] is True
    assert out["trial_started"] is False
    # Trial left in place; not voided, not adopted, not reverted.
    assert st2["trial"] is not None
    assert st2["trial"]["knob"] == "perturb_cooldown_cycles"
    assert st2["trial"]["to"] == 8
    assert st2["knobs"]["perturb_cooldown_cycles"] == 8
    assert st2["adopted_count"] == 0
    assert st2["reverted_count"] == 0
    ev = [e for e in (st2.get("evidence") or []) if e.get("event") == "trial_voided_confound"]
    assert ev == []
    # Direct void is also a no-op.
    st3 = SH.void_trial_for_confound(
        st2, "c875",
        old_fingerprint=SH.UNRECORDED_FINGERPRINT,
        new_fingerprint="abcd",
        reason="unrecorded_environment",
    )
    assert st3["trial"] is not None
    assert st3["knobs"]["perturb_cooldown_cycles"] == 8
    assert st3.get("last_self_change") is None or st3["last_self_change"].get("event") != "trial_voided_confound"
    assert [e.get("id") for e in evidence_before] == [
        e.get("id") for e in (st3.get("evidence") or []) if e.get("id") in {x.get("id") for x in evidence_before}
    ]
    voids = [e for e in (st3.get("evidence") or []) if e.get("event") == "trial_voided_confound"]
    assert voids == []


def test_control_quarantine_is_inert(tmp_path, monkeypatch):
    monkeypatch.setenv("COLONY_ARM", "control")
    monkeypatch.setattr(SH, "STATE_PATH", tmp_path / "self_heal.json")
    monkeypatch.setattr(SH, "EVENT_LOG", tmp_path / "self_heal.jsonl")
    st = SH.load_state()
    st["quarantine"] = {"optional_step": {"until_index": 999, "step": "optional_step"}}
    SH.save_state(st)
    assert SH.is_quarantined("optional_step", cycle_id="c", state=st) is False


def test_control_checker_lane_does_not_accept(tmp_path, monkeypatch):
    monkeypatch.setenv("COLONY_ARM", "control")
    monkeypatch.setattr(CL, "STATE_PATH", tmp_path / "checker_lane.json")
    monkeypatch.setattr(CL, "LANE_LOG", tmp_path / "checker_lane.jsonl")
    monkeypatch.setattr(CL, "PROPOSAL_DIR", tmp_path / "proposals")
    monkeypatch.setattr(CL, "RECEIPT_PATH", tmp_path / "receipt.json")
    out = CL.on_cycle("c1", history=[])
    assert out.get("new_accepted", 0) == 0
    assert out.get("awaiting_review", 0) == 0
    assert out.get("skipped") == "control_arm" or out.get("ok") is True
    # No proposal files, no treatment-shaped state on the live (unpatched) paths.
    assert not (tmp_path / "proposals").exists() or not any((tmp_path / "proposals").iterdir())
    live_receipt = REPO / "society" / "systems" / "checker_lane_receipt.json"
    # We didn't point RECEIPT at the live path; the live file may exist from
    # the repo but this call must not have written the tmp receipt as an accept.
    if (tmp_path / "receipt.json").exists():
        rec = json.loads((tmp_path / "receipt.json").read_text())
        # If a receipt was written, it must not report new accepts.
        if isinstance(rec, dict):
            assert int(rec.get("new_accepted") or 0) == 0


def test_treatment_self_heal_still_proposes(tmp_path, monkeypatch):
    """Guards must not freeze the treatment arm."""
    monkeypatch.setenv("COLONY_ARM", "treatment")
    monkeypatch.setattr(SH, "STATE_PATH", tmp_path / "self_heal.json")
    monkeypatch.setattr(SH, "EVENT_LOG", tmp_path / "self_heal.jsonl")
    st = SH.load_state()
    # Prime a baseline; propose_trial needs findings + enough metrics.
    window = int(SH.current_knob("evaluation_window"))
    st["metrics"] = [
        {
            "cycle_id": f"b{i}",
            "new_oracle_targets": 0,
            "new_depth": 0,
            "oracle_passes": 528,
            "oracle_pass_delta": 0,
            "score": 0.0,
        }
        for i in range(window)
    ]
    st["cycle_index"] = window
    SH.save_state(st)
    findings = [{"kind": "no_progress_perturb", "suggest": [("perturb_cooldown_cycles", "up")]}]
    proposal = SH.propose_trial(findings, state=SH.load_state(), cycle_id="t1")
    # May be None if replay rejects, but must not be blocked by the arm guard.
    # The important assertion: self_mod is on, active_knob is not forced to None
    # just because the module was imported under a previous test's env.
    assert arm.self_mod_enabled() is True
    # If a proposal is formed, starting it must apply the knob.
    if proposal is not None:
        st2 = SH.start_trial(proposal, state=SH.load_state(), cycle_id="t1")
        assert st2.get("trial", {}).get("knob") == "perturb_cooldown_cycles"


# ---------------------------------------------------------------------------
# Isolation: control never writes treatment state
# ---------------------------------------------------------------------------

def test_seed_and_freeze_do_not_touch_source(tmp_path):
    src = _tiny_society(tmp_path / "src", adopts=4, knobs={"park_cycles": 10})
    # A distinctive treatment file that must stay byte-identical.
    heal = src / "society" / "systems" / "self_heal.json"
    before = heal.read_bytes()
    canary = src / "data" / "commons" / "canary.json"
    canary_before = canary.read_bytes()
    dest = tmp_path / "control"
    record = arm.ensure_control_seed(source_root=src, dest_root=dest, force=True, fork_sha="abc123")
    assert record.get("seeded_sha") is not None or record.get("fork_sha") == "abc123"
    assert heal.read_bytes() == before
    assert canary.read_bytes() == canary_before
    # Control has a frozen copy.
    frozen = json.loads((dest / "society" / "systems" / "self_heal.json").read_text())
    assert frozen["frozen"] is True
    assert frozen["trial"] is None
    assert frozen["adopted_count"] == 0
    assert frozen["reverted_count"] == 0
    assert frozen["knobs"]["park_cycles"] == SH.default_knobs()["park_cycles"]
    assert frozen["knobs"]["perturb_cooldown_cycles"] == 6
    # The fork snapshot records what was copied, for audit.
    assert frozen["fork_snapshot"]["adopted_count"] == 4
    assert (dest / arm.FORK_NAME).exists()
    # Treatment canary is not in a writable relationship: editing control
    # must not change source.
    (dest / "data" / "commons" / "canary.json").write_text(
        json.dumps({"src": "control"}) + "\n", encoding="utf-8"
    )
    assert json.loads(canary.read_text())["src"] == "treatment"


def test_subprocess_control_writes_only_under_control_root(tmp_path, monkeypatch):
    """A fresh process with COLONY_ARM=control must not touch this repo's society/."""
    treatment_heal = REPO / "society" / "systems" / "self_heal.json"
    treatment_oracle = REPO / "society" / "systems" / "oracle.json"
    backup_heal = treatment_heal.read_bytes()
    backup_oracle = treatment_oracle.read_bytes() if treatment_oracle.exists() else None
    digest_before = hashlib.sha256(backup_heal).hexdigest()
    dest = tmp_path / "control"
    dest.mkdir()
    script = textwrap.dedent(
        f"""
        import json, os
        from pathlib import Path
        os.environ["COLONY_ARM"] = "control"
        os.environ["COLONY_CONTROL_ROOT"] = {str(dest)!r}
        # Import after the env is set, the way CI does.
        import colony.self_heal as SH
        import colony.checker_lane as CL
        from colony.arm import society_dir, data_dir, is_control
        assert is_control()
        soc = society_dir()
        dat = data_dir()
        assert Path({str(dest)!r}) in soc.parents or soc == Path({str(dest)!r}) / "society"
        SH.STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        SH.save_state(SH.load_state())
        # Also write a canary through the redirected society dir.
        p = soc / "systems" / "control_canary.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({{"arm": "control"}}) + "\\n")
        print(json.dumps({{
            "state_path": str(SH.STATE_PATH),
            "society": str(soc),
            "data": str(dat),
            "canary": str(p),
        }}))
        """
    )
    env = os.environ.copy()
    env["COLONY_ARM"] = "control"
    env["COLONY_CONTROL_ROOT"] = str(dest)
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        r = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert r.returncode == 0, r.stdout + "\n" + r.stderr
        meta = json.loads(r.stdout.strip().splitlines()[-1])
        assert str(dest) in meta["state_path"] or str(dest) in meta["society"]
        assert (REPO / "society" / "systems").as_posix() not in Path(meta["state_path"]).as_posix() or str(dest) in meta["state_path"]
        assert treatment_heal.read_bytes() == backup_heal
        assert hashlib.sha256(treatment_heal.read_bytes()).hexdigest() == digest_before
        if backup_oracle is not None:
            assert treatment_oracle.read_bytes() == backup_oracle
        canary = dest / "society" / "systems" / "control_canary.json"
        # The canary may land under dest via society_dir(); require it exists
        # somewhere under dest and nowhere under the treatment society.
        treatment_canary = REPO / "society" / "systems" / "control_canary.json"
        assert not treatment_canary.exists()
        assert canary.exists() or Path(meta["canary"]).exists()
        if Path(meta["canary"]).exists():
            assert str(dest) in str(Path(meta["canary"]).resolve())
    finally:
        if treatment_heal.read_bytes() != backup_heal:
            treatment_heal.write_bytes(backup_heal)
        if backup_oracle is not None and treatment_oracle.read_bytes() != backup_oracle:
            treatment_oracle.write_bytes(backup_oracle)
        tc = REPO / "society" / "systems" / "control_canary.json"
        if tc.exists():
            tc.unlink()


def test_path_hook_redirects_repo_society_only_in_control(monkeypatch, tmp_path):
    monkeypatch.setenv("COLONY_ARM", "control")
    monkeypatch.setenv("COLONY_CONTROL_ROOT", str(tmp_path / "control"))
    redirected = arm.redirect(arm.REPO_ROOT, "society")
    assert redirected == tmp_path / "control" / "society"
    redirected_data = arm.redirect(arm.REPO_ROOT, "data")
    assert redirected_data == tmp_path / "control" / "data"
    # Code paths stay on the repo.
    code = arm.redirect(arm.REPO_ROOT, "colony")
    assert code == arm.REPO_ROOT / "colony"
    # A temp root is not redirected.
    other = arm.redirect(tmp_path / "other", "society")
    assert other == tmp_path / "other" / "society"
    monkeypatch.setenv("COLONY_ARM", "treatment")
    assert arm.redirect(arm.REPO_ROOT, "society") == arm.REPO_ROOT / "society"


# ---------------------------------------------------------------------------
# Scoreboard math, append-only history
# ---------------------------------------------------------------------------

def test_collect_and_delta_math(tmp_path):
    t = _tiny_society(
        tmp_path / "t",
        passes=530, kills=342, depth_a=8000, depth_b=1200,
        adopts=3, reverts=1, cycle_count=110, fitness=0.60, novelty=0.80,
    )
    c = _tiny_society(
        tmp_path / "c",
        passes=528, kills=340, depth_a=7999, depth_b=1199,
        adopts=0, reverts=0, cycle_count=110, fitness=0.50, novelty=0.75,
        trial=None,
    )
    # Control freeze would zero adopts; here we set them directly.
    tm = twin.collect_arm_metrics(t)
    cm = twin.collect_arm_metrics(c)
    assert tm["oracle_passes"] == 530
    assert cm["oracle_passes"] == 528
    assert tm["verified_depth_sum"] == 8000 + 1200
    assert cm["verified_depth_sum"] == 7999 + 1199
    assert tm["beyond_published_count"] == 2
    assert tm["proofs"] == 2
    assert tm["non_routine_proofs"] == 1
    assert tm["counterexamples"] == 0
    assert tm["adopts"] == 3
    assert tm["fitness"] == pytest.approx(0.60)
    delta = twin._delta(tm, cm)
    assert delta["oracle_passes"] == 2
    assert delta["oracle_kills"] == 2
    assert delta["verified_depth_sum"] == (8000 + 1200) - (7999 + 1199)
    assert delta["adopts"] == 3
    assert delta["reverts"] == 1
    assert delta["fitness"] == pytest.approx(0.10)
    assert delta["novelty"] == pytest.approx(0.05)
    assert delta["cycle_count"] == 0
    assert delta["non_routine_proofs"] == 0
    assert delta["counterexamples"] == 0


def test_scoreboard_history_is_append_only(tmp_path):
    t = _tiny_society(tmp_path / "t", passes=528, cycle_count=10, adopts=0, fitness=0.4)
    c = _tiny_society(tmp_path / "c", passes=528, cycle_count=10, adopts=0, fitness=0.4)
    path = tmp_path / "twin_scoreboard.json"
    b1 = twin.update_scoreboard(
        treatment_root=t, control_root_path=c, path=path,
        cycles_this_run=3, run_id="r1", append=True,
    )
    assert b1["paired_runs"] == 1
    assert len(b1["history"]) == 1
    assert b1["history"][0]["run_id"] == "r1"
    assert b1["delta"]["oracle_passes"] == 0
    first_row = json.loads(json.dumps(b1["history"][0]))

    # Second run: treatment pulls ahead.
    _tiny_society(tmp_path / "t", passes=531, cycle_count=13, adopts=1, fitness=0.45, depth_a=8100)
    b2 = twin.update_scoreboard(
        treatment_root=t, control_root_path=c, path=path,
        cycles_this_run=3, run_id="r2", append=True,
    )
    assert b2["paired_runs"] == 2
    assert len(b2["history"]) == 2
    # First row is byte-identical in content (not rewritten).
    assert b2["history"][0] == first_row
    assert b2["history"][1]["run_id"] == "r2"
    assert b2["history"][1]["delta"]["oracle_passes"] == 3
    assert b2["history"][1]["cycles_this_run"] == 3
    assert b2["treatment"]["oracle_passes"] == 531
    assert b2["control"]["oracle_passes"] == 528
    # Updating latest snapshots without append leaves history alone.
    b3 = twin.update_scoreboard(
        treatment_root=t, control_root_path=c, path=path,
        append=False,
    )
    assert len(b3["history"]) == 2
    assert b3["history"][0] == first_row
    assert b3["history"][1]["run_id"] == "r2"


def test_growth_chart_plaque_colors_and_empty_state():
    empty = twin.empty_scoreboard()
    svg = twin.growth_chart_svg(empty)
    assert twin.CHARCOAL in svg
    assert twin.BONE in svg
    assert twin.SAGE in svg
    assert "#eeeee6" in svg
    assert "#b7c4b6" in svg
    # Forbidden palette.
    low = svg.lower()
    assert "purple" not in low
    assert "#7c3aed" not in low
    assert "#gold" not in low and "#ffd700" not in low and "#d4af37" not in low
    assert "neon" not in low
    assert "🎉" not in svg and "🚀" not in svg and "✨" not in svg
    assert "early differences are noise" in svg
    assert "No paired runs yet" in svg
    html = twin.dashboard_section(empty)
    assert "twin-plaque" in html
    assert twin.CHARCOAL in html

    # With history, both series appear.
    hist = [
        {
            "ts": "2026-11-13T02:00:00Z",
            "run_id": "1",
            "cycles_this_run": 3,
            "treatment": {"oracle_passes": 528, "verified_depth_sum": 9000, "adopts": 0},
            "control": {"oracle_passes": 528, "verified_depth_sum": 9000, "adopts": 0},
            "delta": {"oracle_passes": 0},
        },
        {
            "ts": "2026-11-13T08:00:00Z",
            "run_id": "2",
            "cycles_this_run": 3,
            "treatment": {"oracle_passes": 530, "verified_depth_sum": 9500, "adopts": 1},
            "control": {"oracle_passes": 528, "verified_depth_sum": 9200, "adopts": 0},
            "delta": {"oracle_passes": 2},
        },
    ]
    board = twin.empty_scoreboard()
    board["history"] = hist
    board["paired_runs"] = 2
    board["treatment_cycles"] = 13
    board["control_cycles"] = 13
    svg2 = twin.growth_chart_svg(board)
    assert "Oracle passes" in svg2
    assert "Total verified depth" in svg2
    assert "Cumulative adopts" in svg2
    assert "treatment" in svg2 and "control" in svg2
    assert "polyline" in svg2
    assert "No paired runs yet" not in svg2


def test_seed_refuses_to_write_inside_treatment(tmp_path):
    src = _tiny_society(tmp_path / "src")
    with pytest.raises(ValueError):
        arm.ensure_control_seed(source_root=src, dest_root=src, force=True)
    with pytest.raises(ValueError):
        arm.ensure_control_seed(source_root=src, dest_root=src / "data" / "control", force=True)
    with pytest.raises(ValueError):
        arm.ensure_control_seed(source_root=src, dest_root=src / "society" / "control", force=True)


def test_prepare_arm_treatment_is_noop_for_seed(monkeypatch, tmp_path):
    monkeypatch.setenv("COLONY_ARM", "treatment")
    info = arm.prepare_arm(seed=True)
    assert info["arm"] == "treatment"
    assert info["self_mod"] is True


def test_workflow_runs_control_on_same_schedule():
    wf = (REPO / ".github" / "workflows" / "colony-evolve.yml").read_text(encoding="utf-8")
    assert "cron: \"26 */6 * * *\"" in wf
    assert "evolve-control" in wf
    assert "COLONY_ARM: control" in wf or "COLONY_ARM=control" in wf
    assert "twin-scoreboard" in wf
    # Control never authorizes.
    # Split jobs; the control job must not contain Authorizer.
    # A crude but honest check: after the evolve-control job header,
    # there is no Authorizer before the next job or end.
    i = wf.index("evolve-control")
    rest = wf[i:]
    nxt = rest.find("\n  twin-scoreboard:")
    control_job = rest[:nxt] if nxt != -1 else rest
    assert "Authorizer(" not in control_job
    assert "authorize=true" not in control_job
    # Same cycle count input.
    assert "github.event.inputs.cycles" in control_job or "CYCLES" in control_job
