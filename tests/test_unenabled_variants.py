"""human_guide: seek unenabled harder variants built from proven lemmas (discovered, cited)."""
from __future__ import annotations

import json

from colony.lessons import (
    write_human_guide,
    guide_seeks_unenabled_variants,
    unenabled_chain_variants,
    variant_mutation_snippets,
    preferred_variant_mutations,
    target_enabled,
    seek_proposal_from_guides,
    chain_cite_evidence,
)
from colony.findings_coupling import hearing_score_proposal


def _fake_repo(tmp_path, monkeypatch):
    import colony.lessons as L

    root = tmp_path / "repo"
    bench = root / "society" / "benchmarks"
    art = bench / "artifacts"
    art.mkdir(parents=True)
    (art / "toy_impl.py").write_text(
        "def check_a(n):\n    return True\n\n"
        "def check_b(n):\n    return True\n\n"
        "def check_chain():\n    return check_a(1) and check_b(2)\n\n"
        "def check_unproven_part():\n    return True\n\n"
        "def check_mixed():\n    return check_a(1) and check_unproven_part()\n\n"
        "check_adversarial_chain = check_chain\n\n"
        "LEMMAS = [\n"
        "    ('a_lemma', lambda: check_a(3), True),\n"
        "    ('b_lemma', lambda: check_b(3), True),\n"
        "    ('chain', check_chain, True),\n"
        "    ('unproven_part', check_unproven_part, False),\n"
        "    ('adversarial_chain', check_adversarial_chain, False),\n"
        "    ('mixed_variant', check_mixed, False),\n"
        "]\n",
        encoding="utf-8",
    )
    (bench / "toy_microbench.py").write_text("P = 'artifacts/toy_impl.py'\n", encoding="utf-8")
    latest = {"benches": [{"checks": {"hard:a_lemma": True, "hard:b_lemma": True, "hard:chain": True}}]}
    (bench / "latest.json").write_text(json.dumps(latest), encoding="utf-8")
    monkeypatch.setattr(L, "ROOT", root)
    monkeypatch.setattr(L, "BENCH_DIR", bench)
    monkeypatch.setattr(L, "BENCH_ARTIFACTS_DIR", art)
    monkeypatch.setattr(L, "BENCH_LATEST", bench / "latest.json")
    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")


def _guide():
    write_human_guide(
        what="SEEK harder unenabled variants built from proven lemmas; cite the artifacts",
        author="James Jackson",
        mutation="seek_unenabled_variants_from_proven_lemmas",
        catalog_hint={"prefer": ["unenabled_variants"], "require": ["bench_cite"]},
        tags=["human_guide", "seek_unproven", "unenabled_variant", "chain", "cite", "seek"],
    )


def test_variants_discovered_from_catalog_not_listed(tmp_path, monkeypatch):
    _fake_repo(tmp_path, monkeypatch)
    rows = unenabled_chain_variants()
    names = [r["name"] for r in rows]
    # adversarial_chain: disabled + built from proven chain/a/b -> found
    assert names == ["adversarial_chain"]
    r = rows[0]
    assert r["components"][0] == "chain" and set(r["components"]) == {"chain", "a_lemma", "b_lemma"}
    assert r["artifact"] == "society/benchmarks/artifacts/toy_impl.py"
    assert r["bench"] == ["society/benchmarks/toy_microbench.py"]
    # mixed_variant has an unproven component; unproven_part has no components -> excluded
    assert "mixed_variant" not in names and "unproven_part" not in names
    assert target_enabled("chain") is True
    assert target_enabled("adversarial_chain") is False
    assert target_enabled("no_such") is None


def test_guide_gates_desk_candidates(tmp_path, monkeypatch):
    _fake_repo(tmp_path, monkeypatch)
    assert guide_seeks_unenabled_variants() is False
    assert variant_mutation_snippets() == []
    _guide()
    assert guide_seeks_unenabled_variants() is True
    assert variant_mutation_snippets() == [("adversarial_chain", "hard_enable", "enable:adversarial_chain")]
    assert preferred_variant_mutations() == ["adversarial_chain"]


def test_guide_avoid_drops_variant(tmp_path, monkeypatch):
    _fake_repo(tmp_path, monkeypatch)
    _guide()
    write_human_guide(
        what="DROP chain theme",
        author="James Jackson",
        mutation="drop",
        catalog_hint={"avoid": ["adversarial_chain"]},
        tags=["human_guide", "drop"],
    )
    assert preferred_variant_mutations() == []


def test_pick_mutation_order_prefers_variants(tmp_path, monkeypatch):
    _fake_repo(tmp_path, monkeypatch)
    _guide()
    import colony.exploration_budget as EB

    monkeypatch.setattr(EB, "BUDGET_PATH", tmp_path / "exploration_budget.json")
    cands = [
        ("easy_pad_square_again", "easy_pad", "pad"),
        ("derived_chain_stress", "hard_enable", "enable:derived_chain_stress"),
        ("adversarial_chain", "hard_enable", "enable:adversarial_chain"),
    ]
    assert EB.pick_mutation_order(cands)[0][0] == "adversarial_chain"


def test_seek_skips_enabled_targets_and_cites(tmp_path, monkeypatch):
    _fake_repo(tmp_path, monkeypatch)
    _guide()
    pick = seek_proposal_from_guides(cycle_id="t_var")
    assert pick is not None
    title, hyp, action = pick
    assert action == "seek_enable:adversarial_chain"
    assert "not-yet-enabled variant" in hyp
    assert "society/benchmarks/artifacts/toy_impl.py" in hyp
    ev = chain_cite_evidence(action)
    assert "society/benchmarks/toy_microbench.py" in ev
    assert {"lemma:chain", "lemma:a_lemma", "lemma:b_lemma"} <= set(ev)
    verdict, rationale = hearing_score_proposal(
        title=title, hypothesis=hyp, evidence_urls=["cycle:t", *ev], cited=0,
        prior_titles=set(), fitness_aggregate=0.8,
    )
    assert "without citing society/benchmarks" not in rationale


def test_real_repo_variants_are_disabled_and_composed():
    for r in unenabled_chain_variants(respect_cooldown=False):
        assert target_enabled(r["name"]) is False
        assert r["components"]
        assert r["artifact"].startswith("society/benchmarks/artifacts/")


def test_spark_priors_surface_variants(tmp_path, monkeypatch):
    _fake_repo(tmp_path, monkeypatch)
    _guide()
    from colony.emergence.spark import lesson_priors_for_spark

    assert "unenabled_variants: adversarial_chain" in lesson_priors_for_spark(limit=8)
