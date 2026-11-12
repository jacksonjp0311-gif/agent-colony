"""Definition-parity / prime-oddness extension of the known-in-principle check (colony/definition_parity.py).

Regression claims are the surprises the 2026-10-23 component-fact check let through; each must now be
labelled known_in_principle(definition_parity). Mechanisms, not a list of signatures: the claims are
rebuilt from their expressions and explained from definitions / elementary facts."""
import pytest

from colony import compositional as CP
from colony import definition_parity as DP
from colony import frontier_conjectures as FC


@pytest.fixture(scope="module")
def T():
    return FC.Tables(lim=FC.BRIDGE_LIM, exp_n=FC.BRIDGE_EXP)


def _c(lhs, **params):
    params.setdefault("s", 0)
    return {"kind": "cong", "params": params, "_le": FC.parse(lhs), "_re": None}


REGRESSION = [
    ("dbl(oxa177115)", dict(m=2, q=1, r=0)),          # A177115 even at even indices
    ("dbl(oxa177122)", dict(m=2, q=1, r=1)),          # A177122 odd at even indices
    ("dbl(oxa009191)", dict(m=2, q=6, r=0, s=4)),     # 85b99e19: gcd(m, d(m)) even, m = 8 (mod 12)
    ("prime[oxa080076]", dict(m=2, q=1, r=1)),        # Proth primes odd
    ("maxgap[oxa080076]", dict(m=2, q=1, r=0)),       # max gap of odd primes even
    ("cmax[oxa080076]", dict(m=2, q=1, r=0)),
    ("ple3[oxa080076]", dict(m=2, q=1, r=1)),
    ("gcd(n,tau)", dict(m=2, q=12, r=0, s=8)),        # gcd(m, d(m)) even for m = 8 (mod 12)
]


@pytest.mark.parametrize("lhs,params", REGRESSION)
def test_regression_known_in_principle(T, lhs, params):
    ex = CP.explain(_c(lhs, **params), T)
    assert ex and ex["label"] == "known_in_principle(definition_parity)", lhs
    assert ex["facts"]


def test_regression_51c52e42_modpat(T):
    # gcd(gcd(n, d(n)), A083105) mod 2 by n mod 6. A009191 follows from its definition;
    # A083105 is only a 2-kernel fitted to the table, so the pattern is not a proof.
    c = {"kind": "modpat", "params": {"P": 6, "m": 2, "pat": [1, 0, 1, 1, 1, 1]},
         "_le": FC.parse("gcd(oxa009191,oxa083105)"), "_re": None}
    ex = CP.explain(c, T)
    assert ex and ex["label"] == "confirmed on range"
    assert any("kernel" in f and "confirmed on" in f for f in ex["facts"])
    assert any("definition" in f for f in ex["facts"])
    bad = dict(c, params={"P": 6, "m": 2, "pat": [1, 1, 1, 1, 1, 0]})
    assert DP.explain(bad, T) is None


def test_convolution_definition_reduces_mod_2(T):
    aut = DP.conv_automaton(DP._entry("oxa177115")["name"])
    assert aut is not None
    assert DP.prim_automaton("oxa177115", T)[1].startswith("A177115: definition")


def test_proth_primes_recognised_as_prime_valued(T):
    assert DP.prime_valued("oxa080076", T)


def test_false_or_unimplied_claims_not_labelled(T):
    # A177115 at odd indices: a(2m+1) = a(m) + k + l (mod 2) varies -> not implied
    assert CP.explain(_c("oxa177115", m=2, q=2, r=1, s=1), T) is None
    assert DP.explain(_c("oxa177115", m=2, q=2, r=1, s=1), T) is None
    # gcd(m, d(m)) at m = 1 (mod 12) is not forced even (m = 1, 25, 49 ... are squares)
    assert DP.explain(_c("gcd(n,tau)", m=2, q=12, r=0, s=1), T) is None
    # only mod-2 claims are in scope
    assert DP.explain(_c("prime[oxa080076]", m=3, q=1, r=1), T) is None


