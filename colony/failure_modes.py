"""Item 89: the exact failure mode of every rejected, reverted, inconclusive or voided self-change.

Every self-heal knob trial and every self-build blueprint trial that does not end kept writes
one append-only row to ``data/commons/self_change_failures.jsonl``: which metric lost, against
what (baseline window or the control twin), by how much, and which check failed. Self-build
self-test rejections are logged as one row per proposal turn.

The next generation reads the log back:
  * self-build (``component_penalty``): a component whose blueprints lost on the same metric
    against the same reference (a real loss, not an inconclusive/void) is weighted down, so the
    generator moves to components and operators that have not failed that way;
  * self-heal (``heal_repeat_failures``): a (knob, direction) that already failed with the same
    mode sorts after one that has not.
Inconclusive and voided trials are logged but carry no penalty (no evidence either way).

Read-only for the Oracle and every gate; control arm: no rows, no penalties.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "commons" / "self_change_failures.jsonl"
BLUEPRINT_METRICS = ("oracle_passes", "verified_depth_sum")
PENALTY_STEP = 0.5          # weight multiplier 1 / (1 + PENALTY_STEP * n_real_losses)
REAL_LOSS_OUTCOMES = ("reverted", "revert")


def live() -> bool:
    if (os.environ.get("COLONY_FAILURE_MODES") or "live").strip().lower() in {"0", "off", "false", "no"}:
        return False
    try:
        from colony.arm import self_mod_enabled
        return bool(self_mod_enabled())
    except Exception:  # noqa: BLE001
        return False


def _utc() -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def append(row: Mapping[str, Any], path: Path | None = None) -> dict[str, Any] | None:
    if not live():
        return None
    out = {"ts": _utc(), **dict(row), "authorized": False}
    try:
        p = Path(path or LOG)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(out, sort_keys=True, default=str) + "\n")
    except Exception:  # noqa: BLE001 -- logging must never break a cycle
        return None
    return out


def load(path: Path | None = None) -> list[dict[str, Any]]:
    try:
        text = Path(path or LOG).read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 -- missing / unreadable: no history
        return []
    rows = []
    for line in text.splitlines():
        try:
            r = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(r, dict):
            rows.append(r)
    return rows


def _f(x: Any) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- self-build

def blueprint_row(close: Mapping[str, Any], *, components: Iterable[str] = ()) -> dict[str, Any] | None:
    """Failure row for a blueprint close/void row (None when it was kept)."""
    outcome = str(close.get("outcome") or "")
    if outcome == "kept" or not outcome:
        return None
    verdict = dict(close.get("verdict") or {})
    tg = verdict.get("trial_gain")
    bg = verdict.get("baseline_gain")
    metrics: dict[str, Any] = {}
    lost: list[dict[str, Any]] = []
    if isinstance(tg, (list, tuple)) and len(tg) == 2:
        bg = bg if isinstance(bg, (list, tuple)) and len(bg) == 2 else (0.0, 0.0)
        for i, m in enumerate(BLUEPRINT_METRICS):
            t, b = _f(tg[i]) or 0.0, _f(bg[i]) or 0.0
            metrics[m] = {"trial_gain_vs_twin": t, "baseline_gain_vs_twin": b, "vs_baseline": t - b}
        # The decision is lexicographic (oracle_passes first): the first metric that is not
        # strictly ahead is the one that lost.
        for ref, key in (("baseline", "vs_baseline"), ("twin", "trial_gain_vs_twin")):
            vals = [metrics[m][key] for m in BLUEPRINT_METRICS]
            if tuple(vals) > (0.0, 0.0):
                continue
            m = BLUEPRINT_METRICS[0] if vals[0] != 0 else BLUEPRINT_METRICS[1]
            lost.append({"metric": m, "against": ref, "by": metrics[m][key]})
    check = str(verdict.get("reason") or close.get("reason") or outcome)
    return {
        "event": "self_change_failure", "kind": "blueprint", "cycle_id": close.get("cycle_id"),
        "subject": {"blueprint": close.get("blueprint"), "operator": close.get("operator"),
                    "steps": close.get("steps"), "components": sorted(set(components))},
        "outcome": outcome, "failed_check": check, "mode": f"{outcome}:{check}",
        "metrics": metrics, "lost": lost,
    }


def log_blueprint(close: Mapping[str, Any] | None, *, components: Iterable[str] = (),
                  path: Path | None = None) -> dict[str, Any] | None:
    if not close:
        return None
    row = blueprint_row(close, components=components)
    return append(row, path) if row else None


def log_rejections(cycle_id: str, rejected: list[Mapping[str, Any]], *, path: Path | None = None) -> dict[str, Any] | None:
    """One row per proposal turn: every blueprint candidate the self-test rejected, with why."""
    if not rejected:
        return None
    reasons = Counter(str(r.get("reason") or "").split(":")[0] for r in rejected)
    return append({"event": "self_change_failure", "kind": "blueprint_self_test", "cycle_id": cycle_id,
                   "outcome": "rejected", "failed_check": "self_test", "mode": "rejected:self_test",
                   "n_rejected": len(rejected), "by_reason": dict(reasons),
                   "rejected": [dict(r) for r in rejected[:40]]}, path)


def hive_pick_row(result: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Spark idea: exact cause when a Hive cycle voted but started no trial (abstain, no legal
    proposal, deferral). Read-only on Hive; the Wilson gate itself is untouched."""
    if not isinstance(result, Mapping) or result.get("skipped"):
        return None
    vote = result.get("vote")
    if not isinstance(vote, Mapping) or result.get("started"):
        return None
    win = vote.get("winner") if isinstance(vote.get("winner"), Mapping) else {}
    run = vote.get("runner_up") if isinstance(vote.get("runner_up"), Mapping) else {}
    reason = str(vote.get("reason") or "unknown")
    outcome = "abstained" if vote.get("abstained") else "accepted_not_started"
    lower = int(vote.get("lower_permille") or 0)
    gate = int(vote.get("wilson_gate") or 700)
    return {"event": "self_change_failure", "kind": "hive_pick", "cycle_id": str(result.get("cycle_id") or ""),
            "outcome": outcome, "failed_check": reason, "mode": f"{outcome}:{reason}",
            "winner": win.get("fingerprint"), "label": win.get("label"), "card_id": win.get("card_id") or "",
            "role": win.get("role"), "runner_up": run.get("fingerprint"),
            "lower_permille": lower, "wilson_gate": gate, "short_by_permille": max(0, gate - lower),
            "margin": int(vote.get("margin") or 0), "bucket": int(vote.get("bucket") or 0),
            "bucket_n": int(vote.get("bucket_n") or 0), "n_votes": int(vote.get("n_votes") or 0),
            "n_vetoes": int(vote.get("n_vetoes") or 0), "n_proposals": int(result.get("n_proposals") or 0)}


