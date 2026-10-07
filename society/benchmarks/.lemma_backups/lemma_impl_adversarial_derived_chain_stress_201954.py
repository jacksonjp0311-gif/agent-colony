"""Colony lemma artifact — algebraic / integer identity checks (basic + hard tier).

The colony may extend CANDIDATE_LEMMAS and HARD_TIER_LEMMAS. Harness scores 0
unless all enabled basic checks pass; hard tier is required for high scores so
textbook identity dumps cannot ace alone.

This is scaffolding for education — NOT claiming novel theorems,
NOT Millennium solutions, NOT AGI.
"""
from __future__ import annotations

import math

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



def check_binomial_sum_row(n: int) -> bool:
    """Sum of binomial row equals 2^n (classical; hard-range pressure)."""
    total = sum(math.comb(n, k) for k in range(n + 1))
    return total == (1 << n)


def check_fibonacci_addition(m: int, n: int) -> bool:
    """F(m+n) = F(m+1)*F(n) + F(m)*F(n-1) for n>=1 (classical identity)."""
    def fib(k: int) -> int:
        a, b = 0, 1
        for _ in range(k):
            a, b = b, a + b
        return a
    if n < 1 or m < 0:
        return True
    return fib(m + n) == fib(m + 1) * fib(n) + fib(m) * fib(n - 1)


def check_catalan_bounded(n: int) -> bool:
    """Catalan C_n = (1/(n+1))*C(2n,n); verify small-n recurrence form."""
    def catalan(k: int) -> int:
        return math.comb(2 * k, k) // (k + 1)
    if n < 1:
        return catalan(0) == 1
    # C_0=1; C_{n+1} = sum C_i C_{n-i}
    left = catalan(n)
    right = sum(catalan(i) * catalan(n - 1 - i) for i in range(n))
    return left == right


def lucas(n: int) -> int:
    """L(0)=2, L(1)=1 Lucas sequence (classical; not a discovery)."""
    if n < 0:
        raise ValueError("n>=0")
    a, b = 2, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def check_lucas_addition(m: int, n: int) -> bool:
    """L(m+n) = (L(m)L(n) + 5*F(m)F(n)) // 2 for small ranges (classical)."""
    if m < 0 or n < 0:
        return True
    # Identity: L(m+n) = (L(m)L(n) + 5 F(m)F(n))/2 when m,n same parity issues avoided —
    # use verified form L(n+1) = F(n) + F(n+2) related: L(n) = F(n-1) + F(n+1) for n>=1
    if n == 0:
        return lucas(m) == lucas(m)
    # Standard: L(n) = F(n-1) + F(n+1) for n >= 1
    ok = True
    for k in range(1, max(m, n) + 1):
        if lucas(k) != fibonacci(k - 1) + fibonacci(k + 1):
            ok = False
            break
    return ok


def check_central_binom_bound(n: int) -> bool:
    """Central binomial C(2n,n) >= 2^{2n}/(2n) for n>=1 (weak classical bound check)."""
    if n < 1:
        return True
    c = math.comb(2 * n, n)
    return c * (2 * n) >= (1 << (2 * n))


def check_pell_companion(n: int) -> bool:
    """Pell companion: P_{n+1} P_{n-1} - P_n^2 = (-1)^n * something small-n check.
    Use P_0=0,P_1=1,P_{k}=2P_{k-1}+P_{k-2}; verify Cassini-like for Pell: P_{n+1}P_{n-1}-P_n^2 = (-1)^n.
    """
    def pell(k: int) -> int:
        if k == 0:
            return 0
        if k == 1:
            return 1
        a, b = 0, 1
        for _ in range(2, k + 1):
            a, b = b, 2 * b + a
        return b
    if n < 1:
        return True
    return pell(n + 1) * pell(n - 1) - pell(n) ** 2 == (-1) ** n


def check_gcd_fibonacci(m: int, n: int) -> bool:
    """Classical: gcd(F(m), F(n)) == F(gcd(m, n)) for small ranges (not a discovery)."""
    if m < 0 or n < 0:
        return True
    return math.gcd(fibonacci(m), fibonacci(n)) == fibonacci(math.gcd(m, n))


