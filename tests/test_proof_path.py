"""Stage 4: proof path + separate checker."""
import copy

import pytest

from colony import frontier_conjectures as FC
from colony import proof_check as K
from colony import proof_path as PP

pytest.importorskip("sympy")


@pytest.fixture(scope="module")
def T():
    return FC.Tables(lim=6000, exp_n=300)


def C(kind, lhs, rhs="", **params):
    return {"kind": kind, "lhs": lhs, "rhs": rhs, "params": params}


def test_lemma_guard(T):
    assert K.guard(T)["ok"]


def test_periodic_proofs_and_rejections(T):
    good = C("cong", "sigma[digsum]", m=3, r=0, q=3, s=2)
    cert = PP.prove(good, T)
    assert cert and cert["method"] == "periodic residues"
    assert K.check(cert, good, T)[0]
    bad = C("cong", "sigma[digsum]", m=3, r=1, q=3, s=2)
    assert PP.prove(bad, T) is None
    assert not K.check(cert, bad, T)[0]                      # a certificate does not transfer
    t = copy.deepcopy(cert)
    node = next(iter(t["classes"].values()))["lhs"]
    node["val"] = K.V(node["val"]["c"] + 1, node["val"]["a"], node["val"]["d"])
    assert not K.check(t, good, T)[0]                        # tampered value rejected
    assert PP.prove(C("cong", "D((digsum*digsum))", m=2, r=1, q=2, s=0), T)
    assert PP.prove(C("cong", "cmax[gpf]", m=3, r=1, q=2, s=1), T)
    assert PP.prove(C("cong", "S((phi*rad))", m=2, r=1, q=1, s=0), T)
    assert PP.prove(C("cong", "tau", m=2, r=0, q=1, s=0), T) is None   # false (squares)


def test_inequality_and_closed_form(T):
    le = C("le", "(gpf-tau)", "dbl((gpf-bigomega))")
    cert = PP.prove(le, T)
    assert cert and cert["method"] == "basic-inequality derivation" and K.check(cert, le, T)[0]
    assert PP.prove(C("le", "dbl((gpf-bigomega))", "(gpf-tau)"), T) is None
    rec = C("rec", "dbl((pow2-lpf))", c=[-4, 5])
    cert = PP.prove(rec, T)
    assert cert and cert["method"] == "closed form (sympy)"
    assert PP.prove(C("rec", "dbl((pow2-lpf))", c=[-4, 6]), T) is None
    assert PP.prove(C("identity", "dbl(fib)", "(fib*lucas)"), T)
    assert PP.prove(C("identity", "dbl(fib)", "(fib*fib)"), T) is None


def test_mode_default(monkeypatch):
    monkeypatch.delenv("COLONY_PROOF", raising=False)
    assert PP.mode() == "shadow"


def test_textbook_lemmas(T):
    """Prime-race steps, digit-pair parity, tau(p) = 2, sopfr(p-1) <= p-1, squarefree split."""
    goods = [C("cong", "D(gcd(cheb4,phi))", m=2, r=0, q=3, s=2),
             C("cong", "S(gcd(digsum,phi))", m=2, r=1, q=4, s=3),
             C("le", "sopfr[phi]", "(sopfr-omega)"),
             C("divides", "tau[lpf]", "(lpf-pell)")]
    rules = []
    for g in goods:
        cert = PP.prove(g, T)
        assert cert and K.check(cert, g, T)[0], g
        rules.append(cert)
    assert PP.prove(C("cong", "D(gcd(cheb4,phi))", m=2, r=1, q=3, s=2), T) is None
    assert PP.prove(C("cong", "S(gcd(digsum,phi))", m=2, r=0, q=4, s=3), T) is None
    assert PP.prove(C("le", "(sopfr-omega)", "sopfr[phi]"), T) is None
    assert PP.prove(C("divides", "tau[lpf]", "(lpf-fib)"), T) is None
    bad = C("cong", "S(gcd(digsum,phi))", m=2, r=0, q=4, s=3)
    assert not K.check(rules[1], bad, T)[0]


def test_step_and_branch_unit():
    assert K.step_lemma("pi", 0, 2, True) and K.step_lemma("pi", 1, 2, True) is None
    assert K.step_lemma("digsum", 1, 2, True)[1] == 1 and K.step_lemma("digsum", 0, 2, True) is None
    assert K.compose_prime_lemma("tau", "lpf", True)[2] == 2
    assert K.compose_prime_lemma("tau", "lpf", False) is None and K.compose_prime_lemma("tau", "rad", True) is None
    assert K.branch_value("tau", (0, 1, 1), 1, 0)[1] == K.V(0, {}, 2)
    assert K.branch_value("tau", (0, 1, 1), 2, 0) is None and K.branch_value("tau", (0, 1), 1, 0) is None
