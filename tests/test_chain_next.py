"""Back-to-back evolve chaining: decision logic and workflow contract."""
from __future__ import annotations

from pathlib import Path

import pytest

import colony.chain_next as CN

WF = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "colony-evolve.yml"


def _run(rid, status="completed", conclusion="success", branch="main"):
    return {"id": rid, "status": status, "conclusion": conclusion, "head_branch": branch}


def test_kill_switch_default_on():
    assert CN.kill_switch_off(None) is False
    assert CN.kill_switch_off("") is False
    assert CN.kill_switch_off("on") is False
    assert CN.kill_switch_off("ON") is False
    assert CN.kill_switch_off("off") is True
    assert CN.kill_switch_off("OFF") is True
    assert CN.kill_switch_off(" off ") is True


def test_dispatch_when_default_on_and_main_clear():
    ok, reason = CN.should_dispatch(
        chain_var=None,
        ref="refs/heads/main",
        current_run_id=11,
        other_active=[_run(11, status="in_progress", conclusion="")],
        prior_completed=[_run(10, conclusion="success")],
        current_evolve_result="success",
    )
    assert ok is True and reason == "ok"


def test_skip_when_kill_switch_off():
    ok, reason = CN.should_dispatch(
        chain_var="off",
        ref="main",
        current_run_id=11,
        other_active=[],
        prior_completed=[],
        current_evolve_result="success",
    )
    assert ok is False and reason == "kill_switch"


def test_skip_when_not_main():
    ok, reason = CN.should_dispatch(
        chain_var="",
        ref="refs/heads/chain-and-caps",
        current_run_id=11,
        other_active=[],
        prior_completed=[],
        current_evolve_result="success",
    )
    assert ok is False and reason == "not_main"


def test_skip_if_another_run_queued_or_in_progress():
    ok, reason = CN.should_dispatch(
        chain_var="",
        ref="main",
        current_run_id=11,
        other_active=[_run(12, status="queued", conclusion="")],
        prior_completed=[],
        current_evolve_result="success",
    )
    assert ok is False and reason == "already_active"
    ok, reason = CN.should_dispatch(
        chain_var="",
        ref="main",
        current_run_id=11,
        other_active=[_run(13, status="in_progress", conclusion="")],
        prior_completed=[],
        current_evolve_result="success",
    )
    assert ok is False and reason == "already_active"


def test_current_run_does_not_count_as_already_active():
    ok, reason = CN.should_dispatch(
        chain_var="",
        ref="main",
        current_run_id=11,
        other_active=[_run(11, status="in_progress", conclusion="")],
        prior_completed=[],
        current_evolve_result="success",
    )
    assert ok is True and reason == "ok"


def test_chain_after_single_or_double_failure():
    ok, reason = CN.should_dispatch(
        chain_var="",
        ref="main",
        current_run_id=11,
        other_active=[],
        prior_completed=[_run(10, conclusion="success")],
        current_evolve_result="failure",
    )
    assert ok is True and reason == "ok"
    ok, reason = CN.should_dispatch(
        chain_var="",
        ref="main",
        current_run_id=13,
        other_active=[],
        prior_completed=[
            _run(12, conclusion="failure"),
            _run(11, conclusion="success"),
        ],
        current_evolve_result="failure",
    )
    assert ok is True and reason == "ok"


def test_stop_after_three_consecutive_failures():
    ok, reason = CN.should_dispatch(
        chain_var="",
        ref="main",
        current_run_id=13,
        other_active=[],
        prior_completed=[
            _run(12, conclusion="failure"),
            _run(11, conclusion="timed_out"),
            _run(10, conclusion="success"),
        ],
        current_evolve_result="failure",
    )
    assert ok is False and reason == "consecutive_failures"


def test_cancelled_runs_do_not_count_toward_streak():
    # Two real failures around a cancelled run: still chain.
    assert CN.consecutive_failure_streak(
        [_run(12, conclusion="cancelled"), _run(11, conclusion="failure")],
        "failure",
    ) == 2
    # A success after failures resets.
    assert CN.consecutive_failure_streak(
        [_run(12, conclusion="failure"), _run(11, conclusion="failure")],
        "success",
    ) == 0


def test_dispatch_inputs_never_authorize():
    inputs = CN.dispatch_inputs()
    assert inputs["authorize"] == "false"
    assert inputs["cycles"] == "3"
    assert inputs["run_control"] == "true"
    with pytest.raises(ValueError, match="never dispatch with authorize"):
        CN.dispatch_inputs(authorize="true")
    with pytest.raises(ValueError, match="never dispatch with authorize"):
        CN.dispatch_inputs(authorize="TRUE")


def test_workflow_chains_on_main_with_kill_switch_and_actions_write():
    s = WF.read_text(encoding="utf-8")
    assert "chain-next:" in s
    assert "colony.chain_next" in s or "colony/chain_next.py" in s
    assert "vars.COLONY_CHAIN" in s
    assert "actions: write" in s
    # The chain job itself must not run the Authorizer, and the dispatch
    # must hard-code authorize=false.
    assert "EVOLVE_RESULT: ${{ needs.evolve.result }}" in s
    assert "CURRENT_RUN_ID: ${{ github.run_id }}" in s
    chain = s[s.index("chain-next:"):]
    assert "authorize=true" not in chain
    assert "inputs.authorize" not in chain
    # Always run after the evolve jobs, including on failure, only on main.
    header = chain.split("steps:")[0]
    assert "always()" in header
    assert "github.ref == 'refs/heads/main'" in header
    # Concurrency still serializes the evolve group (no pile-up of overlapping evolves).
    assert "group: colony-evolve" in s
    assert "cancel-in-progress: false" in s