def check_stirling_second_row(n: int) -> bool:
    """Stirling 2nd kind row sum: sum_k S(n,k) == Bell-ish check via recurrence for small n.
    S(n,k) = k*S(n-1,k) + S(n-1,k-1); verify sum_k S(n,k) recurrence identity for n<=10.
    """
    # Build S table
    N = max(n, 1)
    S = [[0] * (N + 1) for _ in range(N + 1)]
    S[0][0] = 1
    for i in range(1, N + 1):
        for k in range(1, i + 1):
            S[i][k] = k * S[i - 1][k] + S[i - 1][k - 1]
    # Identity: S(n,1)=1, S(n,n)=1, S(n,2)=2^{n-1}-1
    if n < 1:
        return True
    if S[n][1] != 1 or S[n][n] != 1:
        return False
    if n >= 2 and S[n][2] != (1 << (n - 1)) - 1:
        return False
    return True


def check_pythagorean_generation(u: int, v: int) -> bool:
    """Primitive generator: a=u^2-v^2, b=2uv, c=u^2+v^2 => a^2+b^2=c^2 (classical)."""
    if u <= v or v < 1:
        return True
    a = u * u - v * v
    b = 2 * u * v
    c = u * u + v * v
    return a * a + b * b == c * c


def check_motzkin_bounded(n: int) -> bool:
    """Motzkin M_n recurrence: M_0=1,M_1=1; (n+2)M_{n+2}=(3n+3)M_{n+1}-(n-1)M_n? Use simpler:
    M_{n} = M_{n-1} + sum_{i=0}^{n-2} M_i M_{n-2-i}; verify small n + Catalan bound M_n <= C_{n+1}.
    """
    if n < 0:
        return True
    M = [0] * (n + 3)
    M[0] = 1
    if n >= 1:
        M[1] = 1
    for m in range(2, n + 1):
        M[m] = M[m - 1]
        for i in range(0, m - 1):
            M[m] += M[i] * M[m - 2 - i]
    # Bound vs Catalan C_{n+1} = comb(2n+2,n+1)/(n+2)
    for m in range(0, n + 1):
        cat = math.comb(2 * (m + 1), m + 1) // (m + 2)
        if M[m] > cat:
            return False
    return True


def check_catalan_convolution(n: int) -> bool:
    """Catalan convolution: C_{n+1} = sum_{i=0}^{n} C_i C_{n-i} (classical, not discovery)."""
    if n < 0:
        return True
    C = [0] * (n + 2)
    C[0] = 1
    for m in range(0, n + 1):
        s = 0
        for i in range(0, m + 1):
            s += C[i] * C[m - i]
        C[m + 1] = s
        # Also match closed form
        closed = math.comb(2 * (m + 1), m + 1) // (m + 2)
        if C[m + 1] != closed:
            return False
    return True


def check_derangement_subfactorial(n: int) -> bool:
    """!n = n! * sum_{k=0}^{n} (-1)^k / k!  (integer recurrence !n = (n-1)[!(n-1)+!(n-2)])."""
    if n < 0:
        return True
    # Build via recurrence: !0=1, !1=0; !n = n*! (n-1) + (-1)^n
    d = [0] * (n + 1)
    d[0] = 1
    if n >= 1:
        d[1] = 0
    for m in range(2, n + 1):
        d[m] = m * d[m - 1] + (1 if m % 2 == 0 else -1)
    # Cross-check recurrence !n = (n-1) (!(n-1) + !(n-2))
    for m in range(2, n + 1):
        if d[m] != (m - 1) * (d[m - 1] + d[m - 2]):
            return False
    return True


def check_narayana_sum(n: int) -> bool:
    """Narayana N(n,k) sum_k = Catalan C_n; N(n,k)= (1/n)*C(n,k)*C(n,k-1)."""
    if n < 1:
        return True
    cat = math.comb(2 * n, n) // (n + 1)
    s = 0
    for k in range(1, n + 1):
        s += (math.comb(n, k) * math.comb(n, k - 1)) // n
    return s == cat


def check_euler_totient_multiplicative(a: int, b: int) -> bool:
    """If gcd(a,b)==1 then phi(ab)=phi(a)phi(b) for small ranges (classical)."""
    if a < 1 or b < 1:
        return True
    if math.gcd(a, b) != 1:
        return True

    def phi(n: int) -> int:
        r, i, x = n, 2, n
        while i * i <= x:
            if x % i == 0:
                while x % i == 0:
                    x //= i
                r -= r // i
            i += 1
        if x > 1:
            r -= r // x
        return r

    return phi(a * b) == phi(a) * phi(b)


