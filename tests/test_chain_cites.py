"""human_guide: chain proposals cite proven lemmas + society/benchmarks artifacts."""
from __future__ import annotations

import json

from colony.lessons import (
    write_human_guide,
    guide_requires_chain_cites,
    chain_citations,
    chain_cite_note,
    chain_cite_evidence,
    seek_proposal_from_guides,
)
from colony.findings_coupling import hearing_score_proposal


def _seed(tmp_path, monkeypatch, *, cite: bool = True):
    import colony.lessons as L

    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")
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
        tags=["human_guide", "invariant", "chain", "compose", "derived_chain"],
    )
    if cite:
        write_human_guide(
            what="CITE proven lemmas + society/benchmarks artifacts in chain proposals",
            author="James Jackson",
            mutation="chain_cite_proven_lemmas_and_benchmarks",
            catalog_hint={"require": ["bench_cite", "lemma_cite"], "add_mutation": "derived_chain_stress"},
            tags=["human_guide", "cite", "cite_benchmarks", "cite_lemmas"],
        )


def _fake_bench(tmp_path, monkeypatch, *, chain_pass: bool = True):
    """Tiny artifact tree so lookups are proven to come from the repo, not hardcoded."""
    import colony.lessons as L

    root = tmp_path / "repo"
    art = root / "society" / "benchmarks" / "artifacts"
    art.mkdir(parents=True)
    (art / "toy_impl.py").write_text(
        "def check_alpha(n):\n    return True\n\n"
        "def check_beta(n):\n    return True\n\n"
        "def check_toy_chain():\n    return check_alpha(1) and check_beta(2)\n\n"
        "LEMMAS = [\n"
        "    ('alpha_lemma', lambda: all(check_alpha(n) for n in range(3)), True),\n"
        "    ('beta_lemma', lambda: check_beta(1), True),\n"
        "    ('toy_chain', check_toy_chain, True),\n"
        "]\n",
        encoding="utf-8",
    )
    (root / "society" / "benchmarks" / "toy_microbench.py").write_text(
        "PATH = 'artifacts/toy_impl.py'\n", encoding="utf-8"
    )
    latest = {
        "benches": [
            {"checks": {"hard:alpha_lemma": True, "hard:beta_lemma": False, "hard:toy_chain": chain_pass}}
        ]
    }
    (root / "society" / "benchmarks" / "latest.json").write_text(json.dumps(latest), encoding="utf-8")
    monkeypatch.setattr(L, "ROOT", root)
    monkeypatch.setattr(L, "BENCH_DIR", root / "society" / "benchmarks")
    monkeypatch.setattr(L, "BENCH_ARTIFACTS_DIR", art)
    monkeypatch.setattr(L, "BENCH_LATEST", root / "society" / "benchmarks" / "latest.json")


def test_guide_flag(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, cite=False)
    assert guide_requires_chain_cites() is False
    _seed(tmp_path, monkeypatch, cite=True)
    assert guide_requires_chain_cites() is True


def test_citations_looked_up_from_artifacts(tmp_path, monkeypatch):
    _fake_bench(tmp_path, monkeypatch)
    c = chain_citations("toy_chain")
    assert c is not None
    assert c["artifact"] == "society/benchmarks/artifacts/toy_impl.py"
    assert c["function"] == "check_toy_chain"
    assert [l["lemma"] for l in c["links"]] == ["alpha_lemma", "beta_lemma"]
    # Only lemmas passing in latest.json count as proven
    assert [l["proven"] for l in c["links"]] == [True, False]
    assert c["chain_proven"] is True
    assert c["bench"] == ["society/benchmarks/toy_microbench.py"]
    note = chain_cite_note(c)
    assert "society/benchmarks/artifacts/toy_impl.py::check_toy_chain" in note
    assert "proven lemmas [alpha_lemma]" in note and "unverified links [beta_lemma]" in note


def test_no_artifact_no_invented_cite(tmp_path, monkeypatch):
    _fake_bench(tmp_path, monkeypatch)
    assert chain_citations("not_a_real_chain") is None
    assert chain_cite_note(None) == ""


def test_real_repo_chain_cites_derived_chain_stress():
    c = chain_citations("derived_chain_stress")
    assert c is not None
    assert c["artifact"].startswith("society/benchmarks/artifacts/")
    assert any(l["lemma"] == "workload_derived_chain" for l in c["links"])
    assert c["bench"], "a microbench must run the artifact"


def test_seek_chain_proposal_carries_cite_and_survives_hearing_rule(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, cite=True)
    pick = seek_proposal_from_guides(cycle_id="t_cite")
    assert pick is not None
    title, hyp, action = pick
    assert action.startswith("seek_enable:")
    assert "society/benchmarks/artifacts/" in hyp
    ev = chain_cite_evidence(action)
    assert any(e.startswith("society/benchmarks/") for e in ev)
    verdict, rationale = hearing_score_proposal(
        title=title,
        hypothesis=hyp,
        evidence_urls=["charter:civilization-freedom", "cycle:t", *ev],
        cited=0,
        prior_titles=set(),
        fitness_aggregate=0.8,
    )
    assert "without citing society/benchmarks" not in rationale


def test_hearing_still_rejects_uncited_chain():
    # The hearing rule is untouched: a lemma/bench claim with no bench path still fails.
    verdict, rationale = hearing_score_proposal(
        title="Chain `derived_chain_stress` from invariant priors",
        hypothesis="Compose proven lemmas into a longer chain for more fitness.",
        evidence_urls=["charter:civilization-freedom"],
        cited=0,
        prior_titles=set(),
        fitness_aggregate=0.8,
    )
    assert verdict == "reject"
    assert "society/benchmarks" in rationale


def test_without_cite_guide_no_evidence_added(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, cite=False)
    assert chain_cite_evidence("seek_enable:derived_chain_stress") == []
