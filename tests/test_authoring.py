"""Desk authoring of new disabled hard checks from proven lemmas (guide: become an author)."""
from __future__ import annotations

import ast
import json

import pytest

import colony.authoring as A
from colony.lessons import write_human_guide, write_lesson

BASE = '''
def check_a(n: int) -> bool:
    """sum of first n odds = n^2"""
    return sum(2 * i + 1 for i in range(n)) == n * n


def check_b(n: int) -> bool:
    """2^n via doubling"""
    x = 1
    for _ in range(n):
        x *= 2
    return x == (1 << n)


def check_triv(n: int) -> bool:
    return True


def check_self(n: int) -> bool:
    return n == n


{extra_fns}
# Adversarial aliases used by Oracle theme held-out windows (same callables)

CANDIDATE_LEMMAS = [
    ("a_lemma", lambda: all(check_a(n) for n in range(0, 10)), True),
]

HARD_TIER_LEMMAS = [
    ("b_lemma", lambda: all(check_b(n) for n in range(0, 10)), True),
    ("triv_lemma", lambda: all(check_triv(n) for n in range(0, 10)), True),
    ("self_lemma", lambda: all(check_self(n) for n in range(0, 10)), True),
{extra_entries}]
'''


def _repo(tmp_path, monkeypatch, *, extra_fns="", extra_entries="", latest=None):
    import colony.lessons as L

    root = tmp_path / "repo"
    bench = root / "society" / "benchmarks"
    art = bench / "artifacts"
    art.mkdir(parents=True)
    (art / "lemma_impl.py").write_text(
        BASE.format(extra_fns=extra_fns, extra_entries=extra_entries), encoding="utf-8"
    )
    (bench / "lemma_microbench.py").write_text("P = 'artifacts/lemma_impl.py'\n", encoding="utf-8")
    checks = latest or {"basic:a_lemma": True, "hard:b_lemma": True, "hard:triv_lemma": True, "hard:self_lemma": True}
    (bench / "latest.json").write_text(json.dumps({"benches": [{"checks": checks}]}), encoding="utf-8")
    for attr, val in (
        ("ROOT", root), ("BENCH_DIR", bench), ("BENCH_ARTIFACTS_DIR", art),
        ("BENCH_LATEST", bench / "latest.json"),
        ("LESSONS_JSONL", tmp_path / "lessons.jsonl"), ("LEDGER_SYSTEM", tmp_path / "ledger.json"),
    ):
        monkeypatch.setattr(L, attr, val)
    return art / "lemma_impl.py"


def _guide():
    write_human_guide(
        what="BECOME AN AUTHOR: compose proven lemmas into new disabled checks",
        author="James Jackson",
        mutation="author_new_hard_checks_from_proven_lemmas",
        catalog_hint={"prefer": ["author_new_checks"], "require": ["bench_cite"]},
        tags=["human_guide", "author_checks", "become_author", "unenabled_variant", "cite", "chain", "compose"],
    )


def test_generates_disabled_check_from_proven_lemmas(tmp_path, monkeypatch):
    path = _repo(tmp_path, monkeypatch)
    _guide()
    assert A.guide_authoring_active()
    rows = A.author_checks(cycle_id="t1")
    assert len(rows) == 1 and rows[0]["accepted"]
    name = rows[0]["name"]
    assert name == "authored_a_lemma__b_lemma_w1"
    src = path.read_text()
    ast.parse(src)
    assert f'("{name}", check_{name}, False),' in src  # written DISABLED
    # windows are disjoint from (past) the base range(0, 10)
    assert "range(10, 15)" in rows[0]["assertion"]
    from colony.lessons import target_enabled, unenabled_chain_variants, chain_citations
    assert target_enabled(name) is False
    var = {v["name"]: v for v in unenabled_chain_variants()}
    assert set(var[name]["components"]) == {"a_lemma", "b_lemma"}
    c = chain_citations(name)
    assert c["artifact"] == "society/benchmarks/artifacts/lemma_impl.py"
    assert c["bench"] == ["society/benchmarks/lemma_microbench.py"]
    # lesson cites component artifacts
    les = [json.loads(l) for l in (tmp_path / "lessons.jsonl").read_text().splitlines()]
    auth = [e for e in les if e.get("type") == "authored_check"]
    assert auth and any("::check_a" in x for x in auth[0]["evidence"])


def test_bounded_per_cycle(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch)
    _guide()
    assert len(A.author_checks(cycle_id="t", max_new=1)) <= 1
    assert A.MAX_AUTHORED_PER_CYCLE >= 1 and A.MAX_AUTHORED_TOTAL >= A.MAX_AUTHORED_PER_CYCLE


def test_trivial_components_excluded(tmp_path, monkeypatch):
    path = _repo(tmp_path, monkeypatch)
    names = [c["lemma"] for c in A.eligible_components(path.read_text())]
    assert names == ["a_lemma", "b_lemma"]  # `return True` and `n == n` rejected


def test_non_falsifiable_and_empty_window_rejected(tmp_path, monkeypatch):
    path = _repo(tmp_path, monkeypatch)
    src = path.read_text()
    empty = A.insert_disabled(src, "authored_empty", (
        "def check_authored_empty() -> bool:\n"
        "    return all(check_a(n) for n in range(5, 5)) and all(check_b(n) for n in range(5, 5))\n"
    ))
    r = A.verify_candidate(empty, "authored_empty", ["check_a", "check_b"])
    assert not r["accepted"] and r["reason"].startswith("trivial")
    taut = A.insert_disabled(src, "authored_taut", (
        "def check_authored_taut() -> bool:\n"
        "    return [check_a(n) for n in range(10, 15)] is not None and [check_b(n) for n in range(10, 15)] is not None\n"
    ))
    r = A.verify_candidate(taut, "authored_taut", ["check_a", "check_b"])
    assert not r["accepted"] and r["reason"] == "trivial:not_falsifiable"


