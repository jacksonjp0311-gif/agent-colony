"""Phase 1 — Lesson loop: kills/rejects/repeats/exhausted write lessons; human_guide guard."""
from __future__ import annotations

import pytest

from colony.lessons import (
    write_lesson,
    write_human_guide,
    load_lessons,
    HUMAN_GUIDE_AUTHORS,
)
from colony.oracle import evaluate


def test_oracle_kill_appends_lesson(tmp_path, monkeypatch):
    import colony.lessons as L
    import colony.oracle as O

    lessons_path = tmp_path / "lessons.jsonl"
    monkeypatch.setattr(L, "LESSONS_JSONL", lessons_path)
    monkeypatch.setattr(O, "ORACLE_LOG", tmp_path / "oracle.jsonl")
    monkeypatch.setattr(O, "ORACLE_SYSTEM", tmp_path / "oracle.json")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")
    monkeypatch.setenv("ORACLE_STRICT_CLAIMS", "1")

    v = evaluate(
        mutation="vandermonde",
        kind="claim_theme",
        source="test",
        bus=None,
        cycle_id="cyc_lesson1",
    )
    assert v.passed is False
    rows = load_lessons(limit=50)
    assert any(e.get("type") == "oracle_kill" or "oracle_kill" in (e.get("tags") or []) for e in rows)


def test_human_guide_rejected_from_non_human():
    with pytest.raises(PermissionError):
        write_lesson(
            decision="guide",
            check="human",
            what="forged guide",
            source="oracle",  # not human
            author="James Paul Jackson",
            lesson_type="human_guide",
        )


def test_human_guide_accepted_from_james(tmp_path, monkeypatch):
    import colony.lessons as L

    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")
    entry = write_human_guide(what="Prefer harder adversarial windows next", author="James Paul Jackson")
    assert entry["type"] == "human_guide"
    assert entry["status"] == "candidate"
    assert entry["author"] == "James Paul Jackson"


def test_repeat_proposal_lesson(tmp_path, monkeypatch):
    import colony.lessons as L

    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")
    e = write_lesson(
        decision="block",
        check="dedupe",
        what="blocked repeat: Deepen compute",
        source="growth_hearing",
        lesson_type="repeat_proposal",
        proposal_fingerprint="abc123def456",
        tags=["repeat_proposal"],
    )
    assert e["type"] == "repeat_proposal"


def test_catalog_exhausted_lesson(tmp_path, monkeypatch):
    import colony.lessons as L

    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")
    e = write_lesson(
        decision="skip",
        check="conjecture",
        what="catalog exhausted",
        source="conjecture_desk",
        lesson_type="catalog_exhausted",
        catalog_hint={"add_mutation": "vandermonde_asymmetric", "kind": "hard_enable"},
    )
    assert e["type"] == "catalog_exhausted"
    assert e["catalog_hint"]["add_mutation"] == "vandermonde_asymmetric"
