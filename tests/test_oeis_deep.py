"""Beyond-b-file search, fast evaluators, g.f. guess-and-verify and the honest scoreboard."""
from fractions import Fraction

from colony import oeis_conjectures as OC
from colony import oeis_deep as D
from colony import oeis_eval_b as B
from colony import oeis_guess as G
from colony import proof_check as PC

FIB = "Expansion of 1/(1-x-x^2)."
CAT = "(1-sqrt(1-4*x))/(2*x)"
MOTZ = "(1-x-sqrt(1-2*x-3*x^2))/(2*x^2)"


def _ent(text, name=FIB, n=60, eid="d"):
    d = OC.parse_definition(name)
    terms = [int(c) for c in OC._series_A(d["expr"], n)]
    return {"id": eid, "anum": "A999998", "name": name, "offset": 0, "section": "formula", "text": text,
            "claim": OC.normalize(text), "definition": d, "terms": terms, "data_n": 30, "refs": {}}


def test_series_paths_agree_and_sqrt():
    for ex in (CAT, MOTZ, "1/((1+x)*(sqrt(1-4*x^2)-x))", "(1-x)/sqrt((1-3*x)/(1+x))"):
        a = OC._series_A(ex, 30)
        b = B.series_expr(B.compile_expr(ex), 30)
        assert [Fraction(x) for x in a] == [Fraction(x) for x in b], ex
    assert [int(c) for c in B.series_expr(B.compile_expr(CAT), 8)] == [1, 1, 2, 5, 14, 42, 132, 429]


def test_parse_alg_definition_and_dfinite_statement():
    d = OC.parse_definition("Expansion of " + MOTZ + ".")
    assert d and d["kind"] == "alg"
    c = OC.normalize("Conjecture D-finite with recurrence: (n+2)*a(n) -(2*n+1)*a(n-1) -3*(n-1)*a(n-2) = 0.")
    assert c["form"] == "relation"


def test_kitamasa_matches_iteration():
    cf = D.cfinite(OC.parse_definition(FIB), 0, [int(c) for c in OC._series_A("1/(1-x-x^2)", 40)])
    xs = D.iter_exact(cf, 300)
    for n in (0, 1, 17, 150, 300):
        assert D.kitamasa(cf, n) == xs[n]
        assert D.kitamasa(cf, n, D.P2) == xs[n] % D.P2
    assert D.iter_mod(cf, 300, D.P1)[300] == xs[300] % D.P1


def test_holonomic_certificate_accepts_true_rejects_false():
    cat = [int(c) for c in B.series_expr(B.compile_expr(CAT), 300)]
    ok, why = PC.check_holonomic(CAT, 0, ["(n+1)*a(n) - 2*(2*n-1)*a(n-1)", "0"], ["="], 1, cat)
    assert ok, why
    bad, _ = PC.check_holonomic(CAT, 0, ["(n+1)*a(n) - 2*(2*n+1)*a(n-1)", "0"], ["="], 1, cat)
    assert not bad
    inh, _ = PC.check_holonomic(CAT, 0, ["(n+1)*a(n) - 2*(2*n-1)*a(n-1) - 1", "0"], ["="], 1, cat)
    assert not inh


def test_guess_is_heuristic_until_certified():
    assert "HEURISTIC" in G.__doc__
    mot = [int(c) for c in B.series_expr(B.compile_expr(MOTZ), 200)]
    cr = G.certified_recurrence(MOTZ, 0, mot)
    assert cr and cr["certificate"] and cr["order"] >= 1
    h = D.Holo(cr, 0)
    assert D.matches_bfile(h, 0, mot)
    assert h.exact(400)[399] == h.b_value(399)


def test_deep_counterexample_beyond_bfile_needs_two_paths():
    e = _ent("Conjecture: a(n) = a(n-1) + a(n-2) + floor(n/50000) for n > 1.", eid="deepfail")
    r = OC.attempt_disprove(e, None, fetch=False)
    assert r["status"] == "counterexample_verified"
    assert r["counterexample_n"] == 50000 and r["deep_fail_n"] == 50000
    assert r["fails_B"]


def test_deep_extension_true_claim_and_scoreboard():
    e = _ent("Conjecture: a(n) = a(n-1) + a(n-2) for n > 1.", eid="deepok")
    r = OC.attempt_disprove(e, None, fetch=False)
    assert r["status"] == "holds_on_range" and r["deep_hi"] > 1000
    st = {}
    OC._score(st, e, [r])
    sb = OC.scoreboard(st)
    assert sb["beyond_published_range"] == 1 and sb["score"] == 1 and sb["max_depth"] == r["deep_hi"]
    OC._score(st, e, [{"status": "counterexample_verified", "counterexample_n": 5}])
    assert OC.scoreboard(st)["score"] == 2


def test_definition_must_match_bfile():
    e = _ent("Conjecture: a(n) = a(n-1) + a(n-2) for n > 1.", eid="mism")
    e["terms"] = e["terms"][:30] + [e["terms"][30] + 1] + e["terms"][31:]
    g = D.generator(e)
    assert g is not None and not D.matches_bfile(g, 0, e["terms"])
