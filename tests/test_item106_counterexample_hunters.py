"""Item 106: counterexample hunters (far residues + CRT lift, cross-entropy index search with shrinking)."""
from fractions import Fraction

from colony import counterexample_hunters as H
from colony import oeis_deep as D


class _Fake:
    """Holo-like generator: a(n) = n except a(5000) = 0 (a planted far counterexample)."""
    s0 = 0

    def _v(self, i):
        return 0 if i == 5000 else i

    def mod(self, M, hi, seconds=1e9):
        return [self._v(i) % M for i in range(0, min(hi, 20000) + 1)]

    def b_value(self, n, M=None):
        v = self._v(n)
        return v % M if M else Fraction(v)

    def exact(self, hi, seconds=1e9, bits=0):
        return [self._v(i) for i in range(hi + 1)]


def _entry(parts, rels=("=",), mod=None):
    return {"id": "t", "anum": "A000000", "claim": {"form": "relation", "parts": list(parts), "rels": list(rels),
                                                     "mod": mod}}


def test_crt_lift_recovers_small_signed_values():
    for v in (-123456789, 0, 7, 10 ** 15 + 3):
        rs = [(v % p, p) for p in H.PRIMES]
        assert H.crt_lift(rs)["symmetric"] == v


def test_far_modular_finds_and_confirms_planted_failure():
    e = _entry(["a(n)-a(n-1)", "1"])
    r = H.far_modular(e, _Fake(), 100, 10.0)
    assert r["status"] == "counterexample_confirmed" and r["n"] == 5000
    assert r["lift"]["symmetric"] == -5000          # (0 - 4999) - 1
    assert all(r["per_modulus"])


def test_far_modular_holds_reports_range():
    e = _entry(["a(n)", "n"])

    class Ok(_Fake):
        def _v(self, i):
            return i
    r = H.far_modular(e, Ok(), 10, 5.0)
    assert r["status"] == "holds_mod_primes" and r["hi"] >= 10000


def test_non_ring_safe_claims_skipped():
    e = _entry(["1/a(n)", "n"])
    assert H.far_modular(e, _Fake(), 10, 1.0)["status"] == "not_ring_safe"


def test_cem_samples_far_indices_and_shrinks():
    # a(n) = n as a C-finite recurrence; the (false) congruence a(n) == 0 mod 7 fails almost everywhere.
    cf = {"s0": 0, "seed": [Fraction(0), Fraction(1)], "c": [Fraction(2), Fraction(-1)]}
    g = D.CF(cf)
    e = _entry(["a(n)", "0"], mod=7)
    r = H.cem_sample(e, g, 10 ** 7, seed=1, seconds=5.0)
    assert r["status"] == "counterexample_confirmed"
    assert r["n"] <= r["n_hit"] and r["n"] % 7 != 0
    assert r["n_hit"] >= 10 ** 7


def test_cem_identity_that_holds_finds_nothing():
    cf = {"s0": 0, "seed": [Fraction(0), Fraction(1)], "c": [Fraction(1), Fraction(1)]}   # Fibonacci
    e = _entry(["a(n)", "a(n-1)+a(n-2)"])
    r = H.cem_sample(e, D.CF(cf), 10 ** 7, seed=3, seconds=3.0)
    assert r["status"] == "no_violation_sampled" and r["sampled"] > 0


def test_cem_needs_random_access():
    assert H.cem_sample(_entry(["a(n)", "n"]), _Fake(), 10, 1, 1.0)["status"] == "no_random_access"


def test_off_on_control(monkeypatch):
    from colony import arm
    monkeypatch.setattr(arm, "is_control", lambda: True)
    assert H.enabled() is False
    assert H.turn("c1") is None


def test_switch_off(monkeypatch):
    monkeypatch.setenv("COLONY_CE_HUNTERS", "off")
    assert H.enabled() is False


def test_conditional_definitions_never_hunted():
    e = {"id": "x", "anum": "A1", "claim": {"form": "relation", "parts": ["a(n)", "n"], "rels": ["="]},
         "definition": {"kind": "holo", "provenance": "formula", "polys": {"0": [1], "1": [-1]}},
         "offset": 0, "terms": list(range(50))}
    assert H._held_targets([e], {"targets": {"x": {"status": "holds_on_range"}}}) == []
