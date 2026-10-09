"""Frontier desk: bounded evidence on open statements — never proof, never auto-disproof."""
from __future__ import annotations

import json

import pytest

import colony.frontier as FR


@pytest.fixture
def impl():
    return FR.load_impl()


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    import colony.exploration_budget as B
    import colony.lessons as L

    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")
    monkeypatch.setattr(B, "BUDGET_PATH", tmp_path / "exploration_budget.json")
    cat = json.loads(FR.CATALOG.read_text())
    monkeypatch.setattr(FR, "CATALOG", tmp_path / "frontier.json")
    monkeypatch.setattr(FR, "LOG", tmp_path / "frontier.jsonl")
    monkeypatch.setattr(FR, "SYSTEM", tmp_path / "frontier_system.json")
    (tmp_path / "frontier.json").write_text(json.dumps(cat))
    monkeypatch.setattr("colony.feeds.conj_sequence_items", lambda: [])
    return tmp_path


def _guide():
    from colony.lessons import write_human_guide
    write_human_guide(what="frontier", author="James Jackson", tags=["human_guide", "frontier"],
                      catalog_hint={"prefer": ["frontier"]})


def _target(cat, tid):
    return next(t for t in cat["targets"] if t["id"] == tid)


# ---------------------------------------------------------------- catalog + labeling

def test_catalog_is_labeled_evidence_not_proof():
    cat = json.loads(FR.CATALOG.read_text())
    assert cat["label"] == "bounded evidence, not proof" and cat["proof"] is False
    fams = {t["family"] for t in cat["targets"]}
    assert {"goldbach", "collatz", "legendre", "lehmer_totient", "erdos_straus", "twin_hl"} <= fams
    for t in cat["targets"]:
        assert t["proof"] is False and t["label"] == "bounded evidence, not proof"
        assert t["verified"] is None  # the colony starts with nothing it has not checked itself


def test_frontier_is_not_in_any_proof_scored_tier():
    from society.benchmarks.lemma_microbench import run as run_lemma
    names = " ".join(run_lemma()["checks"])
    for t in json.loads(FR.CATALOG.read_text())["targets"]:
        assert t["id"] not in names and t["family"] + "_" not in names.replace("legendre_duplication", "")
    assert FR.IMPL.parent.name != "artifacts"  # out of the lemma/artifact scans
    import colony.fitness as F
    assert "frontier" not in open(F.__file__, encoding="utf-8").read()


# ---------------------------------------------------------------- generation + guards

def test_task_generation_beyond_catalog_and_dedupe(sandbox):
    cat = FR.load_catalog()
    t = _target(cat, "goldbach_even")
    task, why = FR.make_task(t, done=set())
    assert why == "" and task["lo"] == 4 and task["hi"] == 4 + t["window"] - 1
    assert task["enabled"] is False and task["label"] == "bounded evidence, not proof"
    t["verified"] = {"lo": 4, "hi": 1000}
    task2, _ = FR.make_task(t, done=set())
    assert task2["lo"] == 1001  # strictly beyond the recorded range
    _, why2 = FR.make_task(t, done={task2["fingerprint"]})
    assert why2 == "dedupe"
    t["window"] = 5
    _, why3 = FR.make_task(t, done=set())
    assert why3.startswith("trivial")


def test_time_budget_reports_partial_prefix(impl):
    d = impl.Deadline(0.0)  # already expired
    r = impl.check_collatz(1, 10**7, d)
    assert r["complete"] is False and r["budget_hit"] is True and r["checked_hi"] < 10**7
    assert r["proof"] is False


def test_run_task_extends_and_spot_checks(sandbox, impl):
    cat = FR.load_catalog()
    t = _target(cat, "legendre_square_gap")
    task, _ = FR.make_task(t, done=set())
    res = FR.run_task(task, t, impl)
    assert res["outcome"] == "extended" and res["verified_hi"] == task["hi"]
    assert res["independent_spots"] >= 2 and res["proof"] is False
    FR.apply_result(t, res)
    assert t["verified"]["hi"] == task["hi"] and t["verified"]["label"] == "bounded evidence, not proof"


# ---------------------------------------------------------------- counterexample path

class _FakeImpl:
    """Primary checker that reports a 'counterexample' at n=50; independent verifier decides."""

    def __init__(self, real, independent_agrees: bool):
        self.real = real
        self.Deadline = real.Deadline
        agrees = independent_agrees

        def check(lo, hi, deadline):
            return real._result(lo, hi, 49, counterexample=50, deadline=deadline)

        def holds(n):
            return not agrees if n == 50 else True

        self.FAMILIES = {"goldbach": (check, holds)}


