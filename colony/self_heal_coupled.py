"""Item 74: binding caps under current knobs, coupled cap trials, compute_bound.

A target can sit between two caps: at gf_term_cap 2310 the term cap binds
(depth = cap - 1); at gf 2865 the 8 s time cap binds (depth 75). Single-knob
trials then alternate forever, and a trial built from a row recorded under
other knob values predicts a target its knob cannot move.

- (a) ``binding_cap_now``: the binding cap of a target is read only from
  attempt rows whose recorded knob values (planned term cap, cap_value)
  match the CURRENT knob values. Rows from cycles with other knob values
  are ignored. ``prediction_fits`` uses it before any cap trial opens.
- (b) ``detect_flip`` / ``coupled_proposal``: when a recent non-adopted trial
  on the knob that binds now pushed the same target into a different cap
  (still binding at that knob's current value), one coupled trial raises
  both knobs together, each clamped to its KnobSpec bounds. It uses the
  normal single trial slot, the same 6-cycle window, and the same
  strictly-better rule on predicted-target depth gain.
- (c) ``retire_compute_bound``: a coupled trial that is not adopted, or a
  flip whose second knob is already at its physical ceiling, retires the
  target from the cap ladder (append-only ``target_retired`` evidence,
  reason ``compute_bound``). Predictions skip it, so the budget moves to
  other targets and knobs. It returns to the ladder only if one of the two
  knobs later rises above the value it had at retirement.

Tighten-only: the Oracle, P >= 0.70, the 150 cap, Wilson, windows,
strictly-better, the triviality filter and Athanor are untouched. Every
entry point is a no-op on the control arm.
"""
from __future__ import annotations

import math
from typing import Any

FLIP_LOOKBACK_EVENTS = 40
# Item 76: e.g.f. / series cost grows about cubically in the number of terms
# (O(L^2) coefficient products on O(L)-bit numbers): gf 2865 -> 3975 took
# ~2.8x the time. A coupled raise aims to fit inside this share of the new
# time budget.
TIME_COST_POWER = 3.0
TIME_FIT_MARGIN = 0.9
# Only the most recent time-capped rows: older ones ran under other code or
# runners (A126089 once timed out at gf 2310 and later finished 2865).
TIME_ROWS_RECENT = 3
CLOSED_FAIL = ("trial_inconclusive", "revert")


def _self_mod() -> bool:
    try:
        from colony.arm import self_mod_enabled
        return bool(self_mod_enabled())
    except Exception:
        return True


def _log(attempt_log: dict[str, Any] | None) -> dict[str, Any]:
    if attempt_log is not None:
        return attempt_log
    try:
        from colony.oeis_conjectures import load_attempt_log
        return load_attempt_log()
    except Exception:
        return {"attempts": []}


def _rows(tid: str, log: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in (log.get("attempts") or []) if isinstance(r, dict) and str(r.get("id") or "") == tid]


def _num(x: Any) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def row_cap(row: dict[str, Any]) -> tuple[str, float | None, frozenset[str]]:
    """(cap_reason, cap_value, knobs that bind it) for one attempt row."""
    from colony.oeis_conjectures import cap_of_row, knobs_for_cap_reason
    reason, val = cap_of_row(row, None)
    if not reason:
        return "", None, frozenset()
    return str(reason), _num(val), frozenset(knobs_for_cap_reason(reason, row=row))


def term_knob_of(tid: str, log: dict[str, Any]) -> str:
    """Term-cap knob of a target, from its latest term-cap row that maps to one."""
    from colony.oeis_conjectures import CAP_TERM, term_cap_knob_for
    for row in reversed(_rows(tid, log)):
        if row.get("cap_reason") == CAP_TERM:
            k = term_cap_knob_for(None, row=row)
            if k:
                return k
    return ""


def _match(val: Any, cur: Any, tol: float = 1e-9) -> bool:
    a, b = _num(val), _num(cur)
    return a is not None and b is not None and abs(a - b) <= tol


