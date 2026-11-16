"""Item 91: knowledge-library method cards -> Hive-testable method ops.

A method card (``data/commons/method_cards.jsonl``, item 79) already names one
bounded Hive op (today: ``set_knob`` name + direction). On its own a card
finding has no Bitwork match, so its margin is 0 and the Wilson gate always
abstains: the card is never tested.

This module turns each distinct card op into a deterministic Hive library
record (a *method op*): the card's op, filed under the failure class its
concept addresses, with the card text as the symptom. Bitwork can then
retrieve it for a live finding of that class. Nothing else changes:

* The Wilson 700 permille gate, its calibration (replay slice uses only
  ``positive`` records; a method op is ``unknown`` and never enters it), the
  self-heal 6-cycle windows and the strictly-better rule decide. A winning
  method op goes to the ordinary trial and is kept or auto-reverted, and that
  real outcome is what Hive learns from (mine_self_heal).
* Ops are validated by ``hive.ops.validate`` (closed op set, invariant
  fragments rejected); an invalid card op is skipped.
* No outside model, no web code: a fixed concept -> failure-class table.
* Append-only (``library.append_record``, idempotent by id). Control arm:
  no-op (Hive learning is off there).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parent.parent
CARDS_PATH = ROOT / "data" / "commons" / "method_cards.jsonl"

# Card concept -> the Hive failure class (seed vocabulary) the method addresses.
CONCEPT_CLASS: dict[str, str] = {
    "curriculum": "no_progress_perturb",
    "stochastic_search": "no_progress_perturb",
    "early_stopping": "no_progress_perturb",
    "swarm_consensus": "empty_perturb_pool",
    "prediction_error": "dead_end_streak",
    "novelty_diversity": "repeated_targets",
    "working_memory_attention": "repeated_targets",
}
# Cards written before concepts were stored: infer from the knob they move.
KNOB_CONCEPT: dict[str, str] = {
    "curriculum_pace": "curriculum",
    "perturb_epsilon": "stochastic_search",
    "perturb_max_cycles": "early_stopping",
    "perturb_wide_epsilon": "swarm_consensus",
    "stall_cycles": "prediction_error",
    "family_rotation_penalty": "novelty_diversity",
    "unused_menu_cycles": "working_memory_attention",
}


def load_cards(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or CARDS_PATH
    out: list[dict[str, Any]] = []
    try:
        for ln in p.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and isinstance(row.get("op"), Mapping):
                out.append(row)
    except OSError:
        pass
    return out


def _concept(card: Mapping[str, Any]) -> str:
    c = str(card.get("concept") or "")
    if c:
        return c
    return KNOB_CONCEPT.get(str((card.get("op") or {}).get("name") or ""), "")


def method_op_records(cards: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One record per (failure class, op), in first-seen card order. Pure."""
    from hive.ops import validate

    by_id: dict[str, dict[str, Any]] = {}
    for card in cards:
        op = dict(card.get("op") or {})
        fc = CONCEPT_CLASS.get(_concept(card))
        if not fc or not op:
            continue
        v = validate(op)
        if not v.ok:
            continue
        key = f"{op.get('op')}:{op.get('name') or op.get('target_kind') or ''}:{op.get('direction') or ''}"
        rid = f"method_op:{fc}:{key}"
        rec = by_id.get(rid)
        if rec is None:
            method = str(card.get("method") or "").strip()
            rec = by_id[rid] = {
                "id": rid,
                "source": "method_card",
                "kind": "method_op",
                "label": fc,
                "failure_class": fc,
                "symptom": f"{fc.replace('_', ' ')} {_concept(card).replace('_', ' ')} {method}".strip(),
                "action": op,
                "outcome": "unknown",  # a hypothesis: only a real trial outcome teaches Hive
                "evidence": {"card_ids": [], "concept": _concept(card), "method": method[:200],
                             "failure_class": fc},
            }
        cid = str(card.get("id") or "")
        if cid and cid not in rec["evidence"]["card_ids"]:
            rec["evidence"]["card_ids"].append(cid)
    return list(by_id.values())


def install(*, cards: Iterable[Mapping[str, Any]] | None = None, path: Path | None = None) -> list[dict[str, Any]]:
    """Append method ops missing from the Hive library. Self-mod arm only; never rewrites."""
    try:
        from colony.arm import self_mod_enabled
        if not self_mod_enabled():
            return []
    except Exception:  # noqa: BLE001
        return []
    from hive import library as FL

    dest = path or FL.LIBRARY_LOG
    have = FL.known_ids(path=dest)
    written: list[dict[str, Any]] = []
    for rec in method_op_records(cards if cards is not None else load_cards()):
        row = FL.append_record(rec, path=dest, known=have)
        if row is not None:
            written.append(row)
    return written
