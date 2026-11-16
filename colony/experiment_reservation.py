"""Item 104: one exclusive experiment reservation across self-build, self-heal and Hive.

Measured before this item (scripts/item104_trial_overlap_audit.py, read-only):

- ``self_heal.start_trial`` checked only its own state. Self-heal's *proposer* waited for an
  open blueprint trial (item 80), but Hive hands knob winners straight to ``start_trial``
  (``hive.swarm.start_knob_trial`` checked only ``self_heal`` busy). Two Hive-started
  park_cycles trials opened inside open blueprint trials (2026-11-16 02:33Z inside
  bp_8d66d1f8, 05:36Z inside bp_default; the second blueprint was then scored "reverted"
  over a window that contained the Hive trial).
- Hive rule trials checked only Hive's own trial slot.
- Self-heal's wait on self-build failed OPEN: an import/read error meant "not blocked".

This module is the single answer to "may ``requester`` open an experiment now?". The three
experiment slots are derived from the subsystems' own state files (no separate lock that can
go stale): ``self_build`` (self_build.json ``trial``), ``self_heal`` (self_heal.json ``trial``;
a Hive knob trial lives there too) and ``hive_rule`` (swarm_learn.json ``trial``). A requester
may open only when no OTHER slot holds a trial. A state file that exists but cannot be read
or parsed FAILS CLOSED (``reservation_unreadable``): nothing opens until it is readable.

No gate changes: windows, Wilson 700 permille, strictly-better rule and P are untouched; this
only stops two experiments from being scored over the same cycles.

Switch ``COLONY_EXPERIMENT_RESERVATION`` = live (default) | off. Always off on the control
arm (the control arm runs no self-modification at all).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping

SLOTS = ("self_build", "self_heal", "hive_rule")


def enabled() -> bool:
    try:
        from colony.arm import self_mod_enabled
        if not self_mod_enabled():
            return False
    except Exception:  # noqa: BLE001
        return False
    return (os.environ.get("COLONY_EXPERIMENT_RESERVATION") or "live").strip().lower() == "live"


class Unreadable(RuntimeError):
    pass


def _strict_trial(path: Path) -> Any:
    """The ``trial`` field of a state file. Missing file = no trial; unreadable = raise."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        txt = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None   # gone between exists() and read (or refused as absent): no trial recorded
    except Exception as exc:  # noqa: BLE001
        raise Unreadable(f"{p.name}: {type(exc).__name__}") from exc
    try:
        raw = json.loads(txt)
    except Exception as exc:  # noqa: BLE001
        raise Unreadable(f"{p.name}: {type(exc).__name__}") from exc
    if not isinstance(raw, dict):
        raise Unreadable(f"{p.name}: not an object")
    return raw.get("trial")


def _paths() -> dict[str, Path]:
    from colony import self_build as _sb
    from colony import self_heal as _sh
    import hive.swarm as _sw
    return {"self_build": Path(_sb.STATE_PATH), "self_heal": Path(_sh.STATE_PATH),
            "hive_rule": Path(_sw.STATE_PATH)}


def holders(states: Mapping[str, Any] | None = None,
            paths: Mapping[str, Path] | None = None) -> list[str]:
    """Slots that hold an open trial. ``states`` (slot -> state dict) overrides the file read
    for a slot whose caller already has its live in-memory state. Raises ``Unreadable``."""
    states = dict(states or {})
    out: list[str] = []
    ps: Mapping[str, Path] | None = paths
    for slot in SLOTS:
        if slot in states and isinstance(states[slot], Mapping):
            trial = states[slot].get("trial")
        else:
            if ps is None:
                try:
                    ps = _paths()
                except Exception as exc:  # noqa: BLE001
                    raise Unreadable(f"paths: {type(exc).__name__}") from exc
            trial = _strict_trial(ps[slot])
        if trial:
            out.append(slot)
    return out


def check(requester: str, *, states: Mapping[str, Any] | None = None,
          paths: Mapping[str, Path] | None = None,
          holders_fn: Callable[..., list[str]] | None = None) -> dict[str, Any]:
    """May ``requester`` open an experiment now? ``ok`` False names who holds it (or why)."""
    if requester not in SLOTS:
        return {"ok": False, "reason": "unknown_requester", "requester": requester}
    if not enabled():
        return {"ok": True, "reason": "reservation_off", "requester": requester}
    try:
        held = (holders_fn or holders)(states=states, paths=paths)
    except Exception as exc:  # noqa: BLE001  (fail closed)
        return {"ok": False, "reason": "reservation_unreadable", "requester": requester,
                "detail": str(exc)[:160]}
    others = [h for h in held if h != requester]
    if others:
        return {"ok": False, "reason": f"{others[0]}_trial_open", "holder": others[0],
                "holders": others, "requester": requester}
    return {"ok": True, "reason": "free", "requester": requester, "holders": held}


