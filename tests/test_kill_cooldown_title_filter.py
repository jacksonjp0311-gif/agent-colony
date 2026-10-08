"""Kill cooldown counts only real Oracle kills of a lemma/claim — never title-only kills of a
seek proposal whose target resolved. Guide-based blocks are separate and persist."""
from __future__ import annotations

import json

import pytest

import colony.lessons as L
from colony.lessons import (
    KILL_COOLDOWN_THRESHOLD,
    blocked_themes,
    is_title_only_kill,
    oracle_kill_theme_counts,
    theme_is_blocked,
)

TARGET = "adversarial_hockey_deep"  # real catalog entry → resolves


def _kill(mutation, *, source, family, i):
    return {"id": f"les_k{i}", "ts": f"2026-10-07T20:{i:02d}:00Z", "cycle_id": f"c{i}",
            "type": "oracle_kill", "decision": "revert", "check": "oracle", "mutation": mutation,
            "what": "Oracle FAIL kills keep.", "source": source, "family": family,
            "skill_bias": {}, "genome_prior": {}, "catalog_hint": {}, "tags": ["oracle_kill"]}


def _guide(theme):
    return {"id": "les_guide_drop", "ts": "2026-10-07T09:00:00Z", "type": "human_guide",
            "decision": "guide", "check": "human", "mutation": "", "source": "human",
            "author": "James Jackson", "what": f"Drop {theme}.",
            "catalog_hint": {"drop_theme": [theme]}, "tags": ["human_guide"]}


@pytest.fixture
def lessons(tmp_path, monkeypatch):
    path = tmp_path / "lessons.jsonl"
    monkeypatch.setattr(L, "LESSONS_JSONL", path)

    def write(rows):
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return write


def test_title_only_kills_of_resolved_target_are_ignored(lessons):
    titles = [f"Chain `{TARGET}` citing Some paper", f"Seek `{TARGET}` citing X (cycle 9)",
              f"Chain `{TARGET}` citing Some paper", f"Chain `{TARGET}` citing Y"]
    rows = [_kill(t, source="novelty_gate", family="process", i=i) for i, t in enumerate(titles)]
    lessons(rows)
    assert all(is_title_only_kill(r) for r in rows)
    assert TARGET not in oracle_kill_theme_counts()
    assert not theme_is_blocked(TARGET)


def test_real_kills_of_the_lemma_still_count_to_threshold(lessons):
    real = [_kill(TARGET, source="conjecture_desk", family="hard_enable", i=i) for i in range(3)]
    noise = [_kill(f"Chain `{TARGET}` citing P", source="novelty_gate", family="process", i=10 + i)
             for i in range(5)]
    lessons(real[:2] + noise)
    assert oracle_kill_theme_counts().get(TARGET) == 2
    assert not theme_is_blocked(TARGET)  # 2 real kills < 3; title noise adds nothing
    lessons(real + noise)
    assert oracle_kill_theme_counts().get(TARGET) == KILL_COOLDOWN_THRESHOLD == 3
    assert blocked_themes()[TARGET] == "kill_cooldown:3"


def test_unresolved_or_non_title_kills_keep_counting(lessons):
    # novelty-gate process kill on text that names no catalog entry: still counts (fail closed)
    unresolved = [_kill("Deepen compute-useful math from accepted findings", source="novelty_gate",
                        family="process", i=i) for i in range(3)]
    # a novelty-gate kill whose mutation IS the lemma (not a title) counts
    lemma_itself = [_kill(TARGET, source="novelty_gate", family="process", i=20 + i) for i in range(3)]
    lessons(unresolved + lemma_itself)
    assert not any(is_title_only_kill(r) for r in unresolved + lemma_itself)
    c = oracle_kill_theme_counts()
    assert c.get(TARGET) == 3
    assert sum(c.values()) == 6


def test_human_guide_drop_persists_regardless_of_counts(lessons):
    theme = "vandermonde_asymmetric"
    title_noise = [_kill(f"Seek `{theme}` citing P", source="novelty_gate", family="process", i=i)
                   for i in range(10)]
    lessons(title_noise + [_guide(theme)])
    assert theme not in oracle_kill_theme_counts()  # its title kills no longer count…
    assert blocked_themes()[theme] == "guide_avoid"  # …but James's drop guide still blocks it
    assert theme_is_blocked(theme)
    lessons([_guide(theme)])  # no kills at all
    assert theme_is_blocked(theme)
