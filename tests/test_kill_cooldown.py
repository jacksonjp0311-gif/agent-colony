"""Kill cooldown: drop repeatedly Oracle-killed themes; seek elsewhere."""
from __future__ import annotations

import json

from colony.lessons import (
    write_lesson,
    write_human_guide,
    theme_key,
    theme_is_blocked,
    blocked_themes,
    oracle_kill_theme_counts,
    next_unblocked_mutation,
    seek_proposal_from_guides,
)


def test_theme_key_from_seek_title():
    assert theme_key("Seek `vandermonde_asymmetric` citing New algebraic points") == "vandermonde_asymmetric"
    assert theme_key("seek_enable:binomial_hockey_deep") == "binomial_hockey_deep"
    assert theme_key("enable:fibonacci_cassini_ext") == "fibonacci_cassini_ext"


def test_kill_cooldown_blocks_after_threshold(tmp_path, monkeypatch):
    import colony.lessons as L

    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")

    for i in range(3):
        write_lesson(
            decision="revert",
            check="oracle",
            what=f"Oracle FAIL on vandermonde_asymmetric #{i}",
            source="oracle",
            lesson_type="oracle_kill",
            mutation=f"Seek `vandermonde_asymmetric` citing paper {i}",
            tags=["oracle_kill"],
        )

    counts = oracle_kill_theme_counts()
    assert counts.get("vandermonde_asymmetric", 0) >= 3
    assert theme_is_blocked("vandermonde_asymmetric") is True
    assert "vandermonde_asymmetric" in blocked_themes()

    # Unrelated theme still free
    assert theme_is_blocked("binomial_hockey_deep") is False


def test_guide_avoid_and_seek_skips_cooled(tmp_path, monkeypatch):
    import colony.lessons as L

    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")

    for i in range(3):
        write_lesson(
            decision="revert",
            check="oracle",
            what="kill",
            source="oracle",
            lesson_type="oracle_kill",
            mutation="Seek `vandermonde_asymmetric` citing x",
            tags=["oracle_kill"],
        )

    write_human_guide(
        what="DROP AFTER REPEATED KILLS: seek elsewhere",
        author="James Jackson",
        mutation="drop_test",
        catalog_hint={
            "avoid": ["vandermonde_asymmetric", "process_spam"],
            "drop_theme": ["vandermonde_asymmetric"],
            "prefer": ["novelty", "drop_cooled_theme"],
            "add_mutation": "binomial_hockey_deep",
            "seek": ["papers.jsonl", "ledger"],
        },
        skill_bias={"gather": 0.1},
        genome_prior={"explore": 0.05},
        tags=["human_guide", "seek", "kill_cooldown", "drop"],
    )
    # Become guide so seek_proposal_from_guides is enabled
    write_human_guide(
        what="BECOME: prefer novelty avoid process spam",
        author="James Jackson",
        mutation="become_test",
        catalog_hint={"prefer": ["novelty"], "avoid": ["process_spam"]},
        tags=["human_guide", "become"],
    )

    assert next_unblocked_mutation(
        ["vandermonde_asymmetric", "binomial_hockey_deep"]
    ) == "binomial_hockey_deep"

    pick = seek_proposal_from_guides(cycle_id="t")
    assert pick is not None
    title, hyp, action = pick
    assert "vandermonde_asymmetric" not in action
    assert "vandermonde_asymmetric" not in title
    assert "binomial_hockey_deep" in action or "seek_enable:" in action


def test_propose_improvement_blocks_cooled_theme(tmp_path, monkeypatch):
    import colony.lessons as L
    from colony.fitness import EvolutionEngine

    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")

    for i in range(3):
        write_lesson(
            decision="revert",
            check="oracle",
            what="kill",
            source="oracle",
            lesson_type="oracle_kill",
            mutation="Seek `vandermonde_asymmetric` citing x",
            tags=["oracle_kill"],
        )

    class FakeReg:
        def best_for(self, *_a, **_k):
            return "spark"

    eng = EvolutionEngine(
        state_data={"improvement_proposals": [], "improvements": []},
        registry=FakeReg(),
        workshop=None,
    )
    prop = eng.propose_improvement(
        cycle_id="cyc_cool",
        metrics={"aggregate": 0.8},
        title="Seek `vandermonde_asymmetric` citing paper",
        hypothesis="test",
        action="seek_enable:vandermonde_asymmetric",
    )
    assert prop.get("status") == "blocked_kill_cooldown"
    assert prop.get("cooled_theme") == "vandermonde_asymmetric"
    assert prop.get("attempted_by") == "spark"


def test_spark_priors_include_cooled(tmp_path, monkeypatch):
    import colony.lessons as L
    from colony.emergence.spark import lesson_priors_for_spark

    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")

    for i in range(3):
        write_lesson(
            decision="revert",
            check="oracle",
            what="kill",
            source="oracle",
            lesson_type="oracle_kill",
            mutation="Seek `vandermonde_asymmetric` citing x",
            tags=["oracle_kill"],
        )
    write_human_guide(
        what="DROP AFTER REPEATED KILLS",
        author="James Jackson",
        mutation="drop_prior",
        tags=["human_guide", "kill_cooldown", "drop"],
        catalog_hint={"drop_theme": ["vandermonde_asymmetric"], "avoid": ["vandermonde_asymmetric"]},
    )
    priors = lesson_priors_for_spark(limit=8)
    assert "cooled_themes" in priors
    assert "vandermonde_asymmetric" in priors