def experiment_holder(requester: str) -> str | None:
    """Hive host hook: None when ``requester`` may open, else the refusal reason."""
    r = check(requester)
    return None if r.get("ok") else str(r.get("reason"))


# --------------------------------------------------------------------------- overlap audit (flag)
def cycle_ts(cycle_id: Any) -> str | None:
    """'20261116T010000Z_7b716e' -> '2026-11-16T01:00:00Z' (None if not a cycle id)."""
    c = str(cycle_id or "")
    if len(c) < 16 or c[8] != "T" or c[15] != "Z":
        return None
    return f"{c[0:4]}-{c[4:6]}-{c[6:8]}T{c[9:11]}:{c[11:13]}:{c[13:15]}Z"


def trial_intervals(*, blueprint_rows: list[Mapping[str, Any]] | None = None,
                    heal_state: Mapping[str, Any] | None = None,
                    hive_state: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Every experiment interval the logs know: slot, id, start ts, end ts (None = still open)."""
    out: list[dict[str, Any]] = []
    if blueprint_rows is None:
        try:
            from colony import self_build as _sb
            blueprint_rows = _sb.load_log()
        except Exception:  # noqa: BLE001
            blueprint_rows = []
    opened: dict[str, Mapping[str, Any]] = {}
    for r in blueprint_rows or []:
        ev = r.get("event")
        if ev == "blueprint_trial_open":
            opened[str(r.get("blueprint"))] = r
        elif ev in ("blueprint_trial_close", "blueprint_trial_void"):
            o = opened.pop(str(r.get("blueprint")), None)
            if o is not None:
                out.append({"slot": "self_build", "id": str(r.get("blueprint")),
                            "start": cycle_ts(o.get("cycle_id")), "end": cycle_ts(r.get("cycle_id")),
                            "outcome": r.get("outcome")})
    for bid, o in opened.items():
        out.append({"slot": "self_build", "id": bid, "start": cycle_ts(o.get("cycle_id")), "end": None,
                    "outcome": "open"})
    if heal_state is None:
        try:
            from colony import self_heal as _sh
            heal_state = _sh.load_state()
        except Exception:  # noqa: BLE001
            heal_state = {}
    for e in (heal_state or {}).get("evidence") or []:
        if isinstance(e, Mapping) and e.get("event") in ("adopt", "revert", "trial_inconclusive",
                                                          "trial_voided_confound") and e.get("started_cycle"):
            out.append({"slot": "self_heal", "id": f"{e.get('knob')}@{e.get('started_cycle')}",
                        "start": cycle_ts(e.get("started_cycle")), "end": cycle_ts(e.get("cycle_id")),
                        "outcome": e.get("event")})
    t = (heal_state or {}).get("trial")
    if isinstance(t, Mapping) and t.get("started_cycle"):
        out.append({"slot": "self_heal", "id": f"{t.get('knob')}@{t.get('started_cycle')}",
                    "start": cycle_ts(t.get("started_cycle")), "end": None, "outcome": "open"})
    if hive_state is None:
        try:
            import hive.swarm as _sw
            hive_state = _sw.load_state()
        except Exception:  # noqa: BLE001
            hive_state = {}
    t = (hive_state or {}).get("trial")
    if isinstance(t, Mapping) and t.get("started_cycle"):
        out.append({"slot": "hive_rule", "id": f"{t.get('fingerprint')}@{t.get('started_cycle')}",
                    "start": cycle_ts(t.get("started_cycle")), "end": None, "outcome": "open"})
    for e in (hive_state or {}).get("evidence") or []:
        if isinstance(e, Mapping) and e.get("event") in ("adopt", "revert", "trial_voided") \
                and e.get("started_cycle") and str(e.get("via") or "") != "self_heal":
            out.append({"slot": "hive_rule", "id": f"{e.get('fingerprint')}@{e.get('started_cycle')}",
                        "start": cycle_ts(e.get("started_cycle")), "end": cycle_ts(e.get("cycle_id")),
                        "outcome": e.get("event")})
    return [x for x in out if x.get("start")]


def overlapping(start: str | None, end: str | None, intervals: list[Mapping[str, Any]],
                exclude_id: str | None = None) -> list[dict[str, Any]]:
    """Intervals that share time with [start, end] (strict overlap; touching ends do not count)."""
    if not start:
        return []
    hi = end or "9999"
    out = []
    for iv in intervals:
        if exclude_id and iv.get("id") == exclude_id:
            continue
        s, e = str(iv.get("start")), str(iv.get("end") or "9999")
        if s < hi and start < e:
            out.append({k: iv.get(k) for k in ("slot", "id", "start", "end", "outcome")})
    return out
