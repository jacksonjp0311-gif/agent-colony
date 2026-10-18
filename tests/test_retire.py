"""colony.retire: rule-based retirement of low-value authored checks (report-only by default)."""
from __future__ import annotations

import ast
import json
from datetime import datetime, timezone

from colony import retire as R
from colony.authoring import FALLBACK_MARKER, _entries

SRC = f'''
def check_alpha(n):
    return n >= 0


def check_beta(n):
    return n + 1 > n


def check_authored_alpha__beta_w1() -> bool:
    """pair"""
    return all((check_alpha(n) for n in range(10, 20))) and all((check_beta(n) for n in range(5, 9)))


def check_authored_alpha__beta_w2() -> bool:
    """pair on a receipt"""
    return all((check_alpha(n) for n in range(30, 40))) and all((check_beta(n) for n in range(50, 59)))


def check_authored_linked() -> bool:
    return all(check_alpha(n) and check_beta(n) and n == n for n in range(3))
''' + "".join(f'''

def check_authored_sieve_fam_g{{g}}_w1() -> bool:
    return True
'''.format(g=g) for g in (2, 4, 6, 8, 10)) + f'''

{FALLBACK_MARKER}
BASIC: list = [("alpha", lambda: check_alpha(3), True)]
HARD_TIER_LEMMAS: list = [
    ("beta", lambda: check_beta(3), True),
    ("authored_alpha__beta_w1", check_authored_alpha__beta_w1, True),
    ("authored_alpha__beta_w2", check_authored_alpha__beta_w2, True),
    ("authored_linked", check_authored_linked, True),
''' + "".join(f'    ("authored_sieve_fam_g{g}_w1", check_authored_sieve_fam_g{g}_w1, True),\n' for g in (2, 4, 6, 8, 10)) + "]\n"

NOW = datetime(2026, 10, 18, 3, 0, tzinfo=timezone.utc)


def _oracle():
    rows = []
    for i, g in enumerate((2, 4, 6, 8, 10)):
        rows.append({"mutation": f"authored_sieve_fam_g{g}_w1", "passed": True, "ts": f"2026-10-17T0{i}:00:00Z"})
    rows.append({"mutation": "authored_alpha__beta_w1", "passed": True, "ts": "2026-10-17T05:00:00Z"})
    return rows


def _plan(**kw):
    args = dict(src=SRC, oracle_rows=_oracle(), deps=set(), receipts={"authored_alpha__beta_w2"}, guides=set(),
                code=set(), k_prior=0.10921, now=NOW, frontier_new=lambda n: True)
    args.update(kw)
    return R.plan(**args)


def test_rule_categories_and_protections():
    p = _plan()
    names = {c["name"]: c for c in p["candidates"]}
    # newest sweeps go first; KEEP_MIN (3) earliest members stay
    assert {n for n, c in names.items() if c["category"] == "sweep"} == {
        "authored_sieve_fam_g8_w1", "authored_sieve_fam_g10_w1"}
    assert names["authored_alpha__beta_w1"]["category"] == "textbook_pair"
    assert "authored_alpha__beta_w2" not in names and "receipt" in p["protected"]["authored_alpha__beta_w2"]
    assert "authored_linked" not in names          # not a plain pairing: it links the two facts
    assert all(not n.startswith(("alpha", "beta")) for n in names)  # catalog lemmas never considered


def test_bar_guide_code_grace_and_fail_closed_protect():
    p = _plan(deps={"authored_sieve_fam_g10_w1"}, guides={"authored_alpha__beta_w1"})
    names = {c["name"] for c in p["candidates"]}
    assert "authored_sieve_fam_g10_w1" not in names and "authored_alpha__beta_w1" not in names
    assert "authored_sieve_fam_g6_w1" in names     # the next sweep member takes its place
    p = _plan(now=datetime(2026, 10, 17, 5, 30, tzinfo=timezone.utc))
    assert "authored_alpha__beta_w1" in p["protected"]  # verdict 30 min ago: grace
    assert _plan(deps=None)["n_candidates"] == 0      # shortlist unavailable -> retire nothing


def test_trivial_frontier_category():
    src = SRC.replace(FALLBACK_MARKER, 'def check_authored_frontier_le_xabc_w1() -> bool:\n    return True\n\n\n'
                      + FALLBACK_MARKER).replace(
        "HARD_TIER_LEMMAS: list = [\n", 'HARD_TIER_LEMMAS: list = [\n    ("authored_frontier_le_xabc_w1", check_authored_frontier_le_xabc_w1, True),\n')
    p = _plan(src=src, frontier_new=lambda n: False)
    assert any(c["name"] == "authored_frontier_le_xabc_w1" and c["category"] == "trivial_frontier"
               for c in p["candidates"])
    p = _plan(src=src, frontier_new=lambda n: None)  # cannot tell -> keep
    assert not any(c["category"] == "trivial_frontier" for c in p["candidates"])