def row_consistent(row: dict[str, Any], knobs: dict[str, Any], term_knob: str) -> bool:
    """True when every knob value this row reveals equals the current knob value."""
    from colony.oeis_conjectures import CAP_TERM
    if term_knob and term_knob in knobs and row.get("planned") is not None:
        if not _match(row.get("planned"), knobs[term_knob], 2):
            return False
    reason, val, bound = row_cap(row)
    if not reason or val is None:
        return True
    if reason == CAP_TERM:
        return not term_knob or term_knob not in knobs or _match(val, knobs[term_knob], 2)
    if len(bound) == 1:
        (k,) = tuple(bound)
        if k in knobs:
            return _match(val, knobs[k], 1e-6)
    return True


def binding_cap_now(tid: str, knobs: dict[str, Any], *,
                    attempt_log: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Binding cap of ``tid`` from its latest row recorded under the current knob values."""
    log = _log(attempt_log)
    tk = term_knob_of(tid, log)
    for row in reversed(_rows(tid, log)):
        if row_consistent(row, knobs, tk):
            reason, val, bound = row_cap(row)
            return {"cap_reason": reason, "cap_value": val, "knobs": sorted(bound),
                    "cycle_id": row.get("cycle_id"), "term_knob": tk}
    return None


def prediction_fits(tid: str, knob: str, knobs: dict[str, Any], *,
                    attempt_log: dict[str, Any] | None = None) -> bool | None:
    """(a) Does raising ``knob`` move ``tid`` under the current knobs?

    None when no row was recorded under the current knob values (the caller
    keeps its previous rule).
    """
    now = binding_cap_now(tid, knobs, attempt_log=attempt_log)
    if now is None:
        return None
    if not now["cap_reason"]:
        return True
    return knob in now["knobs"]


# --- (c) compute_bound retirement --------------------------------------------

def compute_bound(state: dict[str, Any] | None, tid: str) -> bool:
    return bool(state) and tid in (state.get("compute_bound_targets") or {})


def retire_compute_bound(state: dict[str, Any], tid: str, *, cycle_id: str, why: str,
                         knobs_at: dict[str, Any], trial_evidence_id: str | None = None) -> dict[str, Any] | None:
    if not _self_mod() or compute_bound(state, tid):
        return None
    from colony.self_heal import append_evidence
    ev = append_evidence(state, {
        "event": "target_retired",
        "cycle_id": cycle_id,
        "target": tid,
        "reason": "compute_bound",
        "detail": why,
        "knobs": dict(knobs_at),
        "trial_evidence_id": trial_evidence_id,
        "applied_to_live_oracle": False,
        "authorized": False,
    })
    reg = dict(state.get("compute_bound_targets") or {})
    reg[tid] = {"cycle_id": cycle_id, "detail": why, "knobs": dict(knobs_at), "evidence_id": ev.get("id")}
    state["compute_bound_targets"] = reg
    return ev


def refresh_compute_bound(state: dict[str, Any], cycle_id: str = "") -> list[str]:
    """Return a target to the ladder once one of its knobs rose above the retirement value."""
    if not _self_mod():
        return []
    reg = dict(state.get("compute_bound_targets") or {})
    knobs = state.get("knobs") or {}
    back: list[str] = []
    for tid, rec in list(reg.items()):
        for k, v in (rec.get("knobs") or {}).items():
            a, b = _num(knobs.get(k)), _num(v)
            if a is not None and b is not None and a > b:
                back.append(tid)
                break
    if back:
        from colony.self_heal import append_evidence
        for tid in back:
            reg.pop(tid, None)
            append_evidence(state, {"event": "target_unretired", "cycle_id": cycle_id, "target": tid,
                                    "reason": "knob_rose_above_retirement_value",
                                    "applied_to_live_oracle": False, "authorized": False})
        state["compute_bound_targets"] = reg
    return back


# --- (b) flip detection and the coupled proposal ------------------------------

def _trial_cycles(e: dict[str, Any]) -> set[str]:
    cycles = {str(e.get("started_cycle") or "")}
    cycles |= {str(r.get("cycle_id") or "") for r in (e.get("trial_metrics") or []) if isinstance(r, dict)}
    cycles.discard("")
    return cycles


def detect_flip(state: dict[str, Any], tid: str, *,
                attempt_log: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """A recent failed trial on the knob binding ``tid`` now pushed it into another cap.

    The other cap must still bind at its knob's current value (row cap_value
    equals the current knob value), so the flip is real under today's knobs.
    """
    log = _log(attempt_log)
    knobs = state.get("knobs") or {}
    now = binding_cap_now(tid, knobs, attempt_log=log)
    if not now or not now["cap_reason"] or len(now["knobs"]) != 1:
        return None
    b = now["knobs"][0]
    rows = _rows(tid, log)
    evidence = [e for e in list(state.get("evidence") or [])[-FLIP_LOOKBACK_EVENTS:] if isinstance(e, dict)]
    best: dict[str, Any] | None = None
    for e in evidence:
        if e.get("event") not in CLOSED_FAIL or str(e.get("knob") or "") != b or e.get("coupled"):
            continue
        if tid not in (e.get("predicted_targets") or []):
            continue
        tried = _num(e.get("from"))
        cur_b = _num(knobs.get(b))
        if tried is None or cur_b is None or tried <= cur_b:
            continue
        cycles = _trial_cycles(e)
        for row in rows:
            if str(row.get("cycle_id") or "") not in cycles:
                continue
            reason, val, bound = row_cap(row)
            if not reason or b in bound or len(bound) != 1:
                continue
            (o,) = tuple(bound)
            if o not in knobs or not _match(val, knobs[o], 2 if "term" in o else 1e-6):
                continue
            if best is None or tried < best["failed_value"]:
                best = {"target": tid, "knob": b, "failed_value": e.get("from"),
                        "other_knob": o, "other_cap_reason": reason,
                        "binding_now": now["cap_reason"], "trial_evidence_id": e.get("id")}
    return best


def coupled_already_failed(state: dict[str, Any], tid: str, knob: str, other: str) -> dict[str, Any] | None:
    for e in reversed(list(state.get("evidence") or [])):
        if not isinstance(e, dict) or e.get("event") not in CLOSED_FAIL:
            continue
        c = e.get("coupled") or {}
        if str(e.get("knob") or "") == knob and c.get("knob") == other and tid in (e.get("predicted_targets") or []):
            return e
    return None


def coupled_values(knob: str, cur: Any, to: Any, other: str, other_cur: Any) -> Any:
    """Second knob value for a coupled raise, within its KnobSpec bounds.

    At least one normal step. A time cap is scaled by (to/cur)^2 and a digit
    cap by (to/cur) when the first knob is a term cap (a deeper range costs
    more time and more digits); a term cap uses the frontier step.
    """
    from colony.self_heal import KNOB_SPECS, clamp, frontier_cap_value, stepped_value
    from colony.oeis_conjectures import TERM_CAP_KNOBS
    spec = KNOB_SPECS[other]
    step = stepped_value(other, "up", current=other_cur)
    if step is None:
        return None
    want = float(step)
    if knob in TERM_CAP_KNOBS and other not in TERM_CAP_KNOBS:
        ratio = float(to) / max(1.0, float(cur))
        power = 2.0 if other == "deep_seconds" else 1.0
        want = max(want, float(other_cur) * ratio ** power)
    elif other in TERM_CAP_KNOBS:
        f = frontier_cap_value(other, "up", current=other_cur)
        if f is not None:
            want = max(want, float(f))
    if spec.kind == "int":
        val = clamp(other, int(math.ceil(want)))
    else:
        val = clamp(other, math.ceil(want * 10.0) / 10.0)
    if float(val) <= float(other_cur):
        return None
    return val


def coupled_proposal(state: dict[str, Any], targets: list[str], *, cycle_id: str,
                     attempt_log: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """(b)/(c) One coupled trial for the first flipped target, or retire it.

    Returns {"knob","from","to","coupled":{...},"predicted_targets":[tid],...}
    fields for propose_trial to complete, or None.
    """
    if not _self_mod():
        return None
    from colony.self_heal import KNOB_SPECS, eligible_target_ids, state_knob
    from colony.oeis_conjectures import cap_override
    log = _log(attempt_log)
    knobs = state.get("knobs") or {}
    for tid in targets:
        if compute_bound(state, tid):
            continue
        flip = detect_flip(state, tid, attempt_log=log)
        if not flip:
            continue
        b, o = flip["knob"], flip["other_knob"]
        cur_b, cur_o = state_knob(state, b), state_knob(state, o)
        knobs_at = {b: cur_b, o: cur_o}
        failed = coupled_already_failed(state, tid, b, o)
        if failed is not None:
            retire_compute_bound(state, tid, cycle_id=cycle_id, why="coupled_trial_not_adopted",
                                 knobs_at=knobs_at, trial_evidence_id=failed.get("id"))
            continue
        if float(cur_o) >= float(KNOB_SPECS[o].hi) or float(cur_b) >= float(KNOB_SPECS[b].hi):
            retire_compute_bound(state, tid, cycle_id=cycle_id, why="knob_at_physical_ceiling",
                                 knobs_at=knobs_at, trial_evidence_id=flip.get("trial_evidence_id"))
            continue
        to_b = flip["failed_value"]
        to_o = coupled_values(b, cur_b, to_b, o, cur_o)
        if to_o is None:
            retire_compute_bound(state, tid, cycle_id=cycle_id, why="knob_at_physical_ceiling",
                                 knobs_at=knobs_at, trial_evidence_id=flip.get("trial_evidence_id"))
            continue
        fit = None
        if o == "deep_seconds":
            # Item 76: when the time cap stopped the failed raise, size the
            # pair from the observed time (cubic cost): at least the time
            # estimate for deep_seconds, and a narrower term step when even
            # the knob's ceiling cannot cover the full raise.
            need = time_needed(tid, b, to_b, attempt_log=log)
            if need is not None and need > float(to_o):
                from colony.self_heal import clamp as _clamp
                to_o = _clamp(o, max(float(to_o), math.ceil(need * 10.0) / 10.0))
            fit = fit_term_to_time(tid, b, cur_b, to_b, to_o, attempt_log=log)
            if fit is None:
                retire_compute_bound(state, tid, cycle_id=cycle_id, why="time_cap_beyond_knob_ceiling",
                                     knobs_at=knobs_at, trial_evidence_id=flip.get("trial_evidence_id"))
                continue
            if fit != to_b:
                fit, to_b = to_b, fit
            else:
                fit = None
        try:
            before = eligible_target_ids()
            with cap_override(b, to_b), cap_override(o, to_o):
                after = eligible_target_ids()
        except Exception:
            continue
        if tid not in (set(after) - set(before)):
            continue
        return {
            "knob": b, "from": cur_b, "to": to_b, "direction": "up",
            "coupled": {"knob": o, "from": cur_o, "to": to_o, "direction": "up",
                        "cap_reason": flip["other_cap_reason"]},
            "coupled_flip": {k: flip[k] for k in ("target", "binding_now", "other_cap_reason", "trial_evidence_id")},
            **({"narrowed_to_time_budget": {"failed_to": fit, "to": to_b}} if fit is not None else {}),
            "exploratory": True,
            "predicted_targets": [tid],
        }
    return None


def after_close(state: dict[str, Any], trial: dict[str, Any], decision: str, *, cycle_id: str) -> None:
    """(c) A coupled trial that is not adopted retires its predicted targets."""
    if not _self_mod() or not trial.get("coupled") or decision == "adopt":
        return
    knobs_at = {str(trial.get("knob")): trial.get("from")}
    for c in [trial["coupled"]] + list(trial.get("coupled_more") or []):
        if isinstance(c, dict) and c.get("knob"):
            knobs_at[str(c.get("knob"))] = c.get("from")
    for tid in trial.get("predicted_targets") or []:
        retire_compute_bound(state, str(tid), cycle_id=cycle_id, why="coupled_trial_not_adopted",
                             knobs_at=knobs_at, trial_evidence_id=trial.get("evidence_id"))


# --- Item 76: a term-cap raise that the time cap would stop ------------------

def _attempt_reach(row: dict[str, Any]) -> float | None:
    """Depth the attempt itself reached (before any item-76 floor)."""
    for key in ("attempt_verified_depth", "verified_depth", "depth"):
        v = _num(row.get(key))
        if v is not None:
            return v
    return None


def _time_rows(tid: str, log: dict[str, Any]) -> list[tuple[float, float]]:
    """(planned, seconds) of the latest rows where the time cap stopped ``tid`` short.

    ``seconds`` is the larger of the recorded time cap and the measured
    ``deep_elapsed_s`` (a lower bound on the time that depth needs).
    """
    from colony.oeis_conjectures import CAP_TIME
    out: list[tuple[float, float]] = []
    for row in reversed(_rows(tid, log)):
        if row.get("cap_reason") != CAP_TIME:
            continue
        planned = _num(row.get("planned"))
        reach = _attempt_reach(row)
        if not planned or planned <= 0 or (reach is not None and reach >= planned - 1):
            continue
        base = [x for x in (_num(row.get("cap_value")), _num(row.get("deep_elapsed_s"))) if x]
        if not base:
            continue
        out.append((planned, max(base)))
        if len(out) >= TIME_ROWS_RECENT:
            break
    return out


def _measured_time_rows(tid: str, log: dict[str, Any]) -> list[tuple[float, float]]:
    """Item 78: (planned, seconds) actually measured on series-path rows.

    A series attempt expands the whole planned length before any cap is
    applied, so ``deep_elapsed_s`` (recorded since item 76) is the time that
    planned depth took on the runner, whether or not the time cap fired.
    The latest few, newest first.
    """
    out: list[tuple[float, float]] = []
    for row in reversed(_rows(tid, log)):
        if row.get("fast_cfinite") is True:
            continue
        planned, secs = _num(row.get("planned")), _num(row.get("deep_elapsed_s"))
        if not planned or planned <= 0 or not secs or secs <= 0:
            continue
        out.append((planned, secs))
        if len(out) >= TIME_ROWS_RECENT:
            break
    return out


def time_points(tid: str, log: dict[str, Any]) -> list[tuple[float, float, float]]:
    """(planned, seconds, fit margin) for the time model of ``tid``.

    Measured rows (item 78) are exact, so they fit the budget without the
    safety margin; without them, the lower bounds from time-capped rows are
    used with TIME_FIT_MARGIN (item 76).
    """
    measured = _measured_time_rows(tid, log)
    if measured:
        return [(p, s, 1.0) for p, s in measured]
    return [(p, s, TIME_FIT_MARGIN) for p, s in _time_rows(tid, log)]


def time_needed(tid: str, knob: str, to: Any, *,
                attempt_log: dict[str, Any] | None = None) -> float | None:
    """Seconds ``tid`` is expected to need when ``knob`` (a term cap) goes to ``to``.

    From ``time_points``: measured series times when recorded (item 78),
    else rows where the time cap stopped the attempt short of its planned
    depth (the larger of the cap and any measured time), scaled by
    (to / planned)^TIME_COST_POWER (series cost grows about cubically in
    the number of terms). The largest estimate, or None without time
    evidence for this target.
    """
    log = _log(attempt_log)
    tk = term_knob_of(tid, log)
    if tk and tk != knob:
        return None
    goal = _num(to)
    if goal is None or goal <= 0:
        return None
    best: float | None = None
    for planned, secs, _margin in time_points(tid, log):
        need = secs * (goal / planned) ** TIME_COST_POWER
        best = need if best is None else max(best, need)
    return best


def fit_term_to_time(tid: str, knob: str, cur: Any, to: Any, seconds: Any, *,
                     attempt_log: dict[str, Any] | None = None) -> Any:
    """Largest term-cap value in (cur, to] whose expected time fits ``seconds``.

    Uses the same time-capped rows as ``time_needed`` with a safety margin.
    Returns ``to`` unchanged when it already fits or there is no time
    evidence, and None when no value above ``cur`` fits (the raise cannot
    escape the time cap within the second knob's bounds).
    """
    from colony.self_heal import clamp
    log = _log(attempt_log)
    goal, lo, budget = _num(to), _num(cur), _num(seconds)
    if goal is None or lo is None or budget is None or budget <= 0:
        return to
    need = time_needed(tid, knob, to, attempt_log=log)
    if need is None or need <= budget * min(m for _p, _s, m in time_points(tid, log)):
        return to
    limit = goal
    for planned, secs, margin in time_points(tid, log):
        limit = min(limit, planned * (budget * margin / secs) ** (1.0 / TIME_COST_POWER))
    val = clamp(knob, int(math.floor(limit)))
    if float(val) <= lo:
        return None
    return val


def time_risk_coupled(state: dict[str, Any], knob: str, cur: Any, to: Any,
                      predicted: list[str], *,
                      attempt_log: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Item 76 (b): turn a single term-cap raise into a coupled raise.

    When a predicted target already timed out at a smaller planned depth
    (or at this one) and the time it is expected to need at ``to`` is above
    the current ``deep_seconds``, the single raise would only re-hit the
    time cap (the gf 2865 -> 3975 trial). Return the ``coupled`` fields that
    also raise ``deep_seconds`` (scaled like the adopted coupled trial #9,
    at least the estimate, clamped to its KnobSpec bounds). None when there
    is no time risk, the second knob cannot rise, or the pair already failed
    for that target (item 74 retires it then). No-op on the control arm.
    """
    if not _self_mod():
        return None
    from colony.oeis_conjectures import TERM_CAP_KNOBS
    from colony.self_heal import KNOB_SPECS, clamp, state_knob
    other = "deep_seconds"
    if knob not in TERM_CAP_KNOBS or other not in KNOB_SPECS:
        return None
    log = _log(attempt_log)
    cur_o = state_knob(state, other)
    for tid in predicted or []:
        tid = str(tid)
        if compute_bound(state, tid):
            continue
        need = time_needed(tid, knob, to, attempt_log=log)
        if need is None or need <= float(cur_o):
            continue
        if coupled_already_failed(state, tid, knob, other) is not None:
            continue
        to_o = coupled_values(knob, cur, to, other, cur_o)
        if to_o is None:
            continue
        to_o = max(float(to_o), float(clamp(other, math.ceil(need * 10.0) / 10.0)))
        to_o = clamp(other, to_o)
        if float(to_o) <= float(cur_o):
            continue
        # Past the second knob's ceiling the full raise cannot fit: aim the
        # term cap at the largest value that does (None: nothing fits).
        term_to = fit_term_to_time(tid, knob, cur, to, to_o, attempt_log=log)
        if term_to is None:
            continue
        return {
            "term_to": term_to,
            "coupled": {"knob": other, "from": cur_o, "to": to_o, "direction": "up",
                        "cap_reason": "time_cap"},
            "coupled_time_risk": {"target": tid, "need_seconds": round(float(need), 2),
                                  "deep_seconds": cur_o, "term_cap_to": to,
                                  "term_cap_fit": term_to},
        }
    return None
