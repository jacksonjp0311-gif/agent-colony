"""Append-only library of failures and fixes, mined from the colony's own history.

Every record is a structured example: symptom features, an optional
fix action, and the evidence that verified (or rejected) it. The
library is the teaching set for the Bitwork router. Records are only
ever appended; existing lines are never rewritten. Seed patterns are
derived in this file from merged PRs #1–#7 and from the diagnosis
vocabulary the colony already uses — they are not a rewrite of any
live log.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from hive.bitwork import Router, action_fingerprint
from hive.ops import validate

ROOT = Path(__file__).resolve().parent.parent
LIBRARY_LOG = ROOT / "data" / "commons" / "fix_library.jsonl"

# How many recent log rows to scan when mining. Bounded so CI stays short.
MINE_LIMIT = 400


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id() -> str:
    return "fx_" + uuid.uuid4().hex[:12]


def _atomic_append(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(dict(record), sort_keys=True, default=str, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _read_jsonl(path: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return []
    lines = text.splitlines()
    if limit is not None and limit > 0:
        lines = lines[-limit:]
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


# ---------------------------------------------------------------------------
# Seed patterns (derived from PRs #1–#7). Immutable descriptions.
# Shipped as JSONL under hive/data/ so Hive can be copied out and examined
# on its own. Same content, same ids, as the original in-code list.
# ---------------------------------------------------------------------------

_DATA = Path(__file__).resolve().parent / "data"


def _load_jsonl(name: str) -> list[dict[str, Any]]:
    path = _DATA / name
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


_SEED_CACHE: list[dict[str, Any]] | None = None


def seed_patterns() -> list[dict[str, Any]]:
    """Deterministic seed examples. Same list every call, no writes.

    Each positive pattern has a paraphrase with the same action so
    held-out replay has a sibling to retrieve. Negative invariant
    examples have no paraphrase (they must not be proposed).
    """
    global _SEED_CACHE
    if _SEED_CACHE is None:
        _SEED_CACHE = _load_jsonl("seeds.jsonl") + _load_jsonl("paraphrases.jsonl")
    return [dict(p) for p in _SEED_CACHE]


def feature_text(record: Mapping[str, Any]) -> str:
    """Canonical symptom string used as the Bitwork query / example."""
    symptom = str(record.get("symptom") or record.get("features") or "").strip()
    if symptom:
        return symptom
    label = str(record.get("label") or "").replace("_", " ")
    kind = str(record.get("kind") or "")
    return f"{kind} {label}".strip()


def action_key_of(record: Mapping[str, Any]) -> str:
    action = record.get("action")
    if isinstance(action, Mapping) and action:
        return action_fingerprint(action)
    return str(record.get("label") or record.get("kind") or "unknown")


def canonicalize(record: Mapping[str, Any], *, assign_id: bool = True) -> dict[str, Any]:
    """Shape a record for the append-only log. Does not write."""
    action = record.get("action")
    validated = None
    if isinstance(action, Mapping) and action:
        # Negative invariant examples are stored even though they fail
        # validation — that is the point of the example.
        validated = validate(action)
        action_out: dict[str, Any] | None = (
            validated.as_dict() if validated.ok else dict(action)
        )
    else:
        action_out = None
    rid = str(record.get("id") or "") or (_new_id() if assign_id else "")
    outcome = str(record.get("outcome") or "unknown")
    if outcome not in ("positive", "negative", "unknown"):
        outcome = "unknown"
    out = {
        "id": rid,
        "ts": str(record.get("ts") or _utc()),
        "cycle_id": str(record.get("cycle_id") or ""),
        "source": str(record.get("source") or "unknown"),
        "kind": str(record.get("kind") or "failure"),
        "label": str(record.get("label") or ""),
        "symptom": feature_text(record),
        "action": action_out,
        "action_key": action_key_of({"action": action_out, **{k: record.get(k) for k in ("label", "kind")}}),
        "outcome": outcome,
        "evidence": dict(record.get("evidence") or {}) if isinstance(record.get("evidence"), Mapping) else {},
        "applied_to_live_oracle": False,
        "authorized": False,
    }
    if validated is not None:
        out["action_ok"] = validated.ok
        out["action_reason"] = validated.reason
        out["action_fingerprint"] = validated.fingerprint
    return out


# ---------------------------------------------------------------------------
# Append-only I/O and router training
# ---------------------------------------------------------------------------

def load_records(*, path: Path | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    return _read_jsonl(path or LIBRARY_LOG, limit=limit)


def known_ids(records: Iterable[Mapping[str, Any]] | None = None, *, path: Path | None = None) -> set[str]:
    rows = list(records) if records is not None else load_records(path=path)
    return {str(r.get("id") or "") for r in rows if r.get("id")}


def append_record(
    record: Mapping[str, Any],
    *,
    path: Path | None = None,
    known: set[str] | None = None,
) -> dict[str, Any] | None:
    """Append one record if its id is new. Returns the written record, or None."""
    dest = path or LIBRARY_LOG
    row = canonicalize(record)
    rid = str(row.get("id") or "")
    have = known if known is not None else known_ids(path=dest)
    if rid and rid in have:
        return None
    _atomic_append(dest, row)
    if known is not None and rid:
        known.add(rid)
    return row


def seed_into(
    *,
    path: Path | None = None,
    known: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Write seed patterns that are not already in the log. Never rewrites."""
    dest = path or LIBRARY_LOG
    have = known if known is not None else known_ids(path=dest)
    written: list[dict[str, Any]] = []
    for raw in seed_patterns():
        # Seeds have fixed ids; canonicalize keeps them.
        row = append_record(raw, path=dest, known=have)
        if row is not None:
            written.append(row)
    return written


