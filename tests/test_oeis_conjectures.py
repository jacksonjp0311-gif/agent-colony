"""OEIS conjecture targets: normaliser, two code paths, credit rules, checker (colony/oeis_conjectures.py)."""
import json

import pytest

from colony import oeis_conjectures as OC
from colony import proof_check as PC

FIBNAME = "Expansion of (1-x^3)/(1-x-x^2)."


def _ent(claim_text, name=FIBNAME, n=60, data_n=30, terms=None, refs=None, eid="t"):
    d = OC.parse_definition(name)
    if terms is None:
        terms = [int(c) for c in OC._series_A(d["expr"], n)]
    return {"id": eid, "anum": "A999999", "name": name, "offset": 0, "section": "formula", "text": claim_text,
            "claim": OC.normalize(claim_text), "definition": d, "terms": terms, "data_n": data_n, "refs": refs or {}}


def test_normalize_forms():
    assert OC.normalize("Conjecture: 5 is the only prime in this sequence.")["form"] == "only_prime"
    c = OC.normalize("Conjecture: a(n) = a(n-1)+a(n-2) for n>3. - _X Y_, Jan 01 2020")
    assert c["form"] == "relation" and c["n0"] == 4 and c["rels"] == ["="]
    g = OC.normalize("G.f.: (1-x^3)/(1-x-x^2) (conjecture). - _P B_, Aug 10 2009")
    assert g == {"form": "gf", "expr": "(1-x^3)/(1-x-x^2)"}
    r = OC.normalize("Conjecture: a(n) = 2*F(n-1) for n >= 3, where F = A000045.")
    assert "fib(n-1)" in r["parts"][1]
    with pytest.raises(OC.Unparsed):
        OC.normalize("Conjecture: a(n) ~ c * n^2 * log(n).")


def test_paths_agree_on_identity():
    e = _ent("Conjecture: a(n) = 2*F(n-1) for n >= 3, where F = A000045.")
    tA = OC.test_claim(e["claim"], OC._tables(e), "A")
    tB = OC.test_claim(e["claim"], OC._tables(e), "B")
    assert tA["first_fail"] is None and tB["first_fail"] is None and tA["tested"] == tB["tested"] > 50


def test_fails_in_data_gets_no_credit():
    e = _ent("Conjecture: a(n) = 2*F(n) for n >= 3, where F = A000045.")
    r = OC.attempt_disprove(e, fetch=False)
    assert r["status"] == "fails_in_data" and OC.credit_of(r, None) == 0.0


def test_synthetic_counterexample_verified_by_both_paths():
    terms = [n * n + 1 for n in range(40)]
    terms[35] = 4  # breaks "a(n) is odd or ... " style claims beyond DATA
    e = _ent("Conjecture: a(n) > n^2 for all n.", name="Squares plus one.", terms=terms, data_n=20)
    e["definition"] = None
    r = OC.attempt_disprove(e, fetch=False)
    assert r["status"] == "counterexample_verified" and r["counterexample_n"] == 35
    assert OC.credit_of(r, None) == OC.CREDIT_RESOLVE


def test_extension_credit_small():
    e = _ent("Conjecture: a(n) = a(n-1)+a(n-2) for n>3.")
    r = OC.attempt_disprove(e, fetch=False)
    assert r["status"] == "holds_on_range" and r["deep_terms"] > len(e["terms"])
    c = OC.credit_of(r, None)
    assert 0 < c <= OC.CREDIT_EXTEND
    assert OC.credit_of(r, r["range"][1]) == 0.0


def test_checker_accepts_true_rejects_false():
    for t in ("G.f.: (1-x^3)/(1-x-x^2) (conjecture).", "Conjecture: a(n) = a(n-1)+a(n-2) for n>3.",
              "Conjecture: a(n) = 2*F(n-1) for n >= 3, where F = A000045."):
        assert OC.attempt_prove(_ent(t))["status"] == "proved_checked", t
    for t in ("G.f.: (1-x^2)/(1-x-x^2) (conjecture).", "Conjecture: a(n) = a(n-1)+a(n-2) for n>1.",
              "Conjecture: a(n) = 2*F(n) for n >= 3, where F = A000045."):
        assert OC.attempt_prove(_ent(t))["status"] == "proof_rejected", t


def test_checker_rejects_tampered_definition():
    e = _ent("G.f.: (1-x^3)/(1-x-x^2) (conjecture).")
    cert = {"type": "gf_identity", "definition": {"kind": "gf", "expr": "(1-x^3)/(1-x-x^2)"}, "offset": 0,
            "claim": e["claim"], "anum": "A999999", "def_text": "Expansion of 1/(1-x)."}
    assert PC.check_oeis(cert, e["terms"])[0] is False
    cert["def_text"] = FIBNAME
    bad = list(e["terms"]); bad[20] += 1
    assert PC.check_oeis(cert, bad)[0] is False


def test_choose_deterministic_and_skips_resolved():
    menu = [_ent("Conjecture: a(n) = a(n-1)+a(n-2) for n>3.", eid=f"t{i}") for i in range(8)]
    s = {"targets": {"t0": {"status": "proved_checked"}}, "families": {}}
    a = [e["id"] for e in OC.choose(menu, s, "c1")]
    assert a == [e["id"] for e in OC.choose(menu, s, "c1")] and "t0" not in a and len(a) == OC.PICKS


def test_shadow_writes_no_state(tmp_path, monkeypatch):
    menu = {"entries": [_ent("Conjecture: a(n) = a(n-1)+a(n-2) for n>3.")]}
    monkeypatch.setattr(OC, "MENU", tmp_path / "m.json")
    monkeypatch.setattr(OC, "STATE", tmp_path / "s.json")
    monkeypatch.setattr(OC, "REPORT", tmp_path / "r.json")
    monkeypatch.setattr(OC, "REVIEW", tmp_path / "rv.md")
    OC.MENU.write_text(json.dumps(menu))
    monkeypatch.setenv("COLONY_OEIS_CONJ", "shadow")
    OC.run_cycle("c1", fetch=False)
    assert OC.REPORT.exists() and not OC.STATE.exists() and not OC.REVIEW.exists()
    monkeypatch.setenv("COLONY_OEIS_CONJ", "live")
    OC.run_cycle("c2", fetch=False)
    st = json.loads(OC.STATE.read_text())
    assert st["targets"]["t"]["status"] == "proved_checked" and OC.REVIEW.exists()
