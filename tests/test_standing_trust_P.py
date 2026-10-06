"""Phase 3 — P scoring + gate filters authorize queue."""
from __future__ import annotations

from colony.standing_trust import (
    STANDING_TRUST_P_MIN,
    compute_proposal_P,
    meets_standing_trust,
)


def test_compute_proposal_P_range():
    P, terms = compute_proposal_P(
        mutation="some_novel_thing",
        action="hard_enable:vandermonde_asymmetric",
        fingerprint="deadbeef0001",
        oracle={"passed": True, "fitness_credit": True, "hear": {"bus_ok": True}},
        novelty={"textbook_reuse": 0.0},
        bench_delta=0.05,
        lesson_consistency=1.0,
    )
    assert P is not None
    assert 0.0 <= P <= 1.0
    assert terms["P_oracle"] == 1.0
    assert terms["P_novelty"] == 1.0
    assert P >= 0.7  # strong evidence should clear gate


def test_P_kill_oracle_low():
    P, terms = compute_proposal_P(
        mutation="vandermonde",
        action="claim",
        fingerprint="x",
        oracle={"passed": False, "fitness_credit": False, "hear": {"bus_ok": True}},
        novelty={"textbook_reuse": 0.9},
        bench_delta=-0.01,
        lesson_consistency=0.0,
    )
    assert P is not None
    assert P < STANDING_TRUST_P_MIN


def test_meets_standing_trust_gate():
    assert meets_standing_trust(0.70, machine_checked=True) is True
    assert meets_standing_trust(0.69, machine_checked=True) is False
    assert meets_standing_trust(0.99, machine_checked=False) is False
    assert meets_standing_trust(None, machine_checked=True) is False


def test_repeat_blocks_novelty_term(tmp_path, monkeypatch):
    import colony.lessons as L

    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")
    L.write_lesson(
        decision="block",
        check="dedupe",
        what="blocked",
        source="growth_hearing",
        lesson_type="repeat_proposal",
        proposal_fingerprint="fp_repeat_1",
    )
    P, terms = compute_proposal_P(
        mutation="Deepen compute",
        action="mandate:cite",
        fingerprint="fp_repeat_1",
        oracle={"passed": True, "fitness_credit": True, "hear": {"bus_ok": True}},
        novelty={"textbook_reuse": 0.0},
        bench_delta=0.1,
        lesson_consistency=0.4,
    )
    assert terms["P_novelty"] == 0.0


def test_catalog_not_exhausted_has_new_mutations():
    from colony.conjecture_mutations import all_snippets, MUTATION_SNIPPETS

    names = {n for n, _, _ in all_snippets()}
    for need in (
        "vandermonde_asymmetric",
        "binomial_hockey_deep",
        "fibonacci_cassini_ext",
        "derived_chain_stress",
    ):
        assert need in names
    # Disabled in lemma_impl so desk can hard_enable
    from society.benchmarks.artifacts.lemma_impl import HARD_TIER_LEMMAS

    by = {n: en for n, _, en in HARD_TIER_LEMMAS}
    assert by.get("vandermonde_asymmetric") is False
