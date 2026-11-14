"""Back-to-back Colony evolve chaining.

When an evolve run on main finishes, this module decides whether to
dispatch the next one (cycles=3, authorize=false, run_control=true).
It never authorizes. A repo variable COLONY_CHAIN=off is the kill
switch; unset or any other value means on. It will not dispatch if
another evolve run is already queued or in progress (excluding the
run that is finishing), and it stops after three consecutive evolve
job failures so a broken main cannot loop.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Iterable, Mapping

WORKFLOW_ID = 367686498
WORKFLOW_FILE = "colony-evolve.yml"
FAIL_STREAK_LIMIT = 3
DEFAULT_CYCLES = "3"
DEFAULT_RUN_CONTROL = "true"
# Hard rule: chained runs never authorize.
DEFAULT_AUTHORIZE = "false"

_FAILURE_CONCLUSIONS = frozenset({"failure", "timed_out", "startup_failure"})
_SUCCESS_CONCLUSIONS = frozenset({"success"})
_ACTIVE_STATUSES = frozenset({"queued", "in_progress", "waiting", "pending", "requested"})
# Statuses queried from the API before dispatching. Must cover every
# status in _ACTIVE_STATUSES.
ACTIVE_LIST_STATUSES = ("in_progress", "queued", "waiting", "pending", "requested")
_IGNORE_CONCLUSIONS = frozenset({"cancelled", "skipped", "action_required", "neutral", "stale"})


def kill_switch_off(chain_var: str | None) -> bool:
    """True only when the repo variable is explicitly off."""
    return str(chain_var or "").strip().lower() == "off"


def is_main_ref(ref: str | None) -> bool:
    r = str(ref or "").strip()
    return r in ("refs/heads/main", "main")


def current_run_result(
    needs_json: str | None,
    evolve_result: str | None = None,
) -> str:
    """Whole-run result for the finishing run, from all needed jobs.

    Prior runs are judged by their run-level ``conclusion``, which is
    ``failure`` when any job failed. To count the finishing run the same
    way, it is a failure when any needed job failed or timed out, a
    success when every needed job succeeded or was skipped, and
    otherwise falls back to the evolve job's result.
    """
    results: list[str] = []
    try:
        needs = json.loads(needs_json or "") if needs_json else {}
    except (TypeError, ValueError):
        needs = {}
    if isinstance(needs, dict):
        for job in needs.values():
            if isinstance(job, dict):
                results.append(str(job.get("result") or "").strip().lower())
    if not results:
        return str(evolve_result or "").strip().lower()
    if any(r in ("failure", "timed_out") for r in results):
        return "failure"
    if any(r == "cancelled" for r in results):
        return "cancelled"
    if all(r in ("success", "skipped") for r in results) and any(
        r == "success" for r in results
    ):
        return "success"
    return str(evolve_result or "").strip().lower()


def consecutive_failure_streak(
    prior_completed: Iterable[Mapping[str, Any]],
    current_evolve_result: str | None = None,
) -> int:
    """Trailing evolve failures, newest first, including the run just finishing.

    ``current_evolve_result`` is ``needs.evolve.result`` (the treatment
    job). Cancelled / skipped prior runs are ignored, not counted.
    A success resets the streak. The current run is not yet in the
    completed list when the chain job runs, so its result is passed in.
    """
    streak = 0
    current = str(current_evolve_result or "").strip().lower()
    if current in _FAILURE_CONCLUSIONS:
        streak = 1
    elif current in _SUCCESS_CONCLUSIONS or current == "":
        if current in _SUCCESS_CONCLUSIONS:
            return 0
    # current skipped/cancelled: do not start a streak from it; still
    # inspect prior completed runs below.
    for run in prior_completed:
        conclusion = str(run.get("conclusion") or "").strip().lower()
        if conclusion in _IGNORE_CONCLUSIONS or not conclusion:
            continue
        if conclusion in _SUCCESS_CONCLUSIONS:
            break
        if conclusion in _FAILURE_CONCLUSIONS:
            streak += 1
        else:
            break
    return streak


def active_other_runs(
    runs: Iterable[Mapping[str, Any]],
    current_run_id: int | str | None,
) -> list[Mapping[str, Any]]:
    """Evolve runs that are queued or in progress, excluding this run."""
    current = str(current_run_id or "").strip()
    out: list[Mapping[str, Any]] = []
    for run in runs:
        if str(run.get("id") or "").strip() == current:
            continue
        status = str(run.get("status") or "").strip().lower()
        if status in _ACTIVE_STATUSES:
            out.append(run)
    return out


def should_dispatch(
    *,
    chain_var: str | None,
    ref: str | None,
    current_run_id: int | str | None,
    other_active: Iterable[Mapping[str, Any]],
    prior_completed: Iterable[Mapping[str, Any]],
    current_evolve_result: str | None = None,
) -> tuple[bool, str]:
    """Return (dispatch?, reason). Never inspects authorize inputs."""
    if kill_switch_off(chain_var):
        return False, "kill_switch"
    if not is_main_ref(ref):
        return False, "not_main"
    active = active_other_runs(other_active, current_run_id)
    if active:
        return False, "already_active"
    streak = consecutive_failure_streak(prior_completed, current_evolve_result)
    if streak >= FAIL_STREAK_LIMIT:
        return False, "consecutive_failures"
    return True, "ok"


def dispatch_inputs(
    *,
    cycles: str = DEFAULT_CYCLES,
    authorize: str = DEFAULT_AUTHORIZE,
    run_control: str = DEFAULT_RUN_CONTROL,
) -> dict[str, str]:
    """Inputs for the next evolve run. authorize=true is rejected."""
    if str(authorize).strip().lower() != "false":
        raise ValueError("chain must never dispatch with authorize=true")
    return {
        "cycles": str(cycles or DEFAULT_CYCLES),
        "authorize": "false",
        "run_control": str(run_control or DEFAULT_RUN_CONTROL),
        "offline": "false",
    }


def _gh(args: list[str], *, token: str | None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if token:
        env["GH_TOKEN"] = token
        env["GITHUB_TOKEN"] = token
    return subprocess.run(
        ["gh", *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def _list_runs(repo: str, status: str, token: str | None) -> list[dict[str, Any]]:
    path = (
        f"repos/{repo}/actions/workflows/{WORKFLOW_ID}/runs"
        f"?status={status}&branch=main&per_page=30"
    )
    proc = _gh(["api", path], token=token)
    if proc.returncode != 0:
        raise RuntimeError(f"gh api {status} failed: {proc.stderr or proc.stdout}")
    data = json.loads(proc.stdout or "{}")
    runs = data.get("workflow_runs") or []
    return [r for r in runs if isinstance(r, dict)]


def _dispatch(repo: str, token: str | None, inputs: Mapping[str, str]) -> None:
    args = [
        "workflow", "run", str(WORKFLOW_ID),
        "--repo", repo,
        "--ref", "main",
    ]
    for key, value in inputs.items():
        args.extend(["-f", f"{key}={value}"])
    proc = _gh(args, token=token)
    if proc.returncode != 0:
        raise RuntimeError(f"workflow_dispatch failed: {proc.stderr or proc.stdout}")


def main(argv: list[str] | None = None) -> int:
    del argv  # env-driven; kept for python -m compatibility
    chain_var = os.environ.get("COLONY_CHAIN")
    ref = os.environ.get("GITHUB_REF") or os.environ.get("GITHUB_REF_NAME") or ""
    current_run_id = os.environ.get("CURRENT_RUN_ID") or os.environ.get("GITHUB_RUN_ID") or ""
    evolve_result = current_run_result(
        os.environ.get("NEEDS_JSON"), os.environ.get("EVOLVE_RESULT")
    )
    repo = os.environ.get("GITHUB_REPOSITORY") or ""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""

    if not repo:
        print("chain: skip missing_repo", flush=True)
        return 1

    try:
        # Every active status, including "pending": the evolve workflow
        # shares one concurrency group, so a new dispatch would replace a
        # pending run (for example one James started by hand).
        other_active = []
        for status in ACTIVE_LIST_STATUSES:
            other_active.extend(_list_runs(repo, status, token))
        completed = _list_runs(repo, "completed", token)
    except Exception as exc:
        print(f"chain: error listing runs: {exc}", flush=True)
        return 1

    ok, reason = should_dispatch(
        chain_var=chain_var,
        ref=ref,
        current_run_id=current_run_id,
        other_active=other_active,
        prior_completed=completed,
        current_evolve_result=evolve_result,
    )
    if not ok:
        extra = ""
        if reason == "already_active":
            ids = [
                str(r.get("id"))
                for r in active_other_runs(other_active, current_run_id)
            ]
            extra = f" runs={ids}"
        elif reason == "consecutive_failures":
            extra = (
                f" streak={consecutive_failure_streak(completed, evolve_result)}"
                f" limit={FAIL_STREAK_LIMIT}"
            )
        elif reason == "kill_switch":
            extra = f" COLONY_CHAIN={chain_var!r}"
        print(f"chain: skip {reason}{extra}", flush=True)
        return 0

    inputs = dispatch_inputs()
    # Belt and braces: authorize is always false at the call site too.
    assert inputs["authorize"] == "false"
    print(
        "chain: dispatching "
        f"cycles={inputs['cycles']} authorize=false run_control={inputs['run_control']}",
        flush=True,
    )
    try:
        _dispatch(repo, token, inputs)
    except Exception as exc:
        print(f"chain: dispatch failed: {exc}", flush=True)
        return 1
    print("chain: dispatched", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
