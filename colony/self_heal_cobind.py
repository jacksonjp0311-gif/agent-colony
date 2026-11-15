"""Item 77: co-binding caps. Simulate pairwise / triple cap raises as one trial.

A126089 at depth 2864 is held by two caps at once: gf_term_cap 2865 (depth
cap-1) and the 10400-digit cap (binds near n=2875). Raising either alone
gains about 10 terms or none, so every single-knob prediction is empty
and self-heal skips no_signal_baseline cycle after cycle.

- ``simulate``: for one target, predict the depth reached under candidate
  values of its term cap, ``deep_digits`` and ``deep_seconds`` from its own
  attempt rows: term cap -> depth cap-1; digit cap -> the digit-growth
  model fitted to its recent digit-capped rows (digits ~ a*n, with the
  slope's own growth); time cap -> the item-76 cubic estimate from recent
  time-capped rows. Every subset of those knobs is tried. Retired knobs,
  knobs on cooldown and knobs at their KnobSpec ceiling are left out, and
  every value is clamped to its KnobSpec bounds.
- ``cobind_proposal``: when every single-knob raise gains a negligible
  amount for a recent target, the best multi-knob raise (strictly larger
  predicted gain, above the negligible bar) is proposed as ONE coupled
  trial: the term knob is the trial knob, the second knob is ``coupled``
  and a third goes in ``coupled_more``. All of them apply together, share
  one fingerprint and revert together. Same slot, 6-cycle window and
  strictly-better rule; a combination that already failed for a target is
  not repeated (item 74 retires the target as compute_bound then).
- ``note_zero_prediction_skip``: after ZERO_PREDICTION_STREAK consecutive
  skips where every explored candidate predicted no target, one
  append-only ``co_binding_caps`` finding names each target and the caps
  binding it, so the stall shows a cause instead of a flat baseline.

Tighten-only: the Oracle, P >= 0.70, the 150 cap, Wilson, windows,
strictly-better, the triviality filter and Athanor are untouched. Every
entry point is a no-op on the control arm.
"""
from __future__ import annotations

import itertools
import math
from typing import Any, Callable

DIGIT_KNOB = "deep_digits"
TIME_KNOB = "deep_seconds"
DIGIT_ROWS_RECENT = 3
DIGIT_MARGIN = 1.01           # digit budget sized 1% above the modelled need
NEGLIGIBLE_MIN_GAIN = 25      # terms
NEGLIGIBLE_FRACTION = 0.01    # of the current depth
ZERO_PREDICTION_STREAK = 6
LOOKBACK_EVENTS = 40
CLOSED_FAIL = ("trial_inconclusive", "revert")
INF = float("inf")


def _self_mod() -> bool:
    try:
        from colony.arm import self_mod_enabled
        return bool(self_mod_enabled())
    except Exception:
        return True


def _num(x: Any) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def negligible_gain(depth: float) -> float:
    return max(float(NEGLIGIBLE_MIN_GAIN), NEGLIGIBLE_FRACTION * float(depth or 0))


# --- target evidence -----------------------------------------------------------

def current_depth(tid: str, log: dict[str, Any]) -> int:
    from colony.self_heal_coupled import _rows
    best = 0
    for r in _rows(tid, log):
        v = _num(r.get("verified_depth"))
        if v is None:
            v = _num(r.get("depth"))
        if v is not None:
            best = max(best, int(v))
    return best


def digit_points(tid: str, log: dict[str, Any]) -> list[tuple[float, float]]:
    """(n, digits) where the digit cap stopped ``tid``: the latest few, by n."""
    from colony.oeis_conjectures import CAP_DIGIT
    from colony.self_heal_coupled import _attempt_reach, _rows
    pts: dict[float, float] = {}
    for r in reversed(_rows(tid, log)):
        if r.get("cap_reason") != CAP_DIGIT:
            continue
        n, d = _attempt_reach(r), _num(r.get("cap_value"))
        if not n or not d or n <= 0 or d <= 0 or n in pts:
            continue
        pts[n] = d
        if len(pts) >= DIGIT_ROWS_RECENT:
            break
    return sorted(pts.items())


