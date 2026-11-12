"""Stall recovery, cooldowns, and PERTURB mode.

Recovery / PERTURB never changes the Oracle, the 0.70 authorize gate, the
150 authored-check cap, or Athanor math. They only change what gets tried.

A claim_theme killed as saturated-plus-already-in-ledger is cooled by
``colony.lessons`` until a harder unused window exists. This module adds a
persisted proposal park: a fingerprint blocked as a dedupe repeat two cycles
in a row is parked for N cycles (6 to start), and its turn goes to a
different source.

STALL is true when Oracle passes are unchanged for six cycles, or when every
Oracle-bound or desk turn in the last three cycles ended in a block, a skip,
or the same kill. On STALL the colony enters PERTURB, a seeded exploration
mode. It leaves on a new Oracle pass, a genuinely new kill reason, or after
nine cycles. A timeout doubles parked durations and widens the draw.
"""
from __future__ import annotations

import hashlib
import json
import random
import subprocess
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "society" / "systems" / "stall_state.json"

STALL_CYCLES = 6
STALL_DEAD_END_CYCLES = 3
IDENTICAL_KILL_RUN = 3
PARK_CYCLES = 6
BLOCK_STREAK_TO_PARK = 2
PERTURB_MAX_CYCLES = 9
PERTURB_EPSILON = 0.3
PERTURB_WIDE_EPSILON = 0.5
PERTURB_MIN_TARGETS = 2
UNUSED_MENU_CYCLES = 20
CLAIM_SHAPES = ("congruence", "divisibility", "growth_bound", "gf_identity")
MUTATION_INGREDIENTS = ("sequence", "modulus", "offset", "window")

# ---------------------------------------------------------------------------
# Existing recovery (Oracle-log only). Callers and tests depend on these.
# ---------------------------------------------------------------------------


def load_oracle_rows(limit: int = 2500) -> list[dict[str, Any]]:
    from colony.oracle import ORACLE_LOG

    if not ORACLE_LOG.exists():
        return []
    out: list[dict[str, Any]] = []
    for ln in ORACLE_LOG.read_text(encoding="utf-8").splitlines()[-limit:]:
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _kill_sig(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(k) for k in (row.get("kills") or []))


