"""Items 72 and 73: cap-ladder diminishing returns, ceiling retirement, narrowing.

Tighten-only additions to self-heal. None of this touches the Oracle, the
P >= 0.70 gate, the 150 cap, the Hive Wilson gate, the 6-cycle windows, the
strictly-better rule, or Athanor math. Every entry point is a no-op on the
control arm (self-modification disabled).

- Item 73a: a cap knob whose value sits at its physical ceiling (its
  ``KnobSpec.hi``) is retired (append-only ``action_retired`` evidence), and
  findings stop suggesting it. A finding whose every binding knob is retired
  stops counting as a finding.
- Item 73b: under a flat (no-signal) baseline, exploratory trials with
  predicted targets already open and are judged on predicted-target depth
  gain (items 58/64, PR #25). The one thing that kept the colony stuck was the
  repeat guard: the same knob, value and targets already ended without
  credit. When that earlier trial was blocked because its predicted target hit
  a DIFFERENT cap (for example a time cap after a term-cap raise overshot the
  time budget), the knob is retried at the midpoint step instead (bounded),
  still judged strictly better over the full window.
- Item 72: once a knob has been adopted at least twice in a row on the same
  predicted targets with Oracle passes unchanged, a further adopt of that
  knob on those targets also needs marginal value: an Oracle pass delta, more
  new Oracle targets than the baseline, freed authored slots, or depth gain
  on a target outside the predicted set. Without it the trial closes
  ``inconclusive`` (reason ``diminishing_returns``), and the proposer tries
  other knobs/targets first.
"""
from __future__ import annotations

from typing import Any

LADDER_MIN_ADOPTS = 2
NARROW_MAX_DEPTH = 4
NARROW_MIN_FRACTION = 0.02  # stop halving below 2% of the knob's range


def _self_mod() -> bool:
    try:
        from colony.arm import self_mod_enabled
        return bool(self_mod_enabled())
    except Exception:
        return True


# --- 73a: retire cap knobs at their physical ceiling --------------------------

def ceiling_of(knob: str) -> int | float | None:
    from colony.self_heal import KNOB_SPECS, CAP_KNOBS
    if knob not in CAP_KNOBS or knob not in KNOB_SPECS:
        return None
    return KNOB_SPECS[knob].hi


def retire_ceiling_cap_knobs(state: dict[str, Any], cycle_id: str = "") -> list[dict[str, Any]]:
    """Record ``action_retired`` for cap knobs at their ceiling; un-retire when they move."""
    if not _self_mod():
        return []
    from colony.self_heal import CAP_KNOBS, append_evidence, state_knob
    retired = dict(state.get("retired_cap_knobs") or {})
    out: list[dict[str, Any]] = []
    for knob in CAP_KNOBS:
        hi = ceiling_of(knob)
        if hi is None:
            continue
        try:
            cur = state_knob(state, knob)
        except Exception:
            continue
        at_ceiling = float(cur) >= float(hi)
        if at_ceiling and knob not in retired:
            ev = append_evidence(state, {
                "event": "action_retired",
                "cycle_id": cycle_id,
                "knob": knob,
                "value": cur,
                "ceiling": hi,
                "reason": "at_physical_ceiling",
                "applied_to_live_oracle": False,
                "authorized": False,
            })
            retired[knob] = {"value": cur, "ceiling": hi, "cycle_id": cycle_id, "evidence_id": ev.get("id")}
            out.append(ev)
        elif not at_ceiling and knob in retired:
            retired.pop(knob, None)
    state["retired_cap_knobs"] = retired
    return out


def filter_retired_findings(findings: list[dict[str, Any]], state: dict[str, Any]) -> list[dict[str, Any]]:
    """Drop retired knobs from suggestions; drop a cap finding that only names retired knobs."""
    if not _self_mod():
        return list(findings or [])
    retired = set((state.get("retired_cap_knobs") or {}).keys())
    if not retired:
        return list(findings or [])
    out: list[dict[str, Any]] = []
    for f in findings or []:
        f = dict(f)
        sugg = [tuple(p) for p in (f.get("suggest") or [])]
        kept = [p for p in sugg if p[0] not in retired]
        if sugg and not kept and str(f.get("kind") or "") == "depth_at_physical_cap":
            continue  # every binding cap is at its physical ceiling
        if len(kept) != len(sugg):
            f["suggest"] = kept
            f["retired_suggestions"] = sorted({p[0] for p in sugg if p[0] in retired})
        out.append(f)
    return out