def log_hive_pick(result: Mapping[str, Any] | None, *, path: Path | None = None) -> dict[str, Any] | None:
    row = hive_pick_row(result)
    return append(row, path) if row else None


def component_losses(rows: list[dict[str, Any]] | None = None) -> Counter:
    """Real losses (reverted blueprints) per component; inconclusive/voided are not counted."""
    rows = load() if rows is None else rows
    c: Counter = Counter()
    for r in rows:
        if r.get("kind") != "blueprint" or r.get("outcome") not in REAL_LOSS_OUTCOMES:
            continue
        for name in (r.get("subject") or {}).get("components") or []:
            c[str(name)] += 1
    return c


def component_penalty(name: str, losses: Mapping[str, int] | None = None) -> float:
    if not live():
        return 1.0
    n = int((losses if losses is not None else component_losses()).get(name) or 0)
    return 1.0 / (1.0 + PENALTY_STEP * n)


# --------------------------------------------------------------------------- self-heal

_HEAL_FAIL = {"revert": "reverted", "trial_inconclusive": "inconclusive", "trial_voided_confound": "voided"}


def _mean(rows: Iterable[Mapping[str, Any]], key: str) -> float | None:
    vals = [v for v in (_f((r or {}).get(key)) for r in rows) if v is not None]
    return sum(vals) / len(vals) if vals else None


def heal_row(ev: Mapping[str, Any]) -> dict[str, Any] | None:
    outcome = _HEAL_FAIL.get(str(ev.get("event") or ""))
    if outcome is None:
        return None
    trial_rows = list(ev.get("trial_metrics") or [])
    base_rows = list(ev.get("baseline_metrics") or [])
    keys = sorted({k for r in trial_rows + base_rows if isinstance(r, dict) for k, v in r.items()
                   if isinstance(v, (int, float)) and not isinstance(v, bool)})
    metrics: dict[str, Any] = {}
    for k in keys:
        t, b = _mean(trial_rows, k), _mean(base_rows, k)
        if t is not None and b is not None:
            metrics[k] = {"trial": round(t, 6), "baseline": round(b, 6), "delta": round(t - b, 6)}
    lost = sorted(({"metric": k, "against": "baseline", "by": v["delta"]} for k, v in metrics.items()
                   if v["delta"] < 0), key=lambda x: x["by"])
    ts, bs = _f(ev.get("trial_score")), _f(ev.get("baseline_score"))
    if ts is not None and bs is not None:
        metrics["score"] = {"trial": ts, "baseline": bs, "delta": ts - bs}
        if ts <= bs:
            lost.insert(0, {"metric": "score", "against": "baseline", "by": ts - bs})
    check = str(ev.get("reason") if outcome != "voided" else (ev.get("reason") or "environment_changed"))
    if outcome == "reverted" and ev.get("decision_requested") not in (None, "revert"):
        check = "did_not_improve"
    return {
        "event": "self_change_failure", "kind": "self_heal", "cycle_id": ev.get("cycle_id"),
        "subject": {"knob": ev.get("knob"), "direction": ev.get("direction"), "from": ev.get("from"),
                    "to": ev.get("to"), "evidence_id": ev.get("id")},
        "outcome": outcome, "failed_check": check, "mode": f"{outcome}:{check}",
        "metrics": metrics, "lost": lost[:8],
    }


def log_heal_events(events: Iterable[Mapping[str, Any]], *, path: Path | None = None) -> list[dict[str, Any]]:
    out = []
    for ev in events:
        row = heal_row(ev)
        if row:
            got = append(row, path)
            if got:
                out.append(got)
    return out


def heal_repeat_failures(knob: str, direction: str, rows: list[dict[str, Any]] | None = None) -> int:
    """Real losses (reverts) already logged for this (knob, direction)."""
    if not live():
        return 0
    rows = load() if rows is None else rows
    return sum(1 for r in rows if r.get("kind") == "self_heal" and r.get("outcome") == "reverted"
               and (r.get("subject") or {}).get("knob") == knob
               and (r.get("subject") or {}).get("direction") == direction)


def summary(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = load() if rows is None else rows
    by_kind: dict[str, Counter] = {}
    lost: Counter = Counter()
    for r in rows:
        by_kind.setdefault(str(r.get("kind")), Counter())[str(r.get("mode"))] += 1
        for x in r.get("lost") or []:
            lost[f"{x.get('metric')}<{x.get('against')}"] += 1
    return {"n": len(rows), "modes": {k: dict(v) for k, v in by_kind.items()}, "lost": dict(lost)}