def cycle_series(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per cycle, in log order, with that cycle's new passes and kill signatures."""
    order: list[str] = []
    bucket: dict[str, dict[str, Any]] = {}
    for row in rows:
        cid = str(row.get("cycle_id") or "")
        if not cid:
            continue
        if cid not in bucket:
            order.append(cid)
            bucket[cid] = {"cycle_id": cid, "passes": 0, "kills": []}
        if row.get("passed") is True:
            bucket[cid]["passes"] += 1
        elif row.get("passed") is False:
            sig = _kill_sig(row)
            if sig:
                bucket[cid]["kills"].append(sig)
    total = 0
    series = []
    for cid in order:
        info = bucket[cid]
        total += int(info["passes"])
        series.append({
            "cycle_id": cid,
            "passes": int(info["passes"]),
            "pass_total": total,
            "kills": list(info["kills"]),
        })
    return series


def assess_recovery(rows: list[dict[str, Any]], *, cycles: int = STALL_CYCLES) -> dict[str, Any]:
    """Return ``{on, reason, pass_total}`` for a flat run of ``cycles`` cycles.

    ``on`` is true only when each of the last ``cycles`` cycles added zero
    passes and the newest cycle did not introduce a kill signature absent from
    the earlier cycles of that window.
    """
    series = cycle_series(rows)
    if len(series) < cycles:
        return {"on": False, "reason": "too_few_cycles", "pass_total": series[-1]["pass_total"] if series else 0}
    window = series[-cycles:]
    total = window[-1]["pass_total"]
    if any(item["passes"] > 0 for item in window):
        return {"on": False, "reason": "new_pass", "pass_total": total}
    earlier: set[tuple[str, ...]] = set()
    for item in window[:-1]:
        earlier.update(item["kills"])
    fresh = [sig for sig in window[-1]["kills"] if sig not in earlier]
    if fresh and earlier:
        return {"on": False, "reason": "new_kill", "pass_total": total, "new_kills": fresh}
    return {"on": True, "reason": "flat_passes", "pass_total": total}


def identical_kill_streak(
    mutation: str,
    rows: list[dict[str, Any]],
    *,
    run: int = IDENTICAL_KILL_RUN,
) -> bool:
    """True when this mutation's last ``run`` Oracle failures share one kill list."""
    name = (mutation or "").strip()
    if not name:
        return False
    mine = [_kill_sig(r) for r in rows if str(r.get("mutation") or "") == name and r.get("passed") is False]
    if len(mine) < run:
        return False
    tail = mine[-run:]
    return len(set(tail)) == 1 and bool(tail[0])


def recovery_skips(name: str, rows: list[dict[str, Any]] | None = None) -> bool:
    """True when recovery or PERTURB is on and ``name`` (or its theme) is on an identical-kill streak."""
    rows = load_oracle_rows() if rows is None else rows
    if not (assess_recovery(rows)["on"] or perturb_active()):
        return False
    if identical_kill_streak(name, rows):
        return True
    try:
        from colony.lessons import theme_key
        key = theme_key(name)
    except Exception:
        key = ""
    return bool(key) and key != name and identical_kill_streak(key, rows)


def in_recovery_mode(rows: list[dict[str, Any]] | None = None) -> bool:
    """True when the Oracle-log recovery is on, or PERTURB is active."""
    if perturb_active():
        return True
    rows = load_oracle_rows() if rows is None else rows
    return bool(assess_recovery(rows).get("on"))


# ---------------------------------------------------------------------------
# Persisted state
# ---------------------------------------------------------------------------

def _empty_state() -> dict[str, Any]:
    return {
        "version": 1,
        "cycles": [],
        "proposal_parks": {},
        "pass_history": [],
        "kill_history": [],
        "turns": [],
        "targets_tried": [],
        "last_new_pass_cycle": "",
        "stall_cycles": 0,
        "perturb": {
            "active": False,
            "entered_at": "",
            "seed": None,
            "cycles_in_mode": 0,
            "park_multiplier": 1,
            "epsilon": PERTURB_EPSILON,
            "exit_reason": "",
            "exit_cycle": "",
        },
    }


def load_state() -> dict[str, Any]:
    state = _empty_state()
    path = STATE_PATH
    if not path.exists():
        return state
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return state
    if not isinstance(raw, dict):
        return state
    state.update(raw)
    state.setdefault("cycles", [])
    state.setdefault("proposal_parks", {})
    state.setdefault("pass_history", [])
    state.setdefault("kill_history", [])
    state.setdefault("turns", [])
    state.setdefault("targets_tried", [])
    state.setdefault("perturb", _empty_state()["perturb"])
    for key, default in _empty_state()["perturb"].items():
        state["perturb"].setdefault(key, default)
    return state


def save_state(state: dict[str, Any]) -> Path:
    path = STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def _cycle_index(state: dict[str, Any], cycle_id: str) -> int:
    cycles = state.setdefault("cycles", [])
    cid = str(cycle_id or "")
    if cid and cid not in cycles:
        cycles.append(cid)
    if cid and cid in cycles:
        return cycles.index(cid)
    return max(0, len(cycles) - 1)


def remember_cycle(cycle_id: str) -> int:
    state = load_state()
    idx = _cycle_index(state, cycle_id)
    save_state(state)
    return idx


# ---------------------------------------------------------------------------
# Item 1: proposal cooldown (park after two consecutive dedupe blocks)
# ---------------------------------------------------------------------------

def note_dedupe_block(
    fingerprint: str,
    title: str = "",
    action: str = "",
    cycle_id: str = "",
) -> dict[str, Any]:
    """Record a ``blocked_repeat``. Park the fingerprint after two consecutive cycles."""
    fp = (fingerprint or "").strip()
    if not fp:
        return {}
    state = load_state()
    idx = _cycle_index(state, cycle_id)
    parks = state.setdefault("proposal_parks", {})
    rec = parks.get(fp) or {
        "title": title,
        "action": action,
        "blocks": [],
        "consecutive": 0,
        "parked_until": -1,
        "duration": PARK_CYCLES * int(state.get("perturb", {}).get("park_multiplier") or 1),
    }
    if title:
        rec["title"] = title
    if action:
        rec["action"] = action
    blocks = list(rec.get("blocks") or [])
    if cycle_id and blocks and blocks[-1] == cycle_id:
        parks[fp] = rec
        save_state(state)
        return rec
    consecutive = 1
    if blocks and cycle_id:
        last = blocks[-1]
        cycles = state["cycles"]
        if last in cycles and idx - cycles.index(last) == 1:
            consecutive = int(rec.get("consecutive") or 0) + 1
        elif last == cycle_id:
            consecutive = int(rec.get("consecutive") or 1)
    elif not blocks:
        consecutive = 1
    if cycle_id:
        blocks.append(cycle_id)
    rec["blocks"] = blocks[-20:]
    rec["consecutive"] = consecutive
    duration = int(rec.get("duration") or PARK_CYCLES)
    duration = max(duration, PARK_CYCLES * int(state.get("perturb", {}).get("park_multiplier") or 1))
    rec["duration"] = duration
    already_parked = int(rec.get("parked_until") or -1) > idx
    if consecutive >= BLOCK_STREAK_TO_PARK and not already_parked:
        # Park the next `duration` cycles (not counting this block cycle).
        rec["parked_until"] = idx + duration + 1
        rec["parked_from"] = idx + 1
        rec["parked_at_cycle"] = cycle_id
    parks[fp] = rec
    save_state(state)
    return rec


def is_parked(fingerprint: str, cycle_id: str = "") -> bool:
    """True when this proposal fingerprint is in its park window."""
    fp = (fingerprint or "").strip()
    if not fp:
        return False
    state = load_state()
    rec = (state.get("proposal_parks") or {}).get(fp)
    if not rec:
        return False
    until = int(rec.get("parked_until") or -1)
    if until < 0:
        return False
    cycles = list(state.get("cycles") or [])
    if cycle_id:
        if cycle_id in cycles:
            idx = cycles.index(cycle_id)
        else:
            # A cycle not yet recorded sits just after the last known one.
            idx = len(cycles)
    else:
        idx = max(0, len(cycles) - 1)
    fr = int(rec.get("parked_from") or -1)
    if fr >= 0 and idx < fr:
        return False
    return idx < until


def parked_fingerprints(cycle_id: str = "") -> set[str]:
    state = load_state()
    idx = _cycle_index(state, cycle_id) if cycle_id else max(0, len(state.get("cycles") or []) - 1)
    out = set()
    for fp, rec in (state.get("proposal_parks") or {}).items():
        if int(rec.get("parked_until") or -1) > idx:
            out.add(fp)
    return out


def ingest_dedupe_history(
    events: Iterable[dict[str, Any]] | None = None,
    *,
    lookback: int = 400,
) -> dict[str, Any]:
    """Park any fingerprint already blocked as a repeat in the last two recorded cycles.

    ``events`` is an optional list of ``{fingerprint, cycle_id, title, action}``.
    When omitted, recent ``repeat_proposal`` lessons are read.
    """
    rows: list[dict[str, Any]]
    if events is not None:
        rows = list(events)
    else:
        rows = []
        try:
            from colony.lessons import LESSONS_JSONL
            path = LESSONS_JSONL
        except Exception:
            path = None
        if path is not None and path.exists():
            for ln in path.read_text(encoding="utf-8").splitlines()[-lookback:]:
                if not ln.strip():
                    continue
                try:
                    row = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                tags = {str(t) for t in (row.get("tags") or [])}
                ltype = str(row.get("type") or row.get("lesson_type") or "")
                if "repeat_proposal" not in tags and ltype != "repeat_proposal":
                    continue
                if str(row.get("decision") or "") not in ("block", "skip"):
                    continue
                fp = str(row.get("proposal_fingerprint") or "")
                if not fp:
                    continue
                rows.append({
                    "fingerprint": fp,
                    "cycle_id": str(row.get("cycle_id") or ""),
                    "title": str(row.get("mutation") or row.get("what") or ""),
                    "action": "",
                })
    by_fp: dict[str, list[str]] = {}
    meta: dict[str, dict[str, str]] = {}
    order: list[str] = []
    for ev in rows:
        fp = str(ev.get("fingerprint") or "")
        cid = str(ev.get("cycle_id") or "")
        if not fp or not cid:
            continue
        if cid not in order:
            order.append(cid)
        lst = by_fp.setdefault(fp, [])
        if cid not in lst:
            lst.append(cid)
        meta[fp] = {"title": str(ev.get("title") or ""), "action": str(ev.get("action") or "")}
    if len(order) < BLOCK_STREAK_TO_PARK:
        # Still record the blocks we saw, so a following cycle can complete the streak.
        for fp, cids in by_fp.items():
            for cid in cids:
                note_dedupe_block(fp, meta[fp]["title"], meta[fp]["action"], cid)
        return load_state()
    last_two = set(order[-BLOCK_STREAK_TO_PARK:])
    for fp, cids in by_fp.items():
        present = [c for c in cids if c in last_two]
        # Apply blocks in cycle order so consecutive detection works.
        for cid in cids:
            note_dedupe_block(fp, meta[fp]["title"], meta[fp]["action"], cid)
        if set(present) >= last_two:
            # note_dedupe_block already parks on the second consecutive; nothing more to do.
            pass
    return load_state()


def give_turn_elsewhere(
    cycle_id: str,
    excluded: Iterable[str] = (),
    *,
    picker: Callable[[], tuple[str, str, str] | None] | None = None,
) -> dict[str, Any]:
    """Send a parked proposal's turn to a different source.

    Tries ``picker`` (an alternate title, hypothesis, action) if it is not
    parked, otherwise one OEIS idle-turn attempt, and in PERTURB also the
    seeded target draw. Never judges or scores the result itself.
    """
    excluded_fps = {str(x) for x in excluded}
    result: dict[str, Any] = {"cycle_id": cycle_id, "source": "", "proposal": None, "oeis": None, "perturb": None}
    if picker is not None:
        try:
            alt = picker()
        except Exception:
            alt = None
        if alt:
            title, hypothesis, action = alt
            try:
                from colony.fitness import proposal_fingerprint
                fp = proposal_fingerprint(title, action)
            except Exception:
                fp = f"{title}|{action}"
            if fp not in excluded_fps and not is_parked(fp, cycle_id):
                result["source"] = "alternate_proposal"
                result["proposal"] = {"title": title, "hypothesis": hypothesis, "action": action, "fingerprint": fp}
                return result
    try:
        from colony.oeis_conjectures import idle_turn
        result["oeis"] = idle_turn(cycle_id or "parked_turn")
        if result["oeis"] and (result["oeis"].get("chosen") or result["oeis"].get("results")):
            result["source"] = result["source"] or "oeis_idle"
    except Exception:
        result["oeis"] = None
    if perturb_active():
        try:
            result["perturb"] = run_perturb_turn(cycle_id, n=PERTURB_MIN_TARGETS)
            result["source"] = result["source"] or "perturb"
        except Exception:
            pass
    if not result["source"]:
        result["source"] = "none"
    return result


# ---------------------------------------------------------------------------
# Turns, pass history, stall assessment
# ---------------------------------------------------------------------------

DEAD_END_OUTCOMES = frozenset({"block", "skip", "identical_kill"})


def record_turn(cycle_id: str, kind: str, name: str, outcome: str, **extra: Any) -> None:
    """Record one Oracle-bound or desk turn for stall condition (b)."""
    if not cycle_id:
        return
    state = load_state()
    _cycle_index(state, cycle_id)
    turns = state.setdefault("turns", [])
    entry = {"cycle_id": cycle_id, "kind": kind, "name": name, "outcome": outcome}
    entry.update({k: v for k, v in extra.items() if v is not None})
    # Idempotent: same turn twice in one cycle is one turn.
    for prev in reversed(turns[-30:]):
        if (prev.get("cycle_id") == cycle_id and prev.get("kind") == kind
                and prev.get("name") == name and prev.get("outcome") == outcome):
            return
    turns.append(entry)
    state["turns"] = turns[-400:]
    save_state(state)


def record_pass_total(cycle_id: str, pass_total: int, kills: Iterable[Any] | None = None) -> dict[str, Any]:
    """Snapshot the all-time Oracle pass total at the end of a cycle."""
    state = load_state()
    _cycle_index(state, cycle_id)
    hist = state.setdefault("pass_history", [])
    # Replace a snapshot already taken for this cycle.
    hist = [h for h in hist if str(h.get("cycle_id")) != cycle_id]
    hist.append({"cycle_id": cycle_id, "pass_total": int(pass_total)})
    state["pass_history"] = hist[-80:]
    if kills is not None:
        kh = state.setdefault("kill_history", [])
        sigs = [tuple(k) if not isinstance(k, str) else (k,) for k in kills]
        kh = [h for h in kh if str(h.get("cycle_id")) != cycle_id]
        kh.append({"cycle_id": cycle_id, "kills": [list(s) for s in sigs]})
        state["kill_history"] = kh[-80:]
    # stall_cycles: consecutive cycles at the end whose pass_total equals the latest.
    stall = 0
    if hist:
        latest = hist[-1]["pass_total"]
        for h in reversed(hist):
            if h["pass_total"] == latest:
                stall += 1
            else:
                break
        # The first snapshot of a value is the cycle that produced that total
        # (a new pass, or the start of history). It does not count as stalled.
        if stall >= 1:
            # cycles since the last *change*: stall-1, except we want "cycles
            # since the last new Oracle pass", which is how many snapshots
            # equal the current total, after the change. If the first of the
            # equal run is the last change, stall_cycles = stall - 1 when we
            # can see a prior different total, else stall (no prior pass).
            saw_change = any(h["pass_total"] != latest for h in hist)
            stall_cycles = stall - 1 if saw_change else stall
        else:
            stall_cycles = 0
        if stall == 1 and (len(hist) == 1 or hist[-2]["pass_total"] != latest):
            state["last_new_pass_cycle"] = cycle_id
            stall_cycles = 0
    else:
        stall_cycles = 0
    state["stall_cycles"] = stall_cycles
    save_state(state)
    return {"stall_cycles": stall_cycles, "pass_total": int(pass_total)}


def current_pass_total(rows: list[dict[str, Any]] | None = None) -> int:
    if rows is not None:
        return sum(1 for r in rows if r.get("passed") is True)
    try:
        from colony.oracle import counts
        return int(counts().get("passes") or 0)
    except Exception:
        return 0


def assess_stall(state: dict[str, Any] | None = None) -> dict[str, Any]:
    """STALL when passes are flat for six cycles, or the last three cycles are all dead ends."""
    state = state if state is not None else load_state()
    hist = list(state.get("pass_history") or [])
    reason = ""
    on = False
    if len(hist) >= STALL_CYCLES:
        window = hist[-STALL_CYCLES:]
        totals = [int(h.get("pass_total") or 0) for h in window]
        if len(set(totals)) == 1:
            on = True
            reason = "flat_passes"
    if not on:
        # Dead-end turns: group by cycle, look at the last STALL_DEAD_END_CYCLES
        # cycles that we have turns (or pass snapshots) for.
        cycles = list(state.get("cycles") or [])
        turns = list(state.get("turns") or [])
        if len(cycles) >= STALL_DEAD_END_CYCLES:
            tail = cycles[-STALL_DEAD_END_CYCLES:]
            all_dead = True
            any_turn = False
            for cid in tail:
                outcomes = [str(t.get("outcome") or "") for t in turns if t.get("cycle_id") == cid]
                if not outcomes:
                    # A cycle with no Oracle-bound or desk turn at all is a dead end:
                    # nothing reached the Oracle.
                    any_turn = True
                    continue
                any_turn = True
                if any(o not in DEAD_END_OUTCOMES for o in outcomes):
                    all_dead = False
                    break
            if all_dead and any_turn:
                on = True
                reason = "dead_end_turns"
    return {
        "on": on,
        "reason": reason or "clear",
        "stall_cycles": int(state.get("stall_cycles") or 0),
        "pass_total": int((hist[-1] or {}).get("pass_total") or 0) if hist else 0,
    }


# ---------------------------------------------------------------------------
# Item 4: PERTURB mode
# ---------------------------------------------------------------------------

def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def perturb_seed(cycle_id: str, commit_sha: str | None = None) -> int:
    """Reproducible seed from the cycle id and the commit SHA."""
    sha = (commit_sha if commit_sha is not None else _git_sha()) or "unknown"
    material = f"{cycle_id}:{sha}"
    return int(hashlib.sha256(material.encode("utf-8")).hexdigest()[:16], 16)


def perturb_active() -> bool:
    try:
        return bool((load_state().get("perturb") or {}).get("active"))
    except Exception:
        return False


def _log_lesson(cycle_id: str, what: str, tags: list[str], lesson_type: str = "skip") -> None:
    try:
        from colony.lessons import write_lesson
        write_lesson(
            decision="skip",
            check="stall",
            what=what,
            source="stall",
            cycle_id=cycle_id,
            lesson_type=lesson_type,
            family="stall",
            tags=tags,
        )
    except Exception:
        pass


def enter_perturb(cycle_id: str, reason: str = "flat_passes", commit_sha: str | None = None) -> dict[str, Any]:
    """Enter PERTURB and log the seed. Idempotent if already active."""
    state = load_state()
    pert = state.setdefault("perturb", _empty_state()["perturb"])
    if pert.get("active"):
        return pert
    sha = commit_sha if commit_sha is not None else _git_sha()
    seed = perturb_seed(cycle_id, sha)
    pert.update({
        "active": True,
        "entered_at": cycle_id,
        "seed": seed,
        "commit_sha": sha,
        "reason": reason,
        "cycles_in_mode": 0,
        "epsilon": PERTURB_EPSILON if int(pert.get("park_multiplier") or 1) <= 1 else PERTURB_WIDE_EPSILON,
        "exit_reason": "",
        "exit_cycle": "",
    })
    state["perturb"] = pert
    save_state(state)
    msg = f"STALL detected at cycle {cycle_id}, entering perturb (seed {seed})"
    _log_lesson(cycle_id, msg, tags=["stall_detected", "perturb", reason])
    pert = dict(pert)
    pert["message"] = msg
    return pert


def exit_perturb(cycle_id: str, reason: str) -> dict[str, Any]:
    """Leave PERTURB. A timeout doubles parked durations and widens later draws."""
    state = load_state()
    pert = state.setdefault("perturb", _empty_state()["perturb"])
    if not pert.get("active"):
        return pert
    timeout = reason in ("timeout", "timed_out", "max_cycles")
    if timeout:
        pert["park_multiplier"] = int(pert.get("park_multiplier") or 1) * 2
        pert["epsilon"] = PERTURB_WIDE_EPSILON
        for rec in (state.get("proposal_parks") or {}).values():
            until = int(rec.get("parked_until") or -1)
            duration = int(rec.get("duration") or PARK_CYCLES)
            if until >= 0:
                rec["duration"] = duration * 2
                rec["parked_until"] = until + duration  # extend remaining park by the old duration
    pert["active"] = False
    pert["exit_reason"] = reason
    pert["exit_cycle"] = cycle_id
    pert["cycles_in_mode"] = 0
    state["perturb"] = pert
    save_state(state)
    msg = f"Recovered at cycle {cycle_id} because {reason}"
    _log_lesson(cycle_id, msg, tags=["stall_recovered", "perturb", reason])
    pert = dict(pert)
    pert["message"] = msg
    return pert


def _ledger_seen_ids() -> set[str]:
    seen: set[str] = set()
    try:
        from colony.lessons import LESSONS_JSONL, LEDGER_SYSTEM, theme_key
    except Exception:
        return seen
    for path in (LESSONS_JSONL, LEDGER_SYSTEM):
        if path is None or not Path(path).exists():
            continue
        try:
            raw = Path(path).read_text(encoding="utf-8")
        except OSError:
            continue
        if path == LEDGER_SYSTEM or raw.lstrip().startswith("{") or raw.lstrip().startswith("["):
            try:
                data = json.loads(raw)
            except ValueError:
                data = None
            if isinstance(data, dict):
                for key in ("lessons", "entries", "items"):
                    if isinstance(data.get(key), list):
                        for e in data[key]:
                            if isinstance(e, dict):
                                for field in ("mutation", "check", "id", "target", "anum"):
                                    v = e.get(field)
                                    if v:
                                        seen.add(str(v))
                # ledger may be a name -> record map
                for k in data:
                    if isinstance(k, str) and not k.startswith("_"):
                        seen.add(k)
            elif isinstance(data, list):
                for e in data:
                    if isinstance(e, dict):
                        for field in ("mutation", "check", "id", "target"):
                            if e.get(field):
                                seen.add(str(e[field]))
            continue
        for ln in raw.splitlines()[-800:]:
            try:
                e = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if isinstance(e, dict):
                for field in ("mutation", "check", "id", "target", "anum"):
                    if e.get(field):
                        seen.add(str(e[field]))
    return seen


def _tried_last_n(n: int = UNUSED_MENU_CYCLES) -> set[str]:
    state = load_state()
    cycles = list(state.get("cycles") or [])
    recent = set(cycles[-n:])
    tried: set[str] = set()
    for row in state.get("targets_tried") or []:
        if row.get("cycle_id") in recent or not recent:
            for t in row.get("targets") or []:
                tried.add(str(t))
    return tried


def record_targets_tried(cycle_id: str, targets: Iterable[str]) -> None:
    names = [str(t) for t in targets if t]
    if not cycle_id or not names:
        return
    state = load_state()
    _cycle_index(state, cycle_id)
    rows = [r for r in (state.get("targets_tried") or []) if r.get("cycle_id") != cycle_id]
    rows.append({"cycle_id": cycle_id, "targets": names})
    state["targets_tried"] = rows[-80:]
    save_state(state)


def selection_bonus(target_id: str, *, ledger_seen: set[str] | None = None,
                    tried_recent: set[str] | None = None) -> float:
    """Temporary novelty-exploration bonus. Selection only; never the Oracle or a score."""
    if not perturb_active():
        return 0.0
    ledger_seen = ledger_seen if ledger_seen is not None else _ledger_seen_ids()
    tried_recent = tried_recent if tried_recent is not None else _tried_last_n()
    bonus = 0.0
    tid = str(target_id or "")
    if tid and tid not in ledger_seen:
        bonus += 0.3
    if tid and tid not in tried_recent:
        bonus += 0.2
    return bonus


def mutate_ingredient(
    spec: dict[str, Any],
    rng: random.Random,
    alternatives: dict[str, list[Any]] | None = None,
) -> dict[str, Any]:
    """Copy ``spec`` and change exactly one ingredient (sequence, modulus, offset, or window)."""
    new = dict(spec)
    alts = alternatives or {}
    keys = [k for k in MUTATION_INGREDIENTS if alts.get(k) and any(v != spec.get(k) for v in alts[k])]
    if not keys:
        keys = [k for k in MUTATION_INGREDIENTS if k in spec and alts.get(k)]
    if not keys:
        new["mutated"] = False
        return new
    key = rng.choice(keys)
    options = [v for v in alts[key] if v != spec.get(key)]
    if not options:
        new["mutated"] = False
        return new
    new[key] = rng.choice(options)
    new["mutated"] = True
    new["mutated_from"] = spec.get("id") or spec.get("name")
    new["mutated_ingredient"] = key
    base = str(spec.get("id") or spec.get("name") or "seed")
    new["id"] = f"{base}:{key}={new[key]}"
    return new


def _oeis_candidates(tried: set[str], ledger: set[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        from colony.oeis_conjectures import load_menu, zero_credit_forms, _load, STATE, provable
        menu = load_menu()
        state = _load(STATE, {"targets": {}, "families": {}, "credit_total": 0.0})
        forms = set(zero_credit_forms(state, menu))
        tg = state.get("targets") or {}
    except Exception:
        return out
    for e in menu:
        eid = str(e.get("id") or "")
        form = str((e.get("claim") or {}).get("form") or "")
        st = tg.get(eid) or {}
        if st.get("status") in ("counterexample_verified", "proved_checked", "fails_in_data", "untestable_here"):
            continue
        # Prefer zero-credit and non-routine; still include others as a tail.
        band = 0 if form in forms else (2 if (form == "relation" and provable(e)) else 1)
        unseen = eid not in ledger
        unused = eid not in tried
        out.append({
            "id": eid,
            "source": "oeis",
            "kind": "oeis_conjecture",
            "form": form,
            "anum": e.get("anum"),
            "text": e.get("text") or "",
            "band": band,
            "unseen": unseen,
            "unused": unused,
            "entry": e,
        })
    out.sort(key=lambda t: (t["band"], 0 if t["unseen"] else 1, 0 if t["unused"] else 1, t["id"]))
    return out


def _shape_candidates(tried: set[str], rng: random.Random) -> list[dict[str, Any]]:
    """Claim shapes and unused families, as menu slices, not hardcoded sequences."""
    out = []
    for shape in CLAIM_SHAPES:
        tid = f"shape:{shape}"
        if tid in tried:
            continue
        out.append({
            "id": tid,
            "source": "claim_shape",
            "kind": "claim_shape",
            "form": shape,
            "text": f"explore claim shape {shape}",
            "band": 0,
            "unseen": True,
            "unused": True,
        })
    rng.shuffle(out)
    return out


def select_perturb_targets(
    cycle_id: str,
    n: int = PERTURB_MIN_TARGETS,
    *,
    commit_sha: str | None = None,
    menu: list[dict[str, Any]] | None = None,
    kept_seeds: list[dict[str, Any]] | None = None,
    alternatives: dict[str, list[Any]] | None = None,
) -> list[dict[str, Any]]:
    """Epsilon-greedy draw of at least ``n`` distinct new targets. Seeded and logged."""
    state = load_state()
    pert = state.get("perturb") or {}
    seed = pert.get("seed") if pert.get("active") and pert.get("entered_at") else None
    if seed is None:
        seed = perturb_seed(cycle_id, commit_sha)
    rng = random.Random(int(seed) ^ int(hashlib.sha256(cycle_id.encode()).hexdigest()[:8], 16))
    epsilon = float(pert.get("epsilon") or PERTURB_EPSILON)
    tried = _tried_last_n(UNUSED_MENU_CYCLES)
    ledger = _ledger_seen_ids()
    pool = list(menu) if menu is not None else _oeis_candidates(tried, ledger)
    pool = pool + _shape_candidates(tried, rng)
    # Mutate recently kept seeds: change one ingredient.
    for spec in (kept_seeds or []):
        mutated = mutate_ingredient(spec, rng, alternatives)
        if mutated.get("mutated"):
            mutated.setdefault("source", "mutated_seed")
            mutated.setdefault("kind", "mutated_seed")
            mutated.setdefault("band", 0)
            mutated.setdefault("unseen", mutated["id"] not in ledger)
            mutated.setdefault("unused", True)
            pool.append(mutated)
    if not pool:
        return []
    available = list(pool)
    picked: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def _key(t: dict[str, Any]) -> tuple:
        return (int(t.get("band") or 0), 0 if t.get("unseen") else 1, 0 if t.get("unused") else 1, str(t.get("id") or ""))

    while len(picked) < n and available:
        if rng.random() < epsilon:
            preferred = [t for t in available if t.get("unseen") or t.get("unused")] or available
            choice = preferred[rng.randrange(len(preferred))]
        else:
            choice = sorted(available, key=_key)[0]
        tid = str(choice.get("id") or "")
        available = [t for t in available if str(t.get("id") or "") != tid]
        if not tid or tid in seen_ids:
            continue
        seen_ids.add(tid)
        tagged = dict(choice)
        tagged["perturb_seed"] = int(seed)
        picked.append(tagged)
    return picked


def run_perturb_turn(
    cycle_id: str,
    n: int = PERTURB_MIN_TARGETS,
    *,
    oracle_submit: Callable[[dict[str, Any]], Any] | None = None,
    bus: Any = None,
    commit_sha: str | None = None,
    menu: list[dict[str, Any]] | None = None,
    kept_seeds: list[dict[str, Any]] | None = None,
    alternatives: dict[str, list[Any]] | None = None,
) -> dict[str, Any]:
    """Pick at least ``n`` new targets and send them through the normal pipeline / Oracle.

    ``oracle_submit``, when given (tests), is called with each target and its
    return value is stored. In production, OEIS-shaped targets go through
    ``run_cycle`` / ``attempt_disprove``; a provided bus is used to post and
    ``gate_keep`` the same way the claim pipeline does. The Oracle's verdict
    is not altered.
    """
    targets = select_perturb_targets(
        cycle_id, n=n, commit_sha=commit_sha, menu=menu,
        kept_seeds=kept_seeds, alternatives=alternatives,
    )
    submissions: list[dict[str, Any]] = []
    for t in targets:
        submitted: dict[str, Any] = {"id": t.get("id"), "source": t.get("source"), "reached_oracle": False}
        if oracle_submit is not None:
            try:
                submitted["oracle"] = oracle_submit(t)
                submitted["reached_oracle"] = True
            except Exception as exc:
                submitted["error"] = str(exc)[:200]
        else:
            if t.get("source") == "oeis" and t.get("entry") is not None:
                try:
                    from colony.oeis_conjectures import attempt_disprove, attempt_prove, provable
                    e = t["entry"]
                    acts = []
                    if provable(e) and (e.get("claim") or {}).get("form") != "relation":
                        acts.append(attempt_prove(e))
                    if not acts or acts[-1].get("status") != "proved_checked":
                        acts.append(attempt_disprove(e, fetch=False))
                    submitted["oeis_results"] = acts
                except Exception as exc:
                    submitted["error"] = str(exc)[:200]
            if bus is not None:
                try:
                    from colony.oracle import gate_keep
                    dec, ov = gate_keep(
                        tentative_decision="propose",
                        mutation=str(t.get("id") or "perturb"),
                        kind=str(t.get("kind") or "perturb_explore"),
                        claim_text=str(t.get("text") or t.get("id") or ""),
                        source="stall_perturb",
                        cycle_id=cycle_id,
                        bus=bus,
                    )
                    submitted["oracle_decision"] = dec
                    submitted["oracle_passed"] = bool(getattr(ov, "passed", False))
                    submitted["oracle_kills"] = list(getattr(ov, "kills", []) or [])
                    submitted["reached_oracle"] = True
                except Exception as exc:
                    submitted["oracle_error"] = str(exc)[:200]
        submissions.append(submitted)
    record_targets_tried(cycle_id, [str(t.get("id")) for t in targets])
    return {
        "cycle_id": cycle_id,
        "seed": (targets[0].get("perturb_seed") if targets else perturb_seed(cycle_id, commit_sha)),
        "targets": targets,
        "submissions": submissions,
        "n": len(targets),
        "n_reached_oracle": sum(1 for s in submissions if s.get("reached_oracle")),
    }


def maybe_enter_or_exit(
    cycle_id: str,
    *,
    new_pass: bool | None = None,
    new_kill: bool | None = None,
    commit_sha: str | None = None,
) -> dict[str, Any]:
    """Apply enter / exit rules for the current cycle. Called from cycle hooks."""
    state = load_state()
    pert = state.get("perturb") or {}
    stall = assess_stall(state)
    report: dict[str, Any] = {"stall": stall, "perturb": dict(pert), "action": "none"}
    if pert.get("active"):
        # Count this cycle in mode once we are at end-of-cycle.
        cycles_in = int(pert.get("cycles_in_mode") or 0)
        # Exit conditions take priority.
        if new_pass:
            report["action"] = "exit"
            report["perturb"] = exit_perturb(cycle_id, "new_pass")
            return report
        if new_kill:
            report["action"] = "exit"
            report["perturb"] = exit_perturb(cycle_id, "new_kill")
            return report
        if cycles_in >= PERTURB_MAX_CYCLES:
            report["action"] = "exit"
            report["perturb"] = exit_perturb(cycle_id, "timeout")
            return report
        return report
    if stall.get("on"):
        report["action"] = "enter"
        report["perturb"] = enter_perturb(cycle_id, reason=str(stall.get("reason") or "flat_passes"),
                                          commit_sha=commit_sha)
    return report


def on_cycle_start(cycle_id: str, *, commit_sha: str | None = None) -> dict[str, Any]:
    """Remember the cycle, ingest historical dedupe blocks, and enter PERTURB if stalled."""
    remember_cycle(cycle_id)
    try:
        ingest_dedupe_history()
    except Exception:
        pass
    # Enter at the start so the rest of the cycle explores.
    # Exit is decided at the end, once this cycle's Oracle results are known.
    state = load_state()
    if not (state.get("perturb") or {}).get("active"):
        stall = assess_stall(state)
        if stall.get("on"):
            enter_perturb(cycle_id, reason=str(stall.get("reason") or "flat_passes"), commit_sha=commit_sha)
    return {"perturb_active": perturb_active(), "stall": assess_stall(), "visibility": visibility()}


def on_cycle_end(
    cycle_id: str,
    *,
    pass_total: int | None = None,
    rows: list[dict[str, Any]] | None = None,
    commit_sha: str | None = None,
) -> dict[str, Any]:
    """Record this cycle's pass total and kill reasons; maybe leave PERTURB."""
    rows = rows if rows is not None else load_oracle_rows()
    total = current_pass_total(rows) if pass_total is None else int(pass_total)
    # Kill signatures from this cycle only.
    this = [r for r in rows if str(r.get("cycle_id") or "") == cycle_id]
    kills = [_kill_sig(r) for r in this if r.get("passed") is False]
    passes_here = sum(1 for r in this if r.get("passed") is True)
    snap = record_pass_total(cycle_id, total, kills=kills)
    # Record Oracle turns we can see.
    for r in this:
        outcome = "pass" if r.get("passed") is True else (
            "identical_kill" if identical_kill_streak(str(r.get("mutation") or ""), rows) else "kill"
        )
        record_turn(cycle_id, str(r.get("kind") or "oracle"), str(r.get("mutation") or ""), outcome)
    state = load_state()
    hist = state.get("pass_history") or []
    new_pass = False
    if passes_here > 0:
        new_pass = True
    elif len(hist) >= 2 and hist[-1]["pass_total"] > hist[-2]["pass_total"]:
        new_pass = True
    # Genuinely new kill reason: a signature this cycle that is absent from earlier kill_history.
    earlier: set[tuple[str, ...]] = set()
    for h in (state.get("kill_history") or [])[:-1]:
        for s in h.get("kills") or []:
            earlier.add(tuple(s))
    fresh = [s for s in kills if s and s not in earlier]
    new_kill = bool(fresh) and bool(earlier)
    pert = state.get("perturb") or {}
    if pert.get("active"):
        # Tick cycles-in-mode at the end.
        state = load_state()
        state["perturb"]["cycles_in_mode"] = int(state["perturb"].get("cycles_in_mode") or 0) + 1
        save_state(state)
    report = maybe_enter_or_exit(cycle_id, new_pass=new_pass, new_kill=new_kill, commit_sha=commit_sha)
    report["visibility"] = visibility()
    report["new_pass"] = new_pass
    report["new_kill"] = new_kill
    report["pass_snapshot"] = snap
    return report


# ---------------------------------------------------------------------------
# Item 5: visibility
# ---------------------------------------------------------------------------

def visibility() -> dict[str, Any]:
    """Fields for the fitness and scoreboard output. Not scored, not the Oracle."""
    state = load_state()
    cycles = list(state.get("cycles") or [])
    last3 = set(cycles[-3:])
    targets: set[str] = set()
    for row in state.get("targets_tried") or []:
        if not last3 or row.get("cycle_id") in last3:
            for t in row.get("targets") or []:
                targets.add(str(t))
    # Also count turn names in the last 3 cycles as tried targets.
    for t in state.get("turns") or []:
        if t.get("cycle_id") in last3 and t.get("name"):
            targets.add(str(t["name"]))
    return {
        "stall_cycles": int(state.get("stall_cycles") or 0),
        "perturb_active": bool((state.get("perturb") or {}).get("active")),
        "distinct_targets_tried_last_3_cycles": len(targets),
    }


def format_visibility(vis: dict[str, Any] | None = None) -> str:
    v = vis if vis is not None else visibility()
    return (
        f"stall_cycles {v.get('stall_cycles', 0)}; "
        f"perturb_active {bool(v.get('perturb_active'))}; "
        f"distinct_targets_tried_last_3_cycles {v.get('distinct_targets_tried_last_3_cycles', 0)}"
    )