class DigitModel:
    """digits(n) from recent digit-capped rows, anchored at the latest point.

    One point: digits ~ a*n. Two: the local slope. Three: the slope plus
    its growth per term (terms of an e.g.f. grow like n!, so digits per
    term rise slowly with n). Growth is never negative.
    """

    def __init__(self, pts: list[tuple[float, float]]):
        self.pts = list(pts)
        n2, d2 = pts[-1]
        self.n0, self.d0 = n2, d2
        if len(pts) == 1:
            self.slope, self.curv = d2 / n2, 0.0
        else:
            n1, d1 = pts[-2]
            self.slope = (d2 - d1) / max(1.0, n2 - n1)
            self.curv = 0.0
            if len(pts) >= 3:
                n0, d0 = pts[-3]
                s0 = (d1 - d0) / max(1.0, n1 - n0)
                mid = max(1.0, (n2 - n0) / 2.0)
                self.curv = max(0.0, (self.slope - s0) / mid)
            # the local slope is measured at the middle of the last gap
            self.slope = self.slope + self.curv * (n2 - n1) / 2.0
        self.slope = max(self.slope, 1e-6)

    def digits_at(self, n: float) -> float:
        x = float(n) - self.n0
        return self.d0 + self.slope * x + 0.5 * self.curv * x * x

    def n_at(self, digits: float) -> float:
        y = float(digits) - self.d0
        if self.curv <= 0:
            return self.n0 + y / self.slope
        a, b = 0.5 * self.curv, self.slope
        disc = b * b + 4 * a * y
        if disc < 0:
            return self.n0
        return self.n0 + (-b + math.sqrt(disc)) / (2 * a)

    def summary(self) -> dict[str, Any]:
        return {"points": [[int(n), int(d)] for n, d in self.pts],
                "digits_per_term": round(self.slope, 4), "slope_growth": round(self.curv, 8)}


def digit_model(tid: str, log: dict[str, Any]) -> DigitModel | None:
    pts = digit_points(tid, log)
    return DigitModel(pts) if pts else None


def time_limit(tid: str, seconds: float, log: dict[str, Any]) -> float:
    """Deepest n expected to fit ``seconds`` (item-76 rows); inf without time evidence."""
    from colony.self_heal_coupled import TIME_COST_POWER, time_points
    lim = INF
    for planned, secs, margin in time_points(tid, log):
        lim = min(lim, planned * (float(seconds) * margin / secs) ** (1.0 / TIME_COST_POWER))
    return lim


def reach(tid: str, term_cap: float, digits: float, seconds: float, log: dict[str, Any],
          model: DigitModel | None = None) -> dict[str, float]:
    m = model if model is not None else digit_model(tid, log)
    limits = {
        "term_cap": float(term_cap) - 1,
        "digit_cap": m.n_at(digits) if m is not None else INF,
        "time_cap": time_limit(tid, seconds, log),
    }
    limits["reach"] = min(limits.values())
    return limits


def binding_caps(tid: str, knobs: dict[str, Any], log: dict[str, Any], term_knob: str) -> list[str]:
    """Caps whose predicted limit sits within the negligible margin of the current depth."""
    depth = current_depth(tid, log)
    lim = reach(tid, knobs.get(term_knob, 0), knobs.get(DIGIT_KNOB, 0), knobs.get(TIME_KNOB, 0), log)
    bar = depth + negligible_gain(depth)
    return [k for k in ("term_cap", "digit_cap", "time_cap") if lim[k] <= bar]


# --- simulation ----------------------------------------------------------------

def _usable(state: dict[str, Any], knob: str) -> bool:
    from colony.self_heal import KNOB_SPECS, _knob_on_cooldown, state_knob
    from colony.self_heal_ladder import retired_knob
    if knob not in KNOB_SPECS or retired_knob(state, knob):
        return False
    if _knob_on_cooldown(state, knob, "up"):
        return False
    return float(state_knob(state, knob)) < float(KNOB_SPECS[knob].hi)


def _term_target(state: dict[str, Any], knob: str, cur: Any) -> Any:
    from colony.self_heal import frontier_cap_value, state_knob, stepped_value
    try:
        nv = frontier_cap_value(knob, "up", current=cur, step_size=float(state_knob(state, "step_size")))
    except Exception:
        nv = None
    if nv is None:
        nv = stepped_value(knob, "up", current=cur)
    return nv


