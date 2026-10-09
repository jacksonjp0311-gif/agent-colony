"""Conjecture desk respects the same cooldown filter as seek (no cooled easy-pad retries)."""
from __future__ import annotations

import json

import pytest

PADS = [
    ("easy_pad_commutativity", "easy_pad", "pad"),
    ("easy_pad_abs_identity", "easy_pad", "pad"),
    ("easy_pad_diff_squares", "easy_pad", "pad"),
    ("stem_easy_pad_units", "stem_easy_pad", "pad"),
]


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    import colony.exploration_budget as B
    import colony.lessons as L

    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")
    monkeypatch.setattr(B, "BUDGET_PATH", tmp_path / "exploration_budget.json")
    monkeypatch.setattr(B, "HISTORY", tmp_path / "conjecture_history.jsonl")
    return tmp_path


def _kill(mutation, n):
    from colony.lessons import write_lesson
    for i in range(n):
        write_lesson(decision="revert", check="oracle", what="kill", source="conjecture_desk",
                     mutation=mutation, lesson_type="oracle_kill", family="easy_pad", cycle_id=f"k{mutation}{i}")


def test_filter_reasons_kill_guide_penalty():
    from colony.lessons import MutationCooldown

    cd = MutationCooldown(
        blocked={"easy_pad_commutativity": "kill_cooldown:4"},
        avoided={"easy_pad", "dup"},  # "dup" < 6 chars → label, ignored
        penalties={"hard_x": 3, "hard_y": 2},
    )
    assert cd.reason("easy_pad_commutativity") == "kill_cooldown:4"
    assert cd.reason("easy_pad_diff_squares") == "guide_avoid:easy_pad"
    assert cd.reason("stem_easy_pad_units") == "guide_avoid:easy_pad"
    assert cd.reason("hard_x") == "revert_penalty:3"
    assert cd.allows("hard_y")
    assert cd.allows("dup_window_check")
    assert cd.allows("authored_bell_triangle_recurrence__hermite_recurrence_w1")


def test_mutation_cooldown_reads_kills_and_penalties(sandbox):
    from colony.exploration_budget import record_outcome
    from colony.lessons import mutation_cooldown

    _kill("easy_pad_commutativity", 3)
    _kill("easy_pad_abs_identity", 2)  # below threshold
    for _ in range(3):
        record_outcome("binomial_hockey_deep", "revert", kind="hard_enable")
    cd = mutation_cooldown()
    assert cd.reason("easy_pad_commutativity").startswith("kill_cooldown:")
    assert cd.allows("easy_pad_abs_identity")
    assert cd.reason("binomial_hockey_deep") == "revert_penalty:3"


def test_human_guide_block_respected(sandbox):
    from colony.lessons import mutation_cooldown, next_unblocked_mutation, write_human_guide

    write_human_guide(what="drop easy pads", author="James Jackson",
                      catalog_hint={"avoid": ["easy_pad"], "drop_theme": ["vandermonde_asymmetric"]})
    cd = mutation_cooldown()
    for name, _k, _s in PADS:
        assert not cd.allows(name), name
    assert not cd.allows("vandermonde_asymmetric_w2")
    assert next_unblocked_mutation(["easy_pad_abs_identity", "vandermonde_asymmetric", "derived_chain_stress"]) == "derived_chain_stress"


def test_desk_pick_skips_cooled_pad(sandbox):
    import colony.conjecture_desk as D
    from colony.lessons import mutation_cooldown

    _kill("easy_pad_commutativity", 3)
    ordered = [PADS[0], ("fresh_hard_check", "hard_enable", "enable:fresh_hard_check")]
    name, kind, _snip, cooled = D.pick_mutation(ordered, cooldown=mutation_cooldown(), lemma_src="")
    assert name == "fresh_hard_check" and kind == "hard_enable"
    assert cooled["easy_pad_commutativity"].startswith("kill_cooldown:")


def test_desk_pick_never_forces_a_cooled_pad(sandbox):
    import colony.conjecture_desk as D
    from colony.lessons import mutation_cooldown

    _kill("easy_pad_diff_squares", 3)
    name, *_rest, cooled = D.pick_mutation(
        PADS, cooldown=mutation_cooldown(), force_mutation="easy_pad_diff_squares", lemma_src="")
    assert name is None and "easy_pad_diff_squares" in cooled