def retired_knob(state: dict[str, Any], knob: str) -> bool:
    return knob in (state.get("retired_cap_knobs") or {})


# --- 73b: narrow a repeat exploration that overshot into another cap ----------

def failed_exploration(state: dict[str, Any], knob: str, value: Any, predicted: list[str]) -> dict[str, Any] | None:
    """The close event of an earlier exploratory trial with this knob, value and targets."""
    for e in reversed(list(state.get("evidence") or [])):
        if not isinstance(e, dict) or e.get("event") not in ("trial_inconclusive", "revert"):
            continue
        if not e.get("exploratory") or str(e.get("knob") or "") != knob:
            continue
        try:
            same = float(e.get("from")) == float(value)
        except (TypeError, ValueError):
            same = False
        if same and sorted(e.get("predicted_targets") or []) == sorted(predicted):
            return e
    return None


def overshoot_cap(event: dict[str, Any], knob: str, *, attempt_log: dict[str, Any] | None = None) -> str:
    """Cap reason, bound to a different knob, that held a predicted target during that trial."""
    cycles = {str(event.get("started_cycle") or "")}
    cycles |= {str(r.get("cycle_id") or "") for r in (event.get("trial_metrics") or []) if isinstance(r, dict)}
    cycles.discard("")
    predicted = {str(x) for x in (event.get("predicted_targets") or []) if x}
    if not cycles or not predicted:
        return ""
    try:
        from colony.oeis_conjectures import load_attempt_log, cap_of_row, knobs_for_cap_reason
        log = attempt_log if attempt_log is not None else load_attempt_log()
    except Exception:
        return ""
    for row in list(log.get("attempts") or []):
        if not isinstance(row, dict):
            continue
        if str(row.get("id") or "") not in predicted or str(row.get("cycle_id") or "") not in cycles:
            continue
        if row.get("status") != "holds_on_range":
            continue
        try:
            reason, _v = cap_of_row(row, None)
            if reason and knob not in knobs_for_cap_reason(reason, row=row):
                return str(reason)
        except Exception:
            continue
    return ""


def narrower_after_overshoot(
    state: dict[str, Any],
    knob: str,
    current: Any,
    failed_value: Any,
    predicted: list[str],
    *,
    predict=None,
    attempt_log: dict[str, Any] | None = None,
) -> tuple[Any, list[str], str] | None:
    """Midpoint step when the same exploration failed by overshooting into another cap.

    Returns ``(value, predicted_targets, cap_reason)`` or None. Bounded by
    NARROW_MAX_DEPTH halvings and NARROW_MIN_FRACTION of the knob's range.
    """
    if not _self_mod():
        return None
    from colony.self_heal import KNOB_SPECS, _cast, predicted_new_targets
    spec = KNOB_SPECS.get(knob)
    if spec is None:
        return None
    predict = predict or predicted_new_targets
    lo_step = float(spec.hi - spec.lo) * NARROW_MIN_FRACTION
    hi_val, preds = failed_value, list(predicted)
    for _ in range(NARROW_MAX_DEPTH):
        ev = failed_exploration(state, knob, hi_val, preds)
        if ev is None:
            return None
        why = overshoot_cap(ev, knob, attempt_log=attempt_log)
        if not why:
            return None
        try:
            gap = float(hi_val) - float(current)
        except (TypeError, ValueError):
            return None
        if gap <= lo_step:
            return None
        mid = _cast(spec, float(current) + gap / 2.0)
        if not (float(current) < float(mid) < float(hi_val)):
            return None
        new_preds = list(predict(knob, mid) or [])
        if not new_preds:
            return None
        if failed_exploration(state, knob, mid, new_preds) is None:
            return mid, new_preds, why
        hi_val, preds = mid, new_preds
    return None


# --- 72: cap-ladder diminishing returns ---------------------------------------

