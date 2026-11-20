"""Item 119: stop re-proposing variants of a check family the lesson ledger already holds.

Since 2026-11-19 every Oracle pass was a ``hard_enable`` of a freshly generated
``authored_mut_*`` check. Each one was a new mutation (swap / widen / tighten /
perturb) of a held claim whose *earlier* mutations had already been judged by the
desk (Oracle pass, then "coverage keep refused: lemma score flat", revert) and
were therefore in the lesson ledger. Every such variant was then killed by the
novelty gate as ``already_in_lesson_ledger_or_history``: 0 novelty for one desk
slot each.

A *mutation family* is the source claim a generated check was mutated from
(``source_statement`` in the append-only ``generated_targets.jsonl`` log). A
family is *learned* once any of its members has a judged lesson (any lesson
type other than its own ``authored_check`` birth record). With the switch live:

* ``target_generator.author_targets`` does not author further variants of a
  learned family (counted as ``learned_family_skipped`` in the supply row);
* ``conjecture_desk.pick_mutation`` cools an already-authored, never-judged
  variant of a learned family (reason ``learned_family``);
* a desk turn freed this way goes to the item-118 bank-v2 target supply: one
  extra refill (``target_supply.slot_refill``), cooldown ignored, ``OPEN_MIN``,
  the request budget and the unchanged vetting kept, at most once per cycle.
  The new targets go to the shared supply log, so both arms adopt them on the
  next run exactly like any other supply (fair twin, item 82).

Every decision is one row in the append-only ``data/commons/learned_family_skip.jsonl``.
Tighten-only: nothing is authored, enabled or credited by this module. The
Oracle, P >= 0.70, the 150 cap, Hive's Wilson gate, the evaluation windows,
strictly-better, the triviality filter and Athanor are untouched; authorize stays
false. Switch ``COLONY_LEARNED_FAMILY_SKIP`` = live (default) | off; always off on
the control arm (``self_mod_enabled`` is false there).
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "commons" / "learned_family_skip.jsonl"
LESSONS = ROOT / "data" / "commons" / "lessons.jsonl"
PREFIX = "authored_mut_"
SKIP_REASON = "learned_family"
BIRTH_TYPES = ("authored_check",)


def enabled() -> bool:
    try:
        from colony.arm import self_mod_enabled
        if not self_mod_enabled():
            return False
    except Exception:  # noqa: BLE001
        return False
    return (os.environ.get("COLONY_LEARNED_FAMILY_SKIP") or "live").strip().lower() != "off"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def family_key(statement: Any) -> str:
    """Stable key of a source claim statement ("" when unknown)."""
    s = " ".join(str(statement or "").split()).lower()
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16] if s else ""


def _jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        if Path(path).exists():
            for ln in Path(path).read_text(encoding="utf-8").splitlines():
                if not ln.strip():
                    continue
                try:
                    row = json.loads(ln)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    out.append(row)
    except OSError:
        pass
    return out


def _generator_rows() -> list[dict[str, Any]]:
    try:
        from colony.target_generator import log_path
        return _jsonl(log_path())
    except Exception:  # noqa: BLE001
        return []


def name_families(rows: Iterable[Mapping[str, Any]] | None = None) -> dict[str, str]:
    """authored_mut name -> family key (from the generator's ``authored`` rows)."""
    out: dict[str, str] = {}
    for r in (rows if rows is not None else _generator_rows()):
        if r.get("event") == "authored" and r.get("name"):
            fk = family_key(r.get("source_statement"))
            if fk:
                out[str(r["name"])] = fk
    return out


def judged_names(lessons: Iterable[Mapping[str, Any]] | None = None, *, before: str = "") -> set[str]:
    """authored_mut names with a judged lesson (not just their own birth record)."""
    out: set[str] = set()
    for e in (lessons if lessons is not None else _jsonl(LESSONS)):
        m = str(e.get("mutation") or "")
        if not m.startswith(PREFIX) or str(e.get("type") or "") in BIRTH_TYPES:
            continue
        if before and str(e.get("ts") or "") >= before:
            continue
        out.add(m)
    return out


class Snapshot:
    """Read-only view built once per call site: which families are learned."""

    def __init__(self, gen_rows: Iterable[Mapping[str, Any]] | None = None,
                 lessons: Iterable[Mapping[str, Any]] | None = None, *, before: str = ""):
        self.families = name_families(gen_rows)
        self.judged = judged_names(lessons, before=before)
        self.learned: dict[str, str] = {}
        for n in sorted(self.judged):
            fk = self.families.get(n)
            if fk and fk not in self.learned:
                self.learned[fk] = n

    def learned_by_statement(self, statement: Any) -> str | None:
        """The judged member that makes this source claim's family learned, or None."""
        return self.learned.get(family_key(statement))

    def learned_by_name(self, name: str) -> str | None:
        """For a never-judged authored_mut variant: the judged sibling, or None."""
        if not str(name).startswith(PREFIX) or name in self.judged:
            return None
        fk = self.families.get(str(name))
        return self.learned.get(fk) if fk else None


def snapshot() -> Snapshot | None:
    """None when the switch is off (callers then behave exactly as before)."""
    if not enabled():
        return None
    try:
        return Snapshot()
    except Exception:  # noqa: BLE001  (fail open to old behaviour, never to new credit)
        return None


def _log_path() -> Path:
    return Path(os.environ.get("COLONY_LEARNED_FAMILY_LOG") or LOG)


def log(row: dict[str, Any]) -> None:
    p = _log_path()
    if os.environ.get("PYTEST_CURRENT_TEST") and p == LOG:
        return  # never write the real commons from a unit test
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": _utc(), **row, "authorized": False}, sort_keys=True, default=str) + "\n")
    except OSError:
        pass


def give_slot(cycle_id: str, *, freed: list[str], source: str, supply: Any = None) -> dict[str, Any]:
    """A desk turn freed by the skip goes to one bank-v2 refill (shared supply log, both arms)."""
    if not enabled() or not freed:
        return {"given": False, "reason": "off" if not enabled() else "nothing_freed"}
    try:
        ts = supply or __import__("colony.target_supply", fromlist=["x"])
        rep = ts.slot_refill(cycle_id)
    except Exception as exc:  # noqa: BLE001
        rep = {"error": f"{type(exc).__name__}: {str(exc)[:120]}"}
    out = {"given": True, "to": "bank_v2_refill", "refill": rep}
    log({"event": "slot_given", "cycle_id": cycle_id, "source": source, "freed": list(freed)[:12],
         "refill": {k: v for k, v in (rep or {}).items() if k != "entries"}})
    return out
