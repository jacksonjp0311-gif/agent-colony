"""Trial scoring and crediting only.

These functions decide how an already-recorded trial is scored: verified
depth on predicted targets (item 64), background-tie inconclusive closes
(item 65), and a rescore of recorded per-cycle facts after a scoring-only
change (item 62). They do not apply knobs, open trials, or touch the
Oracle, Athanor, or Hive's Wilson gate.

``colony/self_heal_score.py`` is excluded from the behavior fingerprint,
so a merge that changes only this file does not void an open trial. The
open trial is re-scored from its recorded facts under the new code.
A change to knob behavior, caps, or other evolve-loop modules still
voids the trial.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping


def _int(row: Mapping[str, Any] | None, key: str, default: int = 0) -> int:
    if not isinstance(row, Mapping):
        return default
    try:
        return int(row.get(key) or default)
    except (TypeError, ValueError):
        return default


def _float(row: Mapping[str, Any] | None, key: str, default: float = 0.0) -> float:
    if not isinstance(row, Mapping):
        return default
    try:
        return float(row.get(key) or default)
    except (TypeError, ValueError):
        return default


def trial_activity_rows(trial: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Trial-window metric rows, including post-apply surplus in the start cycle."""
    if not isinstance(trial, dict):
        return []
    rows = [r for r in (trial.get("trial_metrics") or []) if isinstance(r, dict)]
    extra = trial.get("apply_cycle_metrics")
    if isinstance(extra, dict):
        rows = rows + [extra]
    return rows


def row_has_bearing_signal(row: Mapping[str, Any] | None) -> bool:
    """True if the row moved verified depth or the Oracle pass total.

    ``new_oracle_targets`` is the periodic supply alternation (1,0,1,0)
    that has been summing every 6-cycle window to 3.0. It is not a
    signal a knob can honestly win on.
    """
    if not isinstance(row, Mapping):
        return False
    return _int(row, "new_depth") != 0 or _int(row, "oracle_pass_delta") != 0


def window_has_bearing_signal(rows: Iterable[dict[str, Any]] | None) -> bool:
    return any(row_has_bearing_signal(r) for r in list(rows or []))


def windows_are_background_only(trial: dict[str, Any] | None) -> bool:
    """Both windows' scores come only from periodic background activity."""
    if not isinstance(trial, dict):
        return False
    baseline = [r for r in (trial.get("baseline_metrics") or []) if isinstance(r, dict)]
    trial_rows = trial_activity_rows(trial)
    if not baseline or not trial_rows:
        return False
    return (not window_has_bearing_signal(baseline)) and (not window_has_bearing_signal(trial_rows))


def official_target_depths(
    *,
    extensions: Mapping[str, Any] | None = None,
    attempt_log: Mapping[str, Any] | None = None,
) -> dict[str, int]:
    """Best known verified depth by target id (scoreboard, then attempt log)."""
    out: dict[str, int] = {}
    ext = extensions
    if ext is None:
        try:
            from colony.oeis_conjectures import STATE, _load
            state = _load(STATE, {}) or {}
            board = state.get("scoreboard") if isinstance(state, dict) else {}
            ext = (board or {}).get("extensions") or {}
        except Exception:
            ext = {}
    if isinstance(ext, Mapping):
        for eid, rec in ext.items():
            if not eid or not isinstance(rec, dict):
                continue
            try:
                to = int(rec.get("to") or 0)
            except (TypeError, ValueError):
                to = 0
            if to > 0:
                out[str(eid)] = to
    log = attempt_log
    if log is None:
        try:
            from colony.oeis_conjectures import load_attempt_log
            log = load_attempt_log()
        except Exception:
            log = None
    if isinstance(log, Mapping):
        from colony.self_heal import _row_verified_for_metric
        for a in list(log.get("attempts") or []):
            if not isinstance(a, dict):
                continue
            eid = str(a.get("id") or "")
            if not eid:
                continue
            v = _row_verified_for_metric(a, 0)
            if v > out.get(eid, 0):
                out[eid] = v
    return out


def snapshot_pre_trial_depths(
    target_ids: Iterable[str],
    *,
    extensions: Mapping[str, Any] | None = None,
    attempt_log: Mapping[str, Any] | None = None,
) -> dict[str, int]:
    """Record official verified depth of each predicted target at trial start."""
    current = official_target_depths(extensions=extensions, attempt_log=attempt_log)
    out: dict[str, int] = {}
    for tid in target_ids:
        name = str(tid or "")
        if name:
            out[name] = int(current.get(name) or 0)
    return out


