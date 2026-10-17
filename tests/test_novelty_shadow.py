"""Report-only OEIS-names novelty shadow: cached FTS index, hashed receipts, live novelty untouched."""
import gzip
import json

import pytest

from colony import novelty_gate as NG
from colony import novelty_shadow as ns

NAMES = """# OEIS Sequence Names (test fixture)
A000045 Fibonacci numbers: F(n) = F(n-1) + F(n-2) with F(0) = 0 and F(1) = 1.
A000108 Catalan numbers: C(n) = binomial(2n,n)/(n+1).
A001097 Twin primes.
A152051 Hardy-Littlewood approximation to the number of twin primes less than 10^n.
A007530 Prime quadruples: numbers k such that k, k+2, k+6, k+8 are all prime.
A000004 The zero sequence.
"""


@pytest.fixture()
def corpus(tmp_path, monkeypatch):
    monkeypatch.setenv("COLONY_OEIS_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(ns, "STATE", tmp_path / "novelty_shadow.json")
    gz = tmp_path / "names.gz"
    gz.write_bytes(gzip.compress(NAMES.encode()))
    out = ns.build(gz)
    assert out["built"] and out["n_names"] == "6" and "CC BY-SA" in out["credit"]
    return tmp_path


def test_build_is_cached(corpus):
    assert ns.build()["reason"] == "cached"  # no re-download / rebuild


def test_textbook_twin_hl_scores_high_with_hashed_receipts(corpus):
    r = ns.shadow_score("authored_sieve_hl_within_g2_w1")
    assert r["status"] == "ok" and r["shadow_textbook_reuse"] == 1.0
    top = r["matches"][0]
    assert top["anum"] == "A152051" and len(top["name_sha256"]) == 16 and "name" not in top


def test_unrelated_scores_low(corpus):
    assert ns.shadow_score("authored_zeta_weird_w1", "quasi xylophone")["shadow_textbook_reuse"] < 0.75


def test_report_logs_row_and_never_raises(corpus, monkeypatch):
    row = ns.report(mutation="authored_sieve_hl_within_g2_w1", live_textbook_reuse=0.0, live_novel=True)
    st = json.loads(ns.STATE.read_text())
    assert row["mode"] == "report_only" and row["would_flag"]
    assert st["totals"]["would_flag_live_novel"] == 1 and "CC BY-SA" in st["credit"]
    monkeypatch.setattr(ns, "shadow_score", lambda *a, **k: 1 / 0)
    assert ns.report(mutation="x") is None


def test_corpus_absent_no_download(tmp_path, monkeypatch):
    monkeypatch.setenv("COLONY_OEIS_CACHE", str(tmp_path / "none"))
    monkeypatch.setattr(ns.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("download")))
    assert ns.shadow_score("authored_sieve_hl_within_g2_w1") == {"status": "corpus_absent"}


def test_flag_off(corpus, monkeypatch):
    monkeypatch.setenv("COLONY_NOVELTY_SHADOW", "0")
    assert ns.report(mutation="authored_sieve_hl_within_g2_w1") is None
    assert not ns.STATE.exists()


def test_live_novelty_unchanged(corpus, monkeypatch):
    """Same live verdict with the shadow on (flagging) and off; live score untouched."""
    monkeypatch.setattr(NG, "GATE_LOG", corpus / "gate.jsonl")
    monkeypatch.setattr(NG, "stripped_baseline_fails", lambda *a, **k: {"stripped_fails_usefulness": True})
    monkeypatch.setattr(NG, "held_out_harder_survives", lambda *a, **k: {"survives": True})
    name = "authored_sieve_hl_within_g2_w1"
    ov = {"mutation": name, "kind": "hard_enable", "cycle_id": "c1", "passed": True, "kills": []}
    keys = ("novel_to_commons", "kills", "textbook_reuse")
    on = NG.evaluate(mutation=name, kind="hard_enable", cycle_id="c1", oracle_verdict=ov)
    assert json.loads(ns.STATE.read_text())["rows"][-1]["would_flag"]
    monkeypatch.setenv("COLONY_NOVELTY_SHADOW", "0")
    off = NG.evaluate(mutation=name, kind="hard_enable", cycle_id="c1", oracle_verdict=ov)
    assert {k: on[k] for k in keys} == {k: off[k] for k in keys}
    assert on["textbook_reuse"] == NG.textbook_reuse_score(name)
