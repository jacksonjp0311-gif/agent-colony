"""Item 117: workflow_run-triggered evolve obeys the COLONY_CHAIN kill switch."""
from __future__ import annotations

from pathlib import Path

from colony import chain_next as CN

ROOT = Path(__file__).resolve().parent.parent
OK = {"chain_var": "", "ref": "refs/heads/main", "upstream_conclusion": "success", "prior_completed": []}


def test_other_events_pass():
    for ev in ("schedule", "workflow_dispatch", "push"):
        assert CN.gate_workflow_run(event_name=ev, **{**OK, "chain_var": "off"}) == (True, "not_workflow_run")


def test_workflow_run_kill_switch_and_checks():
    assert CN.gate_workflow_run(event_name="workflow_run", **OK) == (True, "ok")
    for v in ("off", "OFF", " Off "):
        assert CN.gate_workflow_run(event_name="workflow_run", **{**OK, "chain_var": v}) == (False, "kill_switch")
    assert CN.gate_workflow_run(event_name="workflow_run", **{**OK, "ref": "refs/heads/x"})[1] == "not_main"
    assert CN.gate_workflow_run(event_name="workflow_run", **{**OK, "upstream_conclusion": "failure"})[1] \
        == "upstream_not_success"
    assert CN.gate_workflow_run(event_name="workflow_run", **{**OK, "prior_completed": None})[1] == "runs_unreadable"
    fails = [{"conclusion": "failure"}] * 3
    assert CN.gate_workflow_run(event_name="workflow_run", **{**OK, "prior_completed": fails})[1] \
        == "consecutive_failures"


def test_gate_main_writes_output(tmp_path, monkeypatch):
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("EVENT_NAME", "workflow_run")
    monkeypatch.setenv("COLONY_CHAIN", "off")
    assert CN.main(["--gate"]) == 0
    assert out.read_text().strip() == "go=false"
    monkeypatch.setenv("EVENT_NAME", "schedule")
    CN.main(["--gate"])
    assert out.read_text().splitlines()[-1] == "go=true"


def test_workflow_wires_gate_and_no_reset_hard():
    wf = (ROOT / ".github" / "workflows" / "colony-evolve.yml").read_text()
    assert "python3 -m colony.chain_next --gate" in wf
    assert wf.count("needs.chain-gate.outputs.go == 'true'") == 4
    assert "git reset --hard" not in wf
    assert "git merge --ff-only origin/main" in wf
