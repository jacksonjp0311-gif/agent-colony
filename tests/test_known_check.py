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


class _FakeNet:
    def __init__(self, recs):
        self.recs = recs

    def get(self, url, name):
        import json
        a = name.split(".")[0]
        return json.dumps([self.recs[a]]) if a in self.recs else None


def test_cfinite_entry_from_oeis_signature_or_stated_recurrence():
    from colony import frontier_conjectures as FC
    from colony import known_check as K
    from colony import obscure_pool as OP
    T = FC.Tables()
    fib_like = [p for p in OP.PRIMS if OP.ANUM.get(p) == "A082411"]
    if not fib_like:
        return
    p = fib_like[0]
    net = _FakeNet({"A082411": {"name": "Second-order linear recurrence sequence with a(n) = a(n-1) + a(n-2)."}})
    e = FC.parse(f"S({p})")
    c = {"kind": "rec", "lhs": f"S({p})", "rhs": "", "params": {}, "_le": e, "_re": None}
    assert K.cfinite_entry(c, T, net, None).startswith("known: its ingredients are C-finite")
    wrong = _FakeNet({"A082411": {"name": "x", "link": ["Index entries for linear recurrences with constant "
                                                        "coefficients, signature (2,1)."]}})
    assert K.cfinite_entry(c, T, wrong, None) is None          # stated signature must hold on our table
    g = FC.parse(f"gcd({p},{p})")
    assert K.cfinite_entry({"kind": "rec", "lhs": "", "params": {}, "_le": g, "_re": None}, T, net, None) is None


def test_recurrence_residues_settle_congruences_finitely():
    """Residues computed from a verified recurrence agree with the table, settle true claims, catch
    false ones, and give a certificate the checker accepts only for citable recurrences."""
    from colony import frontier_conjectures as FC
    from colony import known_check as K
    from colony import proof_check as PC
    T = FC.Tables(lim=3000, exp_n=400)
    x = [int(v) for v in T.t["fib"][1:]]
    u, pre, P = PC.rec_residues(x, [1, 1], 0, 4)
    assert P == 6 and all(u[i] == x[i] % 4 for i in range(len(u)))
    C = lambda lhs, **p: {"kind": "cong", "lhs": lhs, "rhs": "", "params": p, "_le": FC.parse(lhs), "_re": None}  # noqa: E731
    recs = {"fib": {"sig": [1, 1], "k0": 0, "source": "defining: fib"}}
    true = C("dbl(fib)", m=2, r=0, q=3, s=0)            # F(6k) even
    false = C("S(fib)", m=2, r=0, q=3, s=1)
    assert PC.recurrence_residues(true, T, recs)["holds"]
    got = PC.recurrence_residues(false, T, recs)
    assert not got["holds"] and got["first_fail"] is not None
    vals = FC.evaluate(false["_le"], 60, T)                 # first failure agrees with the real values
    assert vals[got["first_fail"] - 1] % 2 != 0
    assert K.recurrence_certificate(true, T, recs)["checker"].endswith("ok")
    fitted = {"fib": {"sig": [1, 1], "k0": 0, "source": "table: fitted"}}
    assert K.recurrence_certificate(true, T, fitted) is None
    claim = {"kind": "cong", "lhs": "dbl(fib)", "rhs": "", "params": true["params"]}
    bad = {"method": "recurrence residues", "Q": 1, "N0": PC.N0, "classes": {},
           "recurrences": {"fib": {"sig": [2, 1], "k0": 0, "source": "oeis A000045"}}}
    assert PC.check(bad, claim, T)[0] is False                # a wrong stated recurrence is rejected
    assert PC.recurrence_residues(C("gcd(fib,lucas)", m=2, r=1, q=1, s=0), T,
                                  dict(recs, lucas=recs["fib"])) is None   # gcd only for r = 0
    # eventually linear (n + c after an irregular start) is found and re-checked on the table
    if "oxa047700" in T.t:           # A047700: irregular start, then n + c
        r = K.verified_recurrence("oxa047700", T)
        assert r and r["sig"][:2] == [2, -1] and not any(r["sig"][2:]) and r["source"].startswith("table")
        lab = K.recurrence_residue(C("S(oxa047700)", m=2, r=1, q=4, s=1), T, None, None)
        assert lab and lab.startswith("known in principle") and "no certificate" in lab