def simulate(state: dict[str, Any], tid: str, *, attempt_log: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Predicted depth for every usable subset of {term cap, deep_digits, deep_seconds}."""
    from colony.self_heal import KNOB_SPECS, clamp, state_knob, stepped_value
    from colony.self_heal_coupled import _log, term_knob_of, time_needed
    log = _log(attempt_log)
    tk = term_knob_of(tid, log)
    if not tk:
        return None
    model = digit_model(tid, log)
    depth = current_depth(tid, log)
    cur = {k: state_knob(state, k) for k in (tk, DIGIT_KNOB, TIME_KNOB)}
    base = reach(tid, cur[tk], cur[DIGIT_KNOB], cur[TIME_KNOB], log, model)
    usable = [k for k in (tk, DIGIT_KNOB, TIME_KNOB) if _usable(state, k)]
    g_goal = _term_target(state, tk, cur[tk]) if tk in usable else None
    out: list[dict[str, Any]] = []
    for size in (1, 2, 3):
        for combo in itertools.combinations(usable, size):
            vals = dict(cur)
            if TIME_KNOB in combo:
                need = time_needed(tid, tk, g_goal, attempt_log=log) if (tk in combo and g_goal) else None
                step = stepped_value(TIME_KNOB, "up", current=cur[TIME_KNOB])
                want = max(float(step or cur[TIME_KNOB]), float(need or 0.0))
                vals[TIME_KNOB] = clamp(TIME_KNOB, math.ceil(want * 10.0) / 10.0)
            if tk in combo:
                if g_goal is None:
                    continue
                g = float(g_goal)
                # A raise the time budget cannot cover is narrowed to fit it.
                g = min(g, math.floor(time_limit(tid, vals[TIME_KNOB], log)) + 1)
                vals[tk] = clamp(tk, int(g))
            if DIGIT_KNOB in combo:
                if model is not None and tk in combo:
                    # Sized from observed digit growth so the new term cap is reachable.
                    want = math.ceil(model.digits_at(float(vals[tk]) - 1) * DIGIT_MARGIN)
                else:
                    want = stepped_value(DIGIT_KNOB, "up", current=cur[DIGIT_KNOB]) or cur[DIGIT_KNOB]
                vals[DIGIT_KNOB] = clamp(DIGIT_KNOB, int(want))
            if any(float(vals[k]) <= float(cur[k]) for k in combo):
                continue
            lim = reach(tid, vals[tk], vals[DIGIT_KNOB], vals[TIME_KNOB], log, model)
            r = lim["reach"]
            gain = (r - depth) if math.isfinite(r) else 0.0
            out.append({"knobs": list(combo), "values": {k: vals[k] for k in combo},
                        "reach": None if not math.isfinite(r) else int(r),
                        "gain": int(max(0.0, gain)),
                        "limits": {k: (None if not math.isfinite(v) else int(v))
                                   for k, v in lim.items() if k != "reach"}})
    return {
        "target": tid, "term_knob": tk, "depth": depth, "current": cur,
        "current_limits": {k: (None if not math.isfinite(v) else int(v)) for k, v in base.items()},
        "binding_now": binding_caps(tid, cur, log, tk),
        "digit_model": model.summary() if model is not None else None,
        "candidates": out,
        "spec_hi": {k: KNOB_SPECS[k].hi for k in cur},
    }


def _combo_failed(state: dict[str, Any], tid: str, knobs: list[str]) -> bool:
    want = set(knobs)
    for e in reversed(list(state.get("evidence") or [])):
        if not isinstance(e, dict) or e.get("event") not in CLOSED_FAIL:
            continue
        if tid not in (e.get("predicted_targets") or []):
            continue
        got = {str(e.get("knob") or "")}
        for c in [e.get("coupled") or {}] + list(e.get("coupled_more") or []):
            if isinstance(c, dict) and c.get("knob"):
                got.add(str(c["knob"]))
        if got == want:
            return True
    return False


def recent_targets(state: dict[str, Any]) -> list[str]:
    from colony.self_heal import CAP_KNOBS
    out: list[str] = []
    for e in reversed(list(state.get("evidence") or [])[-LOOKBACK_EVENTS:]):
        if isinstance(e, dict) and str(e.get("knob") or "") in CAP_KNOBS:
            for t in e.get("predicted_targets") or []:
                if t and str(t) not in out:
                    out.append(str(t))
    return out


def cobind_proposal(state: dict[str, Any], targets: list[str] | None = None, *,
                    attempt_log: dict[str, Any] | None = None,
                    eligible: Callable[[], set[str]] | None = None) -> dict[str, Any] | None:
    """One coupled trial over co-binding caps, or None. Fields for propose_trial to complete."""
    if not _self_mod():
        return None
    from colony.oeis_conjectures import cap_override
    from colony.self_heal_coupled import _log, compute_bound
    log = _log(attempt_log)
    if eligible is None:
        from colony.self_heal import eligible_target_ids as eligible
    for tid in (targets if targets is not None else recent_targets(state)):
        if compute_bound(state, tid):
            continue
        sim = simulate(state, tid, attempt_log=log)
        if not sim or sim.get("digit_model") is None:
            continue  # without digit evidence, items 74/76 cover term + time
        bar = negligible_gain(sim["depth"])
        singles = [c for c in sim["candidates"] if len(c["knobs"]) == 1]
        best_single = max([c["gain"] for c in singles] or [0])
        if best_single >= bar:
            continue  # a single-knob trial can already move this target
        multi = [c for c in sim["candidates"] if len(c["knobs"]) >= 2
                 and c["gain"] >= bar and c["gain"] > best_single
                 and not _combo_failed(state, tid, c["knobs"])]
        if not multi:
            continue
        # Largest predicted gain; on a tie, fewer knobs.
        multi.sort(key=lambda c: (-c["gain"], len(c["knobs"])))
        best = multi[0]
        order = [k for k in (sim["term_knob"], DIGIT_KNOB, TIME_KNOB) if k in best["knobs"]]
        try:
            import contextlib
            with contextlib.ExitStack() as stack:
                for k in order:
                    stack.enter_context(cap_override(k, best["values"][k]))
                ok = tid in set(eligible())
        except Exception:
            ok = False
        if not ok:
            continue
        cur = sim["current"]
        reasons = {sim["term_knob"]: "term_cap", DIGIT_KNOB: "digit_cap", TIME_KNOB: "time_cap"}

        def _part(k: str) -> dict[str, Any]:
            return {"knob": k, "from": cur[k], "to": best["values"][k], "direction": "up",
                    "cap_reason": reasons[k]}
        first, rest = order[0], order[1:]
        return {
            "knob": first, "from": cur[first], "to": best["values"][first], "direction": "up",
            "coupled": _part(rest[0]),
            **({"coupled_more": [_part(k) for k in rest[1:]]} if len(rest) > 1 else {}),
            "cobind": {"target": tid, "depth": sim["depth"], "predicted_reach": best["reach"],
                       "predicted_gain": best["gain"], "best_single_gain": best_single,
                       "binding_now": sim["binding_now"], "limits": best["limits"],
                       "digit_model": sim["digit_model"]},
            "exploratory": True,
            "predicted_targets": [tid],
        }
    return None


# --- (3) co_binding_caps finding -------------------------------------------------

def note_zero_prediction_skip(state: dict[str, Any], cycle_id: str,
                              explore_checked: list[dict[str, Any]], *,
                              attempt_log: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Count consecutive all-zero-prediction skips; log one finding at the threshold."""
    if not _self_mod():
        return None
    from colony.self_heal import append_evidence
    from colony.self_heal_coupled import _log, term_knob_of
    # Item 78: a candidate skipped as co-binding (negligible gain) counts as zero.
    all_zero = bool(explore_checked) and all(
        not (c.get("predicted") or []) or c.get("skipped") == "co_binding_caps" for c in explore_checked)
    streak = dict(state.get("zero_prediction_skips") or {})
    if not all_zero:
        state["zero_prediction_skips"] = {"count": 0}
        return None
    if not streak.get("count"):
        streak = {"count": 0, "first_cycle": cycle_id}
    streak["count"] = int(streak.get("count") or 0) + 1
    streak["last_cycle"] = cycle_id
    state["zero_prediction_skips"] = streak
    if streak["count"] < ZERO_PREDICTION_STREAK or streak.get("finding_id"):
        return None
    log = _log(attempt_log)
    knobs = dict(state.get("knobs") or {})
    named: list[dict[str, Any]] = []
    for tid in recent_targets(state):
        tk = term_knob_of(tid, log)
        if not tk:
            continue
        caps = binding_caps(tid, knobs, log, tk)
        if len(caps) >= 2:
            named.append({"target": tid, "binding_caps": caps, "depth": current_depth(tid, log),
                          "knobs": {k: knobs.get(k) for k in (tk, DIGIT_KNOB, TIME_KNOB)}})
    if not named:
        return None
    ev = append_evidence(state, {
        "event": "finding",
        "kind": "co_binding_caps",
        "cycle_id": cycle_id,
        "targets": named,
        "zero_prediction_skips": streak["count"],
        "first_cycle": streak.get("first_cycle"),
        "applied_to_live_oracle": False,
        "authorized": False,
    })
    streak["finding_id"] = ev.get("id")
    state["zero_prediction_skips"] = streak
    state["co_binding_caps"] = {"cycle_id": cycle_id, "targets": named, "evidence_id": ev.get("id")}
    return ev


# --- Item 78: the cobind check in front of every cap trial -------------------

def step_gain(state: dict[str, Any], tid: str, values: dict[str, Any], *,
              attempt_log: dict[str, Any] | None = None) -> int | None:
    """Predicted depth gain on ``tid`` if the cap knobs in ``values`` take those values.

    None when the target has no term-cap evidence or ``values`` names no
    cap that limits it (then this check has nothing to say).
    """
    from colony.self_heal import state_knob
    from colony.self_heal_coupled import _log, term_knob_of
    log = _log(attempt_log)
    tk = term_knob_of(tid, log)
    if not tk:
        return None
    names = (tk, DIGIT_KNOB, TIME_KNOB)
    if not any(k in values for k in names):
        return None
    vals = {k: (values[k] if k in values else state_knob(state, k)) for k in names}
    lim = reach(tid, vals[tk], vals[DIGIT_KNOB], vals[TIME_KNOB], log)
    r = lim["reach"]
    if not math.isfinite(r):
        return None
    return int(max(0.0, r - current_depth(tid, log)))


def trial_values(trial: dict[str, Any]) -> dict[str, Any]:
    """Knob -> value for a proposed trial (single or coupled)."""
    out: dict[str, Any] = {}
    if trial.get("knob"):
        out[str(trial["knob"])] = trial.get("to")
    for c in [trial.get("coupled")] + list(trial.get("coupled_more") or []):
        if isinstance(c, dict) and c.get("knob"):
            out[str(c["knob"])] = c.get("to")
    return out


def negligible_step(state: dict[str, Any], values: dict[str, Any], predicted: list[str], *,
                    attempt_log: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Item 78 (1): None when the step is worth a trial, else why it is not.

    Every predicted target the cobind model knows gains less than the
    item-77 negligible bar under these knob values, because other caps bind
    with it. A target the model cannot judge never blocks the step.
    """
    if not _self_mod() or not predicted:
        return None
    from colony.self_heal_coupled import _log
    log = _log(attempt_log)
    gains: dict[str, int] = {}
    for tid in predicted:
        g = step_gain(state, str(tid), values, attempt_log=log)
        if g is None:
            return None
        if g >= negligible_gain(current_depth(str(tid), log)):
            return None
        gains[str(tid)] = g
    return {"skipped": "co_binding_caps", "predicted_gain": gains}


def retire_time_bound(state: dict[str, Any], targets: list[str], *, cycle_id: str,
                      attempt_log: dict[str, Any] | None = None) -> list[str]:
    """Item 78 (2): time binds at the deep_seconds ceiling for the next useful step.

    With ``deep_seconds`` at its KnobSpec ceiling, a target whose modelled
    time limit at that ceiling is below depth + the negligible bar cannot be
    moved by any cap raise: it is retired as compute_bound (item 74,
    append-only ``target_retired``), so the proposer moves on. It returns
    only if deep_seconds ever rises above the ceiling value.
    """
    if not _self_mod():
        return []
    from colony.self_heal import KNOB_SPECS, state_knob
    from colony.self_heal_coupled import _log, compute_bound, retire_compute_bound, term_knob_of, time_points
    log = _log(attempt_log)
    hi = float(KNOB_SPECS[TIME_KNOB].hi)
    cur = float(state_knob(state, TIME_KNOB))
    if cur < hi:
        return []
    out: list[str] = []
    for tid in targets or []:
        tid = str(tid)
        if compute_bound(state, tid) or not term_knob_of(tid, log) or not time_points(tid, log):
            continue
        depth = current_depth(tid, log)
        lim = time_limit(tid, hi, log)
        if not math.isfinite(lim) or lim >= depth + negligible_gain(depth):
            continue
        ev = retire_compute_bound(state, tid, cycle_id=cycle_id, why="time_cap_at_deep_seconds_ceiling",
                                  knobs_at={TIME_KNOB: cur})
        if ev is not None:
            out.append(tid)
    return out