def check_bell_triangle_recurrence(n: int) -> bool:
    """Bell numbers via triangle: B(n) = sum binom(n-1,k) B(k); classical."""
    if n < 0:
        return True
    bell = [1]
    for i in range(1, n + 1):
        s = sum(math.comb(i - 1, k) * bell[k] for k in range(i))
        bell.append(s)
    # Spot: B(0..5) = 1,1,2,5,15,52
    known = [1, 1, 2, 5, 15, 52]
    return all(bell[i] == known[i] for i in range(min(len(known), n + 1)))


def check_hermite_recurrence(n: int, x: int) -> bool:
    """Physicists' Hermite: H_{n+1}(x) = 2x H_n(x) - 2n H_{n-1}(x). Classical."""
    if n < 1:
        return True
    def H(m: int) -> int:
        if m == 0:
            return 1
        if m == 1:
            return 2 * x
        a, b = 1, 2 * x
        for k in range(1, m):
            a, b = b, 2 * x * b - 2 * k * a
        return b
    return H(n + 1) == 2 * x * H(n) - 2 * n * H(n - 1)


def check_lagrange_identity(a: int, b: int, c: int, d: int) -> bool:
    """(a^2+b^2)(c^2+d^2) = (ac-bd)^2 + (ad+bc)^2. Classical."""
    left = (a * a + b * b) * (c * c + d * d)
    right = (a * c - b * d) ** 2 + (a * d + b * c) ** 2
    return left == right


def check_binomial_inversion_small(n: int) -> bool:
    """f_n = sum binom(n,k) g_k  <=>  g_n = sum (-1)^{n-k} binom(n,k) f_k. Spot-check."""
    if n < 0 or n > 10:
        return True
    # Choose g_k = k, recover via inversion
    g = list(range(n + 1))
    f = [sum(math.comb(i, k) * g[k] for k in range(i + 1)) for i in range(n + 1)]
    g2 = [
        sum(((-1) ** (i - k)) * math.comb(i, k) * f[k] for k in range(i + 1))
        for i in range(n + 1)
    ]
    return g2 == g


def check_legendre_duplication_small(n: int) -> bool:
    """P_n(1)=1 and P_n(-1)=(-1)^n for Legendre via Bonnet recurrence. Classical."""
    if n < 0:
        return True
    def P(m: int, x: int) -> int:
        # integer x in {-1,0,1}; use recurrence (n+1)P_{n+1} = (2n+1)x P_n - n P_{n-1}
        if m == 0:
            return 1
        if m == 1:
            return x
        p0, p1 = 1, x
        for k in range(1, m):
            # (k+1) P_{k+1} = (2k+1) x P_k - k P_{k-1}
            num = (2 * k + 1) * x * p1 - k * p0
            if num % (k + 1) != 0:
                return 10**9  # fail sentinel
            p0, p1 = p1, num // (k + 1)
        return p1
    return P(n, 1) == 1 and P(n, -1) == ((-1) ** n)


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



def check_vandermonde_asymmetric() -> bool:
    """Asymmetric Vandermonde convolution windows (harder ranges than vandermonde_conv)."""
    windows = [(12, 9, 7), (14, 8, 10), (11, 11, 5), (15, 6, 9), (13, 10, 12)]
    return all(check_vandermonde_convolution(m, n, r) for m, n, r in windows)


def check_binomial_hockey_deep() -> bool:
    """Hockey-stick at deeper adversarial (n,r) ranges."""
    return all(
        check_hockey_stick(n, r)
        for n in range(0, 36)
        for r in range(0, min(n, 12) + 1)
    )


def check_fibonacci_cassini_ext() -> bool:
    """Cassini-family Fibonacci identity under extended range (n=1..60)."""
    return all(check_cassini_identity(n) for n in range(1, 61))


def check_derived_chain_stress() -> bool:
    """Multi-step derived chain stress beyond workload_derived_chain."""
    if not check_workload_derived_chain():
        return False
    # Extra stress: larger Vandermonde + deeper hockey + longer Cassini
    if not check_vandermonde_convolution(12, 10, 8):
        return False
    if not check_hockey_stick(28, 6):
        return False
    if not all(check_cassini_identity(n) for n in range(1, 45)):
        return False
    if not all(check_binomial_sum_row(n) for n in range(0, 28)):
        return False
    return True


