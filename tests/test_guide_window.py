"""human_guide rows stay active however far back they sit in lessons.jsonl."""
from __future__ import annotations

import json

from colony.lessons import (
    load_human_guides,
    _lessons_with_guides,
    guide_prefers_invariant_chains,
    catalog_hints_from_lessons,
    digest,
)


def _write(path, rows):
    with path.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_old_guide_beyond_window_still_active(tmp_path, monkeypatch):
    import colony.lessons as L

    path = tmp_path / "lessons.jsonl"
    monkeypatch.setattr(L, "LESSONS_JSONL", path)
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")
    guide = {
        "id": "les_old_guide",
        "type": "human_guide",
        "decision": "guide",
        "what": "COMPOSE proven lemmas into chains",
        "catalog_hint": {"prefer": ["lemma_chain"], "add_mutation": "derived_chain_stress"},
        "tags": ["human_guide", "chain"],
        "expired": False,
    }
    _write(path, [guide])
    # Bury it far beyond any recent-N window (old code only looked at the last 400)
    noise = [
        {"id": f"les_noise_{i}", "type": "oracle_kill", "decision": "revert", "mutation": f"m{i}", "tags": []}
        for i in range(1200)
    ]
    _write(path, noise)
    assert len(L.load_lessons(limit=400)) == 400
    assert all(e["id"] != "les_old_guide" for e in L.load_lessons(limit=400))

    guides = load_human_guides()
    assert [g["id"] for g in guides] == ["les_old_guide"]
    assert any(e.get("id") == "les_old_guide" for e in _lessons_with_guides(lookback=40))
    assert guide_prefers_invariant_chains() is True
    assert any(h.get("add_mutation") == "derived_chain_stress" for h in catalog_hints_from_lessons(lookback=20))
    assert "COMPOSE" in digest(limit=5)


def test_guide_cache_refreshes_on_append_and_skips_expired(tmp_path, monkeypatch):
    import colony.lessons as L

    path = tmp_path / "lessons.jsonl"
    monkeypatch.setattr(L, "LESSONS_JSONL", path)
    _write(path, [{"id": "g1", "type": "human_guide", "decision": "guide", "expired": False}])
    assert [g["id"] for g in load_human_guides()] == ["g1"]
    _write(path, [
        {"id": "g2", "type": "human_guide", "decision": "guide", "expired": True},
        {"id": "g3", "type": "human_guide", "decision": "guide", "expired": False},
    ])
    assert [g["id"] for g in load_human_guides()] == ["g1", "g3"]
    assert [g["id"] for g in load_human_guides(include_expired=True)] == ["g1", "g2", "g3"]


def test_uptake_counts_old_guides(tmp_path, monkeypatch):
    import colony.lessons as L
    from colony.fitness import _lesson_uptake_term

    path = tmp_path / "lessons.jsonl"
    monkeypatch.setattr(L, "LESSONS_JSONL", path)
    _write(path, [{
        "id": "g_old", "type": "human_guide", "decision": "guide", "expired": False,
        "skill_bias": {"gather": 0.1}, "catalog_hint": {"add_mutation": "x"},
    }])
    _write(path, [{"id": f"n{i}", "type": "skip", "decision": "skip"} for i in range(500)])
    assert _lesson_uptake_term() > 0.0
