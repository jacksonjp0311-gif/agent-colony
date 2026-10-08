"""External mind — plain desk-outcome recording (bridge dynamics).

This module used to be a stub that base64-decoded ``society/briefs/external_mind_py_*.b64``
and exec'd the result. Those parts were never committed, so the loader exec'd nothing and
every ``from colony.external_mind import ...`` raised ImportError (since 2026-09-26). That
silently disabled the conjecture desk's keep/revert lessons and exploration-budget updates.

It is now ordinary readable code with no decoding, no exec, no network and no writes outside
``data/commons/``:

* ``record_desk_outcome`` — append one keep/revert/skip row to ``data/commons/desk_outcomes.jsonl``
  (the "commons append on keep/revert" from CREATOR_BRIEF_bridge_dynamics.md).
* ``lineage_lesson_ids`` — ids of real prior lessons that named this exact mutation before the
  outcome (its authoring record, the hint lessons / human guides that asked for it). The desk
  cites these on its keep/revert lesson. Nothing is cited when no such lesson exists.

``propose`` (the Lift 5 external-mind proposal batch) is intentionally NOT provided here: its
original implementation never existed in this repo, and the bridge brief records that unmeasured
external-mind proposals were rejected at authorize anyway. growth.py already treats its absence
as a witnessed skip.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent.parent
DESK_OUTCOMES_JSONL = ROOT / "data" / "commons" / "desk_outcomes.jsonl"

# catalog_hint keys whose value names a mutation the lesson asked the desk to try
_HINT_MUTATION_KEYS = ("add_mutation", "chain_mutation")
_HINT_MUTATION_LIST_KEYS = ("prefer_mutations",)
MAX_CITES = 3


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hint_names(hint: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for k in _HINT_MUTATION_KEYS:
        v = hint.get(k)
        if isinstance(v, str) and v:
            names.add(v)
    for k in _HINT_MUTATION_LIST_KEYS:
        v = hint.get(k)
        if isinstance(v, list):
            names.update(str(x) for x in v if x)
    return names


def lineage_lesson_ids(
    mutation: str,
    *,
    lessons: Iterable[dict[str, Any]] | None = None,
    exclude_cycle: str = "",
) -> list[str]:
    """Real prior lessons that named ``mutation`` exactly, most relevant first.

    1. its authoring record (type ``authored_check`` with the same mutation) — newest;
    2. human guides whose catalog_hint names the mutation (add/chain/prefer_mutations);
    3. the newest non-guide lesson whose catalog_hint.add_mutation names it (the queue hint).

    Lessons written in ``exclude_cycle`` (this desk judgment's own cycle) are not cited.
    Exact name match only; no fuzzy/theme matching, so nothing is cited "for the metric".
    """
    if not mutation:
        return []
    if lessons is None:
        try:
            from colony.lessons import LESSONS_JSONL

            rows: list[dict[str, Any]] = []
            if LESSONS_JSONL.exists():
                for line in LESSONS_JSONL.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            lessons = rows
        except Exception:  # noqa: BLE001
            return []
    rows = [e for e in lessons if e.get("id") and (not exclude_cycle or e.get("cycle_id") != exclude_cycle)]

    authored = [e for e in rows if e.get("type") == "authored_check" and e.get("mutation") == mutation]
    guides = [
        e for e in rows
        if e.get("type") == "human_guide" and mutation in _hint_names(e.get("catalog_hint") or {})
    ]
    hints = [
        e for e in rows
        if e.get("type") != "human_guide"
        and e.get("type") != "authored_check"
        and (e.get("catalog_hint") or {}).get("add_mutation") == mutation
    ]
    out: list[str] = []
    if authored:
        out.append(authored[-1]["id"])
    for g in guides:
        out.append(g["id"])
    if hints:
        out.append(hints[-1]["id"])
    seen: set[str] = set()
    uniq = [i for i in out if not (i in seen or seen.add(i))]
    return uniq[:MAX_CITES]


def record_desk_outcome(
    *,
    decision: str,
    mutation: str,
    before_score: float | None,
    after_score: float | None,
    kind: str = "",
    note: str = "",
    cycle_id: str = "",
    paper_cites: list[str] | None = None,
    lesson_cites: list[str] | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Append one desk outcome row to the commons. Candidate only; never accepted here."""
    entry = {
        "ts": _utc(),
        "cycle_id": cycle_id,
        "decision": decision,
        "mutation": mutation,
        "kind": kind,
        "before_score": before_score,
        "after_score": after_score,
        "note": (note or "")[:500],
        "paper_cites": [str(c)[:200] for c in (paper_cites or [])][:8],
        "lesson_cites": list(lesson_cites or [])[:MAX_CITES],
        "status": "candidate",
        "not_discovery": True,
    }
    out = path or DESK_OUTCOMES_JSONL
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


if __name__ == "__main__":  # pragma: no cover - manual inspection helper
    print(json.dumps({"desk_outcomes": str(DESK_OUTCOMES_JSONL)}, indent=2))
