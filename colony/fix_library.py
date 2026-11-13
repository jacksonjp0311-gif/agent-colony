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

from colony.bitwork import Router, action_fingerprint
from colony.fix_actions import validate

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
# ---------------------------------------------------------------------------

def seed_patterns() -> list[dict[str, Any]]:
    """Deterministic seed examples. Same list every call, no I/O.

    Each positive pattern has a paraphrase with the same action so
    held-out replay has a sibling to retrieve. Negative invariant
    examples have no paraphrase (they must not be proposed).
    """
    return [dict(p) for p in _SEED_PATTERNS + _SEED_PARAPHRASES]


# Symptom text is deliberate: distinctive words so leave-one-out
# retrieval can tell the cases apart, while staying plain and factual.
_SEED_PATTERNS: tuple[dict[str, Any], ...] = (
    # PR #1 — stall loop: park repeats, hand off idle turns, PERTURB.
    {
        "id": "seed:pr1:repeated-targets-park",
        "source": "pr1",
        "kind": "fix",
        "label": "repeated_targets",
        "symptom": (
            "stall loop same targets selected repeatedly "
            "park repeats hand off idle turns"
        ),
        "action": {"op": "set_knob", "name": "park_cycles", "direction": "up"},
        "outcome": "positive",
        "evidence": {
            "pr": 1,
            "summary": "Park a repeated proposal so the stall loop stops replaying it.",
        },
    },
    {
        "id": "seed:pr1:unused-menu-handoff",
        "source": "pr1",
        "kind": "fix",
        "label": "repeated_targets",
        "symptom": (
            "idle turns handed to perturb unused menu already tried "
            "same target list"
        ),
        "action": {"op": "set_knob", "name": "unused_menu_cycles", "direction": "up"},
        "outcome": "positive",
        "evidence": {
            "pr": 1,
            "summary": "Look further back before treating a target as already tried.",
        },
    },
    # PR #2 — empty labels, parked proof chains, OEIS retry loops.
    {
        "id": "seed:pr2:empty-label-skip",
        "source": "pr2",
        "kind": "fix",
        "label": "empty_claim_label",
        "symptom": (
            "empty claim label reached the oracle skip blank titles "
            "retry loop on a parked proof chain"
        ),
        "action": {
            "op": "add_skip_rule",
            "target_kind": "empty_label",
            "cycles": 12,
        },
        "outcome": "positive",
        "evidence": {
            "pr": 2,
            "summary": "Skip empty claim labels so they never reach the Oracle.",
        },
    },
    {
        "id": "seed:pr2:parked-chain",
        "source": "pr2",
        "kind": "fix",
        "label": "parked_proof_chain",
        "symptom": (
            "parked proof chain stayed parked then retried "
            "identical kill on the same chain"
        ),
        "action": {
            "op": "add_park_rule",
            "target_kind": "proof_chain_parked",
            "cycles": 12,
        },
        "outcome": "positive",
        "evidence": {
            "pr": 2,
            "summary": "Keep a parked proof chain parked instead of retrying it.",
        },
    },
    # PR #3 — tighten-only checker lane: route triviality to the lane.
    {
        "id": "seed:pr3:triviality-to-checker",
        "source": "pr3",
        "kind": "fix",
        "label": "trivial_claim",
        "symptom": (
            "trivial claim pattern slipped a known-bad kill "
            "propose a tighter triviality check for the checker lane"
        ),
        "action": {
            "op": "add_triviality_candidate",
            "pattern": "textbook identity restated",
            "pattern_type": "literal",
        },
        "outcome": "positive",
        "evidence": {
            "pr": 3,
            "summary": "Route a new triviality pattern to the tighten-only checker lane.",
        },
    },
    # PR #4 — PERTURB replaying already-held ranges.
    {
        "id": "seed:pr4:already-held-skip",
        "source": "pr4",
        "kind": "fix",
        "label": "no_progress_perturb",
        "symptom": (
            "perturb spent its picks on already held ranges "
            "same targets cannot move no progress session"
        ),
        "action": {
            "op": "add_skip_rule",
            "target_kind": "already_held_range",
            "cycles": 8,
        },
        "outcome": "positive",
        "evidence": {
            "pr": 4,
            "summary": "Skip already-held ranges that cannot move further.",
        },
    },
    {
        "id": "seed:pr4:perturb-cooldown",
        "source": "pr4",
        "kind": "fix",
        "label": "immediate_reentry",
        "symptom": (
            "perturb timed out then switched right back on "
            "immediate reentry after a no-progress session"
        ),
        "action": {
            "op": "set_knob",
            "name": "perturb_cooldown_cycles",
            "direction": "up",
        },
        "outcome": "positive",
        "evidence": {
            "pr": 4,
            "summary": "Rest longer after a no-progress PERTURB timeout.",
        },
    },
    # PR #5 — self-heal: high revert rate means smaller steps, longer windows.
    {
        "id": "seed:pr5:high-revert-step",
        "source": "pr5",
        "kind": "fix",
        "label": "high_revert_rate",
        "symptom": (
            "self heal high revert rate trials keep failing "
            "take a smaller step and judge over a longer window"
        ),
        "action": {"op": "set_knob", "name": "step_size", "direction": "down"},
        "outcome": "positive",
        "evidence": {
            "pr": 5,
            "summary": "Shrink the self-heal step when trials keep getting reverted.",
        },
    },
    {
        "id": "seed:pr5:high-revert-window",
        "source": "pr5",
        "kind": "fix",
        "label": "high_revert_rate",
        "symptom": (
            "self heal trials judged too quickly high revert rate "
            "lengthen the evaluation window"
        ),
        "action": {"op": "set_knob", "name": "evaluation_window", "direction": "up"},
        "outcome": "positive",
        "evidence": {
            "pr": 5,
            "summary": "Judge a trial over more cycles when the revert rate is high.",
        },
    },
    # PR #6 — zero eligible targets, legacy depth treated as verified.
    {
        "id": "seed:pr6:zero-picks-idle",
        "source": "pr6",
        "kind": "fix",
        "label": "no_progress_perturb",
        "symptom": (
            "perturb found zero eligible targets and sat idle "
            "legacy requested depth treated as verified"
        ),
        "action": {
            "op": "set_knob",
            "name": "perturb_zero_pick_cycles",
            "direction": "up",
        },
        "outcome": "positive",
        "evidence": {
            "pr": 6,
            "summary": "Leave a zero-pick PERTURB session instead of sitting idle.",
        },
    },
    {
        "id": "seed:pr6:dead-end-park",
        "source": "pr6",
        "kind": "fix",
        "label": "dead_end_streak",
        "symptom": (
            "dead end streak all block skip identical kill "
            "park the repeating proposal sooner"
        ),
        "action": {"op": "set_knob", "name": "park_cycles", "direction": "up"},
        "outcome": "positive",
        "evidence": {
            "pr": 6,
            "summary": "Park a dead-end streak instead of replaying it.",
        },
    },
    # PR #7 — depth at a physical evaluator cap; use the corrected metric.
    {
        "id": "seed:pr7:depth-at-cap-fast",
        "source": "pr7",
        "kind": "fix",
        "label": "depth_at_physical_cap",
        "symptom": (
            "evaluator hit a built-in term cap depth at physical cap "
            "raise the fast term cap so a held target can go deeper"
        ),
        "action": {"op": "set_knob", "name": "fast_term_cap", "direction": "up"},
        "outcome": "positive",
        "evidence": {
            "pr": 7,
            "summary": "Raise the fast term cap when a held target is stuck at it.",
        },
    },
    {
        "id": "seed:pr7:depth-at-cap-gf",
        "source": "pr7",
        "kind": "fix",
        "label": "depth_at_physical_cap",
        "symptom": (
            "generating function term cap reached algebraic series "
            "raise the slow series cap within the exact cheap bound"
        ),
        "action": {"op": "set_knob", "name": "gf_term_cap", "direction": "up"},
        "outcome": "positive",
        "evidence": {
            "pr": 7,
            "summary": "Raise the series-arithmetic cap when that is the blocker.",
        },
    },
    {
        "id": "seed:pr7:mark-ceiling",
        "source": "pr7",
        "kind": "fix",
        "label": "depth_at_physical_cap",
        "symptom": (
            "target cannot be pushed further evaluator cap_reason recorded "
            "mark a ceiling so the stall mode does not sit on it"
        ),
        "action": {
            "op": "mark_ceiling",
            "target": "held-at-cap",
            "depth": 1200,
            "reason": "evaluator_cap",
        },
        "outcome": "positive",
        "evidence": {
            "pr": 7,
            "summary": "Record an evaluator ceiling instead of retrying the same depth.",
        },
    },
    # Negative examples: attempts that must never be learned as "fixes".
    {
        "id": "seed:neg:loosen-oracle",
        "source": "invariant",
        "kind": "failure",
        "label": "invariant_touch",
        "symptom": "lower the oracle threshold so more claims pass loosen the P gate",
        "action": {"op": "set_knob", "name": "oracle_p", "direction": "down"},
        "outcome": "negative",
        "evidence": {
            "summary": "Any proposal that loosens the Oracle or the P gate is rejected.",
        },
    },
    {
        "id": "seed:neg:authored-cap",
        "source": "invariant",
        "kind": "failure",
        "label": "invariant_touch",
        "symptom": "raise the authored check cap above one hundred fifty",
        "action": {"op": "set_knob", "name": "authored_cap", "value": 200},
        "outcome": "negative",
        "evidence": {
            "summary": "The 150 authored-check cap is not a knob.",
        },
    },
)

