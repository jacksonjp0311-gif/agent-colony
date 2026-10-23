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
    ("S(oxa157100)", dict(m=2, q=2, r=1, s=0)),       # A157100 partial sums odd at even n
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
    # gcd(gcd(n, d(n)), A083105) mod 2 by n mod 6: even iff n even, d(n) even and A083105(n) even
    c = {"kind": "modpat", "params": {"P": 6, "m": 2, "pat": [1, 0, 1, 1, 1, 1]},
         "_le": FC.parse("gcd(oxa009191,oxa083105)"), "_re": None}
    ex = CP.explain(c, T)
    assert ex and ex["label"] == "known_in_principle(definition_parity)"
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


def test_trivial_reason_label(T, monkeypatch):
    monkeypatch.setenv("COLONY_COMPOSITIONAL", "live")
    import random
    assert FC.trivial_reason(_c("dbl(oxa177115)", m=2, q=1, r=0), T, random.Random(0), FC.fit_n()) == \
        "known_in_principle(definition_parity)"
