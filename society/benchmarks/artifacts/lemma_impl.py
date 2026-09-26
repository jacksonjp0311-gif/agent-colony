"""Colony lemma artifact — algebraic / integer identity checks (basic + hard tier).

The colony may extend CANDIDATE_LEMMAS and HARD_TIER_LEMMAS. Harness scores 0
unless all enabled basic checks pass; hard tier is required for high scores so
textbook identity dumps cannot ace alone.

This is scaffolding for education — NOT claiming novel theorems,
NOT Millennium solutions, NOT AGI.
"""
from __future__ import annotations

from typing import Callable


def binomial(n: int, k: int) -> int:
    if k < 0 or k > n:
        return 0
    k = min(k, n - k)
    r = 1
    for i in range(k):
        r = r * (n - i) // (i + 1)
    return r


def fibonacci(n: int) -> int:
    """F(0)=0, F(1)=1, … iterative (educational, not a discovery)."""
    if n < 0:
        raise ValueError("n>=0")
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def check_square_of_sum(a: int, b: int) -> bool:
    """(a+b)^2 = a^2 + 2ab + b^2"""
    return (a + b) ** 2 == a * a + 2 * a * b + b * b


def check_difference_of_squares(a: int, b: int) -> bool:
    """a^2 - b^2 = (a-b)(a+b)"""
    return a * a - b * b == (a - b) * (a + b)


def check_sum_first_n_odds(n: int) -> bool:
    """1+3+...+(2n-1) = n^2"""
    if n < 0:
        return False
    s = sum(2 * i - 1 for i in range(1, n + 1))
    return s == n * n


def check_binomial_symmetry(n: int, k: int) -> bool:
    """C(n,k) = C(n, n-k)"""
    return binomial(n, k) == binomial(n, n - k)


def check_pascal_identity(n: int, k: int) -> bool:
    """C(n,k) = C(n-1,k-1) + C(n-1,k) for 0<k<n"""
    if n <= 0 or k <= 0 or k >= n:
        return True
    return binomial(n, k) == binomial(n - 1, k - 1) + binomial(n - 1, k)


