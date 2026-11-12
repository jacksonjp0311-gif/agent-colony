"""Beyond-b-file search, fast evaluators, g.f. guess-and-verify and the honest scoreboard."""
import json
from fractions import Fraction
from pathlib import Path

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


def test_companion_power_matches_kitamasa_and_jumps():
    cf = D.cfinite(OC.parse_definition(FIB), 0, [int(c) for c in OC._series_A("1/(1-x-x^2)", 8)])
    xs = D.iter_exact(cf, 80)
    for n in (0, 1, 7, 40, 80):
        assert D.companion_pow(cf, n) == xs[n]
        assert D.CF(cf).b_value(n) == xs[n]
        assert D.companion_pow(cf, n, D.P2) == xs[n] % D.P2
    # A far index is one matrix power, and it agrees with the other log-time method.
    n = 100_000
    assert D.companion_pow(cf, n, D.P2) == D.kitamasa(cf, n, D.P2)


def test_series_modp_matches_exact_reduction():
    p = 1_000_003
    exact = [int(c) % p for c in B.series_expr(B.compile_expr("1/(1-x-x^2)"), 40)]
    assert B.series_div_modp([1], [1, -1, -1], 40, p) == exact
    assert B.series_mul_modp(exact, [1, -1, -1], 40, p) == [1] + [0] * 39
    assert B.series_pow_modp([1, 1], 5, 8, p)[:6] == [1, 5, 10, 10, 5, 1]


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


def test_cfinite_closure_and_heuristic_guess():
    """A product of two checked recurrences is a routine proof. A bare fit is not."""
    fib = []
    a, b = 1, 1
    for _ in range(48):
        fib.append(a)
        a, b = b, a + b
    squares = [v * v for v in fib]
    fit = G.guess_cfinite(squares)
    assert fit
    text = "a(n) = " + "+".join(f"({int(c)})*a(n-{i + 1})" for i, c in enumerate(fit))
    parsed = OC.parse_definition(text)
    assert parsed and parsed["kind"] == "rec"
    fib_def = OC.parse_definition(FIB)
    cert = {"type": "cfinite_identity", "definition": parsed, "offset": 0, "def_text": text,
            "claim": {"form": "relation", "parts": ["a(n)", "A000045(n)*A000045(n)"], "rels": ["="], "n0": 0},
            "sequences": {"A000045": {"definition": fib_def, "offset": 0, "terms": fib[:36]}}}
    ok, why = PC.check_oeis(cert, squares[:36])
    assert ok, why
    assert "routine" in why
    cert["claim"] = {"form": "relation", "parts": ["a(n)", "A000045(n)*A000045(n)+1"], "rels": ["="], "n0": 0}
    bad, _ = PC.check_oeis(cert, squares[:36])
    assert bad is False
    guess = PC.guess_and_verify(None, squares[:36], 0)
    assert guess["status"] == "heuristic"
    proved = PC.guess_and_verify("1/(1-x-x^2)", fib[:36], 0)
    assert proved["status"] == "proved_checked" and proved["routine"] is True
    same, why_eq = PC.recurrence_equivalent({1: 1, 2: 1}, {1: 1, 2: 1, 3: 0}, fib[:24], 0)
    assert same, why_eq
    assert "routine" in why_eq
    differ, _ = PC.recurrence_equivalent({1: 1, 2: 1}, {1: 2}, fib[:24], 0)
    assert differ is False


def test_deep_counterexample_beyond_bfile_needs_two_paths():
    e = _ent("Conjecture: a(n) = a(n-1) + a(n-2) + floor(n/50000) for n > 1.", eid="deepfail")
    r = OC.attempt_disprove(e, None, fetch=False)
    assert r["status"] == "counterexample_verified"
    assert r["counterexample_n"] == 50000 and r["deep_fail_n"] == 50000
    assert r["fails_B"]