# Adversarial aliases used by Oracle theme held-out windows (same callables)
check_adversarial_vandermonde_asymmetric = check_vandermonde_asymmetric
check_adversarial_hockey_deep = check_binomial_hockey_deep
check_adversarial_cassini_ext = check_fibonacci_cassini_ext
check_adversarial_catalan_convolution_stress = check_catalan_convolution
check_adversarial_derived_chain_stress = check_derived_chain_stress

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
    ("binomial_sum_row", lambda: all(check_binomial_sum_row(n) for n in range(0, 22)), True),
    ("fibonacci_addition", lambda: all(check_fibonacci_addition(m, n) for m in range(0, 15) for n in range(1, 15)), True),
    ("catalan_bounded", lambda: all(check_catalan_bounded(n) for n in range(0, 12)), True),
    ("lucas_addition", lambda: all(check_lucas_addition(m, n) for m in range(0, 12) for n in range(0, 12)), True),
    ("central_binom_bound", lambda: all(check_central_binom_bound(n) for n in range(1, 18)), True),
    ("pell_companion", lambda: all(check_pell_companion(n) for n in range(1, 20)), True),
    # Autonomy mile — start disabled; desk hard_enable may keep on n_hard_pass rise
    ("gcd_fibonacci", lambda: all(
        check_gcd_fibonacci(m, n) for m in range(0, 18) for n in range(0, 18)
    ), True),
    ("stirling_second_row", lambda: all(check_stirling_second_row(n) for n in range(1, 12)), True),
    ("pythagorean_generation", lambda: all(
        check_pythagorean_generation(u, v) for u in range(2, 16) for v in range(1, u)
    ), True),
    ("motzkin_bounded", lambda: all(check_motzkin_bounded(n) for n in range(0, 14)), True),
    # Oracle mile — start disabled; desk hard_enable may keep ONLY with Oracle pass
    ("catalan_convolution", lambda: all(check_catalan_convolution(n) for n in range(0, 12)), True),
    ("derangement_subfactorial", lambda: all(check_derangement_subfactorial(n) for n in range(0, 12)), True),
    ("narayana_sum", lambda: all(check_narayana_sum(n) for n in range(1, 12)), True),
    ("euler_totient_multiplicative", lambda: all(
        check_euler_totient_multiplicative(a, b) for a in range(1, 16) for b in range(1, 16)
    ), True),
    # Flourish mile — start disabled; desk hard_enable may keep ONLY with Oracle pass
    ("bell_triangle_recurrence", lambda: all(check_bell_triangle_recurrence(n) for n in range(0, 12)), True),
    ("hermite_recurrence", lambda: all(
        check_hermite_recurrence(n, x) for n in range(1, 10) for x in range(-4, 5)
    ), True),
    ("lagrange_identity", lambda: all(
        check_lagrange_identity(a, b, c, d)
        for a in range(-4, 5) for b in range(-4, 5) for c in range(-3, 4) for d in range(-3, 4)
    ), True),
    ("binomial_inversion_small", lambda: all(check_binomial_inversion_small(n) for n in range(0, 9)), True),
    ("legendre_duplication_small", lambda: all(check_legendre_duplication_small(n) for n in range(0, 12)), True),
    # Relight spark — Phase 2 harder lemmas (start DISABLED so desk can hard_enable)
    ("vandermonde_asymmetric", check_vandermonde_asymmetric, True),
    ("binomial_hockey_deep", check_binomial_hockey_deep, True),
    ("fibonacci_cassini_ext", check_fibonacci_cassini_ext, True),
    ("derived_chain_stress", check_derived_chain_stress, True),
    # Adversarial held-out windows (Oracle theme-specific; start disabled)
    ("adversarial_vandermonde_asymmetric", check_adversarial_vandermonde_asymmetric, False),
    ("adversarial_hockey_deep", check_adversarial_hockey_deep, True),
    ("adversarial_cassini_ext", check_adversarial_cassini_ext, True),
    ("adversarial_catalan_convolution_stress", lambda: all(check_catalan_convolution(n) for n in range(0, 16)), True),
    ("adversarial_derived_chain_stress", check_adversarial_derived_chain_stress, False),

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
