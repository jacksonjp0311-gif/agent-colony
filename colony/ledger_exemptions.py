"""Item 97 (James, delegated 2026-11-16 4:33 AM ET): ledger entries that came ONLY from the old
wrong STEM held-out test do not count as prior knowledge.

Before PR #59 every ``stem_enable`` was judged by the lemma hard-tier held-out test, which can
never pass for that kind (``held_out:hard_tier_green_and_hard_enable``). A candidate killed only
by that kill left lesson/history entries, and every later proposal was then killed as
``already_in_lesson_ledger_or_history``.

This module never edits or deletes an entry. It reads an append-only exemption record,
data/commons/ledger_exemptions.jsonl, which lists the exact entries by source file, a hash of
the raw line, the lesson id and the timestamp. The novelty gate's ledger check skips only
those listed entries, on the treatment arm. Every other condition of the gate is unchanged,
and every other entry still counts.

Which gate rows count as bug-only (``bug_only_rows``), in time order:
  * kind ``stem_enable``;
  * every kill in the row is either the old held-out kill or a ledger kill;
  * a ledger kill qualifies only if every earlier ledger trace of that name is already exempt.
    A trace is any lesson whose mutation or family contains the name, or any history row whose
    mutation contains it.
A row with any other kill (trivial, textbook, stripped baseline, Oracle ...) is never bug-only.
The entries of a bug-only row are: lessons with that mutation and cycle_id, and history rows
with that mutation at the row's timestamp.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
EXEMPT_LOG = Path(os.path.join(os.fspath(ROOT), "data", "commons", "ledger_exemptions.jsonl"))
BUG_KILL = "held_out:hard_tier_green_and_hard_enable"
LEDGER_KILL = "already_in_lesson_ledger_or_history"
RULE = "item97_stem_held_out_bug_not_prior_knowledge"


def line_id(raw: str) -> str:
    return hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()[:20]


def active() -> bool:
    try:
        from colony.arm import self_mod_enabled
        return bool(self_mod_enabled())
    except Exception:  # noqa: BLE001
        return False


def exempt_ids(path: Path | None = None) -> set[tuple[str, str]]:
    """{(source, line_id)} listed in the append-only exemption record. Empty off-treatment."""
    p = path or EXEMPT_LOG
    out: set[tuple[str, str]] = set()
    if not p.exists():
        return out
    for ln in p.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if e.get("rule") == RULE and e.get("source") in ("lessons", "history") and e.get("line_id"):
            out.add((str(e["source"]), str(e["line_id"])))
    return out


def _read(path: Path) -> list[tuple[str, dict[str, Any]]]:
    out = []
    if not path.exists():
        return out
    for ln in path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            out.append((ln, json.loads(ln)))
        except json.JSONDecodeError:
            continue
    return out


def _traces(name: str, lessons, history, before_ts: str) -> list[tuple[str, str, dict[str, Any]]]:
    n = name.lower()
    out = []
    for raw, e in lessons:
        if str(e.get("ts") or "") < before_ts and (
                n in str(e.get("mutation") or "").lower() or n in str(e.get("family") or "").lower()):
            out.append(("lessons", line_id(raw), e))
    for raw, e in history:
        if str(e.get("ts") or "") < before_ts and n in str(e.get("mutation") or "").lower():
            out.append(("history", line_id(raw), e))
    return out


def bug_only_rows(gate_path: Path, lessons_path: Path, history_path: Path) -> list[dict[str, Any]]:
    """Exemption records for every entry that came only from the old STEM held-out bug."""
    gate = [e for _r, e in _read(gate_path)]
    lessons, history = _read(lessons_path), _read(history_path)
    exempt: set[tuple[str, str]] = set()
    records: list[dict[str, Any]] = []
    for row in gate:
        if str(row.get("kind") or "") != "stem_enable" or row.get("novel_to_commons"):
            continue
        kills = [str(k) for k in (row.get("kills") or [])]
        if not kills or any(k not in (BUG_KILL, LEDGER_KILL) for k in kills):
            continue
        name, ts, cyc = str(row.get("mutation") or ""), str(row.get("ts") or ""), str(row.get("cycle_id") or "")
        if not name or not ts:
            continue
        if LEDGER_KILL in kills:
            prior = _traces(name, lessons, history, ts)
            if not prior or any((s, i) not in exempt for s, i, _e in prior):
                continue  # some earlier trace is real prior knowledge: not bug-only
        own = []
        for raw, e in lessons:
            if str(e.get("mutation") or "") == name and cyc and str(e.get("cycle_id") or "") == cyc:
                own.append(("lessons", raw, e))
        for raw, e in history:
            if str(e.get("mutation") or "") == name and str(e.get("ts") or "") == ts:
                own.append(("history", raw, e))
        for src, raw, e in own:
            key = (src, line_id(raw))
            if key in exempt:
                continue
            exempt.add(key)
            records.append({
                "rule": RULE, "source": src, "line_id": key[1], "entry_id": e.get("id"),
                "entry_ts": e.get("ts"), "mutation": name, "cycle_id": cyc or None,
                "gate_row_ts": ts, "gate_kills": kills,
                "why": ("gate row killed only by the pre-#59 STEM held-out bug"
                        + (" (ledger kill whose earlier traces are all exempt)" if LEDGER_KILL in kills else "")),
            })
    return records
