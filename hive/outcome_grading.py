"""Item 110: grade Hive predictions by outcome, not by exact-action match.

Before this, a shadow pick (Hive abstained at the Wilson gate and
remembered its top action) was scored correct only when its action
fingerprint equalled the action self-heal later adopted for the same
failure class. A pick of ``fast_term_cap up`` resolved by a
``gf_term_cap up`` adopt counted as wrong, whatever ``fast_term_cap up``
itself would have done.

Outcome grading asks the question the gate is meant to ask: would the
proposed action have helped? It only uses measured trial results:

* a prediction is graded by the first *decisive* trial (adopt or revert)
  of the same action family (``set_knob`` name + direction, or the exact
  non-knob fingerprint) that **started at or after** the prediction and
  within ``HORIZON_HOURS`` of it. No foreknowledge: a trial that was
  already running or already closed cannot grade a later prediction.
* adopt (scored strictly better than its baseline over the unchanged
  6-cycle window) = correct; revert = wrong.
* voided, inconclusive or no matching trial = abstain: no row, no credit
  either way. Making a prediction never earns credit by itself.
* repeated identical predictions graded by the same trial collapse into
  one unit per margin bucket, so one trial cannot be counted 30 times
  as 30 independent successes (that would loosen the Wilson gate).

Graded units are appended to a separate ledger
(``data/commons/hive_outcome_grades.jsonl``). Existing shadow rows and
the old match-graded ``shadow`` counts in state are never rewritten;
with the switch on, bucket totals use ``outcome`` instead of ``shadow``.
The Wilson 95% lower bound and the 700 permille gate are unchanged.

Switch: ``HIVE_OUTCOME_GRADING`` (default on in treatment; off when
``COLONY_ARM=control`` or the switch is ``off``). Hive does not import
colony; the arm is read from the environment.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from hive.bitwork import action_fingerprint, margin_bucket, wilson_lower_permille

ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = ROOT / "data" / "commons" / "hive_outcome_grades.jsonl"

HORIZON_HOURS = 48
RULE = "outcome_v1"
SOURCE = "outcome"


def outcome_grading_enabled() -> bool:
    if (os.environ.get("COLONY_ARM") or "treatment").strip().lower() == "control":
        return False
    return (os.environ.get("HIVE_OUTCOME_GRADING") or "on").strip().lower() != "off"


def _parse_ts(value: Any) -> datetime | None:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        if len(s) >= 16 and s[8] == "T" and s[:8].isdigit():  # cycle id 20261114T081411Z_xxx
            return datetime.strptime(s[:16], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def family_of(action: Mapping[str, Any] | None = None, fingerprint: str | None = None) -> str:
    """``set_knob`` -> name + direction (stepped value ignored); others exact."""
    if isinstance(action, Mapping) and action:
        if str(action.get("op") or "") == "set_knob":
            name, direction = action.get("name"), action.get("direction")
            if not name or not direction:
                return ""
            return f"set_knob:direction={direction}:name={name}"
        return action_fingerprint(action)
    fp = str(fingerprint or "")
    if not fp:
        return ""
    parts = [p for p in fp.split(":") if not p.startswith("value=")]
    if parts and parts[0] == "set_knob":
        kv = dict(p.split("=", 1) for p in parts[1:] if "=" in p)
        if not kv.get("name") or not kv.get("direction"):
            return ""
        return f"set_knob:direction={kv['direction']}:name={kv['name']}"
    return ":".join(parts)


def collect_predictions(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every remembered Hive shadow pick, with the time it was made.

    State shadows carry their own ``ts``. Older resolved shadows that
    were compacted out of state survive only as calibration outcome
    rows; their prediction time comes from the cycle id.
    """
    out: dict[str, dict[str, Any]] = {}
    for s in list(state.get("shadows") or []):
        if not isinstance(s, Mapping):
            continue
        sid = str(s.get("id") or "")
        fam = family_of(s.get("action") if isinstance(s.get("action"), Mapping) else None,
                        str(s.get("fingerprint") or "") or None)
        at = _parse_ts(s.get("cycle_id")) or _parse_ts(s.get("ts"))
        if sid and fam and at is not None:
            out[sid] = {"id": sid, "family": fam, "at": at, "margin": int(s.get("margin") or 0),
                        "label": s.get("label"), "cycle_id": s.get("cycle_id")}
    cal = state.get("calibration") if isinstance(state.get("calibration"), Mapping) else {}
    for o in list(cal.get("outcomes") or []):
        if not isinstance(o, Mapping) or o.get("source") != "shadow":
            continue
        sid = str(o.get("id") or "")
        if not sid or sid in out:
            continue
        fam = family_of(None, str(o.get("shadow_fingerprint") or "") or None)
        at = _parse_ts(o.get("cycle_id"))
        if fam and at is not None:
            out[sid] = {"id": sid, "family": fam, "at": at, "margin": int(o.get("margin") or 0),
                        "label": o.get("label"), "cycle_id": o.get("cycle_id")}
    return sorted(out.values(), key=lambda p: (p["at"], p["id"]))