def _passes(rows) -> list[int]:
    out = []
    for r in rows or []:
        if isinstance(r, dict) and r.get("oracle_passes") is not None:
            try:
                out.append(int(r["oracle_passes"]))
            except (TypeError, ValueError):
                continue
    return out


def ladder_state(state: dict[str, Any], knob: str, predicted: list[str],
                 trial: dict[str, Any] | None = None) -> dict[str, Any]:
    """Consecutive adopts of ``knob`` on ``predicted`` with Oracle passes unchanged."""
    targets = sorted({str(x) for x in (predicted or []) if x})
    out = {"active": False, "adopts": 0, "passes_flat": False, "knob": knob, "targets": targets}
    if not targets or not knob:
        return out
    run: list[dict[str, Any]] = []
    for e in reversed(list(state.get("evidence") or [])):
        if not isinstance(e, dict) or e.get("event") != "adopt":
            continue
        same = str(e.get("knob") or "") == knob and sorted(e.get("predicted_targets") or []) == targets
        if not same:
            break
        run.append(e)
    out["adopts"] = len(run)
    if len(run) < LADDER_MIN_ADOPTS:
        return out
    passes: list[int] = []
    for e in run:
        passes += _passes(e.get("baseline_metrics")) + _passes(e.get("trial_metrics"))
    if trial:
        passes += _passes(trial.get("baseline_metrics")) + _passes(trial.get("trial_metrics"))
    out["passes_flat"] = bool(passes) and min(passes) == max(passes)
    out["active"] = out["passes_flat"]
    return out


def snapshot_marginal_baseline(trial: dict[str, Any]) -> None:
    """At trial start: authored count and every target's official depth."""
    try:
        from colony.authoring import authored_count
        trial["authored_at_start"] = int(authored_count())
    except Exception:
        pass
    try:
        from colony.self_heal_score import official_target_depths
        trial["target_depths_at_start"] = {k: int(v) for k, v in official_target_depths().items()}
    except Exception:
        pass


def marginal_value(trial: dict[str, Any], *, authored_now: int | None = None,
                   depths_now: dict[str, int] | None = None) -> list[str]:
    """Reasons this trial added value beyond climbing its own predicted targets."""
    reasons: list[str] = []
    rows = [r for r in (trial.get("trial_metrics") or []) if isinstance(r, dict)]
    base = [r for r in (trial.get("baseline_metrics") or []) if isinstance(r, dict)]
    if any(int(r.get("oracle_pass_delta") or 0) > 0 for r in rows):
        reasons.append("oracle_pass_delta")
    if sum(int(r.get("new_oracle_targets") or 0) for r in rows) > sum(int(r.get("new_oracle_targets") or 0) for r in base):
        reasons.append("new_oracle_targets")
    start_n = trial.get("authored_at_start")
    if start_n is not None:
        if authored_now is None:
            try:
                from colony.authoring import authored_count
                authored_now = int(authored_count())
            except Exception:
                authored_now = None
        if authored_now is not None and int(authored_now) < int(start_n):
            reasons.append("freed_slots")
    start_depths = trial.get("target_depths_at_start")
    if isinstance(start_depths, dict):
        if depths_now is None:
            try:
                from colony.self_heal_score import official_target_depths
                depths_now = official_target_depths()
            except Exception:
                depths_now = {}
        predicted = {str(x) for x in (trial.get("predicted_targets") or [])}
        for tid, d in (depths_now or {}).items():
            if tid in predicted:
                continue
            if int(d or 0) > int(start_depths.get(tid) or 0):
                reasons.append("second_target_depth")
                break
    return reasons


def apply_diminishing_returns(state: dict[str, Any], trial: dict[str, Any], decision: str,
                              reason: str | None) -> tuple[str, str | None]:
    """Tighten-only: an adopt on an active ladder without marginal value becomes inconclusive."""
    if decision != "adopt" or not _self_mod():
        return decision, reason
    lad = ladder_state(state, str(trial.get("knob") or ""), list(trial.get("predicted_targets") or []), trial)
    if not lad["active"]:
        return decision, reason
    mv = marginal_value(trial)
    trial["ladder"] = {**lad, "marginal_value": mv}
    if mv:
        return decision, reason
    return "inconclusive", "diminishing_returns"
