"""Item 102: self-build round two learns from its own kept / reverted blueprints.

Measured (data/commons/blueprint_log.jsonl): every blueprint trial so far has been one more
OEIS-desk block added on top of the active blueprint. oeis_extra_pass and oeis_swarm_improvers
were both reverted (not strictly better than baseline and twin), oeis_consensus_vote and
oeis_novelty_archive were voided, and the ranking still put five more OEIS-desk duplicates on
top (insert_front / add / replace of oeis_* blocks). Item 89's per-component penalty only touches
the exact component that lost.

Two lessons now feed the candidate ranking (colony.self_build.candidates):
  * no re-add: a child that ADDS a component whose own blueprint was reverted (in any position or
    size: add, insert_front, replace, pair, use of a macro containing it) is not proposed again;
  * desk lesson: each component's weight is multiplied by 1 / (1 + 0.5 * reverted adds from its
    desk), so after repeated OEIS-desk losses a different desk or a structural move (move, swap,
    split, remove, ...) ranks first.
Kept components are untouched (crossover already reuses them); voided / inconclusive trials are
no evidence either way. Trials are judged exactly as before (strictly better than baseline AND
twin over the same windows). Nothing in an open trial changes.

Switch ``COLONY_SELF_BUILD_LESSONS`` = live (default) | off; off on the control arm.
"""
from __future__ import annotations

import os
from collections import Counter
from typing import Any, Iterable, Mapping

DESK_STEP = 0.5


def enabled() -> bool:
    try:
        from colony.arm import self_mod_enabled
        if not self_mod_enabled():
            return False
    except Exception:  # noqa: BLE001
        return False
    return (os.environ.get("COLONY_SELF_BUILD_LESSONS") or "live").strip().lower() == "live"


def reverted_components(rows: Iterable[Mapping[str, Any]]) -> Counter:
    """Components ADDED by blueprints whose trial closed reverted (append-only log replay)."""
    added: dict[str, list[str]] = {}
    out: Counter = Counter()
    for r in rows:
        ev, bid = r.get("event"), str(r.get("blueprint") or "")
        if ev == "blueprint_trial_open":
            added[bid] = [str(a.get("component") if isinstance(a, Mapping) else a)
                          for a in (r.get("added") or r.get("evidence") or [])]
        elif ev == "blueprint_trial_close" and r.get("outcome") == "reverted":
            for c in added.get(bid, []):
                if c:
                    out[c] += 1
    return out


def desk_losses(reverted: Mapping[str, int], components: Mapping[str, Mapping[str, Any]]) -> Counter:
    out: Counter = Counter()
    for c, n in reverted.items():
        desk = str((components.get(c) or {}).get("desk") or "")
        if desk:
            out[desk] += int(n)
    return out


def lessons(rows: Iterable[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    from colony.self_build import COMPONENTS, load_log
    rev = reverted_components(load_log() if rows is None else rows)
    return {"reverted": dict(rev), "desk_losses": dict(desk_losses(rev, COMPONENTS))}


def expand_names(name: str, macros: Mapping[str, Any]) -> list[str]:
    if name in macros:
        return [str(s.get("component")) for s in (macros[name].get("steps") or []) if isinstance(s, Mapping)]
    return [name]


def blocked(added: Iterable[Mapping[str, Any]], les: Mapping[str, Any], macros: Mapping[str, Any]) -> bool:
    rev = les.get("reverted") or {}
    return any(c in rev for a in added for c in expand_names(str(a.get("component")), macros))


def desk_factor(name: str, les: Mapping[str, Any], components: Mapping[str, Mapping[str, Any]],
                macros: Mapping[str, Any]) -> float:
    dl = les.get("desk_losses") or {}
    f = 1.0
    for c in expand_names(name, macros):
        desk = str((components.get(c) or {}).get("desk") or "")
        f *= 1.0 / (1.0 + DESK_STEP * int(dl.get(desk) or 0))
    return f