def collect_trials(heal_evidence: Iterable[Any], swarm_evidence: Iterable[Any] = ()) -> list[dict[str, Any]]:
    """Decisive measured trials: (family, start, close, adopt?)."""
    trials: list[dict[str, Any]] = []
    open_start: dict[str, datetime] = {}
    for ev in heal_evidence:
        if not isinstance(ev, Mapping):
            continue
        name = str(ev.get("event") or "")
        knob = ev.get("knob")
        direction = ev.get("direction")
        if not knob or not direction:
            continue
        fam = f"set_knob:direction={direction}:name={knob}"
        at = _parse_ts(ev.get("ts"))
        if at is None:
            continue
        if name == "trial_start":
            open_start[fam] = at
        elif name in ("adopt", "revert"):
            start = open_start.pop(fam, None)
            if start is None:
                continue  # start not in retained evidence: timing unknown, abstain
            trials.append({"id": str(ev.get("id") or f"{fam}@{ev.get('ts')}"), "family": fam,
                           "start": start, "close": at, "event": name, "via": "self_heal",
                           "baseline_score": ev.get("baseline_score"), "trial_score": ev.get("trial_score")})
        elif name in ("trial_voided_confound", "trial_inconclusive", "trial_skipped"):
            open_start.pop(fam, None)
    for ev in swarm_evidence:  # Hive's own non-knob rule trials
        if not isinstance(ev, Mapping) or ev.get("via") != "swarm_rule":
            continue
        if str(ev.get("event") or "") not in ("adopt", "revert"):
            continue
        fam = family_of(ev.get("action") if isinstance(ev.get("action"), Mapping) else None,
                        str(ev.get("fingerprint") or "") or None)
        start = _parse_ts(ev.get("started_at") or ev.get("start_cycle_id"))
        close = _parse_ts(ev.get("ts"))
        if fam and start is not None and close is not None:
            trials.append({"id": str(ev.get("id") or f"{fam}@{ev.get('ts')}"), "family": fam,
                           "start": start, "close": close, "event": ev.get("event"), "via": "swarm_rule",
                           "baseline_score": ev.get("baseline_score"), "trial_score": ev.get("trial_score")})
    trials.sort(key=lambda t: (t["start"], t["id"]))
    return trials


def grade(predictions: list[dict[str, Any]], trials: list[dict[str, Any]],
          horizon_hours: int = HORIZON_HOURS) -> dict[str, Any]:
    """Pure grading. Returns per-prediction grades and collapsed units."""
    per: list[dict[str, Any]] = []
    units: dict[str, dict[str, Any]] = {}
    horizon = horizon_hours * 3600
    for p in predictions:
        hit = None
        for t in trials:
            if t["family"] != p["family"]:
                continue
            dt = (t["start"] - p["at"]).total_seconds()
            if 0 <= dt <= horizon:
                hit = t
                break
        if hit is None:
            per.append({**p, "graded": False})
            continue
        correct = hit["event"] == "adopt"
        per.append({**p, "graded": True, "correct": correct, "trial_id": hit["id"]})
        edge = int(margin_bucket(int(p["margin"])))
        uid = f"og:{hit['id']}:{p['family']}:b{edge}"
        u = units.get(uid)
        if u is None:
            units[uid] = {
                "id": uid, "rule": RULE, "source": SOURCE, "family": p["family"],
                "trial_id": hit["id"], "trial_event": hit["event"], "trial_via": hit["via"],
                "trial_start": hit["start"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                "trial_close": hit["close"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                "baseline_score": hit.get("baseline_score"), "trial_score": hit.get("trial_score"),
                "margin": int(p["margin"]), "bucket": edge, "correct": correct,
                "n_predictions": 1, "prediction_ids": [p["id"]],
            }
        else:
            u["n_predictions"] += 1
            u["prediction_ids"].append(p["id"])
            u["margin"] = min(u["margin"], int(p["margin"]))
    graded = [g for g in per if g["graded"]]
    return {
        "predictions": per,
        "units": sorted(units.values(), key=lambda u: u["id"]),
        "n_predictions": len(per),
        "n_graded": len(graded),
        "n_correct": sum(1 for g in graded if g["correct"]),
        "n_wrong": sum(1 for g in graded if not g["correct"]),
        "n_abstain": len(per) - len(graded),
    }


def load_ledger(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or LEDGER_PATH
    rows: list[dict[str, Any]] = []
    if not p.exists():
        return rows
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(row, dict) and row.get("rule") == RULE:
            rows.append(row)
    return rows


def append_units(units: list[dict[str, Any]], path: Path | None = None) -> list[dict[str, Any]]:
    """Append units not yet in the ledger. Existing rows are never touched.

    A unit is complete once its trial has closed (only predictions made
    before the trial started can attach), so a written id never changes.
    """
    p = path or LEDGER_PATH
    have = {r.get("id") for r in load_ledger(p)}
    new = [u for u in units if u["id"] not in have]
    if not new:
        return []
    p.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with p.open("a", encoding="utf-8") as fh:
        for u in new:
            fh.write(json.dumps({**u, "graded_at": now}, sort_keys=True) + "\n")
    return new


def apply_to_calibration(cal: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    """Replace the ``outcome`` slice of each bucket from the ledger (idempotent)."""
    for bucket in cal.get("buckets") or []:
        bucket.setdefault("by_source", {})[SOURCE] = {"n": 0, "correct": 0}
    by_edge = {int(b.get("min_margin") or 0): b for b in cal.get("buckets") or []}
    for r in rows:
        b = by_edge.get(int(margin_bucket(int(r.get("margin") or 0))))
        if b is None:
            continue
        s = b["by_source"][SOURCE]
        s["n"] += 1
        s["correct"] += 1 if r.get("correct") else 0


def summary(cal: Mapping[str, Any]) -> dict[str, Any]:
    out = []
    for b in cal.get("buckets") or []:
        out.append({"min_margin": b.get("min_margin"), "n": b.get("n"), "correct": b.get("correct"),
                    "lower_permille": b.get("lower_permille"),
                    "clears_700": int(b.get("lower_permille") or 0) >= 700})
    return {"buckets": out}


__all__ = (
    "HORIZON_HOURS", "LEDGER_PATH", "append_units", "apply_to_calibration", "collect_predictions",
    "collect_trials", "family_of", "grade", "load_ledger", "outcome_grading_enabled", "summary",
    "wilson_lower_permille",
)
