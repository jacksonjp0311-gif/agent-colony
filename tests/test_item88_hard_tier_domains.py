"""Item 88: new hard-tier families (classical theorems) the desk may hard_enable through the Oracle.

Fixture-only: runs the check functions directly on their catalog window and on the disjoint
shifted window the Oracle uses; it never enables anything and does not read run state.
"""
from __future__ import annotations

import pytest

import society.benchmarks.artifacts.lemma_impl as LI
from colony.conjecture_mutations import MUTATION_SNIPPETS

# name -> (check, base window lo, hi)
NEW = {
    "jacobi_two_squares": (LI.check_jacobi_two_squares, 1, 400),
    "jacobi_four_squares": (LI.check_jacobi_four_squares, 1, 90),
    "legendre_factorial_valuation": (LI.check_legendre_factorial_valuation, 0, 200),
    "kummer_carries": (LI.check_kummer_carries, 0, 40),
    "ramanujan_partition_congruences": (LI.check_ramanujan_partition_congruences, 0, 30),
    "primitive_root_count": (LI.check_primitive_root_count, 2, 200),
    "zeckendorf_unique": (LI.check_zeckendorf_unique, 1, 300),
    "dedekind_reciprocity": (LI.check_dedekind_reciprocity, 2, 30),
    "korselt_criterion": (LI.check_korselt_criterion, 4, 1200),
    "pisano_prime_period": (LI.check_pisano_prime_period, 7, 400),
}


@pytest.mark.parametrize("name", sorted(NEW))
def test_new_family_holds_on_base_and_shifted_window(name):
    fn, lo, hi = NEW[name]
    assert all(fn(n) for n in range(lo, hi))
    assert all(fn(n) for n in range(hi, 2 * hi - lo))  # the Oracle's disjoint shifted window


@pytest.mark.parametrize("name", sorted(NEW))
def test_new_family_is_in_catalog_and_desk_snippets(name):
    assert name in {n for n, _f, _e in LI.HARD_TIER_LEMMAS}
    assert (name, "hard_enable", f"enable:{name}") in MUTATION_SNIPPETS


def test_checks_are_not_vacuous():
    # Known values: each statement is exercised, not trivially true.
    assert LI._r2(25) == 12 and LI._r2(3) == 0
    assert LI._vp(math_factorial(10), 2) == 8
    assert LI._carries(1, 1, 2) == 1
    assert LI._partition_counts(9)[9] == 30
    assert LI._pisano(7) == 16
    assert LI.check_korselt_criterion(561)  # Carmichael: both sides true
    assert LI._dedekind_sum(1, 3) != 0


def math_factorial(n):
    import math
    return math.factorial(n)