def predicted_depth_gain(
    trial: dict[str, Any] | None,
    *,
    extensions: Mapping[str, Any] | None = None,
    attempt_log: Mapping[str, Any] | None = None,
    current_depths: Mapping[str, int] | None = None,
) -> tuple[int, dict[str, int]]:
    """Sum of (current − pre-trial) verified depth on predicted targets.

    Returns ``(0, {})`` when the trial names no predicted targets.
    """
    if not isinstance(trial, dict):
        return 0, {}
    predicted = [str(x) for x in (trial.get("predicted_targets") or []) if x]
    if not predicted:
        return 0, {}
    pre = trial.get("pre_trial_depths") if isinstance(trial.get("pre_trial_depths"), dict) else {}
    if current_depths is None:
        current_depths = official_target_depths(extensions=extensions, attempt_log=attempt_log)
    now: dict[str, int] = {}
    gain = 0
    for tid in predicted:
        before = _int(pre, tid, 0)
        after = int(current_depths.get(tid) or 0)
        now[tid] = after
        gain += after - before
    return int(gain), now


def refresh_trial_scores(
    trial: dict[str, Any] | None,
    *,
    extensions: Mapping[str, Any] | None = None,
    attempt_log: Mapping[str, Any] | None = None,
    current_depths: Mapping[str, int] | None = None,
) -> dict[str, Any] | None:
    """Recompute depth-gain and activity fields from recorded facts. In-place."""
    if not isinstance(trial, dict):
        return trial
    from colony.self_heal import trial_comparison_score, window_score

    trial["activity_score"] = trial_comparison_score(trial)
    try:
        trial["baseline_activity_score"] = window_score(trial.get("baseline_metrics") or [])
    except Exception:
        trial["baseline_activity_score"] = _float(trial, "baseline_score", 0.0)
    if trial.get("predicted_targets"):
        gain, now = predicted_depth_gain(
            trial,
            extensions=extensions,
            attempt_log=attempt_log,
            current_depths=current_depths,
        )
        trial["predicted_depth_gain"] = gain
        trial["current_depths"] = now
    return trial


def decide_trial_close(
    trial: dict[str, Any] | None,
    *,
    extensions: Mapping[str, Any] | None = None,
    attempt_log: Mapping[str, Any] | None = None,
    current_depths: Mapping[str, int] | None = None,
) -> tuple[str, str | None]:
    """Return ``(decision, reason)`` for a trial whose window is already full.

    When the trial names predicted targets, verified-depth gain on those
    targets versus pre-trial depth is the primary score. Other activity
    is only a tiebreaker. The strictly-better rule is unchanged: adopt
    needs a strictly higher primary score, or a strictly higher
    tiebreaker when the primary is tied.

    Identical activity scores driven only by periodic background
    activity (the 1,0,1,0 ``new_oracle_targets`` pattern, no depth or
    pass-delta) close as ``inconclusive``, not ``revert``.
    """
    from colony.self_heal import (
        attributable_progress,
        trial_comparison_score,
        trial_is_no_signal,
        window_score,
    )

    if not isinstance(trial, dict):
        return "revert", None
    refresh_trial_scores(
        trial,
        extensions=extensions,
        attempt_log=attempt_log,
        current_depths=current_depths,
    )
    activity = float(trial.get("activity_score") or trial_comparison_score(trial) or 0)
    baseline_activity = float(
        trial.get("baseline_activity_score")
        if trial.get("baseline_activity_score") is not None
        else window_score(trial.get("baseline_metrics") or [])
    )
    predicted = [str(x) for x in (trial.get("predicted_targets") or []) if x]
    background_tie = (
        windows_are_background_only(trial)
        and activity == baseline_activity
    )

    if predicted:
        gain = int(trial.get("predicted_depth_gain") or 0)
        if gain > 0:
            if trial.get("exploratory") and not attributable_progress(trial):
                return "inconclusive", "signal_not_attributable"
            return "adopt", None
        if gain < 0:
            return "revert", None
        # Primary tied (no depth gain). Tiebreaker is the activity score.
        # Item 58: all-zero windows stay "no_signal". Item 65: a
        # nonzero 3.0-vs-3.0 (or other) tie driven only by the
        # periodic supply pattern is "no_variance", not a revert.
        if trial_is_no_signal(trial):
            return "inconclusive", "no_signal"
        if background_tie and activity == baseline_activity and activity != 0:
            return "inconclusive", "no_variance"
        if activity > baseline_activity:
            if trial.get("exploratory") and not attributable_progress(trial):
                return "inconclusive", "signal_not_attributable"
            return "adopt", None
        if (
            trial.get("exploratory")
            and activity >= baseline_activity
            and not attributable_progress(trial)
        ):
            return "inconclusive", "signal_not_attributable"
        return "revert", None

    # No predicted targets: activity score only, with the no-variance guard.
    if activity > baseline_activity:
        if trial.get("exploratory") and not attributable_progress(trial):
            return "inconclusive", "signal_not_attributable"
        return "adopt", None
    if trial_is_no_signal(trial):
        return "inconclusive", "no_signal"
    if background_tie:
        return "inconclusive", "no_variance"
    if trial.get("exploratory") and activity >= baseline_activity and not attributable_progress(trial):
        return "inconclusive", "signal_not_attributable"
    return "revert", None