def test_false_extension_rejected(tmp_path, monkeypatch):
    # A "lemma" that only holds on its base window must not be authored past it
    extra = "def check_small(n: int) -> bool:\n    return n * n < 100\n\n"
    path = _repo(tmp_path, monkeypatch, extra_fns=extra,
                 extra_entries="    (\"small_lemma\", lambda: all(check_small(n) for n in range(0, 10)), True),\n",
                 latest={"basic:a_lemma": True, "hard:b_lemma": True, "hard:small_lemma": True})
    _guide()
    rows = A.author_checks(cycle_id="t", max_new=3)
    assert all("small_lemma" not in r["name"] for r in rows)
    les = [json.loads(l) for l in (tmp_path / "lessons.jsonl").read_text().splitlines()]
    assert any(e.get("type") == "authoring_reject" and "small_lemma" in e["mutation"] for e in les)
    # rejected candidates are not retried (no reject spam)
    n_rej = sum(1 for e in les if e.get("type") == "authoring_reject")
    A.author_checks(cycle_id="t2", max_new=0)
    A.author_checks(cycle_id="t3", max_new=3)
    les2 = [json.loads(l) for l in (tmp_path / "lessons.jsonl").read_text().splitlines()]
    assert sum(1 for e in les2 if e.get("type") == "authoring_reject") == n_rej
    assert "check_small" in path.read_text()


def test_duplicate_body_rejected(tmp_path, monkeypatch):
    dup = ("    (\"my_copy\", lambda: all(check_a(n) for n in range(10, 15)) "
           "and all(check_b(n) for n in range(10, 15)), True),\n")
    _repo(tmp_path, monkeypatch, extra_entries=dup)
    _guide()
    assert A.author_checks(cycle_id="t") == []


def test_blocked_theme_respected(tmp_path, monkeypatch):
    path = _repo(tmp_path, monkeypatch)
    _guide()
    for i in range(3):  # kill cooldown on a_lemma
        write_lesson(decision="revert", check="oracle", what="kill", source="t",
                     mutation="a_lemma", lesson_type="oracle_kill", cycle_id=f"k{i}")
    assert "a_lemma" not in [c["lemma"] for c in A.eligible_components(path.read_text())]
    assert A.author_checks(cycle_id="t") == []


def test_seek_fallback_never_proposes_cooled(tmp_path, monkeypatch):
    import colony.lessons as L

    _repo(tmp_path, monkeypatch)
    _guide()

    class _All(dict):
        def __contains__(self, k):
            return True

    monkeypatch.setattr(L, "blocked_themes", lambda **kw: _All())
    assert L.seek_proposal_from_guides(cycle_id="t") is None


def test_seek_skips_cooled_and_targets_authored(tmp_path, monkeypatch):
    import colony.lessons as L

    _repo(tmp_path, monkeypatch)
    _guide()
    rows = A.author_checks(cycle_id="t1")
    name = rows[0]["name"]
    pick = L.seek_proposal_from_guides(cycle_id="t2")
    assert pick is not None and pick[2] == f"seek_enable:{name}"
    for i in range(3):
        write_lesson(decision="revert", check="oracle", what="kill", source="t",
                     mutation=name, lesson_type="oracle_kill", cycle_id=f"k{i}")
    pick2 = L.seek_proposal_from_guides(cycle_id="t3")
    assert pick2 is None or L.theme_key(pick2[2]) != name


def test_fresh_pass_on_authored_check_gets_P_credit(tmp_path, monkeypatch):
    import colony.standing_trust as ST

    _repo(tmp_path, monkeypatch)
    _guide()
    name = A.author_checks(cycle_id="t1")[0]["name"]
    log = tmp_path / "oracle.jsonl"
    log.write_text(json.dumps({
        "mutation": name, "kind": "hard_enable", "passed": True, "fitness_credit": True,
        "cycle_id": "c2", "sense": {"sense_pass": True}, "hear": {"bus_ok": False}, "kills": [],
    }) + "\n")
    monkeypatch.setattr(ST, "ORACLE_LOG", log)
    title = f"Chain `{name}` citing X"
    assert ST.resolve_proposal_target(action=f"seek_enable:{name}", mutation=title) == name
    P, terms = ST.compute_proposal_P(
        mutation=title, action=f"seek_enable:{name}", novelty={"textbook_reuse": 0.0},
        bench_delta=0.0, cycle_id="c2",
    )
    assert terms["P_oracle"] == 1.0
    assert ST.meets_standing_trust(P, machine_checked=True)
    # same proposal, killed target → stays under the unchanged 0.70 gate
    log.write_text(json.dumps({"mutation": name, "passed": False, "cycle_id": "c2"}) + "\n")
    P2, t2 = ST.compute_proposal_P(
        mutation=title, action=f"seek_enable:{name}", novelty={"textbook_reuse": 0.0},
        bench_delta=0.5, cycle_id="c2",
    )
    assert t2["P_oracle"] == 0.0 and P2 < ST.STANDING_TRUST_P_MIN == 0.70
