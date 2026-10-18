"""Frontier conjecture generator: self-chosen claims, held-out falsification, honest labels."""
from __future__ import annotations

import ast
import json
import random
from pathlib import Path

import pytest

import colony.frontier_conjectures as FC

T = FC.Tables(lim=20000, exp_n=1200)
P = lambda name: ("p", name)  # noqa: E731


def _claim(kind, le, re_=None, params=None):
    return {"kind": kind, "lhs": FC.canon(le), "rhs": FC.canon(re_) if re_ else "", "params": params or {},
            "_le": le, "_re": re_, "id": "x"}


def test_mode_default_shadow(monkeypatch):
    monkeypatch.delenv("COLONY_FRONTIER", raising=False)
    assert FC.mode() == "shadow"
    monkeypatch.setenv("COLONY_FRONTIER", "nonsense")
    assert FC.mode() == "shadow"
    monkeypatch.setenv("COLONY_FRONTIER", "off")
    assert FC.run_cycle("c") == {"skipped": "COLONY_FRONTIER=off"}


def test_primitives_are_right():
    t = T.t
    assert t["phi"][1:13] == [1, 1, 2, 2, 4, 2, 6, 4, 6, 4, 10, 4]
    assert t["sigma"][12] == 28 and t["tau"][12] == 6 and t["mu"][30] == -1 and t["mu"][12] == 0
    assert t["prime"][1:6] == [2, 3, 5, 7, 11] and t["pi"][100] == 25
    assert t["fib"][1:8] == [1, 1, 2, 3, 5, 8, 13] and t["part"][1:8] == [1, 2, 3, 5, 7, 11, 15]


def test_canon_parse_roundtrip_and_commutative_dedupe():
    e = ("+", ("S", P("phi")), ("o", "sigma", P("tau")))
    assert FC.parse(FC.canon(e)) == e or FC.canon(FC.parse(FC.canon(e))) == FC.canon(e)
    assert FC.canon(("*", P("tau"), P("phi"))) == FC.canon(("*", P("phi"), P("tau")))


def test_held_out_falsifies_a_pattern_that_only_fits_small_n():
    # pi(n) <= tau(n)+1 holds for n <= 10 or so, fails later
    c = _claim("le", P("pi"), ("+", P("tau"), P("one")))
    a, b = FC.evaluate(c["_le"], 6, T), FC.evaluate(c["_re"], 6, T)
    assert FC.holds("le", {}, a, b)[0]
    r = FC.test_claim(c, T, 6, 5000, 500)
    assert r["tested"] and r["survived"] is False


def test_trivial_rewrites_are_detected():
    rng = random.Random(1)
    formal = _claim("identity", ("-", ("+", P("phi"), P("n")), P("n")), P("phi"))
    assert FC.trivial_reason(formal, T, rng, 12) == "formal"
    implied = _claim("cong", ("*", P("n"), ("*", P("n"), P("sigma"))), None, {"m": 3, "r": 0, "q": 3, "s": 0})
    assert FC.trivial_reason(implied, T, rng, 12) in ("implied_parts", "idle_part")
    shared = _claim("le", ("*", P("tau"), P("lpf")), ("*", P("tau"), P("sopfr")))
    assert FC.trivial_reason(shared, T, rng, 12) == "shared_operand"


def test_machine_checked_only_for_decidable_cfinite_claims():
    ident = _claim("identity", ("dbl", P("fib")), ("*", P("fib"), P("lucas")))   # F(2n) = F(n) L(n)
    cert = FC.prove(ident, T)
    assert cert and cert["method"] == "C-finite order bound" and cert["checked_terms"] == 6
    wrong = _claim("identity", ("dbl", P("fib")), ("*", P("fib"), P("fib")))
    assert FC.prove(wrong, T) is None
    cong = _claim("cong", P("fib"), None, {"m": 2, "r": 0, "q": 3, "s": 0})   # 2 | F(3k)
    assert FC.prove(cong, T)["method"] == "periodic state space mod m"
    arith = _claim("le", P("phi"), P("n"))
    assert FC.prove(arith, T) is None   # number-theoretic: survives testing, never "proved" here


def test_bm_finds_integer_recurrence():
    assert FC.berlekamp_massey_int(T.t["fib"][1:20]) == [1, 1]
    assert FC.berlekamp_massey_int(T.t["phi"][1:20]) is None


