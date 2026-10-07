"""human_guide: seek machine-checkable invariants; compose lemma chains."""
from __future__ import annotations

from colony.lessons import (
    write_human_guide,
    guide_prefers_invariant_chains,
    preferred_invariant_mutations,
    seek_proposal_from_guides,
    INVARIANT_CHAIN_MUTATIONS,
)
from colony.emergence.spark import lesson_priors_for_spark
from colony.exploration_budget import pick_mutation_order


def _seed_guides(tmp_path, monkeypatch):
    import colony.lessons as L

    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")

    write_human_guide(
        what="SEEK machine-checkable invariants (combinatorics/FFT/kinematics)",
        author="James Jackson",
        mutation="seek_machine_checkable_invariants",
        catalog_hint={
            "prefer": ["invariant", "machine_checkable", "combinatorics"],
            "prefer_mutations": ["derived_chain_stress", "energy_work"],
            "add_mutation": "derived_chain_stress",
            "avoid": ["process_spam", "isolated_rename"],
        },
        skill_bias={"gather": 0.1, "oracle": 0.05},
        genome_prior={"gather": 0.05},
        tags=["human_guide", "invariant", "seek", "machine_checkable"],
    )
    write_human_guide(
        what="COMPOSE proven lemmas into longer proof chains — not isolated renames",
        author="James Jackson",
        mutation="compose_chain_proven_lemmas",
        catalog_hint={
            "prefer": ["lemma_chain", "derived_chain", "compose_lemmas"],
            "chain": ["workload_derived_chain", "derived_chain_stress"],
            "add_mutation": "derived_chain_stress",
            "avoid": ["isolated_rename", "process_spam"],
        },
        skill_bias={"build": 0.1},
        genome_prior={"build": 0.06},
        tags=["human_guide", "invariant", "chain", "compose", "derived_chain"],
    )


def test_guide_prefers_invariant_chains(tmp_path, monkeypatch):
    _seed_guides(tmp_path, monkeypatch)
    assert guide_prefers_invariant_chains() is True
    pref = preferred_invariant_mutations()
    assert pref[0] == "derived_chain_stress"
    assert "energy_work" in pref or "workload_derived_chain" in pref
    assert all(m in pref or m in INVARIANT_CHAIN_MUTATIONS for m in pref[:3])


def test_seek_prefers_chain_mutation(tmp_path, monkeypatch):
    _seed_guides(tmp_path, monkeypatch)
    # Become/process-spam avoid is optional — invariant guides alone enable seek
    pick = seek_proposal_from_guides(cycle_id="t_inv")
    assert pick is not None
    title, hyp, action = pick
    assert "derived_chain_stress" in action or "Chain" in title or "seek_enable:" in action
    assert "isolated rename" in hyp.lower() or "compose" in hyp.lower() or "invariant" in hyp.lower()


def test_spark_priors_surface_invariant_chains(tmp_path, monkeypatch):
    _seed_guides(tmp_path, monkeypatch)
    priors = lesson_priors_for_spark(limit=8)
    assert "invariant_chains" in priors or "derived_chain" in priors or "SEEK" in priors or "COMPOSE" in priors


def test_pick_mutation_order_boosts_chains(tmp_path, monkeypatch):
    _seed_guides(tmp_path, monkeypatch)
    import colony.exploration_budget as EB

    monkeypatch.setattr(EB, "BUDGET_PATH", tmp_path / "exploration_budget.json")
    cands = [
        ("easy_pad_square_again", "easy_pad", "pad"),
        ("vandermonde_conv", "hard_enable", "enable:vandermonde_conv"),
        ("derived_chain_stress", "hard_enable", "enable:derived_chain_stress"),
        ("energy_work", "stem_enable", "enable:energy_work"),
        ("workload_derived_chain", "hard_enable", "enable:workload_derived_chain"),
    ]
    ordered = pick_mutation_order(cands)
    names = [n for n, _, _ in ordered]
    # Chain / invariant mutations should lead easy pads / arbitrary hard enables
    assert names.index("derived_chain_stress") < names.index("easy_pad_square_again")
    assert names.index("workload_derived_chain") < names.index("easy_pad_square_again") or names.index(
        "energy_work"
    ) < names.index("easy_pad_square_again")