def test_counterexample_requires_independent_reverify_and_never_claims(sandbox, impl):
    cat = FR.load_catalog()
    t = _target(cat, "goldbach_even")
    task, _ = FR.make_task(t, done=set())
    # independent verifier disagrees → disagreement (checker bug), NOT a counterexample
    res = FR.run_task(task, t, _FakeImpl(impl, independent_agrees=False))
    assert res["outcome"] == "disagreement" and res["independent_confirms_failure"] is False
    # independent verifier agrees → candidate flagged for review, still not a claim
    t2 = _target(FR.load_catalog(), "goldbach_even")
    res2 = FR.run_task(task, t2, _FakeImpl(impl, independent_agrees=True))
    assert res2["outcome"] == "counterexample_candidate" and res2["proof"] is False
    FR.apply_result(t2, res2)
    assert t2["status"] == "counterexample_review"
    assert "NOT a disproof" in t2["review"]["note"]
    assert t2["verified"]["hi"] == 49  # only the checked prefix before n counts

    class W:
        rows = []

        def record(self, **kw):
            self.rows.append(kw)

    w = W()
    FR._witness(w, "c", t2, res2)
    assert w.rows[0]["kind"] == "frontier_counterexample_candidate"
    assert "NOT a disproof claim" in w.rows[0]["summary"] and "⚠" in w.rows[0]["summary"]


def test_review_status_blocks_target_and_cooldown_respected(sandbox):
    from colony.lessons import MutationCooldown
    cat = FR.load_catalog()
    cd = MutationCooldown(blocked={}, avoided={"frontier_collatz_descent"})
    _target(cat, "goldbach_even")["status"] = "counterexample_review"
    t, blocked = FR.pick_target(cat, cd)
    assert blocked["goldbach_even"] == "counterexample_review"
    assert blocked["collatz_descent"].startswith("guide_avoid")
    assert t is not None and t["id"] not in ("goldbach_even", "collatz_descent")


# ---------------------------------------------------------------- OEIS feed path

def test_oeis_recurrence_on_unused_terms_and_reverify(impl):
    terms = [0, 3]
    for _ in range(30):
        terms.append(6 * terms[-1] - 4 * terms[-2])
    r = impl.check_oeis_recurrence(terms, impl.Deadline(1))
    assert r["holds"] and r["order"] == 2 and r["unused_verified"] >= 6 and r["proof"] is False
    assert impl.reverify_oeis_recurrence(terms, r["order"], r["coeffs"])
    bad = terms[:]
    bad[-1] += 1  # one unused term off → no fit (honest negative)
    assert not impl.check_oeis_recurrence(bad, impl.Deadline(1))["holds"] or \
        impl.check_oeis_recurrence(bad, impl.Deadline(1))["order"] != 2


def test_feed_parser_keeps_ints_only_and_discovery(sandbox, monkeypatch):
    from colony.feeds import parse_oeis_conj
    body = ('[{"number": 69429, "data": "' + ",".join(str(x) for x in range(1, 30)) +
            '", "name": "Half the number <b>x</b>", "keyword": "nonn,easy", '
            '"formula": ["Empirical G.f.: __import__(\\"os\\")"]}]')
    hits = parse_oeis_conj(body, "q")
    assert hits and hits[0]["oeis_id"] == "A069429" and hits[0]["conj_flag"] == "conjectured_formula"
    assert all(isinstance(x, int) for x in hits[0]["terms"])
    assert "formula" not in hits[0] and "__import__" not in json.dumps(hits[0])
    monkeypatch.setattr("colony.feeds.conj_sequence_items",
                        lambda: [{"oeis_id": "A069429", "terms": hits[0]["terms"], "conj_flag": "conjectured_formula"},
                                 {"oeis_id": "A000004", "terms": [0] * 30, "conj_flag": "x"}])
    cat = FR.load_catalog()
    added = FR.discover_oeis_targets(cat)
    assert added == ["oeis_A069429"]  # constant data rejected as trivial
    assert FR.discover_oeis_targets(cat) == []  # dedupe


# ---------------------------------------------------------------- cycle

def test_run_cycle_needs_guide_then_runs_and_logs(sandbox):
    assert FR.run_cycle("c0")["skipped"] == "no_frontier_guide"
    _guide()
    out = FR.run_cycle("c1")
    assert out["ran"] == 1 and out["results"][0]["outcome"] in ("extended", "no_progress")
    rows = [json.loads(x) for x in FR.LOG.read_text().splitlines()]
    assert rows[0]["proof"] is False and rows[0]["label"] == "bounded evidence, not proof"
    sysj = json.loads(FR.SYSTEM.read_text())
    assert sysj["proof"] is False
    # second cycle picks a different (least recently run) target
    out2 = FR.run_cycle("c2")
    assert out2["results"][0]["target"] != out["results"][0]["target"]
