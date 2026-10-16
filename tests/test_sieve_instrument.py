"""Sieve instrument (colony reward 2026-10-16): reproduce known values, caps, HL constants."""
import pytest

from colony.instruments import available, sieve

C_OK = sieve._helper() is not None
# A104062: (n, p_N = prime number 20*10^n, a(n)) — last prime of the quadruple must be <= p_N.
A104062 = [(1, 1223, 1), (2, 17389, 12), (3, 224737, 64), (4, 2750159, 416), (5, 32452843, 2748),
           (6, 373587883, 19348)]


@pytest.mark.parametrize("n,pN,a", A104062)
def test_a104062_known_terms(n, pN, a):
    if pN > sieve.PY_MAX_SPAN and not C_OK:
        pytest.skip("C helper unavailable")
    if n <= 4:
        assert sieve.nth_prime(20 * 10 ** n) == pN
    assert sieve.count_pattern([6, 6, 6], 0, pN - 18 + 1)["total"] == a


def test_twin_counts_and_backends_agree():
    r6 = sieve.count_pattern([2], 0, 10 ** 6, backend="python")
    assert r6["total"] == 8169
    r7 = sieve.count_pattern([2], 0, 10 ** 7, mod=4, checkpoints=[10 ** 6])
    assert r7["total"] == 58980 and r7["checkpoints"][10 ** 6] == 8169
    assert sum(r7["by_residue"].values()) == 58980
    if C_OK:
        assert sieve.count_pattern([2, 4], 0, 10 ** 6)["total"] == \
            sieve.count_pattern([2, 4], 0, 10 ** 6, backend="python")["total"]


def test_hl_constants():
    assert sieve.hl_constant([0, 6, 12, 18]) == pytest.approx(8.30236, abs=2e-4)
    assert sieve.hl_constant([0, 2]) == pytest.approx(1.32032, abs=2e-4)
    assert sieve.hl_constant([0, 2, 4]) == 0.0 and not sieve.is_admissible([0, 2, 4])


def test_hl_forecast_close_to_count():
    f = sieve.forecast_and_count([6, 6, 6], 0, 10 ** 7)
    assert f["agree"] and 0.85 < f["ratio"] < 1.15


def test_caps_and_registry():
    with pytest.raises(sieve.SieveCapExceeded):
        sieve.count_pattern([2], 0, 10 ** 12)
    with pytest.raises(sieve.SieveCapExceeded):
        sieve.count_pattern([2], 0, 10 ** 6, max_span=10 ** 5)
    assert "sieve.count_pattern" in available()
    assert len(sieve.log_checkpoints(10 ** 6, 10 ** 7, 10)) == 10