def test_small_prime_modulus_exact_or_confirmed_on_range():
    proved = DP.explain({"kind": "cong", "params": {"m": 3, "q": 3, "r": 0, "s": 0},
                         "_le": ("p", "n"), "_re": None}, None)
    assert proved and proved["label"] == "known_in_principle(definition_parity)"
    assert "mod 3" in proved["scope"]
    assert DP.explain({"kind": "cong", "params": {"m": 3, "q": 3, "r": 1, "s": 0},
                       "_le": ("p", "n"), "_re": None}, None) is None
    assert DP.explain({"kind": "cong", "params": {"m": 5, "q": 5, "r": 0, "s": 0},
                       "_le": ("p", "n"), "_re": None}, None)["label"].startswith("known_in_principle")
    assert DP.explain({"kind": "cong", "params": {"m": 4, "q": 4, "r": 0, "s": 0},
                       "_le": ("p", "n"), "_re": None}, None) is None

    class Bag:
        t = {"toy": [0] + [n % 3 for n in range(1, 900)]}

    toy = {"kind": "cong", "params": {"m": 3, "q": 3, "r": 0, "s": 0}, "_le": ("p", "toy"), "_re": None}
    got = DP.explain(toy, Bag)
    assert got and got["label"] == "confirmed on range"
    assert "not a proof" in got["scope"] and "3-kernel" in got["scope"]
    bad = {"kind": "cong", "params": {"m": 3, "q": 3, "r": 1, "s": 0}, "_le": ("p", "toy"), "_re": None}
    assert DP.explain(bad, Bag) is None


def test_lpf_parity_reduces_and_gpf_does_not_copy_it(T, monkeypatch):
    """lpf(x) has the parity of x for x >= 1. gpf(x) is even only for powers of 2."""
    lpf_even = _c("lpf[n]", m=2, q=2, r=0, s=0)
    ex = DP.explain(lpf_even, T)
    assert ex and ex["label"] == "known_in_principle(definition_parity)"
    assert any("lpf(x) is odd exactly when x is odd" in f for f in ex["facts"])
    # gpf(n) even for even n is false (gpf(6) = 3). Do not rewrite it to "n is even".
    assert DP.explain(_c("gpf[n]", m=2, q=2, r=0, s=0), T) is None
    # Odd gpf follows from an odd argument, not from the argument's parity in both directions.
    gpf_odd = DP.explain(_c("gpf[prime]", m=2, q=2, r=1, s=0), T)
    assert gpf_odd and "power of 2" in " ".join(gpf_odd["facts"])
    assert gpf_odd["label"] == "known_in_principle(definition_parity)"
    monkeypatch.setenv("COLONY_COMPOSITIONAL", "live")
    monkeypatch.setenv("COLONY_DEEP", "off")
    monkeypatch.setenv("COLONY_REFCHECK_STRONG", "off")
    from colony import surprise_credit as SC
    claim = {"kind": "cong", "lhs": "lpf[fib]", "rhs": "", "params": {"m": 2, "q": 3, "r": 0, "s": 0},
             "unknown": True, "known_check": "no known result found", "reference": "no reference found",
             "prediction": 0.4, "range": [1, 40], "sig": "lpf-fib"}
    why = SC.explained(claim, trivial=False)
    assert why.startswith("known in principle")
    assert SC.credit(claim, trivial=False)["credit"] == 0.0
    # The same reduction does not zero a gpf claim that is not a consequence of parity.
    other = dict(claim, lhs="gpf[n]", params={"m": 2, "q": 2, "r": 0, "s": 0}, sig="gpf-n")
    assert DP.explain({"kind": "cong", "params": other["params"], "_le": FC.parse("gpf[n]"), "_re": None}, T) is None


def test_fitted_kernel_is_confirmed_on_range_not_proved(T):
    """A partial sum whose primitive is only a fitted 2-kernel is confirmed on the table.
    fib's parity uses the C-finite order bound instead, and that one stays a proof."""
    ex = DP.explain(_c("S(oxa157100)", m=2, q=2, r=1, s=0), T)
    assert ex and ex["label"] == "confirmed on range"
    assert "not a proof" in ex["scope"]
    assert any("kernel" in f and "confirmed on" in f for f in ex["facts"])
    fib = DP.explain(_c("fib", m=2, q=3, r=0, s=0), T)
    assert fib and fib["label"] == "known_in_principle(definition_parity)"
    assert any("C-finite order bound" in f for f in fib["facts"])


def test_trivial_reason_label(T, monkeypatch):
    monkeypatch.setenv("COLONY_COMPOSITIONAL", "live")
    import random
    assert FC.trivial_reason(_c("dbl(oxa177115)", m=2, q=1, r=0), T, random.Random(0), FC.fit_n()) == \
        "known_in_principle(definition_parity)"


def _factor_table(apk, n_max: int) -> list[int]:
    """a(0)=0, a(1)..a(n_max) from a multiplicative a(p^e)."""
    out = [0, 1]
    for n in range(2, n_max + 1):
        v = DP._factor_value(apk, n)
        assert v is not None
        out.append(v)
    return out