def train_router(
    records: Iterable[Mapping[str, Any]] | None = None,
    *,
    path: Path | None = None,
    router: Router | None = None,
) -> Router:
    """Build (or extend) a router from library records. Deterministic order."""
    rows = list(records) if records is not None else load_records(path=path)
    rtr = router if router is not None else Router()
    for row in rows:
        text = feature_text(row)
        if not text:
            continue
        label = str(row.get("label") or "unlabelled")
        key = str(row.get("action_key") or action_key_of(row))
        outcome = str(row.get("outcome") or "unknown")
        if outcome == "unknown" and not row.get("action"):
            # A raw failure with no fix yet: still teach the category mask.
            rtr.ensure_category(label)
            continue
        positive = outcome != "negative"
        rtr.learn(
            text,
            category=label,
            action_key=key,
            positive=positive,
            source_id=str(row.get("id") or ""),
            proto_key=str(row.get("id") or ""),
            cues=label.replace("_", " ").split(),
        )
    return rtr


def held_out_cases(records: Iterable[Mapping[str, Any]] | None = None) -> list[tuple[str, str]]:
    """``(symptom, action_key)`` pairs with a known positive action, for replay."""
    cases: list[tuple[str, str]] = []
    for row in (records if records is not None else seed_patterns()):
        if str(row.get("outcome") or "") != "positive":
            continue
        text = feature_text(row)
        key = action_key_of(row)
        if text and key:
            cases.append((text, key))
    return cases


# ---------------------------------------------------------------------------
# Mining live logs (read-only on source files; append-only on the library)
# ---------------------------------------------------------------------------

def _finding_record(finding: Mapping[str, Any], *, cycle_id: str, source: str) -> dict[str, Any]:
    kind = str(finding.get("kind") or "unlabelled")
    evidence = finding.get("evidence") if isinstance(finding.get("evidence"), Mapping) else {}
    # Deterministic id from kind + a stable slice of evidence, so a
    # repeated finding in the same cycle does not duplicate.
    ev_blob = json.dumps(evidence, sort_keys=True, default=str)[:120]
    fid = f"mine:{source}:{kind}:{cycle_id}:{ev_blob}"[:120]
    symptom_parts = [kind.replace("_", " "), source]
    for k, v in list(evidence.items())[:6]:
        symptom_parts.append(f"{k} {v}")
    return {
        "id": fid,
        "cycle_id": cycle_id,
        "source": source,
        "kind": "failure",
        "label": kind,
        "symptom": " ".join(str(p) for p in symptom_parts),
        "action": None,
        "outcome": "unknown",
        "evidence": dict(evidence),
    }