@pytest.fixture
def small(monkeypatch):
    monkeypatch.setattr(FC, "HELD_CHEAP", 4000)
    monkeypatch.setattr(FC, "RETEST_CHEAP", 8000)
    monkeypatch.setattr(FC, "HELD_EXP", 400)
    monkeypatch.setattr(FC, "RETEST_EXP", 600)
    monkeypatch.setattr(FC, "N_EXPR", 120)
    monkeypatch.setattr(FC, "PAIR_BUDGET", 800)
    monkeypatch.setenv("COLONY_FRONTIER", "shadow")


def test_cycle_without_oeis_index_never_claims_surprise(tmp_path, small):
    sp = tmp_path / "s.json"
    s = FC.run_cycle("c1", state_path=sp, T=T, lookup=None, seed="a", F=12, k_prior=0.1)
    c = s["counts"]
    assert c["tested"] > 0 and c["surprises"] == 0
    assert s["oeis_index"].startswith("absent")
    st = json.loads(sp.read_text())
    for r in st["registry"].values():
        assert not r["unknown"]
        assert r["label"].startswith("machine-checked") == bool(r["certificate"])
        assert "proved" not in r["label"]


def test_cycle_preregisters_predictions_and_dedupes(tmp_path, small):
    sp = tmp_path / "s.json"
    lookup = lambda seq: {"status": "not_found", "anums": []}  # noqa: E731
    s1 = FC.run_cycle("c1", state_path=sp, T=T, lookup=lookup, seed="a", F=12, k_prior=0.1)
    st = json.loads(sp.read_text())
    assert st["predictions"]["n"] == s1["counts"]["tested"]
    assert all(0 < r["prediction"] < 1 for r in st["registry"].values())
    s2 = FC.run_cycle("c2", state_path=sp, T=T, lookup=lookup, seed="a", F=12, k_prior=0.1)
    assert s2["counts"]["duplicate"] > 0   # earlier claims / same fitted values are not re-tested
    assert s2["counts"]["retested"] > 0
    assert all(not isinstance(v, list) for h in st["history"] for v in h.values())


def test_holds_on_bridge():
    claim = {"kind": "cong", "lhs": "fib", "rhs": "", "params": {"m": 2, "r": 0, "q": 3, "s": 0}}
    assert FC.holds_on(claim, 40, 600) > 0
    bad = {"kind": "le", "lhs": "pi", "rhs": "(one+tau)", "params": {}}
    assert FC.holds_on(bad, 40, 2000) == 0


def test_markdown_section(tmp_path, small):
    sp = tmp_path / "s.json"
    FC.run_cycle("c1", state_path=sp, T=T, lookup=None, seed="a", F=12, k_prior=0.1)
    md = FC.markdown_section(json.loads(sp.read_text()))
    assert "Frontier conjectures" in md and "report-only" in md and "OEIS index: absent" in md