def test_apply_archives_and_restore_comes_back_disabled(tmp_path):
    lemma = tmp_path / "lemma_impl.py"
    lemma.write_text(SRC)
    rec = tmp_path / "retired.json"
    p = _plan()
    out = R.apply(p, cycle_id="c1", path=lemma, record=rec, check_bench=False)
    assert out["applied"] == len(p["candidates"])
    new = lemma.read_text()
    left = {n for n, _c, _f in _entries(ast.parse(new))}
    assert not left & {c["name"] for c in p["candidates"]}
    assert "def check_authored_alpha__beta_w1" not in new and "check_alpha" in new
    data = json.loads(rec.read_text())
    row = next(r for r in data["records"] if r["name"] == "authored_alpha__beta_w1")
    assert row["category"] == "textbook_pair" and row["enabled"] is True and "def check_" in row["fn_src"]
    assert R.retired_names(rec) >= {"authored_alpha__beta_w1"}
    assert R.retired_pair_families(rec) == {"authored_alpha__beta"}
    assert R.restore("authored_alpha__beta_w1", path=lemma, record=rec)
    ents = {n: f for n, _c, f in _entries(ast.parse(lemma.read_text()))}
    assert ents["authored_alpha__beta_w1"] is False      # back, disabled: must pass the Oracle again
    assert "authored_alpha__beta_w1" not in R.retired_names(rec)


def test_mode_flag(monkeypatch):
    monkeypatch.delenv("COLONY_RETIRE", raising=False)
    assert R.mode() == "shadow"
    monkeypatch.setenv("COLONY_RETIRE", "off")
    assert R.run_cycle("x") == {"skipped": "COLONY_RETIRE=off"}


def test_authoring_never_reauthors_retired(monkeypatch, tmp_path):
    import colony.authoring as A
    import colony.retire as RR
    lemma = tmp_path / "lemma_impl.py"
    lemma.write_text(SRC)
    monkeypatch.setattr(A, "_lemma_impl", lambda: lemma)
    monkeypatch.setattr(A, "MAX_AUTHORED_TOTAL", 10 ** 6)
    seen = {}

    def fake_build(a, b, k):
        name = f"authored_{a['lemma']}__{b['lemma']}_w{k}"
        seen[name] = k
        return name, f"def check_{name}() -> bool:\n    return True\n", ast.parse("x").body[0], "x"
    monkeypatch.setattr(A, "_build_candidate", fake_build)
    monkeypatch.setattr(A, "eligible_components", lambda src: [{"lemma": "alpha", "function": "check_alpha"},
                                                                 {"lemma": "beta", "function": "check_beta"}])
    monkeypatch.setattr(A, "oeis_candidates", lambda src, comps: [])
    monkeypatch.setattr(RR, "retired_names", lambda: {"authored_alpha__beta_w3"})
    monkeypatch.setattr(RR, "retired_pair_families", lambda: {"authored_alpha__beta"})
    out = A.author_checks(max_new=2, write=False)
    # the only pair was retired as a textbook pairing: never re-authored (other sources may still author)
    assert not [r for r in out if r["name"].startswith("authored_alpha__beta")]


def test_hard_tier_delta_adds_back_retired(monkeypatch):
    import colony.fitness as F
    snaps = iter([{"score": 0.86, "n_hard": 213, "n_hard_pass": 213, "ok": True, "n_retired": 11}])
    monkeypatch.setattr(F, "hard_tier_snapshot", lambda: dict(next(snaps)))
    data = {"hard_tier_history": [{"score": 0.86, "n_hard": 224, "n_hard_pass": 224, "ok": True}]}
    assert F.hard_tier_delta(data) == 0.0


def test_shortlist_drops_frontier_target_flagged_trivial(monkeypatch):
    from colony import frontier_checks as FK, shortlist as SL
    monkeypatch.setattr(FK, "trivial_now", lambda name, src=None: True)
    e = SL.evaluate({"id": "p1", "cycle_id": "c"}, oracle_rows=[{"mutation": "authored_frontier_le_xabc_w1",
                                                               "cycle_id": "c", "passed": True}],
                    novelty_rows=[], athanor_rows=[], resolve=lambda p: "authored_frontier_le_xabc_w1",
                    reuse=lambda p: 0.0, p_rule=lambda p: 0.9)
    assert not e["meets_bar"] and "trivial_by_filter" in e["why_not"]
