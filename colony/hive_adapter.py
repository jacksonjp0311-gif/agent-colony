"""Colony adapter for Hive: plain dicts and paths in, decisions out.

This is the only colony module that talks to Hive. Hive never imports
colony. On import, the adapter binds the live self-heal and checker-lane
modules into Hive's host hooks (looked up at call time, so test
monkeypatches still apply) and points Hive at the colony's library and
state paths. The rest of the colony uses the cycle entry points
re-exported here: ``on_cycle``, ``visibility``, ``format_visibility``.
"""
from __future__ import annotations

from pathlib import Path

import colony.checker_lane as _checker
import colony.self_heal as _heal
import hive.library as library
import hive.ops as ops
import hive.swarm as swarm
from hive import host

ROOT = Path(__file__).resolve().parent.parent


def bind() -> None:
    """Attach colony helpers and paths to Hive. Safe to call more than once."""
    host.bind(heal=_heal, checker=_checker)
    library.LIBRARY_LOG = ROOT / "data" / "commons" / "fix_library.jsonl"
    library.ROOT = ROOT
    swarm.ROOT = ROOT
    swarm.STATE_PATH = ROOT / "society" / "systems" / "swarm_learn.json"
    swarm.EVENT_LOG = ROOT / "data" / "commons" / "swarm_learn.jsonl"
    swarm.RULES_PATH = ROOT / "society" / "systems" / "swarm_rules.json"


bind()

# Cycle entry and visibility used by evolve, telemetry, and the dashboard.
from hive.swarm import (  # noqa: E402
    MAX_ACTIONS_PER_CYCLE,
    SWARM_ROLES,
    active_rules,
    format_visibility,
    load_state,
    on_cycle,
    run_cycle,
    visibility,
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
