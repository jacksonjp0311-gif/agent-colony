"""Strong known-results check: each step explains what it should and nothing false."""
import pytest

from colony import frontier_conjectures as FC
from colony import known_check as K


@pytest.fixture(scope="module")
def T():
    return FC.Tables(lim=6000, exp_n=600)


def C(kind, lhs, rhs="", **p):
    return {"kind": kind, "lhs": lhs, "rhs": rhs, "params": p, "_le": FC.parse(lhs), "_re": FC.parse(rhs) if rhs else None}


def test_cfinite_identity(T):
    assert K.cfinite_identity(C("divides", "stree_ladder", "dbl(stree_ladder)"), T)
    assert K.cfinite_identity(C("divides", "fib", "dbl(stree_grid3)"), T)
    assert K.cfinite_identity(C("divides", "pell", "dbl(fib)"), T) is None          # false claim
    assert K.cfinite_identity(C("divides", "part", "dbl(part)"), T) is None          # not C-finite


def test_periodic_and_tautology(T):
    assert K.periodic_null(C("cong", "gcd(match_ladder,stree_ladder)", m=2, r=1, q=1, s=0), T)
    assert K.periodic_null(C("cong", "gcd(match_ladder,stree_ladder)", m=2, r=0, q=1, s=0), T) is None
    r = K.check(C("divides", "gpf[pnot3]", "pnot3"), T)
    assert r["explained"] and r["step"] == "tautology"


def test_unexplained_stays_open(T):
    r = K.check(C("cong", "rev[pdist]", m=2, r=1, q=6, s=1), T)
    assert not r["explained"]


def test_find_recurrence():
    assert K.find_recurrence([int(x) for x in FC.Tables(lim=100, exp_n=120).t["fib"][1:100]]) == [1, 1]


def test_credit_zero_when_explained_live(monkeypatch):
    from colony import surprise_credit as S
    r = {"kind": "divides", "lhs": "stree_ladder", "rhs": "dbl(stree_ladder)", "params": {}, "unknown": True,
         "statement": "zz stree_ladder(n) divides dbl(stree_ladder)(n)", "prediction": 0.2, "hunt_value": 1.0,
         "range": [31, 1000]}
    monkeypatch.setenv("COLONY_REFCHECK_STRONG", "live")
    S._KNOWN.clear()
    assert S.credit(r, trivial=False)["credit"] == 0.0
    monkeypatch.setenv("COLONY_REFCHECK_STRONG", "off")
    S._KNOWN.clear()
    assert S.credit(r, trivial=False)["credit"] > 0


def test_pentagonal_parity_fact(T):
    pent = set()
    for k in range(-60, 61):
        pent.add(k * (3 * k - 1) // 2)
    assert all((T.t["pdist"][n] % 2 == 1) == (n in pent) for n in range(1, 300))
    assert K.periodic_null(C("cong", "rad[pdist]", m=2, r=0, q=5, s=3), T)


def test_deep_range():
    from colony import deep_range as D
    tb = D.tables(30000)
    T2 = FC.Tables(lim=30000, exp_n=300)
    for k in D.DEEP_PRIMS:
        assert tb[k][1:30001] == T2.t[k][1:30001], k
    c = C("cong", "tau", m=2, r=0, q=1, s=0)
    assert D.test(c, T2, N=30000)["status"] == "falsified"
    c = C("cong", "sigma[digsum]", m=3, r=0, q=3, s=2)
    assert D.test(c, T2, N=30000)["status"] == "survived"
    assert D.test(C("divides", "fib", "dbl(fib)"), T2, N=30000)["status"] == "n/a"


def test_parity_reduction_rejects_false_claim(T):
    assert K.periodic_null(C("cong", "rad[pdist]", m=2, r=0, q=5, s=1), T) is None