def test_honest_scoreboard_marks_routine_and_stays_off_fitness(tmp_path, monkeypatch):
    st: dict = {}
    alg = _ent("Conjecture: a(n) = a(n-1) + a(n-2) for n > 1.", eid="algproof")
    alg["definition"] = {"kind": "alg", "expr": "1/(1-x-x^2)"}
    OC._score(st, alg, [{"status": "proved_checked", "checker": "algebraic certificate"}])
    closed = _ent("Conjecture: a(n) = a(n-1) + a(n-2) for n > 1.", eid="cfinite")
    closed["definition"] = {"kind": "gf"}
    OC._score(st, closed, [{"status": "proved_checked", "checker": "routine C-finite closure, order bounds"}])
    other = _ent("Conjecture: a(n) = a(n-1) + a(n-2) for n > 1.", eid="openproof")
    other["definition"] = {"kind": "rec"}
    OC._score(st, other, [{"status": "proved_checked", "checker": "recurrence residues"}])
    ext = _ent("Conjecture: a(n) = a(n-1) + a(n-2) for n > 1.", eid="rangeext")
    OC._score(st, ext, [{"status": "holds_on_range", "action": "attempt_disprove",
                         "bfile_hi": 10, "range": [0, 40]}])
    bad = _ent("Conjecture: a(n) = a(n-1) + a(n-2) for n > 1.", eid="counter")
    OC._score(st, bad, [{"status": "counterexample_verified", "counterexample_n": 9}])
    board = OC.scoreboard(st)
    assert board["counterexamples_verified"] == 1
    assert board["proofs_checked"] == 3
    assert board["proofs_routine_known_in_principle"] == 2
    assert board["beyond_published_range"] == 1
    assert st["scoreboard"]["proofs"]["openproof"]["routine"] is False
    assert st["scoreboard"]["proofs"]["algproof"]["routine"] is True
    line = OC.format_honest_scoreboard(board)
    assert line == "counterexamples 1; proofs 3 (2 routine); past published range 1"
    assert "fitness" not in line and "aggregate" not in board

    from colony import dashboard, telemetry

    data = tmp_path / "data"
    data.mkdir()
    (tmp_path / "society").mkdir()
    (data / "society_state.json").write_text(json.dumps({
        "cycle_count": 3,
        "fitness_history": [{"cycle_id": "c1", "aggregate": 1.5, "tribute_quality": 1,
                              "gather_coverage": 1, "build_reuse": 1, "comm_reply_rate": 0.5,
                              "commons_signal": 0}],
        "agents": {},
        "roles": {},
    }), encoding="utf-8")
    monkeypatch.setattr(OC, "format_honest_scoreboard", lambda board=None: line)
    monkeypatch.setattr(OC, "honest_scoreboard", lambda: dict(board, note="not fitness"))
    dashboard.refresh_dashboard(tmp_path)
    html = (tmp_path / "society" / "DASHBOARD.html").read_text(encoding="utf-8")
    summary = (tmp_path / "society" / "WITNESS_SUMMARY.md").read_text(encoding="utf-8")
    assert "Honest scoreboard" in html and line in html
    assert "Fitness (latest)" in html and "1.5" in summary
    assert f"**Honest scoreboard:** {line}" in summary
    snap = telemetry.gather_internal({"fitness_history": [{"aggregate": 0.2, "cycle_id": "c"}], "agents": {}})
    assert snap["fitness_aggregate"] == 0.2
    assert snap["honest_scoreboard"]["counterexamples_verified"] == 1
    assert snap["honest_scoreboard"]["note"] == "not fitness"
    assert "counterexamples_verified" not in (snap["fitness_latest"] or {})

    workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "colony-evolve.yml"
    text = workflow.read_text(encoding="utf-8")
    assert '"honest_scoreboard": honest' in text
    assert "honest scoreboard: {honest_line}" in text
    assert "format_honest_scoreboard" in text


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