# Paraphrases: same action as the matching seed, different wording.
# Held-out replay retrieves the sibling. Ids are stable.
_SEED_PARAPHRASES: tuple[dict[str, Any], ...] = (
    {
        "id": "seed:pr1:repeated-targets-park:p",
        "source": "pr1",
        "kind": "fix",
        "label": "repeated_targets",
        "symptom": (
            "the stall detector keeps picking the same targets in a loop; "
            "park those repeats and hand the idle turns off"
        ),
        "action": {"op": "set_knob", "name": "park_cycles", "direction": "up"},
        "outcome": "positive",
        "evidence": {"pr": 1, "paraphrase_of": "seed:pr1:repeated-targets-park"},
    },
    {
        "id": "seed:pr1:unused-menu-handoff:p",
        "source": "pr1",
        "kind": "fix",
        "label": "repeated_targets",
        "symptom": (
            "idle turn handoff to perturb treated a target as already tried "
            "because the unused menu window was too short"
        ),
        "action": {"op": "set_knob", "name": "unused_menu_cycles", "direction": "up"},
        "outcome": "positive",
        "evidence": {"pr": 1, "paraphrase_of": "seed:pr1:unused-menu-handoff"},
    },
    {
        "id": "seed:pr2:empty-label-skip:p",
        "source": "pr2",
        "kind": "fix",
        "label": "empty_claim_label",
        "symptom": (
            "a blank title and empty claim label was about to reach the oracle; "
            "skip blank titles and stop the retry loop"
        ),
        "action": {"op": "add_skip_rule", "target_kind": "empty_label", "cycles": 12},
        "outcome": "positive",
        "evidence": {"pr": 2, "paraphrase_of": "seed:pr2:empty-label-skip"},
    },
    {
        "id": "seed:pr2:parked-chain:p",
        "source": "pr2",
        "kind": "fix",
        "label": "parked_proof_chain",
        "symptom": (
            "a parked proof chain was retried and took an identical kill "
            "on the same chain; keep it parked"
        ),
        "action": {"op": "add_park_rule", "target_kind": "proof_chain_parked", "cycles": 12},
        "outcome": "positive",
        "evidence": {"pr": 2, "paraphrase_of": "seed:pr2:parked-chain"},
    },
    {
        "id": "seed:pr3:triviality-to-checker:p",
        "source": "pr3",
        "kind": "fix",
        "label": "trivial_claim",
        "symptom": (
            "a trivial claim pattern let a known-bad case slip through; "
            "propose a tighter triviality check and send it to the checker lane"
        ),
        "action": {
            "op": "add_triviality_candidate",
            "pattern": "textbook identity restated",
            "pattern_type": "literal",
        },
        "outcome": "positive",
        "evidence": {"pr": 3, "paraphrase_of": "seed:pr3:triviality-to-checker"},
    },
    {
        "id": "seed:pr4:already-held-skip:p",
        "source": "pr4",
        "kind": "fix",
        "label": "no_progress_perturb",
        "symptom": (
            "a perturb session spent every pick on already held ranges "
            "that cannot move; skip those ranges in a no progress session"
        ),
        "action": {"op": "add_skip_rule", "target_kind": "already_held_range", "cycles": 8},
        "outcome": "positive",
        "evidence": {"pr": 4, "paraphrase_of": "seed:pr4:already-held-skip"},
    },
    {
        "id": "seed:pr4:perturb-cooldown:p",
        "source": "pr4",
        "kind": "fix",
        "label": "immediate_reentry",
        "symptom": (
            "after a no-progress timeout perturb switched right back on "
            "with immediate reentry; rest longer"
        ),
        "action": {"op": "set_knob", "name": "perturb_cooldown_cycles", "direction": "up"},
        "outcome": "positive",
        "evidence": {"pr": 4, "paraphrase_of": "seed:pr4:perturb-cooldown"},
    },
    {
        "id": "seed:pr5:high-revert-step:p",
        "source": "pr5",
        "kind": "fix",
        "label": "high_revert_rate",
        "symptom": (
            "the self heal loop has a high revert rate and trials keep failing; "
            "take a smaller step"
        ),
        "action": {"op": "set_knob", "name": "step_size", "direction": "down"},
        "outcome": "positive",
        "evidence": {"pr": 5, "paraphrase_of": "seed:pr5:high-revert-step"},
    },
    {
        "id": "seed:pr5:high-revert-window:p",
        "source": "pr5",
        "kind": "fix",
        "label": "high_revert_rate",
        "symptom": (
            "self heal is judging trials too quickly which raises the revert rate; "
            "lengthen the evaluation window"
        ),
        "action": {"op": "set_knob", "name": "evaluation_window", "direction": "up"},
        "outcome": "positive",
        "evidence": {"pr": 5, "paraphrase_of": "seed:pr5:high-revert-window"},
    },
    {
        "id": "seed:pr6:zero-picks-idle:p",
        "source": "pr6",
        "kind": "fix",
        "label": "no_progress_perturb",
        "symptom": (
            "perturb found zero eligible targets and sat idle after "
            "legacy requested depth was treated as verified"
        ),
        "action": {"op": "set_knob", "name": "perturb_zero_pick_cycles", "direction": "up"},
        "outcome": "positive",
        "evidence": {"pr": 6, "paraphrase_of": "seed:pr6:zero-picks-idle"},
    },
    {
        "id": "seed:pr6:dead-end-park:p",
        "source": "pr6",
        "kind": "fix",
        "label": "dead_end_streak",
        "symptom": (
            "a dead end streak of block skip and identical kill; "
            "park the repeating proposal sooner"
        ),
        "action": {"op": "set_knob", "name": "park_cycles", "direction": "up"},
        "outcome": "positive",
        "evidence": {"pr": 6, "paraphrase_of": "seed:pr6:dead-end-park"},
    },
    {
        "id": "seed:pr7:depth-at-cap-fast:p",
        "source": "pr7",
        "kind": "fix",
        "label": "depth_at_physical_cap",
        "symptom": (
            "the evaluator hit a built-in term cap so depth is at a physical cap; "
            "raise the fast term cap and a held target can go deeper"
        ),
        "action": {"op": "set_knob", "name": "fast_term_cap", "direction": "up"},
        "outcome": "positive",
        "evidence": {"pr": 7, "paraphrase_of": "seed:pr7:depth-at-cap-fast"},
    },
    {
        "id": "seed:pr7:depth-at-cap-gf:p",
        "source": "pr7",
        "kind": "fix",
        "label": "depth_at_physical_cap",
        "symptom": (
            "an algebraic generating function reached its series term cap; "
            "raise the slow series cap within the exact cheap bound"
        ),
        "action": {"op": "set_knob", "name": "gf_term_cap", "direction": "up"},
        "outcome": "positive",
        "evidence": {"pr": 7, "paraphrase_of": "seed:pr7:depth-at-cap-gf"},
    },
    {
        "id": "seed:pr7:mark-ceiling:p",
        "source": "pr7",
        "kind": "fix",
        "label": "depth_at_physical_cap",
        "symptom": (
            "a target cannot be pushed further and cap_reason is recorded; "
            "mark a ceiling so stall mode does not sit on it"
        ),
        "action": {
            "op": "mark_ceiling",
            "target": "held-at-cap",
            "depth": 1200,
            "reason": "evaluator_cap",
        },
        "outcome": "positive",
        "evidence": {"pr": 7, "paraphrase_of": "seed:pr7:mark-ceiling"},
    },
)


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
        from colony.self_heal import load_state
        st = load_state()
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
        from colony.self_heal import diagnose
        findings = diagnose(cycle_id)
    except Exception:
        findings = []
    return [
        _finding_record(f, cycle_id=cycle_id, source="stall")
        for f in findings if isinstance(f, Mapping)
    ]


def mine_quarantine(*, cycle_id: str = "") -> list[dict[str, Any]]:
    try:
        from colony.self_heal import load_state
        st = load_state()
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