def test_multiplicative_definition_explains_even_prime_power(T, monkeypatch):
    """A factorization formula that matches the table explains a(p^e * odd) when a(p^e) is even.

    The product-of-prime-powers shape is one vetted form. A second sequence uses a different
    form, so the rule is not a special case of one OEIS entry. A keyword of 'mult' with no
    formula, and a formula that misses the table, explain nothing.
    """
    import random
    ex = DP.explain(_c("dbl(oxa048767)", m=2, q=2, r=0, s=1), T)
    assert ex and ex["label"] == "known_in_principle(definition_parity)"
    blob = " ".join(ex["facts"]).lower()
    assert "multiplicative" in blob and "a(2^1)" in blob and "even" in blob
    # a(4) = 3 is odd, so "even for every even argument" does not follow.
    assert DP.explain(_c("oxa048767", m=2, q=2, r=0, s=0), T) is None
    # The keyword alone is not a definition.
    assert DP.parse_multiplicative_name("Number of widgets.") is None

    # Completely multiplicative a(p) = p is the identity, not the sequence above.
    # On odd n, dbl(a)(n) = a(2n) = 2 * (odd) and the power of 2 is exactly 2^1.
    ident = DP.parse_multiplicative_name("Completely multiplicative with a(p) = p.")
    assert ident and ident["kind"] == "completely"
    terms = _factor_table(DP._apk_fn(ident), 400)

    def _entry(w, _orig=DP._entry):
        if w == "oxsynth":
            return {"anum": "SYNTH", "name": "Completely multiplicative with a(p) = p.", "keyword": "mult"}
        return _orig(w)

    monkeypatch.setattr(DP, "_entry", _entry)

    class Bag:
        t = {"oxsynth": terms}

    synth = {"kind": "cong", "params": {"m": 2, "q": 2, "r": 0, "s": 1},
             "_le": ("dbl", ("p", "oxsynth")), "_re": None}
    assert DP.multiplicative_def("oxsynth", Bag()) is not None
    got = DP.explain(synth, Bag())
    assert got and got["label"] == "known_in_principle(definition_parity)"
    assert any("multiplicative definition (SYNTH)" in f for f in got["facts"])
    # Same formula, table of ones: the definition does not reproduce the table.
    DP._MULT.pop(("oxsynth", 401), None)

    def _entry_bad(w, _orig=DP._entry):
        if w == "oxbad":
            return {"anum": "BAD", "name": "Completely multiplicative with a(p) = p.", "keyword": "mult"}
        return _orig(w)

    monkeypatch.setattr(DP, "_entry", _entry_bad)
    assert DP.multiplicative_def("oxbad", type("B", (), {"t": {"oxbad": [0] + [1] * 400}})()) is None
    # An odd a(p^e) does not force the product even. a(p^e) = 1 for every power.
    ones = DP.parse_multiplicative_name("Multiplicative with a(p^e) = 1.")
    assert ones and ones["kind"] == "at_power"
    DP._MULT.pop(("oxone", len([0] + [1] * 400)), None)

    def _entry_one(w, _orig=DP._entry):
        if w == "oxone":
            return {"anum": "ONE", "name": "Multiplicative with a(p^e) = 1.", "keyword": "easy,mult"}
        return _orig(w)

    monkeypatch.setattr(DP, "_entry", _entry_one)
    one_tab = [0] + [1] * 400
    one_claim = {"kind": "cong", "params": {"m": 2, "q": 2, "r": 0, "s": 1},
                 "_le": ("dbl", ("p", "oxone")), "_re": None}
    assert DP.explain(one_claim, type("B", (), {"t": {"oxone": one_tab}})()) is None

    # The two claims already settled by the existing filter stay settled. They are not this gap.
    monkeypatch.setenv("COLONY_COMPOSITIONAL", "live")
    assert FC.trivial_reason(_c("D((sigma*sqfree))", m=2, q=2, r=0, s=1), T, random.Random(0), FC.fit_n())
    assert FC.trivial_reason(_c("S((pi*pi))", m=2, q=2, r=1, s=0), T, random.Random(0), FC.fit_n())
    monkeypatch.setenv("COLONY_DEEP", "off")
    monkeypatch.setenv("COLONY_REFCHECK_STRONG", "off")
    from colony import surprise_credit as SC
    claim = {"kind": "cong", "lhs": "dbl(oxa048767)", "rhs": "",
             "params": {"m": 2, "q": 2, "r": 0, "s": 1},
             "unknown": True, "known_check": "no known result found",
             "reference": "no reference found", "prediction": 0.4,
             "range": [1, 40], "sig": "mult-factor"}
    why = SC.explained(claim, trivial=False)
    assert why.startswith("known in principle") and "multiplicative" in why.lower()
    assert SC.credit(claim, trivial=False)["credit"] == 0.0
