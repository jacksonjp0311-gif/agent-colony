"""Spark: auto-build the next hard-tier family from vetted OEIS relations when none remain."""
from __future__ import annotations

import math
import shutil
from pathlib import Path

import pytest

import colony.hard_tier_families as H

ROOT = Path(__file__).resolve().parents[1]
LEMMA = ROOT / "society" / "benchmarks" / "artifacts" / "lemma_impl.py"


def _base_src() -> str:
    """The real catalog with every pool family the colony already built removed again
    (in memory only), so pool tests do not depend on how many families were built."""
    import re
    src = LEMMA.read_text(encoding="utf-8")
    for name, _w, fn_src in H.POOL:
        src = src.replace(fn_src.strip("\n") + "\n\n\n", "")
        src = re.sub(rf'^    \("{name}", lambda: .*\n', "", src, flags=re.M)
        assert f"check_{name}" not in src, name
    return src


def _ns(fn_src: str) -> dict:
    ns: dict = {"math": math}
    exec(fn_src, ns)
    return ns


@pytest.mark.parametrize("name,window,fn_src", H.POOL)
def test_pool_entry_holds_on_window_and_shifted_window(name, window, fn_src):
    fn = _ns(fn_src)[f"check_{name}"]
    a, b = window
    assert all(fn(n) for n in range(a, b))
    assert all(fn(n) for n in range(b, 2 * b - a))  # the Oracle's next disjoint window


def test_pool_matches_oeis_opening_terms():
    def motzkin(n):
        return sum(math.comb(n, 2 * k) * (math.comb(2 * k, k) // (k + 1)) for k in range(n // 2 + 1))
    t = H.OEIS_TERMS
    assert [motzkin(n) for n in range(10)] == t["A001006"]
    assert [sum(math.comb(n, k) * math.comb(n + k, k) for k in range(n + 1)) for n in range(8)] == t["A001850"]
    assert [sum(math.comb(n + k, n - k) * (math.comb(2 * k, k) // (k + 1)) for k in range(n + 1))
            for n in range(8)] == t["A006318"]
    assert [sum(math.factorial(n) // (math.factorial(j) * math.factorial(n - 2 * j) * 2 ** j)
                for j in range(n // 2 + 1)) for n in range(10)] == t["A000085"]
    assert [(2 ** n - (-1) ** n) // 3 for n in range(10)] == t["A001045"]
    lu = [2, 1]
    while len(lu) < 10:
        lu.append(lu[-1] + lu[-2])
    assert lu == t["A000032"]
    r = [1, 0]
    for k in range(2, 10):
        r.append((k - 1) * (2 * r[k - 1] + 3 * r[k - 2]) // (k + 1))
    assert r == t["A005043"]


def test_pool_names_are_new_and_not_textbook():
    from colony.novelty_gate import TEXTBOOK_IDENTITIES, textbook_reuse_score
    src = _base_src()
    assert len({n for n, _w, _f in H.POOL}) == len(H.POOL)
    for name, _w, _f in H.POOL:
        assert f'("{name}"' not in src
        assert textbook_reuse_score(name) < 0.34, name
        assert not any(t in name for t in TEXTBOOK_IDENTITIES)


@pytest.mark.parametrize("name,window,fn_src", H.POOL)
def test_pool_entry_verifies_and_is_falsifiable(name, window, fn_src):
    new = H.insert_family(_base_src(), name, window, fn_src)
    v = H.verify(new, name, window)
    assert v["accepted"], v
    assert v["shift_status"] == "pass" and v["mutants_killed"] >= 1


def test_broken_relation_is_rejected():
    name, window, fn_src = H.POOL[3]
    bad = fn_src.replace("math.comb(n + k, k)", "math.comb(n + k, k + 1)")
    assert bad != fn_src
    v = H.verify(H.insert_family(_base_src(), name, window, bad), name, window)
    assert not v["accepted"]


def test_builds_one_disabled_family_only_when_none_remain(tmp_path, monkeypatch):
    monkeypatch.delenv("COLONY_ARM", raising=False)
    monkeypatch.delenv("COLONY_SELF_MOD", raising=False)
    registered = []
    import colony.conjecture_mutations as CM
    monkeypatch.setattr(CM, "register_mutation_candidate", lambda *a, **k: registered.append(a))
    p = tmp_path / "lemma_impl.py"
    p.write_text(_base_src(), encoding="utf-8")
    assert H.families_remaining(p.read_text()) == []
    row = H.build_next(p, cycle_id="t")
    name = H.POOL[0][0]
    assert row and row["name"] == name and row["enabled"] is False
    src = p.read_text()
    assert f'("{name}", lambda: all(check_{name}(n) for n in range(1, 60)), False),' in src
    assert registered == [(name, "hard_enable", f"enable:{name}")]
    # now one family remains → nothing more is built
    assert H.families_remaining(src) == [name]
    assert H.build_next(p, cycle_id="t2") is None
    assert p.read_text() == src


def test_control_arm_never_builds(tmp_path, monkeypatch):
    monkeypatch.setenv("COLONY_SELF_MOD", "off")
    p = tmp_path / "lemma_impl.py"
    shutil.copy(LEMMA, p)
    assert H.build_next(p) is None
    assert p.read_text() == LEMMA.read_text()


def test_real_catalog_untouched_under_tests(monkeypatch):
    monkeypatch.delenv("COLONY_SELF_MOD", raising=False)
    before = LEMMA.read_text()
    assert H.build_next(LEMMA) is None
    assert LEMMA.read_text() == before
