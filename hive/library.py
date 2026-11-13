"""Append-only library of failures and fixes, mined from the colony's own history.

Every record is a structured example: symptom features, an optional
fix action, and the evidence that verified (or rejected) it. The
library is the teaching set for the Bitwork router. Records are only
ever appended; existing lines are never rewritten. Seed patterns are
derived from merged PRs #1–#11 and from real historical failures
with known resolutions — they are not a rewrite of any live log.
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
# Committed snapshot: enough to restore the library when the JSONL log
# is gitignored. Bounded; see compact_records and hive/README.md.
LIBRARY_SNAPSHOT = ROOT / "society" / "systems" / "swarm_library.json"

# How many recent log rows to scan when mining. Bounded so CI stays short.
MINE_LIMIT = 400

# Compaction cap for the committed library snapshot. Seed records are
# always kept. When the live log grows past this, the oldest non-seed
# records are dropped from the snapshot (record contents are never
# rewritten). The JSONL log stays append-only and is not committed.
LIBRARY_KEEP = 2000
SEED_SOURCE_TAGS = frozenset({
    "seed", "paraphrase", "historical",
    "pr1", "pr2", "pr3", "pr4", "pr5", "pr6", "pr7", "pr8", "pr9", "pr10", "pr11",
})


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
# Seed patterns (derived from PRs #1–#11). Immutable descriptions.
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
        _SEED_CACHE = (
            _load_jsonl("seeds.jsonl")
            + _load_jsonl("paraphrases.jsonl")
            + _load_jsonl("historical.jsonl")
        )
    return [dict(p) for p in _SEED_CACHE]


# Structured feature keys shared by seed examples and live findings.
# Live symptoms that dump unique cycle ids and raw evidence lists do
# not overlap this vocabulary, which is why live margins were 0.
STRUCTURED_KEYS: tuple[str, ...] = (
    "failure_class",
    "exit_reason",
    "stall_reason",
    "desk",
    "cap_reason",
    "cap_name",
    "target_kind",
)

# Values that are run-specific noise, not a stable feature class.
_CYCLE_ID_MARKERS = ("T", "Z_")
_SKIP_VALUE_TOKENS = frozenset({"", "none", "null", "[]", "{}", "0"})


def _norm_token(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in text).strip("_")


def _is_stable_value(value: Any) -> bool:
    """Reject unique run identifiers, empty containers, and raw dumps."""
    if value is None or isinstance(value, (list, dict, tuple)):
        return False
    text = str(value).strip()
    if not text or text in _SKIP_VALUE_TOKENS:
        return False
    # Cycle ids look like 20261113T015301Z_759b6f.
    if len(text) >= 16 and "T" in text and ("Z_" in text or text.endswith("Z")):
        if text[:8].isdigit():
            return False
    return True


def _collect_structured_values(record: Mapping[str, Any]) -> dict[str, list[str]]:
    """Gather stable structured values from a record and its evidence."""
    ev = record.get("evidence") if isinstance(record.get("evidence"), Mapping) else {}
    feats = record.get("features") if isinstance(record.get("features"), Mapping) else {}
    bags: dict[str, list[str]] = {k: [] for k in STRUCTURED_KEYS}

    def add(key: str, raw: Any) -> None:
        if key not in bags:
            return
        if isinstance(raw, (list, tuple)):
            for item in raw:
                if isinstance(item, Mapping):
                    if key == "cap_reason" and item.get("cap_reason"):
                        add("cap_reason", item.get("cap_reason"))
                elif _is_stable_value(item):
                    tok = _norm_token(item)
                    if tok and tok not in bags[key]:
                        bags[key].append(tok)
            return
        if not _is_stable_value(raw):
            return
        tok = _norm_token(raw)
        if tok and tok not in bags[key]:
            bags[key].append(tok)

    # failure_class: label, or kind when kind is a diagnosis (not "fix"/"failure").
    kind = str(record.get("kind") or "")
    label = str(record.get("label") or "")
    failure = (
        record.get("failure_class")
        or feats.get("failure_class")
        or ev.get("failure_class")
        or (label if label and label not in {"unlabelled", "unknown"} else "")
        or (kind if kind not in {"fix", "failure", ""} else "")
    )
    add("failure_class", failure)

    for src in (record, feats, ev):
        if not isinstance(src, Mapping):
            continue
        for key in STRUCTURED_KEYS:
            if key == "failure_class":
                continue
            if key in src:
                add(key, src.get(key))
        # Nested recent cap rows from live depth_at_physical_cap findings.
        recent = src.get("recent")
        if isinstance(recent, list):
            for row in recent:
                if isinstance(row, Mapping) and row.get("cap_reason"):
                    add("cap_reason", row.get("cap_reason"))

    return bags


def structured_tokens(record: Mapping[str, Any]) -> list[str]:
    """Stable ``key:value`` tokens shared by seeds and live findings."""
    bags = _collect_structured_values(record)
    tokens: list[str] = []
    for key in STRUCTURED_KEYS:
        for tok in bags[key]:
            tokens.append(f"{key}:{tok}")
    return tokens


def feature_text(record: Mapping[str, Any]) -> str:
    """Canonical symptom string used as the Bitwork query / example.

    Structured tokens (failure class, exit_reason, cap_reason, desk,
    stall_reason, target_kind) are prepended so a live finding and a
    seed for the same class share vocabulary. Unique cycle ids and
    raw evidence dumps are not included. The Wilson gate is unchanged.
    """
    tokens = structured_tokens(record)
    raw_sym = record.get("symptom")
    if isinstance(raw_sym, Mapping):
        symptom = ""
    else:
        symptom = str(raw_sym or "").strip()
    if not symptom:
        label = str(record.get("label") or record.get("failure_class") or record.get("kind") or "")
        symptom = label.replace("_", " ").strip()
        kind = str(record.get("kind") or "")
        if kind and kind not in {"fix", "failure"} and kind.replace("_", " ") not in symptom:
            symptom = f"{kind.replace('_', ' ')} {symptom}".strip()
    parts = tokens + ([symptom] if symptom else [])
    return " ".join(parts).strip()


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
    for key in STRUCTURED_KEYS:
        if record.get(key):
            out[key] = record.get(key)
        elif isinstance(record.get("evidence"), Mapping) and record["evidence"].get(key):
            if key not in ("", None):
                out[key] = record["evidence"].get(key)
    if validated is not None:
        out["action_ok"] = validated.ok
        out["action_reason"] = validated.reason
        out["action_fingerprint"] = validated.fingerprint
    return out


# ---------------------------------------------------------------------------
# Append-only I/O and router training
# ---------------------------------------------------------------------------


def load_records(*, path: Path | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    """Load library records.

    Prefers the append-only JSONL log. If that file is missing or empty
    (a fresh CI checkout, where the log is gitignored), restore from
    the committed snapshot and, when writing to the default log path,
    materialize the JSONL so later appends have a base.
    """
    dest = path or LIBRARY_LOG
    rows = _read_jsonl(dest, limit=limit)
    if rows:
        return rows
    snap = load_snapshot()
    if not snap:
        return []
    if path is None and not dest.exists():
        _write_jsonl(dest, snap)
    if limit is not None and limit > 0:
        return snap[-limit:]
    return snap


def load_snapshot(path: Path | None = None) -> list[dict[str, Any]]:
    dest = path or LIBRARY_SNAPSHOT
    if not dest.exists():
        return []
    try:
        raw = json.loads(dest.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(raw, dict):
        rows = raw.get("records")
    else:
        rows = raw
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _is_seed_record(row: Mapping[str, Any]) -> bool:
    rid = str(row.get("id") or "")
    source = str(row.get("source") or "")
    if source in SEED_SOURCE_TAGS or source.startswith("seed"):
        return True
    if rid.startswith("seed:") or rid.startswith("para:"):
        return True
    return False


def compact_records(records: Iterable[Mapping[str, Any]], *, keep: int = LIBRARY_KEEP) -> list[dict[str, Any]]:
    """Bounded view of the library for the committed snapshot.

    Seed records are always retained. Other records are kept newest
    first until ``keep`` is reached. Record bodies are copied, never
    rewritten. This is a size bound, not a change of meaning.
    """
    rows = [dict(r) for r in records if isinstance(r, Mapping)]
    cap = max(int(keep), 1)
    seeds = [r for r in rows if _is_seed_record(r)]
    rest = [r for r in rows if not _is_seed_record(r)]
    budget = max(cap - len(seeds), 0)
    if budget == 0:
        kept_rest: list[dict[str, Any]] = []
    elif budget < len(rest):
        kept_rest = rest[-budget:]
    else:
        kept_rest = rest
    return seeds + kept_rest


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    lines = [
        json.dumps(dict(r), sort_keys=True, default=str, ensure_ascii=False)
        for r in records
    ]
    body = "\n".join(lines)
    if lines:
        body = body + "\n"
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, sort_keys=True, default=str, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def persist_library(
    *,
    path: Path | None = None,
    snapshot: Path | None = None,
    records: Iterable[Mapping[str, Any]] | None = None,
    keep: int = LIBRARY_KEEP,
) -> list[dict[str, Any]]:
    """Write the committed snapshot from the current library.

    The JSONL log is not rewritten (it stays append-only). Only the
    snapshot is compacted. Returns the records stored in the snapshot.
    """
    src = path or LIBRARY_LOG
    rows = list(records) if records is not None else _read_jsonl(src)
    if not rows:
        rows = load_snapshot(snapshot)
    compacted = compact_records(rows, keep=keep)
    payload = {
        "version": 1,
        "n": len(compacted),
        "keep": int(keep),
        "compacted": len(rows) - len(compacted),
        "note": (
            "Committed Hive library snapshot. The append-only JSONL log "
            "is gitignored; this file is enough to restore the library "
            "across CI runs. Seed records are always kept. Non-seed "
            "records are capped so the total stays at the keep bound "
            "(seeds inclusive). Record contents are never rewritten."
        ),
        "records": compacted,
    }
    _atomic_write_json(snapshot or LIBRARY_SNAPSHOT, payload)
    return compacted



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
        # A voided trial is not a fair test: do not teach from it.
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
    """Idempotent: write seeds once, return whatever this call added.

    After seeding (or a no-op on an already-seeded log), refresh the
    committed snapshot so a fresh checkout can restore the library.
    """
    # If the JSONL is empty, restore from the snapshot first so we
    # do not re-append seeds that are already in the snapshot and
    # then lose later taught records.
    if path is None:
        load_records()
    written = seed_into(path=path)
    try:
        persist_library(path=path)
    except Exception:
        pass
    return written