def check_frobenius_coin_two(a: int = 4, b: int = 7, limit: int = 50) -> bool:
    """For coprime a,b every N > ab-a-b is representable as xa+yb (x,y>=0).
    Small exhaustive check up to `limit` — educational, not a discovery claim.
    """
    if a <= 0 or b <= 0:
        return False
    frobenius = a * b - a - b
    representable = set()
    for x in range(0, limit // a + 2):
        for y in range(0, limit // b + 2):
            representable.add(x * a + y * b)
    for n in range(frobenius + 1, limit + 1):
        if n not in representable:
            return False
    return True


def check_polynomial_expand() -> bool:
    """(x+1)^3 = x^3 + 3x^2 + 3x + 1 via evaluation at sample points."""

    def lhs(x: int) -> int:
        return (x + 1) ** 3

    def rhs(x: int) -> int:
        return x**3 + 3 * x**2 + 3 * x + 1

    return all(lhs(x) == rhs(x) for x in range(-5, 6))


def check_sum_first_n_cubes(n: int) -> bool:
    """1^3+...+n^3 = (n(n+1)/2)^2"""
    if n < 0:
        return False
    s = sum(i ** 3 for i in range(1, n + 1))
    return s == (n * (n + 1) // 2) ** 2


def check_geometric_sum(a: int = 2, n: int = 10) -> bool:
    """1+a+...+a^{n-1} = (a^n-1)/(a-1) for a!=1"""
    if a == 1:
        return True
    lhs = sum(a ** i for i in range(n))
    rhs = (a ** n - 1) // (a - 1)
    return lhs == rhs


def check_handshaking_lemma_small() -> bool:
    """Sum of degrees = 2|E| on a tiny complete graph K4."""
    # K4: 4 verts, each deg 3, edges=6
    degrees = [3, 3, 3, 3]
    edges = 6
    return sum(degrees) == 2 * edges


# ---------------------------------------------------------------------------
# HARD TIER — adversarial ranges + multi-step / derived identities
# Classical small-range dumps alone cannot ace these.
# ---------------------------------------------------------------------------


def check_adversarial_sum_cubes() -> bool:
    """Property test: sum-of-cubes identity on large + edge n (not just n<30)."""
    edges = [0, 1, 2, 50, 100, 200, 500]
    return all(check_sum_first_n_cubes(n) for n in edges)


def check_adversarial_binomial_pascal() -> bool:
    """Adversarial ranges: Pascal + symmetry for n up to 40 (stress factorial growth)."""
    for n in range(0, 41):
        for k in range(0, n + 1):
            if not check_binomial_symmetry(n, k):
                return False
            if 0 < k < n and not check_pascal_identity(n, k):
                return False
    return True


def check_vandermonde_convolution(m: int, n: int, r: int) -> bool:
    """C(m+n, r) = sum_k C(m,k) C(n, r-k) — multi-step binomial identity."""
    if m < 0 or n < 0 or r < 0:
        return False
    lhs = binomial(m + n, r)
    rhs = sum(binomial(m, k) * binomial(n, r - k) for k in range(0, r + 1))
    return lhs == rhs


def check_hockey_stick(n: int, r: int) -> bool:
    """sum_{i=r}^{n} C(i,r) = C(n+1, r+1) for n>=r>=0."""
    if r < 0 or n < r:
        return False
    lhs = sum(binomial(i, r) for i in range(r, n + 1))
    rhs = binomial(n + 1, r + 1)
    return lhs == rhs


def check_cassini_identity(n: int) -> bool:
    """Cassini: F(n+1)F(n-1) - F(n)^2 = (-1)^n for n>=1."""
    if n < 1:
        return True
    return fibonacci(n + 1) * fibonacci(n - 1) - fibonacci(n) ** 2 == (-1) ** n


def check_workload_derived_chain() -> bool:
    """Multi-step proof-style workload (educational, not novel discovery).

    Chain: (1) sum-of-cubes for n=20, (2) Vandermonde at (8,7,5),
    (3) hockey-stick at (15,4), (4) Cassini for n=1..25,
    (5) geometric sum at large exponents, (6) consistency:
        triangular(T)=T(T+1)/2 and sum cubes == T^2 for T=triangular(n).
    All must hold — textbook small dumps alone are insufficient.
    """
    if not check_sum_first_n_cubes(20):
        return False
    if not check_vandermonde_convolution(8, 7, 5):
        return False
    if not check_hockey_stick(15, 4):
        return False
    if not all(check_cassini_identity(n) for n in range(1, 26)):
        return False
    if not all(check_geometric_sum(a, n) for a in (2, 3) for n in (20, 30, 40)):
        return False
    # Derived consistency: T = n(n+1)/2 ; sum_{i=1}^n i^3 = T^2
    for n in (10, 25, 40):
        T = n * (n + 1) // 2
        if sum(i ** 3 for i in range(1, n + 1)) != T * T:
            return False
    return True


# Mutable catalog the conjecture desk may extend / mutate.
# Each entry: (name, zero-arg callable returning bool, enabled)
CANDIDATE_LEMMAS: list[tuple[str, Callable[[], bool], bool]] = [
    ("square_of_sum", lambda: all(check_square_of_sum(a, b) for a in range(-8, 9) for b in range(-8, 9)), True),
    ("difference_of_squares", lambda: all(check_difference_of_squares(a, b) for a in range(-8, 9) for b in range(-8, 9)), True),
    ("sum_first_n_odds", lambda: all(check_sum_first_n_odds(n) for n in range(0, 40)), True),
    ("binomial_symmetry", lambda: all(check_binomial_symmetry(n, k) for n in range(0, 16) for k in range(0, n + 1)), True),
    ("pascal_identity", lambda: all(check_pascal_identity(n, k) for n in range(1, 16) for k in range(1, n)), True),
    ("polynomial_expand_cube", check_polynomial_expand, True),
    ("frobenius_4_7", lambda: check_frobenius_coin_two(4, 7, 60), True),
    ("handshaking_small", check_handshaking_lemma_small, True),
    ("geometric_sum", lambda: all(check_geometric_sum(a, n) for a in (2, 3, 5) for n in range(1, 12)), True),
    ("sum_first_n_cubes", lambda: all(check_sum_first_n_cubes(n) for n in range(0, 30)), True),
]

# Hard tier: adversarial + multi-step. Start with NONE enabled so textbook-only
# baseline is measurable; conjecture desk (or mile) enables/adds hard checks.
# After harden mile we seed two hard checks so score has a real hard component.
HARD_TIER_LEMMAS: list[tuple[str, Callable[[], bool], bool]] = [
    ("adversarial_sum_cubes", check_adversarial_sum_cubes, True),
    ("adversarial_binomial_pascal", check_adversarial_binomial_pascal, True),
    # Remaining hard checks start disabled — desk mutations enable them for score lifts.
    ("vandermonde_conv", lambda: all(
        check_vandermonde_convolution(m, n, r)
        for m in range(0, 12) for n in range(0, 12) for r in range(0, m + n + 1)
    ), True),
    ("hockey_stick", lambda: all(
        check_hockey_stick(n, r) for n in range(0, 25) for r in range(0, n + 1)
    ), True),
    ("cassini", lambda: all(check_cassini_identity(n) for n in range(1, 40)), True),
    ("workload_derived_chain", check_workload_derived_chain, True),
]


def run_basic_checks() -> dict[str, bool]:
    out: dict[str, bool] = {}
    for name, fn, enabled in CANDIDATE_LEMMAS:
        if not enabled:
            continue
        try:
            out[name] = bool(fn())
        except Exception:  # noqa: BLE001
            out[name] = False
    return out


def run_hard_checks() -> dict[str, bool]:
    out: dict[str, bool] = {}
    for name, fn, enabled in HARD_TIER_LEMMAS:
        if not enabled:
            continue
        try:
            out[name] = bool(fn())
        except Exception:  # noqa: BLE001
            out[name] = False
    return out


def run_all_checks() -> dict[str, bool]:
    """Union of basic + hard (hard keys prefixed hard: for harness clarity)."""
    out = run_basic_checks()
    for k, v in run_hard_checks().items():
        out[f"hard:{k}"] = v
    return out


def all_pass() -> bool:
    results = run_all_checks()
    return bool(results) and all(results.values())


def impl_id() -> str:
    basic_n = sum(1 for _, _, e in CANDIDATE_LEMMAS if e)
    hard_n = sum(1 for _, _, e in HARD_TIER_LEMMAS if e)
    return f"lemma_impl_v2_basic{basic_n}_hard{hard_n}"
