import json

import pytest

from colony import recipes
from colony.frontier import load_catalog, load_log


@pytest.fixture(autouse=True)
def _tmp_ledgers(tmp_path, monkeypatch):
    monkeypatch.setattr(recipes, "LEDGER", tmp_path / "recipes.jsonl")
    monkeypatch.setattr(recipes, "USES", tmp_path / "recipe_uses.jsonl")


def _row(tid, **kw):
    r = {"target": tid, "lo": 1, "hi": 1000, "outcome": "extended", "challenger": {"blocked": False},
         "independent_subwindow": [1, 100], "published_reproduced": [], "published_mismatch": [],
         "label": recipes.LABEL, "proof": False, "primary": {"seconds": 0.5, "data": {"engine": "numpy"}},
         "cycle_id": "burst_x", "ts": "2026-10-16T00:00:00Z"}
    r.update(kw)
    return r


def _target(**kw):
    t = {"id": "t1", "family": "prime_run_count", "status": "done", "index_thresholds": [2, 3],
         "known_terms": {"1": 5, "2": 9}, "beyond_record": True}
    t.update(kw)
    return t


def test_strong_success_becomes_recipe_from_recorded_rows():
    rows = [_row("t1", published_reproduced=[1]), _row("t1", published_reproduced=[2], outcome="new_term_candidate", lo=1001, hi=3000)]
    r = recipes.extract(_target(), rows)
    assert r and r["target_type"] == "prime_run_count"
    assert r["verification_ladder"][0] == "reproduce_published_terms_first_or_freeze"
    assert "sub_window_recount_by_second_prime_test" in r["independent_check_method"]
    assert r["speedups"]["batched_windows"] and r["speedups"]["max_window"] == 2000
    assert r["run_stats"]["windows"] == 2 and r["proof"] is False
    assert "counting_over_primes_to_bound" in r["features"]


def test_planted_fake_success_without_verification_is_not_a_recipe():
    fake = _target(status="done")
    rows = [_row("t1", outcome="new_term_candidate", challenger=None, independent_subwindow=None,
                 published_reproduced=[])]
    assert recipes.extract(fake, rows) is None
    why = recipes.verification_failures(fake, rows)
    assert "challenger_missing_or_blocked" in why and "independent_check_missing" in why
    assert any(w.startswith("published_terms_not_all_reproduced") for w in why)
    assert recipes.distill({"targets": [fake]}, rows) == [] and recipes.load() == []


@pytest.mark.parametrize("bad", [dict(outcome="disagreement"), dict(proof=True), dict(published_mismatch=[1]),
                                 dict(challenger={"blocked": True})])
def test_any_failed_rung_blocks_recipe(bad):
    rows = [_row("t1", **{"published_reproduced": [1, 2], "outcome": "new_term_candidate", **bad})]
    assert recipes.extract(_target(), rows) is None


def test_no_terminal_success_is_not_a_recipe():
    assert recipes.extract(_target(status="open"), [_row("t1", published_reproduced=[1, 2])]) is None


def test_retrieve_apply_and_record_use_and_outcome():
    rows = [_row("t1", published_reproduced=[1, 2], outcome="new_term_candidate", hi=5000)]
    assert len(recipes.distill({"targets": [_target()]}, rows)) == 1
    new = {"id": "t2", "family": "prime_run_count", "index_thresholds": [4], "known_terms": {"1": 3}, "max_window": 10**9}
    use = recipes.on_start(new)
    assert use and use["plan"]["same_target_type"] and new["window"] == 5000
    assert "reproduce_published_terms_first_or_freeze" in use["plan"]["verification_ladder"]
    assert recipes.on_start(new) is None  # recorded once
    assert recipes.on_result(new, {"outcome": "extended", "verified_hi": None, "primary": {"seconds": 1}}) is None
    out = recipes.on_result(new, {"outcome": "extended", "verified_hi": 9, "primary": {"seconds": 2}})
    assert out["verified"] and out["time_to_first_verified_s"] == 3 and out["windows_to_first_verified"] == 2
    assert out["helped"] is None
    kinds = [json.loads(l)["kind"] for l in recipes.USES.read_text().splitlines()]
    assert kinds == ["recipe_use", "recipe_outcome"]


def test_unrelated_target_gets_no_recipe():
    recipes.distill({"targets": [_target()]}, [_row("t1", published_reproduced=[1, 2], outcome="new_term_candidate")])
    assert recipes.retrieve({"id": "z"}) == []


def test_seed_a104062_record_yields_recipe():
    cat = load_catalog()
    t = next(x for x in cat["targets"] if x["id"] == "oeis_A104062_next")
    r = recipes.extract(t, load_log(limit=100000))
    assert r is not None and r["reproduce_known_first"] and r["outcome"]["terminal_outcomes"] == ["new_term_candidate"]