def mine_self_heal(*, path: Path | None = None, cycle_id: str = "") -> list[dict[str, Any]]:
    """Turn self-heal adopt / revert evidence into library examples."""
    try:
        from hive import host
        st = host.heal_load_state()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for ev in list(st.get("evidence") or []):
        if not isinstance(ev, Mapping):
            continue
        event = str(ev.get("event") or "")
        if event not in ("adopt", "revert"):
            continue
        knob = str(ev.get("knob") or "")
        direction = str(ev.get("direction") or "")
        reason = str(ev.get("reason") or "")
        if not knob:
            continue
        action = {"op": "set_knob", "name": knob, "direction": direction} if direction else {
            "op": "set_knob", "name": knob, "value": ev.get("to"),
        }
        rid = f"heal:{event}:{ev.get('id') or ev.get('cycle_id') or ''}:{knob}"
        symptom = (
            f"self heal {event} knob {knob} {direction} "
            f"reason {reason.replace('_', ' ')} "
            f"baseline {ev.get('baseline_score')} trial {ev.get('trial_score')}"
        )
        out.append({
            "id": rid,
            "cycle_id": str(ev.get("cycle_id") or cycle_id),
            "source": "self_heal",
            "kind": "fix" if event == "adopt" else "failure",
            "label": reason or event,
            "symptom": symptom,
            "action": action,
            "outcome": "positive" if event == "adopt" else "negative",
            "evidence": {
                "event": event,
                "knob": knob,
                "from": ev.get("from"),
                "to": ev.get("to"),
                "baseline_score": ev.get("baseline_score"),
                "trial_score": ev.get("trial_score"),
                "helped": ev.get("helped"),
            },
        })
    return out


def mine_stall(*, path: Path | None = None, cycle_id: str = "") -> list[dict[str, Any]]:
    """Read stall state and emit failure records for recent diagnoses."""
    try:
        from hive import host
        findings = host.diagnose(cycle_id)
    except Exception:
        findings = []
    return [
        _finding_record(f, cycle_id=cycle_id, source="stall")
        for f in findings if isinstance(f, Mapping)
    ]


def mine_quarantine(*, cycle_id: str = "") -> list[dict[str, Any]]:
    try:
        from hive import host
        st = host.heal_load_state()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for q in list(st.get("quarantine") or []):
        if not isinstance(q, Mapping):
            continue
        step = str(q.get("step") or q.get("name") or "")
        if not step:
            continue
        out.append({
            "id": f"quarantine:{step}:{q.get('until') or q.get('id') or ''}",
            "cycle_id": cycle_id,
            "source": "quarantine",
            "kind": "failure",
            "label": "quarantined_step",
            "symptom": f"optional step {step} quarantined after repeated failures",
            "action": None,
            "outcome": "unknown",
            "evidence": dict(q),
        })
    for fail in list(st.get("failures") or [])[-24:]:
        if not isinstance(fail, Mapping):
            continue
        step = str(fail.get("step") or "")
        err = str(fail.get("error") or fail.get("exc") or "")
        if not step:
            continue
        out.append({
            "id": f"fail:{step}:{fail.get('id') or fail.get('cycle_id') or err[:40]}",
            "cycle_id": str(fail.get("cycle_id") or cycle_id),
            "source": "self_heal",
            "kind": "failure",
            "label": "step_failure",
            "symptom": f"optional step {step} threw {err}",
            "action": None,
            "outcome": "unknown",
            "evidence": {"step": step, "error": err},
        })
    return out


def mine_all(*, cycle_id: str = "", path: Path | None = None) -> list[dict[str, Any]]:
    """Collect new examples from live logs and append those not yet stored."""
    dest = path or LIBRARY_LOG
    have = known_ids(path=dest)
    collected: list[dict[str, Any]] = []
    for row in (
        mine_self_heal(cycle_id=cycle_id)
        + mine_stall(cycle_id=cycle_id)
        + mine_quarantine(cycle_id=cycle_id)
    ):
        written = append_record(row, path=dest, known=have)
        if written is not None:
            collected.append(written)
    return collected


def ensure_seeded(*, path: Path | None = None) -> list[dict[str, Any]]:
    """Idempotent: write seeds once, return whatever this call added."""
    return seed_into(path=path)
