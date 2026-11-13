"""Colony adapter for Hive: plain dicts and paths in, decisions out.

This is the only colony module that talks to Hive. Hive never imports
colony. On import, the adapter binds the live self-heal and checker-lane
modules into Hive's host hooks (looked up at call time, so test
monkeypatches still apply) and points Hive at the colony's library and
state paths. The rest of the colony uses the cycle entry points
re-exported here: ``on_cycle``, ``visibility``, ``format_visibility``.

The control arm disables Hive *through this adapter*. ``on_cycle`` and
``run_cycle`` return without calling Hive when ``hive_learning_enabled()``
is false, so learning does not run and no Hive state is written. Paths
set by ``bind()`` follow the current arm (treatment vs ``control/``).
Hive itself is unchanged.
"""
from __future__ import annotations

from typing import Any

import colony.checker_lane as _checker
import colony.self_heal as _heal
import hive.library as library
import hive.ops as ops
import hive.swarm as swarm
from collections.abc import Mapping

from colony.arm import REPO_ROOT, data_dir, hive_learning_enabled, is_control, society_dir
from hive import host

# Backward-compatible name: the repo root (code, not arm state).
ROOT = REPO_ROOT


class _HealView:
    """Proxy around colony.self_heal that enriches diagnose findings.

    Hive never imports colony. Structured feature tokens (failure
    class, exit_reason, cap_reason, desk, stall_reason) are attached
    here so live queries share the seed vocabulary. Lookups are at
    call time so test monkeypatches on the real module still apply.
    """

    def __init__(self, real: Any) -> None:
        object.__setattr__(self, "_real", real)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    def diagnose(self, cycle_id: str = "", **kwargs: Any) -> list[dict[str, Any]]:
        raw = self._real.diagnose(cycle_id, **kwargs) or []
        return enrich_findings(list(raw))


def enrich_finding(finding: Mapping[str, Any]) -> dict[str, Any]:
    """Attach the structured feature fields Hive's seeds use."""
    out = dict(finding)
    ev = out.get("evidence") if isinstance(out.get("evidence"), Mapping) else {}
    kind = str(out.get("kind") or out.get("label") or "")
    if kind:
        out.setdefault("failure_class", kind)
        out.setdefault("label", kind)
    for key in (
        "exit_reason", "stall_reason", "desk", "cap_reason",
        "cap_name", "target_kind", "failure_class",
    ):
        if out.get(key):
            continue
        if ev.get(key):
            out[key] = ev[key]
    if not out.get("cap_reason"):
        recent = ev.get("recent") if isinstance(ev.get("recent"), list) else []
        for row in recent:
            if isinstance(row, Mapping) and row.get("cap_reason"):
                out["cap_reason"] = row["cap_reason"]
                break
    if not out.get("desk"):
        desk = _desk_hint(ev)
        if desk:
            out["desk"] = desk
    return out


def enrich_findings(findings: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in findings:
        if isinstance(f, Mapping):
            out.append(enrich_finding(f))
    return out


def _desk_hint(evidence: Mapping[str, Any]) -> str:
    for key in ("desk", "idle_desk", "handoff"):
        val = evidence.get(key)
        if val:
            return str(val)
    return ""


def bind() -> None:
    """Attach colony helpers and paths to Hive. Safe to call more than once."""
    host.bind(heal=_HealView(_heal) if _heal is not None else None, checker=_checker)
    library.LIBRARY_LOG = data_dir() / "commons" / "fix_library.jsonl"
    library.LIBRARY_SNAPSHOT = society_dir() / "systems" / "swarm_library.json"
    library.ROOT = REPO_ROOT
    swarm.ROOT = REPO_ROOT
    swarm.STATE_PATH = society_dir() / "systems" / "swarm_learn.json"
    swarm.EVENT_LOG = data_dir() / "commons" / "swarm_learn.jsonl"
    swarm.RULES_PATH = society_dir() / "systems" / "swarm_rules.json"


def _disabled(cycle_id: str = "") -> dict[str, Any]:
    return {
        "ok": True,
        "skipped": True,
        "reason": "control_arm",
        "learning": False,
        "cycle_id": cycle_id,
        "n_proposals": 0,
        "findings": [],
        "applied_to_live_oracle": False,
        "authorized": False,
    }


def run_cycle(cycle_id: str = "") -> dict[str, Any]:
    """Same as Hive's ``run_cycle``, skipped on the control arm."""
    if not hive_learning_enabled():
        return _disabled(cycle_id)
    return swarm.run_cycle(cycle_id)


def on_cycle(cycle_id: str = "") -> dict[str, Any]:
    """Evolve-cycle entry. Control returns without calling Hive."""
    if not hive_learning_enabled():
        return _disabled(cycle_id)
    return swarm.on_cycle(cycle_id)


def visibility(state: dict[str, Any] | None = None) -> dict[str, Any]:
    vis = swarm.visibility(state=state)
    if not hive_learning_enabled():
        vis = dict(vis or {})
        vis["learning"] = False
        vis["swarm_learning"] = False
        vis["skipped"] = "control_arm"
        vis["arm"] = "control" if is_control() else "treatment"
    return vis


def format_visibility(vis: dict[str, Any] | None = None) -> str:
    line = swarm.format_visibility(vis)
    if not hive_learning_enabled():
        return f"{line}; learning off (control arm)"
    return line


bind()

# Cycle helpers used by evolve, telemetry, and the dashboard. on_cycle,
# run_cycle, visibility, and format_visibility are defined above so the
# control arm can disable learning without touching Hive itself.
from hive.swarm import (  # noqa: E402
    MAX_ACTIONS_PER_CYCLE,
    SWARM_ROLES,
    active_rules,
    load_state,
)

__all__ = (
    "MAX_ACTIONS_PER_CYCLE",
    "SWARM_ROLES",
    "active_rules",
    "bind",
    "format_visibility",
    "library",
    "load_state",
    "on_cycle",
    "ops",
    "run_cycle",
    "swarm",
    "visibility",
)