def test_never_imports_scoring_or_oracle():
    tree = ast.parse((Path(FC.__file__)).read_text())
    mods = {getattr(n, "module", None) or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    mods |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(x in m for m in mods for x in ("oracle", "standing_trust", "authorize", "charter", "fitness"))


def test_workflow_flag_present():
    wf = (Path(FC.__file__).resolve().parents[1] / ".github/workflows/colony-evolve.yml").read_text()
    assert "COLONY_FRONTIER: live" in wf and "colony.oeis_terms build" in wf


def test_linear_operator_split_catches_parity_rewrites():
    rng = random.Random(2)
    c = _claim("cong", ("D", ("+", P("digsum"), P("lpf"))), None, {"m": 2, "r": 0, "q": 2, "s": 0})
    assert FC.trivial_reason(c, T, rng, 12) == "implied_parts"


def test_one_congruence_per_expression_on_coarsest_class():
    rng = random.Random(3)
    cl = FC.fit_claims([("D", P("pell"))], T, 12, rng)
    cong = [c for c in cl if c["kind"] == "cong"]
    assert len(cong) == 1 and cong[0]["params"]["q"] == 1


def test_periodic_parts_and_loose_inequalities_are_not_surprises():
    rng = random.Random(4)
    c = _claim("cong", ("D", ("*", P("lpf"), P("pell"))), None, {"m": 2, "r": 1, "q": 1, "s": 0})
    assert FC.trivial_reason(c, T, rng, 12) == "implied_parts"
    loose = _claim("le", ("+", P("bigomega"), P("digsum")), P("sigma"))
    r = FC.test_claim(loose, T, 12, 5000, 500)
    assert r["survived"] and r["loose"]
    tight = _claim("le", P("phi"), ("-", P("n"), P("one")))     # equality at every prime
    r = FC.test_claim(tight, T, 12, 5000, 500)
    assert r["survived"] and not r["loose"]


def test_divisibility_implied_by_a_factor_is_a_rewrite():
    rng = random.Random(5)
    c = _claim("divides", P("gpf"), ("+", P("rad"), P("rad")))
    assert FC.trivial_reason(c, T, rng, 12) in ("implied_parts", "shared_operand", "idle_part")
    c2 = _claim("divides", P("tau"), ("*", P("tau"), P("prime")))
    assert FC.trivial_reason(c2, T, rng, 12) == "implied_parts"


def _triv(kind, lhs, rhs, params=None):
    import random as _r
    c = {"kind": kind, "params": params or {}, "_le": FC.parse(lhs), "_re": FC.parse(rhs) if rhs else None}
    return FC.trivial_reason(c, T, _r.Random("x46c5cc8a"), 12)


def test_case_split_flags_mu_lucas_claim():
    # the first Oracle-passed frontier check: on squarefree n both sides are 1, otherwise n <= Lucas(n)
    assert _triv("le", "gcd(mu,n)", "gcd(lucas,sqfree)") in ("case_split", "idle_part")
    import random as _r
    c = {"kind": "le", "params": {}, "_le": FC.parse("gcd(mu,n)"), "_re": FC.parse("gcd(lucas,sqfree)")}
    assert FC._case_split_trivial(c, T, _r.Random(0), 12)


def test_case_split_sees_through_a_2n_and_constant_branches():
    # mu(4k) = 0, so gcd(mu(2n), 2n) = 2n is even on even n
    assert _triv("cong", "dbl(gcd(mu,n))", None, {"m": 2, "r": 0, "q": 2, "s": 0}) in ("case_split", "parity_rules")
    assert _triv("identity", "mu[gpf]", "mu[lpf]") == "case_split"  # mu(prime) = -1


def test_case_split_does_not_reach_inside_D_wrongly():
    import random as _r
    c = {"kind": "cong", "params": {"m": 2, "r": 0, "q": 2, "s": 1}, "_le": FC.parse("D((sigma*sqfree))"), "_re": None}
    # sigma(n+1) - sigma(n) for odd n with both squarefree is not a per-branch rewrite ...
    assert not FC._case_split_trivial(c, T, _r.Random(0), 12)
    # ... but it does follow from the textbook rule "sigma(n) odd iff n is a square or twice a square"
    assert _triv("cong", "D((sigma*sqfree))", None, {"m": 2, "r": 0, "q": 2, "s": 1}) == "parity_rules"


def test_parity_rules_and_running_sums():
    assert _triv("cong", "S((part*phi))", None, {"m": 2, "r": 1, "q": 1, "s": 0}) == "parity_rules"  # phi even, n >= 3
    assert _triv("cong", "S((sqfree*tau))", None, {"m": 2, "r": 1, "q": 1, "s": 0}) == "parity_rules"  # tau odd iff square
    # no textbook rule for pi(n) parity: kept
    # primes > 2 are odd: sum_{k<=n} pi(k) = sum_{p<=n} (n+1-p) is odd for even n (now explained)
    assert _triv("cong", "S((pi*pi))", None, {"m": 2, "r": 1, "q": 2, "s": 0}) == "parity_rules"
    import random as _r
    c = {"kind": "cong", "params": {"m": 3, "r": 0, "q": 1, "s": 0}, "_le": FC.parse("S((pow2*(n*(n*n))))"), "_re": None}
    assert not FC._running_sum_tail(c, T)


def test_divides_parts_n1_edge_and_products():
    assert _triv("divides", "dbl(gpf)", "(prime*rad)") == "implied_parts"     # gpf(2n) = gpf(n) | rad(n), n >= 2
    assert _triv("divides", "(gpf*phi)", "dbl((phi*rad))") == "implied_parts"  # gpf | rad(2n), phi(n) | phi(2n)


def test_basic_inequalities_by_reduction():
    assert _triv("le", "(gpf-tau)", "dbl((gpf-bigomega))") == "basic_inequality"  # tau >= Omega + 1
    assert _triv("le", "(omega-gpf)", "dbl((omega-gpf))") == "basic_inequality"   # omega(2n) >= omega(n)
    assert _triv("le", "gpf", "rad") == "basic_inequality"
    import random as _r
    c = {"kind": "le", "params": {}, "_le": FC.parse("gpf"), "_re": FC.parse("phi")}
    assert not FC._basic_inequality(c, T)          # gpf <= phi is false (n = 2) and not in the library


def test_rewrite_atoms_closure_but_not_plain_cfinite():
    assert _triv("rec", "dbl((pow2-lpf))", None, {"c": [-4, 5]}) == "rewrite_closure"  # lpf(2n) = 2
    import random as _r
    c = {"kind": "rec", "params": {"c": [4, 4]}, "_le": FC.parse("sh((pell*pow2))"), "_re": None}
    assert FC.trivial_reason(c, T, _r.Random(0), 12) != "rewrite_closure"   # already C-finite: proved, not dropped


def test_growth_dominance():
    assert _triv("le", "n", "lucas") == "growth_dominance"
    assert _triv("le", "(sigma+tau)", "pow2") == "growth_dominance"
    import random as _r
    c = {"kind": "le", "params": {}, "_le": FC.parse("lpf"), "_re": FC.parse("gpf")}
    assert not FC._dominates(c, T)


# ----------------------------------------------------------------------------- wide menu

def test_wide_menu_is_opt_in(monkeypatch):
    monkeypatch.delenv("COLONY_FRONTIER_MENU", raising=False)
    assert FC.menu() == "base" and not set(FC.WIDE) & set(FC.menu_prims())
    monkeypatch.setenv("COLONY_FRONTIER_MENU", "wide")
    assert set(FC.WIDE) <= set(FC.menu_prims())
    rng = random.Random(1)
    exprs = FC.sample_expressions(rng, 200, {})
    assert any(FC.prims_of(e) & set(FC.WIDE) for e in exprs)


def test_ramanujan_is_known_not_a_surprise():
    c = _claim("cong", FC.parse("sh(part)"), None, {"m": 5, "r": 0, "q": 5, "s": 3})
    assert "Ramanujan" in FC.known_result(c)
    c = _claim("cong", FC.parse("part"), None, {"m": 7, "r": 0, "q": 7, "s": 5})
    assert "Ramanujan" in FC.known_result(c)
    c = _claim("cong", FC.parse("part"), None, {"m": 5, "r": 0, "q": 5, "s": 3})
    assert FC.known_result(c) == ""
    # consequences of Ramanujan + periodic parts are implied, not new
    c = _claim("cong", FC.parse("D((fib*part))"), None, {"m": 5, "r": 0, "q": 5, "s": 4})
    assert FC.trivial_reason(c, T, random.Random(0), 12) == "implied_parts"


def test_wide_rules_parity_digits_monotone_and_odd_dbl():
    r = random.Random(0)
    # S(gcd(phi, pi)) parity follows from "primes > 2 are odd" + phi even
    c = _claim("cong", FC.parse("S(gcd(phi,pi))"), None, {"m": 2, "r": 0, "q": 2, "s": 0})
    assert FC.trivial_reason(c, T, r, 12) == "parity_rules"
    # Collatz maxima are even for n >= 2
    c = _claim("cong", FC.parse("S(gcd(cheb4,cmax))"), None, {"m": 2, "r": 1, "q": 2, "s": 0})
    assert FC.trivial_reason(c, T, r, 12) == "parity_rules"
    # base-10 digit sum / reversal keep n mod 9
    c = _claim("cong", FC.parse("rev[sigma]"), None, {"m": 3, "r": 0, "q": 3, "s": 2})
    assert FC.trivial_reason(c, T, r, 12) == "digit_rule"
    # prime(rad n) <= gpf(prime n) = prime(n): monotone outer + rad <= n
    c = _claim("le", FC.parse("prime[rad]"), FC.parse("gpf[prime]"))
    assert FC.trivial_reason(c, T, r, 12) != ""
    # sigma(n) | sigma(2n) sqfree(2n): on odd squarefree n, sigma(2n) = 3 sigma(n)
    c = _claim("divides", FC.parse("sigma"), FC.parse("dbl((sigma*sqfree))"))
    assert FC.trivial_reason(c, T, r, 12) != ""


def test_modpat_kind_holds_and_bridge():
    pat = [FC.tables().t["fib"][i] % 2 for i in range(1, 4)]
    claim = {"kind": "modpat", "lhs": "fib", "rhs": "", "params": {"m": 2, "P": 3, "pat": pat}}
    assert FC.holds_on(claim, 1, 900) > 0
    bad = dict(claim, params={"m": 2, "P": 3, "pat": [1, 1, 1]})
    assert FC.holds_on(bad, 1, 900) == 0
    assert "depends only on n mod 3" in FC.statement(dict(claim, lhs="fib"))