def test_desk_falls_through_to_authoring_when_all_cooled(sandbox, monkeypatch):
    import colony.authoring as A
    import colony.conjecture_desk as D
    import colony.conjecture_mutations as CM
    import colony.exploration_budget as B
    import colony.lessons as L

    for name, _k, _s in PADS:
        _kill(name, 3)
    impl = sandbox / "lemma_impl.py"
    impl.write_text("CHECKS = []\n")
    monkeypatch.setattr(D, "LEMMA_IMPL", impl)
    monkeypatch.setattr(D, "KINEMATICS_IMPL", sandbox / "kin.py")
    monkeypatch.setattr(D, "BACKUP_DIR", sandbox / "b1")
    monkeypatch.setattr(D, "STEM_BACKUP_DIR", sandbox / "b2")
    monkeypatch.setattr(D, "_load_paper_themes", lambda limit=12: [])
    monkeypatch.setattr(D, "propose_from_themes", lambda *a, **k: [])
    monkeypatch.setattr(D, "run_lemma_bench", lambda: {"score": 0.9, "ok": True})
    monkeypatch.setattr(D, "run_stem_bench", lambda: pytest.fail("cooled STEM pad was picked"))
    monkeypatch.setattr(D, "all_snippets", lambda: list(PADS))
    monkeypatch.setattr(D, "recent_revert_counts", lambda limit=30: {})
    monkeypatch.setattr(D, "_append_history", lambda r: None)
    monkeypatch.setattr(D, "_write_witness", lambda rs: None)
    monkeypatch.setattr(L, "variant_mutation_snippets", lambda: [("unenabled_v", "hard_enable", "x")])
    monkeypatch.setattr(B, "pick_mutation_order", lambda c: list(c))
    monkeypatch.setattr(CM, "register_mutation_candidate", lambda *a, **k: None)
    calls = []
    monkeypatch.setattr(A, "guide_authoring_active", lambda: True)
    monkeypatch.setattr(A, "author_checks", lambda **k: calls.append(k) or [{"name": "authored_new_w1", "accepted": True}])
    # the variant must not be pickable either, so everything is cooled/done
    monkeypatch.setattr(D, "_already_has", lambda src, name: name == "unenabled_v")

    r = D.improve_once(cycle_id="cyc_all_cooled")
    assert r.decision == "skip" and not r.mutation
    assert calls, "authoring should run when every candidate is cooled"
    assert "Cooled/blocked skipped" in r.note and "authored_new_w1" in r.note
    for name, _k, _s in PADS:
        assert name in r.note
    rows = [json.loads(l) for l in (sandbox / "lessons.jsonl").read_text().splitlines()]
    hint = [e for e in rows if e.get("type") == "catalog_exhausted"][-1]["catalog_hint"]
    assert "easy_pad" not in str(hint.get("add_mutation") or "")


def test_cooldown_unavailable_fails_closed(sandbox, monkeypatch):
    import colony.conjecture_desk as D
    import colony.lessons as L

    def boom(**_):
        raise RuntimeError("no ledger")

    monkeypatch.setattr(L, "mutation_cooldown", boom)
    impl = sandbox / "lemma_impl.py"
    impl.write_text("CHECKS = []\n")
    monkeypatch.setattr(D, "LEMMA_IMPL", impl)
    monkeypatch.setattr(D, "BACKUP_DIR", sandbox / "b1")
    monkeypatch.setattr(D, "STEM_BACKUP_DIR", sandbox / "b2")
    monkeypatch.setattr(D, "_load_paper_themes", lambda limit=12: [])
    monkeypatch.setattr(D, "propose_from_themes", lambda *a, **k: [])
    monkeypatch.setattr(D, "run_lemma_bench", lambda: {"score": 0.9, "ok": True})
    monkeypatch.setattr(D, "all_snippets", lambda: [("fresh_hard_check", "hard_enable", "x")])
    monkeypatch.setattr(D, "_append_history", lambda r: None)
    monkeypatch.setattr(D, "_write_witness", lambda rs: None)
    r = D.improve_once(cycle_id="c")
    assert r.decision == "skip" and "fail closed" in r.note
