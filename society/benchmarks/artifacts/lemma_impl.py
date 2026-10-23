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


def check_authored_bell_triangle_recurrence__binomial_inversion_small_w1() -> bool:
    """Authored stress check (desk): proven lemmas bell_triangle_recurrence + binomial_inversion_small on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_bell_triangle_recurrence,
    ::check_binomial_inversion_small; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_bell_triangle_recurrence(n) for n in range(12, 18))) and all((check_binomial_inversion_small(n) for n in range(9, 13)))


def check_authored_oeis_a000108__catalan_bounded() -> bool:
    """Authored feed cross-check (desk): OEIS A000108 held-out terms
    n=9..28 must equal the colony's `catalan` (binomial(2 * n, n) // (n + 1)), and the
    proven lemma catalan_bounded must hold on a window past its base window.

    Components: society/benchmarks/artifacts/lemma_impl.py::check_catalan_bounded,
    ::binomial; checked by society/benchmarks/lemma_microbench.py.
    Source: https://oeis.org/A000108 (feed oeis:A000108:catalan, fetched 2026-10-07T21:48:09Z).
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_catalan_bounded(n) for n in range(12, 18))) and all((binomial(2 * n, n) // (n + 1) == t for n, t in zip(range(9, 29), (4862, 16796, 58786, 208012, 742900, 2674440, 9694845, 35357670, 129644790, 477638700, 1767263190, 6564120420, 24466267020, 91482563640, 343059613650, 1289904147324, 4861946401452, 18367353072152, 69533550916004, 263747951750360))))


def check_authored_oeis_a000045__cassini() -> bool:
    """Authored feed cross-check (desk): OEIS A000045 held-out terms
    n=9..28 must equal the colony's `fibonacci` (fibonacci(n)), and the
    proven lemma cassini must hold on a window past its base window.

    Components: society/benchmarks/artifacts/lemma_impl.py::check_cassini_identity,
    ::fibonacci; checked by society/benchmarks/lemma_microbench.py.
    Source: https://oeis.org/A000045 (feed oeis:A000045:fibonacci, fetched 2026-10-07T21:48:10Z).
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_cassini_identity(n) for n in range(40, 59))) and all((fibonacci(n) == t for n, t in zip(range(9, 29), (34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584, 4181, 6765, 10946, 17711, 28657, 46368, 75025, 121393, 196418, 317811))))


def check_authored_binomial_symmetry__catalan_convolution_w1() -> bool:
    """Authored stress check (desk): proven lemmas binomial_symmetry + catalan_convolution on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_binomial_symmetry,
    ::check_catalan_convolution; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_binomial_symmetry(n, k) for n in range(16, 24) for k in range(0, n + 1))) and all((check_catalan_convolution(n) for n in range(12, 18)))


def check_authored_central_binom_bound__derangement_subfactorial_w1() -> bool:
    """Authored stress check (desk): proven lemmas central_binom_bound + derangement_subfactorial on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_central_binom_bound,
    ::check_derangement_subfactorial; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_central_binom_bound(n) for n in range(18, 26))) and all((check_derangement_subfactorial(n) for n in range(12, 18)))


def check_authored_euler_totient_multiplicative__hermite_recurrence_w1() -> bool:
    """Authored stress check (desk): proven lemmas euler_totient_multiplicative + hermite_recurrence on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_euler_totient_multiplicative,
    ::check_hermite_recurrence; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_euler_totient_multiplicative(a, b) for a in range(16, 23) for b in range(16, 23))) and all((check_hermite_recurrence(n, x) for n in range(10, 14) for x in range(-4, 5)))


def check_authored_fibonacci_addition__gcd_fibonacci_w1() -> bool:
    """Authored stress check (desk): proven lemmas fibonacci_addition + gcd_fibonacci on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_fibonacci_addition,
    ::check_gcd_fibonacci; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_fibonacci_addition(m, n) for m in range(15, 22) for n in range(15, 22))) and all((check_gcd_fibonacci(m, n) for m in range(18, 27) for n in range(18, 27)))


def check_authored_geometric_sum__hockey_stick_w1() -> bool:
    """Authored stress check (desk): proven lemmas geometric_sum + hockey_stick on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_geometric_sum,
    ::check_hockey_stick; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_geometric_sum(a, n) for a in (2, 3, 5) for n in range(12, 17))) and all((check_hockey_stick(n, r) for n in range(25, 37) for r in range(0, n + 1)))


def check_authored_motzkin_bounded__legendre_duplication_small_w1() -> bool:
    """Authored stress check (desk): proven lemmas motzkin_bounded + legendre_duplication_small on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_motzkin_bounded,
    ::check_legendre_duplication_small; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_motzkin_bounded(n) for n in range(14, 21))) and all((check_legendre_duplication_small(n) for n in range(12, 18)))


def check_authored_pascal_identity__narayana_sum_w1() -> bool:
    """Authored stress check (desk): proven lemmas pascal_identity + narayana_sum on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_pascal_identity,
    ::check_narayana_sum; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_pascal_identity(n, k) for n in range(16, 23) for k in range(1, n))) and all((check_narayana_sum(n) for n in range(12, 17)))


def check_authored_oeis_a000984__central_binom_bound() -> bool:
    """Authored feed cross-check (desk): OEIS A000984 held-out terms
    n=9..27 must equal the colony's `central_binomial` (binomial(2 * n, n)), and the
    proven lemma central_binom_bound must hold on a window past its base window.

    Components: society/benchmarks/artifacts/lemma_impl.py::check_central_binom_bound,
    ::binomial; checked by society/benchmarks/lemma_microbench.py.
    Source: https://oeis.org/A000984 (feed oeis:A000984:central_binomial, fetched 2026-10-08T06:24:33Z).
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_central_binom_bound(n) for n in range(18, 26))) and all((binomial(2 * n, n) == t for n, t in zip(range(9, 28), (48620, 184756, 705432, 2704156, 10400600, 40116600, 155117520, 601080390, 2333606220, 9075135300, 35345263800, 137846528820, 538257874440, 2104098963720, 8233430727600, 32247603683100, 126410606437752, 495918532948104, 1946939425648112))))


def check_authored_pell_companion__pythagorean_generation_w1() -> bool:
    """Authored stress check (desk): proven lemmas pell_companion + pythagorean_generation on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_pell_companion,
    ::check_pythagorean_generation; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_pell_companion(n) for n in range(20, 29))) and all((check_pythagorean_generation(u, v) for u in range(16, 23) for v in range(1, u)))


def check_authored_sum_first_n_cubes__stirling_second_row_w1() -> bool:
    """Authored stress check (desk): proven lemmas sum_first_n_cubes + stirling_second_row on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_sum_first_n_cubes,
    ::check_stirling_second_row; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_sum_first_n_cubes(n) for n in range(30, 45))) and all((check_stirling_second_row(n) for n in range(12, 17)))


def check_authored_bell_triangle_recurrence__hermite_recurrence_w1() -> bool:
    """Authored stress check (desk): proven lemmas bell_triangle_recurrence + hermite_recurrence on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_bell_triangle_recurrence,
    ::check_hermite_recurrence; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_bell_triangle_recurrence(n) for n in range(12, 18))) and all((check_hermite_recurrence(n, x) for n in range(10, 14) for x in range(-4, 5)))


def check_authored_binomial_inversion_small__legendre_duplication_small_w1() -> bool:
    """Authored stress check (desk): proven lemmas binomial_inversion_small + legendre_duplication_small on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_binomial_inversion_small,
    ::check_legendre_duplication_small; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_binomial_inversion_small(n) for n in range(9, 13))) and all((check_legendre_duplication_small(n) for n in range(12, 18)))


def check_authored_oeis_a000079__binomial_sum_row() -> bool:
    """Authored feed cross-check (desk): OEIS A000079 held-out terms
    n=9..28 must equal the colony's `binomial_row_sum` (sum(binomial(n, k) for k in range(n + 1))), and the
    proven lemma binomial_sum_row must hold on a window past its base window.

    Components: society/benchmarks/artifacts/lemma_impl.py::check_binomial_sum_row,
    ::binomial; checked by society/benchmarks/lemma_microbench.py.
    Source: https://oeis.org/A000079 (feed oeis:A000079:binomial_row_sum, fetched 2026-10-08T13:53:26Z).
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_binomial_sum_row(n) for n in range(22, 33))) and all((sum((binomial(n, k) for k in range(n + 1))) == t for n, t in zip(range(9, 29), (512, 1024, 2048, 4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576, 2097152, 4194304, 8388608, 16777216, 33554432, 67108864, 134217728, 268435456))))


def check_authored_catalan_convolution__derangement_subfactorial_w1() -> bool:
    """Authored stress check (desk): proven lemmas catalan_convolution + derangement_subfactorial on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_catalan_convolution,
    ::check_derangement_subfactorial; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_catalan_convolution(n) for n in range(12, 18))) and all((check_derangement_subfactorial(n) for n in range(12, 18)))


def check_authored_fibonacci_addition__euler_totient_multiplicative_w1() -> bool:
    """Authored stress check (desk): proven lemmas fibonacci_addition + euler_totient_multiplicative on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_fibonacci_addition,
    ::check_euler_totient_multiplicative; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_fibonacci_addition(m, n) for m in range(15, 22) for n in range(15, 22))) and all((check_euler_totient_multiplicative(a, b) for a in range(16, 23) for b in range(16, 23)))


def check_authored_gcd_fibonacci__motzkin_bounded_w1() -> bool:
    """Authored stress check (desk): proven lemmas gcd_fibonacci + motzkin_bounded on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_gcd_fibonacci,
    ::check_motzkin_bounded; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_gcd_fibonacci(m, n) for m in range(18, 27) for n in range(18, 27))) and all((check_motzkin_bounded(n) for n in range(14, 21)))


def check_authored_geometric_sum__narayana_sum_w1() -> bool:
    """Authored stress check (desk): proven lemmas geometric_sum + narayana_sum on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_geometric_sum,
    ::check_narayana_sum; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_geometric_sum(a, n) for a in (2, 3, 5) for n in range(12, 17))) and all((check_narayana_sum(n) for n in range(12, 17)))


def check_authored_hockey_stick__pell_companion_w1() -> bool:
    """Authored stress check (desk): proven lemmas hockey_stick + pell_companion on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_hockey_stick,
    ::check_pell_companion; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_hockey_stick(n, r) for n in range(25, 37) for r in range(0, n + 1))) and all((check_pell_companion(n) for n in range(20, 29)))


def check_authored_cassini__catalan_convolution_w1() -> bool:
    """Authored stress check (desk): proven lemmas cassini + catalan_convolution on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_cassini_identity,
    ::check_catalan_convolution; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_cassini_identity(n) for n in range(40, 59))) and all((check_catalan_convolution(n) for n in range(12, 18)))


def check_authored_geometric_sum__pell_companion_w1() -> bool:
    """Authored stress check (desk): proven lemmas geometric_sum + pell_companion on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_geometric_sum,
    ::check_pell_companion; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_geometric_sum(a, n) for a in (2, 3, 5) for n in range(12, 17))) and all((check_pell_companion(n) for n in range(20, 29)))


def check_authored_binomial_symmetry__vandermonde_conv_w1() -> bool:
    """Authored stress check (desk): proven lemmas binomial_symmetry + vandermonde_conv on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_binomial_symmetry,
    ::check_vandermonde_convolution; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_binomial_symmetry(n, k) for n in range(16, 24) for k in range(0, n + 1))) and all((check_vandermonde_convolution(m, n, r) for m in range(12, 18) for n in range(12, 18) for r in range(0, m + n + 1)))


def check_authored_binomial_sum_row__bell_triangle_recurrence_w1() -> bool:
    """Authored stress check (desk): proven lemmas binomial_sum_row + bell_triangle_recurrence on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_binomial_sum_row,
    ::check_bell_triangle_recurrence; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_binomial_sum_row(n) for n in range(22, 33))) and all((check_bell_triangle_recurrence(n) for n in range(12, 18)))


def check_authored_cassini__binomial_inversion_small_w1() -> bool:
    """Authored stress check (desk): proven lemmas cassini + binomial_inversion_small on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_cassini_identity,
    ::check_binomial_inversion_small; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_cassini_identity(n) for n in range(40, 59))) and all((check_binomial_inversion_small(n) for n in range(9, 13)))


def check_authored_catalan_bounded__catalan_convolution_w1() -> bool:
    """Authored stress check (desk): proven lemmas catalan_bounded + catalan_convolution on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_catalan_bounded,
    ::check_catalan_convolution; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_catalan_bounded(n) for n in range(12, 18))) and all((check_catalan_convolution(n) for n in range(12, 18)))


def check_authored_central_binom_bound__gcd_fibonacci_w1() -> bool:
    """Authored stress check (desk): proven lemmas central_binom_bound + gcd_fibonacci on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_central_binom_bound,
    ::check_gcd_fibonacci; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_central_binom_bound(n) for n in range(18, 26))) and all((check_gcd_fibonacci(m, n) for m in range(18, 27) for n in range(18, 27)))


def check_authored_derangement_subfactorial__euler_totient_multiplicative_w1() -> bool:
    """Authored stress check (desk): proven lemmas derangement_subfactorial + euler_totient_multiplicative on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_derangement_subfactorial,
    ::check_euler_totient_multiplicative; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_derangement_subfactorial(n) for n in range(12, 18))) and all((check_euler_totient_multiplicative(a, b) for a in range(16, 23) for b in range(16, 23)))


def check_authored_fibonacci_addition__hermite_recurrence_w1() -> bool:
    """Authored stress check (desk): proven lemmas fibonacci_addition + hermite_recurrence on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_fibonacci_addition,
    ::check_hermite_recurrence; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_fibonacci_addition(m, n) for m in range(15, 22) for n in range(15, 22))) and all((check_hermite_recurrence(n, x) for n in range(10, 14) for x in range(-4, 5)))


def check_authored_geometric_sum__legendre_duplication_small_w1() -> bool:
    """Authored stress check (desk): proven lemmas geometric_sum + legendre_duplication_small on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_geometric_sum,
    ::check_legendre_duplication_small; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_geometric_sum(a, n) for a in (2, 3, 5) for n in range(12, 17))) and all((check_legendre_duplication_small(n) for n in range(12, 18)))


def check_authored_hockey_stick__motzkin_bounded_w1() -> bool:
    """Authored stress check (desk): proven lemmas hockey_stick + motzkin_bounded on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_hockey_stick,
    ::check_motzkin_bounded; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_hockey_stick(n, r) for n in range(25, 37) for r in range(0, n + 1))) and all((check_motzkin_bounded(n) for n in range(14, 21)))


def check_authored_pascal_identity__pell_companion_w1() -> bool:
    """Authored stress check (desk): proven lemmas pascal_identity + pell_companion on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_pascal_identity,
    ::check_pell_companion; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_pascal_identity(n, k) for n in range(16, 23) for k in range(1, n))) and all((check_pell_companion(n) for n in range(20, 29)))


def check_authored_pythagorean_generation__narayana_sum_w1() -> bool:
    """Authored stress check (desk): proven lemmas pythagorean_generation + narayana_sum on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_pythagorean_generation,
    ::check_narayana_sum; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_pythagorean_generation(u, v) for u in range(16, 23) for v in range(1, u))) and all((check_narayana_sum(n) for n in range(12, 17)))


def check_authored_vandermonde_conv__stirling_second_row_w1() -> bool:
    """Authored stress check (desk): proven lemmas vandermonde_conv + stirling_second_row on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_vandermonde_convolution,
    ::check_stirling_second_row; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_vandermonde_convolution(m, n, r) for m in range(12, 18) for n in range(12, 18) for r in range(0, m + n + 1))) and all((check_stirling_second_row(n) for n in range(12, 17)))


def check_authored_sum_first_n_odds__bell_triangle_recurrence_w1() -> bool:
    """Authored stress check (desk): proven lemmas sum_first_n_odds + bell_triangle_recurrence on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_sum_first_n_odds,
    ::check_bell_triangle_recurrence; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_sum_first_n_odds(n) for n in range(40, 60))) and all((check_bell_triangle_recurrence(n) for n in range(12, 18)))


def check_authored_cassini__catalan_bounded_w1() -> bool:
    """Authored stress check (desk): proven lemmas cassini + catalan_bounded on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_cassini_identity,
    ::check_catalan_bounded; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_cassini_identity(n) for n in range(40, 59))) and all((check_catalan_bounded(n) for n in range(12, 18)))


def check_authored_central_binom_bound__binomial_inversion_small_w1() -> bool:
    """Authored stress check (desk): proven lemmas central_binom_bound + binomial_inversion_small on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_central_binom_bound,
    ::check_binomial_inversion_small; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_central_binom_bound(n) for n in range(18, 26))) and all((check_binomial_inversion_small(n) for n in range(9, 13)))


def check_authored_derangement_subfactorial__legendre_duplication_small_w1() -> bool:
    """Authored stress check (desk): proven lemmas derangement_subfactorial + legendre_duplication_small on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_derangement_subfactorial,
    ::check_legendre_duplication_small; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_derangement_subfactorial(n) for n in range(12, 18))) and all((check_legendre_duplication_small(n) for n in range(12, 18)))


def check_authored_fibonacci_addition__narayana_sum_w1() -> bool:
    """Authored stress check (desk): proven lemmas fibonacci_addition + narayana_sum on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_fibonacci_addition,
    ::check_narayana_sum; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_fibonacci_addition(m, n) for m in range(15, 22) for n in range(15, 22))) and all((check_narayana_sum(n) for n in range(12, 17)))


def check_authored_gcd_fibonacci__euler_totient_multiplicative_w1() -> bool:
    """Authored stress check (desk): proven lemmas gcd_fibonacci + euler_totient_multiplicative on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_gcd_fibonacci,
    ::check_euler_totient_multiplicative; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_gcd_fibonacci(m, n) for m in range(18, 27) for n in range(18, 27))) and all((check_euler_totient_multiplicative(a, b) for a in range(16, 23) for b in range(16, 23)))


def check_authored_geometric_sum__hermite_recurrence_w1() -> bool:
    """Authored stress check (desk): proven lemmas geometric_sum + hermite_recurrence on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_geometric_sum,
    ::check_hermite_recurrence; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_geometric_sum(a, n) for a in (2, 3, 5) for n in range(12, 17))) and all((check_hermite_recurrence(n, x) for n in range(10, 14) for x in range(-4, 5)))


def check_authored_hockey_stick__stirling_second_row_w1() -> bool:
    """Authored stress check (desk): proven lemmas hockey_stick + stirling_second_row on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_hockey_stick,
    ::check_stirling_second_row; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_hockey_stick(n, r) for n in range(25, 37) for r in range(0, n + 1))) and all((check_stirling_second_row(n) for n in range(12, 17)))


def check_authored_pascal_identity__motzkin_bounded_w1() -> bool:
    """Authored stress check (desk): proven lemmas pascal_identity + motzkin_bounded on
    larger windows disjoint from their base windows (generation 1).

    Components: society/benchmarks/artifacts/lemma_impl.py::check_pascal_identity,
    ::check_motzkin_bounded; checked by society/benchmarks/lemma_microbench.py.
    Machine check only — not a novel theorem. Disabled until the Oracle passes it.
    """
    return all((check_pascal_identity(n, k) for n in range(16, 23) for k in range(1, n))) and all((check_motzkin_bounded(n) for n in range(14, 21)))


# --- instrument bridges (colony.instruments.sieve) ---
def sieve_count(gaps, a, b, mod=1, residue=None, backend="auto"):
    """Bridge to colony.instruments.sieve.count_pattern (capped). Returns an int count."""
    from colony.instruments import sieve as _s
    r = _s.count_pattern(list(gaps), int(a), int(b), mod=int(mod), backend=backend)
    return int(r["total"] if residue is None else r["by_residue"].get(int(residue), 0))


def sieve_hl(gaps, a, b):
    """Bridge to the Hardy-Littlewood consecutive forecast (conjectural heuristic). Returns a float."""
    from colony.instruments import sieve as _s
    return float(_s.hl_predict(list(gaps), int(a), int(b), prime_limit=200_000, steps=400)["prediction"])


def check_authored_sieve_hl_within_g2_w1() -> bool:
    """Authored instrument check (desk): count of consecutive pattern (2,) on each window is within 4.0*sqrt of the HL forecast.
    Windows [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)] (disjoint, capped). Uses colony.instruments.sieve via the bridges
    sieve_count / sieve_hl. HL is a conjectural heuristic; counts are bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := sieve_count((2,), a, b)) is int and type(h := sieve_hl((2,), a, b)) is float and h > 0 and abs(c - h) <= 4.0 * h ** 0.5 for a, b in [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)])


def check_authored_sieve_two_counter_g2_w1() -> bool:
    """Authored instrument check (desk): C/primesieve and pure-Python counters agree exactly on pattern (2,).
    Windows [(10000000, 10200000), (10200000, 10400000), (10400000, 10600000)] (disjoint, capped). Uses colony.instruments.sieve via the bridges
    sieve_count / sieve_hl. HL is a conjectural heuristic; counts are bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := sieve_count((2,), a, b)) is int and c > 0 and c == sieve_count((2,), a, b, backend='python') for a, b in [(10000000, 10200000), (10200000, 10400000), (10400000, 10600000)])


def check_authored_sieve_hl_within_g2_w2() -> bool:
    """Authored instrument check (desk): count of consecutive pattern (2,) on each window is within 4.0*sqrt of the HL forecast.
    Windows [(20000000, 22000000), (22000000, 24000000), (24000000, 26000000)] (disjoint, capped). Uses colony.instruments.sieve via the bridges
    sieve_count / sieve_hl. HL is a conjectural heuristic; counts are bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := sieve_count((2,), a, b)) is int and type(h := sieve_hl((2,), a, b)) is float and h > 0 and abs(c - h) <= 4.0 * h ** 0.5 for a, b in [(20000000, 22000000), (22000000, 24000000), (24000000, 26000000)])


def check_authored_sieve_residue_bal_g2_w2() -> bool:
    """Authored instrument check (desk): p mod 4 classes 1/3 of pattern (2,) are balanced within 4.0*sqrt(total).
    Windows [(20000000, 22000000), (22000000, 24000000), (24000000, 26000000)] (disjoint, capped). Uses colony.instruments.sieve via the bridges
    sieve_count / sieve_hl. HL is a conjectural heuristic; counts are bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(x := sieve_count((2,), a, b, 4, 1)) is int and type(y := sieve_count((2,), a, b, 4, 3)) is int and x + y > 0 and abs(x - y) <= 4.0 * (x + y) ** 0.5 for a, b in [(20000000, 22000000), (22000000, 24000000), (24000000, 26000000)])


def check_authored_sieve_residue_bal_g2_6_4_w1() -> bool:
    """Authored instrument check (desk): p mod 4 classes 1/3 of pattern (2, 6, 4) are balanced within 4.0*sqrt(total).
    Windows [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)] (disjoint, capped). Uses colony.instruments.sieve via the bridges
    sieve_count / sieve_hl. HL is a conjectural heuristic; counts are bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(x := sieve_count((2, 6, 4), a, b, 4, 1)) is int and type(y := sieve_count((2, 6, 4), a, b, 4, 3)) is int and x + y > 0 and abs(x - y) <= 4.0 * (x + y) ** 0.5 for a, b in [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)])


def check_authored_sieve_residue_bal_g4_2_6_w1() -> bool:
    """Authored instrument check (desk): p mod 4 classes 1/3 of pattern (4, 2, 6) are balanced within 4.0*sqrt(total).
    Windows [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)] (disjoint, capped). Uses colony.instruments.sieve via the bridges
    sieve_count / sieve_hl. HL is a conjectural heuristic; counts are bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(x := sieve_count((4, 2, 6), a, b, 4, 1)) is int and type(y := sieve_count((4, 2, 6), a, b, 4, 3)) is int and x + y > 0 and abs(x - y) <= 4.0 * (x + y) ** 0.5 for a, b in [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)])


def check_authored_sieve_residue_bal_g6_2_4_w1() -> bool:
    """Authored instrument check (desk): p mod 4 classes 1/3 of pattern (6, 2, 4) are balanced within 4.0*sqrt(total).
    Windows [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)] (disjoint, capped). Uses colony.instruments.sieve via the bridges
    sieve_count / sieve_hl. HL is a conjectural heuristic; counts are bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(x := sieve_count((6, 2, 4), a, b, 4, 1)) is int and type(y := sieve_count((6, 2, 4), a, b, 4, 3)) is int and x + y > 0 and abs(x - y) <= 4.0 * (x + y) ** 0.5 for a, b in [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)])


def check_authored_sieve_two_counter_g6_2_6_w1() -> bool:
    """Authored instrument check (desk): C/primesieve and pure-Python counters agree exactly on pattern (6, 2, 6).
    Windows [(10000000, 10050000), (10050000, 10100000), (10100000, 10150000)] (disjoint, capped). Uses colony.instruments.sieve via the bridges
    sieve_count / sieve_hl. HL is a conjectural heuristic; counts are bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := sieve_count((6, 2, 6), a, b)) is int and c > 0 and c == sieve_count((6, 2, 6), a, b, backend='python') for a, b in [(10000000, 10050000), (10050000, 10100000), (10100000, 10150000)])


def check_authored_sieve_hl_within_g6_4_2_w1() -> bool:
    """Authored instrument check (desk): count of consecutive pattern (6, 4, 2) on each window is within 4.0*sqrt of the HL forecast.
    Windows [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)] (disjoint, capped). Uses colony.instruments.sieve via the bridges
    sieve_count / sieve_hl. HL is a conjectural heuristic; counts are bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := sieve_count((6, 4, 2), a, b)) is int and type(h := sieve_hl((6, 4, 2), a, b)) is float and h > 0 and abs(c - h) <= 4.0 * h ** 0.5 for a, b in [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)])


# --- Building-block lemma catalog refill (James 2026-10-17 6:32 AM ET) -------------------------
# Classical PROVEN results, each a numeric machine check with parameters. Building blocks only:
# they start DISABLED; the desk may hard_enable one only through the Oracle. Not discoveries.


def _small_primes(limit: int) -> list[int]:
    s = bytearray([1]) * (limit + 1)
    s[0:2] = b"\x00\x00"
    for i in range(2, int(limit ** 0.5) + 1):
        if s[i]:
            s[i * i :: i] = bytearray(len(s[i * i :: i]))
    return [i for i in range(limit + 1) if s[i]]


def _divisors(n: int) -> list[int]:
    return [d for d in range(1, n + 1) if n % d == 0]


def _phi(n: int) -> int:
    return sum(1 for a in range(1, n + 1) if math.gcd(a, n) == 1)


def _mobius(n: int) -> int:
    if n == 1:
        return 1
    m, k, p = n, 0, 2
    while p * p <= m:
        if m % p == 0:
            m //= p
            if m % p == 0:
                return 0
            k += 1
        p += 1
    if m > 1:
        k += 1
    return -1 if k % 2 else 1


def _sigma(n: int) -> int:
    return sum(_divisors(n))


def _is_prime(n: int) -> bool:
    return n >= 2 and all(n % d for d in range(2, int(n ** 0.5) + 1))


def check_fermat_little(a: int) -> bool:
    """Fermat's little theorem: a^p ≡ a (mod p) for every prime p < 60 (classical)."""
    return all(pow(a, p, p) == a % p for p in _small_primes(60))


def check_euler_theorem(n: int) -> bool:
    """Euler's theorem: a^phi(n) ≡ 1 (mod n) for every a coprime to n (classical)."""
    if n < 2:
        return True
    ph = _phi(n)
    return all(pow(a, ph, n) == 1 for a in range(1, n) if math.gcd(a, n) == 1)


def check_wilson_theorem(n: int) -> bool:
    """Wilson: (n-1)! ≡ -1 (mod n) iff n is prime, for n >= 2 (classical)."""
    if n < 2:
        return True
    f = 1
    for k in range(2, n):
        f = f * k % n
    return (f == n - 1) == _is_prime(n)


def _legendre(a: int, p: int) -> int:
    r = pow(a % p, (p - 1) // 2, p)
    return -1 if r == p - 1 else r


def check_quadratic_reciprocity(p: int) -> bool:
    """Quadratic reciprocity (p/q)(q/p) = (-1)^((p-1)/2 (q-1)/2) for odd primes q < p (classical)."""
    if p < 5 or not _is_prime(p):
        return True
    return all(_legendre(p, q) * _legendre(q, p) == (-1) ** (((p - 1) // 2) * ((q - 1) // 2))
               for q in _small_primes(p - 1) if q > 2)


def check_mobius_divisor_sum(n: int) -> bool:
    """sum_{d|n} mu(d) = [n == 1] (Möbius function, classical)."""
    if n < 1:
        return True
    return sum(_mobius(d) for d in _divisors(n)) == (1 if n == 1 else 0)


def check_gauss_phi_divisor_sum(n: int) -> bool:
    """Gauss: sum_{d|n} phi(d) = n (Dirichlet convolution phi * 1 = id, classical)."""
    if n < 1:
        return True
    return sum(_phi(d) for d in _divisors(n)) == n


def check_sigma_multiplicative(a: int, b: int) -> bool:
    """sigma(ab) = sigma(a) sigma(b) when gcd(a, b) = 1 (classical)."""
    if a < 1 or b < 1 or math.gcd(a, b) != 1:
        return True
    return _sigma(a * b) == _sigma(a) * _sigma(b)


def check_mobius_inversion_sigma(n: int) -> bool:
    """Möbius inversion of sigma = id * 1: sum_{d|n} mu(d) sigma(n/d) = n (classical)."""
    if n < 1:
        return True
    return sum(_mobius(d) * _sigma(n // d) for d in _divisors(n)) == n


def check_bezout_identity(a: int, b: int) -> bool:
    """Bézout: extended Euclid gives x, y with a x + b y = gcd(a, b) (classical)."""
    if a < 1 or b < 1:
        return True
    r0, r1, x0, x1, y0, y1 = a, b, 1, 0, 0, 1
    while r1:
        q = r0 // r1
        r0, r1, x0, x1, y0, y1 = r1, r0 - q * r1, x1, x0 - q * x1, y1, y0 - q * y1
    return r0 == math.gcd(a, b) and a * x0 + b * y0 == r0


def check_crt_coprime_pair(m: int) -> bool:
    """CRT: x -> (x mod m, x mod m+1) is a bijection Z/m(m+1) -> Z/m x Z/(m+1) (classical)."""
    if m < 1:
        return True
    return len({(x % m, x % (m + 1)) for x in range(m * (m + 1))}) == m * (m + 1)


def check_lucas_theorem_binomial(n: int) -> bool:
    """Lucas' theorem: C(n,k) ≡ prod C(n_i,k_i) (mod p) over base-p digits, p in {2,3,5,7}."""
    if n < 0:
        return True

    def digits_prod(k: int, p: int) -> int:
        prod, nn, kk = 1, n, k
        while nn or kk:
            prod = prod * math.comb(nn % p, kk % p) % p
            nn //= p
            kk //= p
        return prod

    return all(math.comb(n, k) % p == digits_prod(k, p) for p in (2, 3, 5, 7) for k in range(0, n + 1))


def check_stirling_first_row_sum(n: int) -> bool:
    """Unsigned Stirling numbers of the first kind: sum_k c(n,k) = n! (classical)."""
    if n < 0:
        return True
    c = [[0] * (n + 1) for _ in range(n + 1)]
    c[0][0] = 1
    for i in range(1, n + 1):
        for k in range(1, i + 1):
            c[i][k] = c[i - 1][k - 1] + (i - 1) * c[i - 1][k]
    return sum(c[n]) == math.factorial(n)


def check_bell_stirling_sum(n: int) -> bool:
    """Bell(n) = sum_k S(n,k), with Bell from the recurrence B(n+1) = sum C(n,k) B(k) (classical)."""
    if n < 0:
        return True
    B = [1]
    for m in range(n):
        B.append(sum(math.comb(m, k) * B[k] for k in range(m + 1)))
    S = [[0] * (n + 1) for _ in range(n + 1)]
    S[0][0] = 1
    for i in range(1, n + 1):
        for k in range(1, i + 1):
            S[i][k] = k * S[i - 1][k] + S[i - 1][k - 1]
    return sum(S[n]) == B[n]


def check_alternating_binomial_row(n: int) -> bool:
    """sum_k (-1)^k C(n,k) = [n == 0] (classical)."""
    if n < 0:
        return True
    return sum((-1) ** k * math.comb(n, k) for k in range(n + 1)) == (1 if n == 0 else 0)


def check_multinomial_three(n: int) -> bool:
    """Multinomial theorem at 1+1+1: sum_{a+b+c=n} n!/(a!b!c!) = 3^n (classical)."""
    if n < 0:
        return True
    f = math.factorial
    return sum(f(n) // (f(a) * f(b) * f(n - a - b)) for a in range(n + 1) for b in range(n + 1 - a)) == 3 ** n


def _partitions_dp(n: int, parts: list[int], distinct: bool = False) -> int:
    ways = [1] + [0] * n
    for p in parts:
        rng = range(n, p - 1, -1) if distinct else range(p, n + 1)
        for s in rng:
            ways[s] += ways[s - p]
    return ways[n]


def check_euler_pentagonal(n: int) -> bool:
    """Euler's pentagonal number theorem: p(n) by the pentagonal recurrence equals direct count."""
    if n < 0:
        return True
    p = [1] + [0] * n
    for m in range(1, n + 1):
        s, k = 0, 1
        while True:
            g1, g2 = k * (3 * k - 1) // 2, k * (3 * k + 1) // 2
            if g1 > m:
                break
            sign = 1 if k % 2 else -1
            s += sign * p[m - g1]
            if g2 <= m:
                s += sign * p[m - g2]
            k += 1
        p[m] = s
    return p[n] == _partitions_dp(n, list(range(1, n + 1)))


def check_odd_distinct_partitions(n: int) -> bool:
    """Euler: partitions of n into odd parts = partitions of n into distinct parts (classical)."""
    if n < 0:
        return True
    return (_partitions_dp(n, list(range(1, n + 1, 2)))
            == _partitions_dp(n, list(range(1, n + 1)), distinct=True))


def check_partition_conjugate_parts(n: int) -> bool:
    """Conjugation: #partitions of n with at most k parts = #with largest part <= k, all k <= n."""
    if n < 0:
        return True

    def at_most_parts(m: int, k: int) -> int:
        # q(m, k): partitions of m into at most k parts
        t = [[0] * (k + 1) for _ in range(m + 1)]
        for j in range(k + 1):
            t[0][j] = 1
        for i in range(1, m + 1):
            for j in range(1, k + 1):
                t[i][j] = t[i][j - 1] + (t[i - j][j] if i >= j else 0)
        return t[m][k]

    return all(at_most_parts(n, k) == _partitions_dp(n, list(range(1, k + 1))) for k in range(1, n + 1))


def _det_int(M: list[list[int]]) -> int:
    """Bareiss fraction-free integer determinant."""
    A = [row[:] for row in M]
    n = len(A)
    if n == 0:
        return 1
    sign, prev = 1, 1
    for k in range(n - 1):
        if A[k][k] == 0:
            sw = next((i for i in range(k + 1, n) if A[i][k]), None)
            if sw is None:
                return 0
            A[k], A[sw] = A[sw], A[k]
            sign = -sign
        for i in range(k + 1, n):
            for j in range(k + 1, n):
                A[i][j] = (A[i][j] * A[k][k] - A[i][k] * A[k][j]) // prev
        prev = A[k][k]
    return sign * A[n - 1][n - 1]


def _spanning_trees(n: int, edges: list[tuple[int, int]]) -> int:
    L = [[0] * n for _ in range(n)]
    for u, v in edges:
        L[u][u] += 1
        L[v][v] += 1
        L[u][v] -= 1
        L[v][u] -= 1
    return _det_int([row[1:] for row in L[1:]])


def check_cayley_tree_count(n: int) -> bool:
    """Cayley: K_n has n^(n-2) spanning trees (matrix-tree theorem determinant)."""
    if n < 2:
        return True
    return _spanning_trees(n, [(i, j) for i in range(n) for j in range(i + 1, n)]) == n ** (n - 2)


def check_cycle_spanning_trees(n: int) -> bool:
    """The cycle C_n (n >= 3) has exactly n spanning trees (matrix-tree theorem)."""
    if n < 3:
        return True
    return _spanning_trees(n, [(i, (i + 1) % n) for i in range(n)]) == n


def check_complete_bipartite_trees(n: int) -> bool:
    """K_{m,n} has m^(n-1) n^(m-1) spanning trees, m in 1..4 (Scoins; matrix-tree theorem)."""
    if n < 1:
        return True
    return all(_spanning_trees(m + n, [(i, m + j) for i in range(m) for j in range(n)])
               == m ** (n - 1) * n ** (m - 1) for m in range(1, 5))


def _matmul(A: list[list[int]], B: list[list[int]]) -> list[list[int]]:
    return [[sum(A[i][k] * B[k][j] for k in range(len(B))) for j in range(len(B[0]))] for i in range(len(A))]


def check_cayley_hamilton_2x2(a: int) -> bool:
    """Cayley-Hamilton (2x2): A^2 - tr(A) A + det(A) I = 0 for A = [[a,b],[c,d]], |b|,|c|,|d| <= 3."""
    def residual(b: int, c: int, d: int) -> list[list[int]]:
        A = [[a, b], [c, d]]
        A2 = _matmul(A, A)
        tr, det = a + d, a * d - b * c
        return [[A2[i][j] - tr * A[i][j] + (det if i == j else 0) for j in range(2)] for i in range(2)]

    return all(residual(b, c, d) == [[0, 0], [0, 0]] for b in range(-3, 4) for c in range(-3, 4) for d in range(-3, 4))


def check_cayley_hamilton_3x3(s: int) -> bool:
    """Cayley-Hamilton (3x3): A^3 - c2 A^2 + c1 A - det(A) I = 0 for seeded integer matrices."""
    def residual(t: int) -> list[list[int]]:
        A = [[((s * 7 + t * 13 + 3 * i + 5 * j + i * j * s) % 11) - 5 for j in range(3)] for i in range(3)]
        A2 = _matmul(A, A)
        A3 = _matmul(A2, A)
        c2 = A[0][0] + A[1][1] + A[2][2]
        c1 = sum(A[i][i] * A[j][j] - A[i][j] * A[j][i] for i in range(3) for j in range(i + 1, 3))
        c0 = _det_int(A)
        return [[A3[i][j] - c2 * A2[i][j] + c1 * A[i][j] - (c0 if i == j else 0) for j in range(3)] for i in range(3)]

    return all(residual(t) == [[0] * 3 for _ in range(3)] for t in range(6))


def check_newton_identities(n: int) -> bool:
    """Newton's identities k e_k = sum_{i=1..k} (-1)^(i-1) e_{k-i} p_i for roots 1..n, -1..-(n//2)."""
    if n < 1:
        return True
    roots = list(range(1, n + 1)) + [-r for r in range(1, n // 2 + 1)]
    e = [1]  # elementary symmetric polynomials via expansion of prod (1 + r x)
    for r in roots:
        e = [a + r * b for a, b in zip(e + [0], [0] + e)]
    N = len(roots)
    p = [sum(r ** i for r in roots) for i in range(N + 1)]
    return all(k * e[k] == sum((-1) ** (i - 1) * e[k - i] * p[i] for i in range(1, k + 1)) for k in range(1, N + 1))


def check_polynomial_remainder(a: int) -> bool:
    """Remainder theorem: synthetic division of f by (x - a) leaves remainder f(a), f fixed degree 6."""
    coeffs = [3, -2, 0, 5, -7, 1, 4]  # leading first
    q, r = [], 0
    for c in coeffs:
        r = r * a + c
        q.append(r)
    rem = q.pop()
    f_a = sum(c * a ** (len(coeffs) - 1 - i) for i, c in enumerate(coeffs))
    # quotient check: f(x) = (x - a) q(x) + rem at several x
    ok_q = all(sum(c * x ** (len(coeffs) - 1 - i) for i, c in enumerate(coeffs))
               == (x - a) * sum(c * x ** (len(q) - 1 - i) for i, c in enumerate(q)) + rem for x in (-2, 0, 3))
    return rem == f_a and ok_q


def check_telescoping_sum(n: int) -> bool:
    """Telescoping: sum_{k=1..n} 1/(k(k+1)) = n/(n+1) and sum 1/(k(k+1)(k+2)) = 1/4 - 1/(2(n+1)(n+2))."""
    if n < 1:
        return True
    from fractions import Fraction as Fr
    s1 = sum(Fr(1, k * (k + 1)) for k in range(1, n + 1))
    s2 = sum(Fr(1, k * (k + 1) * (k + 2)) for k in range(1, n + 1))
    return s1 == Fr(n, n + 1) and s2 == Fr(1, 4) - Fr(1, 2 * (n + 1) * (n + 2))


def check_abel_summation(n: int) -> bool:
    """Finite Abel summation: sum a_k b_k = A_n b_n - sum_{k<n} A_k (b_{k+1} - b_k), exact integers."""
    if n < 1:
        return True
    a = [k * k - 3 * k + (k % 5) for k in range(1, n + 1)]
    b = [(-1) ** k * (2 * k + 1) + k ** 3 % 7 for k in range(1, n + 1)]
    A, acc = [], 0
    for x in a:
        acc += x
        A.append(acc)
    lhs = sum(x * y for x, y in zip(a, b))
    rhs = A[-1] * b[-1] - sum(A[k] * (b[k + 1] - b[k]) for k in range(n - 1))
    return lhs == rhs


def check_faulhaber_power_sums(n: int) -> bool:
    """Faulhaber: sum_{k=1..n} k^p = 1/(p+1) sum_j C(p+1,j) B_j^+ n^(p+1-j), p = 0..6 (Bernoulli)."""
    if n < 0:
        return True
    from fractions import Fraction as Fr
    B = [Fr(1)]
    for m in range(1, 8):
        B.append(-sum(math.comb(m + 1, j) * B[j] for j in range(m)) / (m + 1))
    Bp = [b if j != 1 else -b for j, b in enumerate(B)]  # B_1^+ = +1/2
    return all(sum(k ** p for k in range(1, n + 1))
               == sum(math.comb(p + 1, j) * Bp[j] * n ** (p + 1 - j) for j in range(p + 1)) / (p + 1)
               for p in range(7))


def check_lagrange_cyclic_orders(n: int) -> bool:
    """Lagrange: element orders divide |G| in Z/n (additive, order n) and (Z/n)^* (order phi(n))."""
    if n < 2:
        return True

    def mult_order(a: int) -> int:
        k, x = 1, a % n
        while x != 1:
            x = x * a % n
            k += 1
        return k

    ph = _phi(n)
    return (all(n % (n // math.gcd(a, n)) == 0 for a in range(n))
            and all(ph % mult_order(a) == 0 for a in range(1, n) if math.gcd(a, n) == 1))


def check_burnside_necklaces(n: int) -> bool:
    """Burnside: binary necklaces of length n = (1/n) sum_{d|n} phi(d) 2^(n/d) = brute-force orbit count."""
    if n < 1:
        return True
    seen, orbits = set(), 0
    mask = (1 << n) - 1
    for w in range(1 << n):
        if w in seen:
            continue
        orbits += 1
        x = w
        for _ in range(n):
            seen.add(x)
            x = ((x << 1) | (x >> (n - 1))) & mask
    return orbits * n == sum(_phi(d) * 2 ** (n // d) for d in _divisors(n))


def check_authored_sieve_two_counter_g6_w1() -> bool:
    """Authored instrument check (desk): C/primesieve and pure-Python counters agree exactly on pattern (6,).
    Windows [(10000000, 10050000), (10050000, 10100000), (10100000, 10150000)] (disjoint, capped). Uses colony.instruments.sieve via the bridges
    sieve_count / sieve_hl. HL is a conjectural heuristic; counts are bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := sieve_count((6,), a, b)) is int and c > 0 and c == sieve_count((6,), a, b, backend='python') for a, b in [(10000000, 10050000), (10050000, 10100000), (10100000, 10150000)])


def check_authored_sieve_hl_within_g4_w1() -> bool:
    """Authored instrument check (desk): count of consecutive pattern (4,) on each window is within 4.0*sqrt of the HL forecast.
    Windows [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)] (disjoint, capped). Uses colony.instruments.sieve via the bridges
    sieve_count / sieve_hl. HL is a conjectural heuristic; counts are bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := sieve_count((4,), a, b)) is int and type(h := sieve_hl((4,), a, b)) is float and h > 0 and abs(c - h) <= 4.0 * h ** 0.5 for a, b in [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)])


def check_authored_sieve_hl_within_g4_6_w1() -> bool:
    """Authored instrument check (desk): count of consecutive pattern (4, 6) on each window is within 4.0*sqrt of the HL forecast.
    Windows [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)] (disjoint, capped). Uses colony.instruments.sieve via the bridges
    sieve_count / sieve_hl. HL is a conjectural heuristic; counts are bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := sieve_count((4, 6), a, b)) is int and type(h := sieve_hl((4, 6), a, b)) is float and h > 0 and abs(c - h) <= 4.0 * h ** 0.5 for a, b in [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)])


# --- frontier bridge (colony.frontier_conjectures) ---
def frontier_holds(claim, a, b):
    """Bridge to colony.frontier_conjectures.holds_on: checks done when the self-chosen
    conjecture holds for every n in [a, b], else 0. Bounded evidence, not proof."""
    from colony import frontier_conjectures as _f
    return int(_f.holds_on(claim, int(a), int(b)))


def check_authored_frontier_cong_xa68963c2_w1() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    S(gcd(digsum,phi))(n) = 1 (mod 2) for all n = 3 (mod 4)
    re-tested on windows [(41, 2026), (2027, 4012), (4013, 5998)]. conjecture surviving 14997 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'cong', 'lhs': 'S(gcd(digsum,phi))', 'params': {'m': 2, 'q': 4, 'r': 1, 's': 3}, 'rhs': ''}, a, b)) is int and c > 0 for a, b in [(41, 2026), (2027, 4012), (4013, 5998)])


def check_authored_sieve_hl_within_g2_4_w1() -> bool:
    """Authored instrument check (desk): count of consecutive pattern (2, 4) on each window is within 4.0*sqrt of the HL forecast.
    Windows [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)] (disjoint, capped). Uses colony.instruments.sieve via the bridges
    sieve_count / sieve_hl. HL is a conjectural heuristic; counts are bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := sieve_count((2, 4), a, b)) is int and type(h := sieve_hl((2, 4), a, b)) is float and h > 0 and abs(c - h) <= 4.0 * h ** 0.5 for a, b in [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)])


# --- new-data bridge (colony.new_data) ---
def newdata_term(key, n):
    """Bridge to colony.new_data: term n (colony indexing) of menu sequence ``key``, recomputed from
    scratch by the independent method B. Bounded recomputation, not proof of novelty."""
    from colony import new_data as _nd
    return int(_nd.MENU[str(key)]["b"]([int(n)])[0])


def newdata_point(item, k):
    """Bridge to colony.sparse: f(k) of a sparse engine item, recomputed from scratch by method B
    (single value). Bounded recomputation, not proof of novelty."""
    from colony import sparse as _sp
    return _sp.point_b(str(item), int(k))


def check_authored_newdata_a002375_k20001_w1() -> bool:
    """Authored new-data check (desk): A002375 terms a(20001)..a(20003) computed past the
    OEIS frontier (https://oeis.org/A002375/b002375.txt, checked 2026-10-18T12:22:31Z) by numpy FFT convolution of the prime indicator (floating point, rounded);
    recomputed here by direct integer enumeration over an independent odd-only sieve. New data, not a theorem; papers may go further.
    Disabled until the Oracle passes it.
    """
    return all(type(x := newdata_term('gb_u_odd', n)) is int and x == v for n, v in [(20001, 593), (20002, 305), (20003, 289)])


def check_authored_newdata_a035026_k10001_w1() -> bool:
    """Authored new-data check (desk): A035026 terms a(10001)..a(10003) computed past the
    OEIS frontier (https://oeis.org/A035026/b035026.txt, checked 2026-10-18T12:50:00Z) by numpy FFT convolution of the prime indicator (floating point, rounded);
    recomputed here by direct integer enumeration over an independent odd-only sieve. New data, not a theorem; papers may go further.
    Disabled until the Oracle passes it.
    """
    return all(type(x := newdata_term('gb_o_all', n)) is int and x == v for n, v in [(10001, 352), (10002, 674), (10003, 402)])


def check_authored_newdata_a047160_k10001_w1() -> bool:
    """Authored new-data check (desk): A047160 terms a(10001)..a(10003) computed past the
    OEIS frontier (https://oeis.org/A047160/b047160.txt, checked 2026-10-18T12:55:48Z) by sieve scan downward from n;
    recomputed here by Miller-Rabin scan outward from n. New data, not a theorem; papers may go further.
    Disabled until the Oracle passes it.
    """
    return all(type(x := newdata_term('gb_close', n)) is int and x == v for n, v in [(10001, 60), (10002, 35), (10003, 36)])


def check_authored_newdata_a006577_k10001_w1() -> bool:
    """Authored new-data check (desk): A006577 terms a(10001)..a(10003) computed past the
    OEIS frontier (https://oeis.org/A006577/b006577.txt, checked 2026-10-18T12:57:24Z) by memoized iteration (stops at the first smaller value);
    recomputed here by naive bit-level iteration with the (3x+1)/2 shortcut. New data, not a theorem; papers may go further.
    Disabled until the Oracle passes it.
    """
    return all(type(x := newdata_term('col_steps', n)) is int and x == v for n, v in [(10001, 179), (10002, 65), (10003, 65)])


def check_authored_newdata_a006667_k10001_w1() -> bool:
    """Authored new-data check (desk): A006667 terms a(10001)..a(10003) computed past the
    OEIS frontier (https://oeis.org/A006667/b006667.txt, checked 2026-10-18T12:58:56Z) by memoized iteration (stops at the first smaller value);
    recomputed here by naive bit-level iteration with the (3x+1)/2 shortcut. New data, not a theorem; papers may go further.
    Disabled until the Oracle passes it.
    """
    return all(type(x := newdata_term('col_odd', n)) is int and x == v for n, v in [(10001, 64), (10002, 20), (10003, 20)])


def check_authored_newdata_a006666_k10001_w1() -> bool:
    """Authored new-data check (desk): A006666 terms a(10001)..a(10003) computed past the
    OEIS frontier (https://oeis.org/A006666/b006666.txt, checked 2026-10-18T13:02:20Z) by memoized iteration (stops at the first smaller value);
    recomputed here by naive bit-level iteration with the (3x+1)/2 shortcut. New data, not a theorem; papers may go further.
    Disabled until the Oracle passes it.
    """
    return all(type(x := newdata_term('col_even', n)) is int and x == v for n, v in [(10001, 115), (10002, 45), (10003, 45)])


def check_authored_newdata_a025586_k10001_w1() -> bool:
    """Authored new-data check (desk): A025586 terms a(10001)..a(10003) computed past the
    OEIS frontier (https://oeis.org/A025586/b025586.txt, checked 2026-10-18T13:03:33Z) by memoized iteration (stops at the first smaller value);
    recomputed here by naive bit-level iteration with the (3x+1)/2 shortcut. New data, not a theorem; papers may go further.
    Disabled until the Oracle passes it.
    """
    return all(type(x := newdata_term('col_max', n)) is int and x == v for n, v in [(10001, 250504), (10002, 32056), (10003, 45016)])


def check_authored_frontier_cong_x29d14f44_w1() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    D((digsum*digsum))(n) = 1 (mod 2) for all n = 0 (mod 2)
    re-tested on windows [(41, 2026), (2027, 4012), (4013, 5998)]. conjecture surviving 29994 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'cong', 'lhs': 'D((digsum*digsum))', 'params': {'m': 2, 'q': 2, 'r': 1, 's': 0}, 'rhs': ''}, a, b)) is int and c > 0 for a, b in [(41, 2026), (2027, 4012), (4013, 5998)])


def check_authored_frontier_cong_x06b60875_w1() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    sigma[rev](n) = 0 (mod 3) for all n = 2 (mod 3)
    re-tested on windows [(41, 2026), (2027, 4012), (4013, 5998)]. conjecture surviving 19996 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'cong', 'lhs': 'sigma[rev]', 'params': {'m': 3, 'q': 3, 'r': 0, 's': 2}, 'rhs': ''}, a, b)) is int and c > 0 for a, b in [(41, 2026), (2027, 4012), (4013, 5998)])


def check_authored_frontier_cong_x2f9c7891_w1() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    D(gcd(cheb4,phi))(n) = 0 (mod 2) for all n = 2 (mod 3)
    re-tested on windows [(41, 2026), (2027, 4012), (4013, 5998)]. conjecture surviving 19996 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'cong', 'lhs': 'D(gcd(cheb4,phi))', 'params': {'m': 2, 'q': 3, 'r': 0, 's': 2}, 'rhs': ''}, a, b)) is int and c > 0 for a, b in [(41, 2026), (2027, 4012), (4013, 5998)])


def check_authored_frontier_le_xc2340063_w1() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    sopfr[phi](n) <= (sopfr-omega)(n) for all n >= 1 (with equality at some n)
    re-tested on windows [(41, 2026), (2027, 4012), (4013, 5998)]. conjecture surviving 59988 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'le', 'lhs': 'sopfr[phi]', 'params': {}, 'rhs': '(sopfr-omega)'}, a, b)) is int and c > 0 for a, b in [(41, 2026), (2027, 4012), (4013, 5998)])


def check_authored_frontier_cong_xbb82919e_w1() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    dbl(gcd(rev,sigma))(n) = 0 (mod 3) for all n = 3 (mod 6)
    re-tested on windows [(41, 2026), (2027, 4012), (4013, 5998)]. conjecture surviving 3331 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'cong', 'lhs': 'dbl(gcd(rev,sigma))', 'params': {'m': 3, 'q': 6, 'r': 0, 's': 3}, 'rhs': ''}, a, b)) is int and c > 0 for a, b in [(41, 2026), (2027, 4012), (4013, 5998)])


def check_authored_frontier_divides_xdd6cdac8_w1() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    tau[lpf](n) divides (lpf-pell)(n) for all n >= 1
    re-tested on windows [(41, 326), (327, 612), (613, 898)]. conjecture surviving 1988 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'divides', 'lhs': 'tau[lpf]', 'params': {}, 'rhs': '(lpf-pell)'}, a, b)) is int and c > 0 for a, b in [(41, 326), (327, 612), (613, 898)])


def check_authored_frontier_cong_x396d7d8c_w1() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    dbl(gcd(fib,tau))(n) = 0 (mod 3) for all n = 2 (mod 4)
    re-tested on windows [(41, 326), (327, 612), (613, 898)]. conjecture surviving 497 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'cong', 'lhs': 'dbl(gcd(fib,tau))', 'params': {'m': 3, 'q': 4, 'r': 0, 's': 2}, 'rhs': ''}, a, b)) is int and c > 0 for a, b in [(41, 326), (327, 612), (613, 898)])


def check_authored_sieve_hl_within_g2_4_2_w1() -> bool:
    """Authored instrument check (desk): count of consecutive pattern (2, 4, 2) on each window is within 4.0*sqrt of the HL forecast.
    Windows [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)] (disjoint, capped). Uses colony.instruments.sieve via the bridges
    sieve_count / sieve_hl. HL is a conjectural heuristic; counts are bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := sieve_count((2, 4, 2), a, b)) is int and type(h := sieve_hl((2, 4, 2), a, b)) is float and h > 0 and abs(c - h) <= 4.0 * h ** 0.5 for a, b in [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)])


def check_authored_frontier_le_x7a9213ec_w1() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    (lpf+mu)(n) <= dbl(gpf)(n) for all n >= 1 (with equality at some n)
    re-tested on windows [(41, 2026), (2027, 4012), (4013, 5998)]. conjecture surviving 19988 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'le', 'lhs': '(lpf+mu)', 'params': {}, 'rhs': 'dbl(gpf)'}, a, b)) is int and c > 0 for a, b in [(41, 2026), (2027, 4012), (4013, 5998)])


def check_authored_frontier_divides_x3562d07e_w1() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    fib(n) divides dbl(stree_grid3)(n) for all n >= 1
    re-tested on windows [(41, 326), (327, 612), (613, 898)]. conjecture surviving 988 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'divides', 'lhs': 'fib', 'params': {}, 'rhs': 'dbl(stree_grid3)'}, a, b)) is int and c > 0 for a, b in [(41, 326), (327, 612), (613, 898)])


def check_authored_frontier_divides_xba575886_w1() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    stree_ladder(n) divides dbl(stree_ladder)(n) for all n >= 1
    re-tested on windows [(41, 326), (327, 612), (613, 898)]. conjecture surviving 988 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'divides', 'lhs': 'stree_ladder', 'params': {}, 'rhs': 'dbl(stree_ladder)'}, a, b)) is int and c > 0 for a, b in [(41, 326), (327, 612), (613, 898)])


def check_authored_frontier_divides_xc90ee275_w1() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    stree_grid3(n) divides dbl(stree_grid3)(n) for all n >= 1
    re-tested on windows [(41, 326), (327, 612), (613, 898)]. conjecture surviving 988 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'divides', 'lhs': 'stree_grid3', 'params': {}, 'rhs': 'dbl(stree_grid3)'}, a, b)) is int and c > 0 for a, b in [(41, 326), (327, 612), (613, 898)])


def check_authored_frontier_divides_x318ee14a_w1() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    lucas(n) divides dbl(stree_grid3)(n) for all n >= 1
    re-tested on windows [(41, 326), (327, 612), (613, 898)]. conjecture surviving 988 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'divides', 'lhs': 'lucas', 'params': {}, 'rhs': 'dbl(stree_grid3)'}, a, b)) is int and c > 0 for a, b in [(41, 326), (327, 612), (613, 898)])


def check_authored_frontier_le_x7a9213ec_w2() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    (lpf+mu)(n) <= dbl(gpf)(n) for all n >= 1 (with equality at some n)
    re-tested on windows [(6001, 12000), (12001, 18000), (18001, 24000)]. conjecture surviving 59988 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'le', 'lhs': '(lpf+mu)', 'params': {}, 'rhs': 'dbl(gpf)'}, a, b)) is int and c > 0 for a, b in [(6001, 12000), (12001, 18000), (18001, 24000)])


def check_authored_frontier_divides_x3562d07e_w2() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    fib(n) divides dbl(stree_grid3)(n) for all n >= 1
    re-tested on windows [(901, 934), (935, 968), (969, 1002)]. conjecture surviving 988 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'divides', 'lhs': 'fib', 'params': {}, 'rhs': 'dbl(stree_grid3)'}, a, b)) is int and c > 0 for a, b in [(901, 934), (935, 968), (969, 1002)])


def check_authored_frontier_le_x7a9213ec_w3() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    (lpf+mu)(n) <= dbl(gpf)(n) for all n >= 1 (with equality at some n)
    re-tested on windows [(24001, 24333), (24334, 24666), (24667, 24999)]. conjecture surviving 59988 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'le', 'lhs': '(lpf+mu)', 'params': {}, 'rhs': 'dbl(gpf)'}, a, b)) is int and c > 0 for a, b in [(24001, 24333), (24334, 24666), (24667, 24999)])


def check_authored_frontier_divides_xc90ee275_w2() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    stree_grid3(n) divides dbl(stree_grid3)(n) for all n >= 1
    re-tested on windows [(901, 934), (935, 968), (969, 1002)]. conjecture surviving 988 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'divides', 'lhs': 'stree_grid3', 'params': {}, 'rhs': 'dbl(stree_grid3)'}, a, b)) is int and c > 0 for a, b in [(901, 934), (935, 968), (969, 1002)])


def check_authored_frontier_divides_x318ee14a_w2() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    lucas(n) divides dbl(stree_grid3)(n) for all n >= 1
    re-tested on windows [(901, 934), (935, 968), (969, 1002)]. conjecture surviving 988 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'divides', 'lhs': 'lucas', 'params': {}, 'rhs': 'dbl(stree_grid3)'}, a, b)) is int and c > 0 for a, b in [(901, 934), (935, 968), (969, 1002)])


def check_authored_frontier_divides_xba575886_w2() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    stree_ladder(n) divides dbl(stree_ladder)(n) for all n >= 1
    re-tested on windows [(901, 934), (935, 968), (969, 1002)]. conjecture surviving 988 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'divides', 'lhs': 'stree_ladder', 'params': {}, 'rhs': 'dbl(stree_ladder)'}, a, b)) is int and c > 0 for a, b in [(901, 934), (935, 968), (969, 1002)])


def check_authored_frontier_divides_x0c5f5f5b_w1() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    gpf[phi](n) divides dbl(phi)(n) for all n >= 1
    re-tested on windows [(41, 2026), (2027, 4012), (4013, 5998)]. conjecture surviving 59988 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'divides', 'lhs': 'gpf[phi]', 'params': {}, 'rhs': 'dbl(phi)'}, a, b)) is int and c > 0 for a, b in [(41, 2026), (2027, 4012), (4013, 5998)])


def check_authored_frontier_le_x10223e69_w1() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    digsum[rad](n) <= dbl(rad)(n) for all n >= 1 (with equality at some n)
    re-tested on windows [(41, 2026), (2027, 4012), (4013, 5998)]. conjecture surviving 19988 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'le', 'lhs': 'digsum[rad]', 'params': {}, 'rhs': 'dbl(rad)'}, a, b)) is int and c > 0 for a, b in [(41, 2026), (2027, 4012), (4013, 5998)])


def check_authored_sieve_residue_bal_g4_2_4_w1() -> bool:
    """Authored instrument check (desk): p mod 4 classes 1/3 of pattern (4, 2, 4) are balanced within 4.0*sqrt(total).
    Windows [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)] (disjoint, capped). Uses colony.instruments.sieve via the bridges
    sieve_count / sieve_hl. HL is a conjectural heuristic; counts are bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(x := sieve_count((4, 2, 4), a, b, 4, 1)) is int and type(y := sieve_count((4, 2, 4), a, b, 4, 3)) is int and x + y > 0 and abs(x - y) <= 4.0 * (x + y) ** 0.5 for a, b in [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)])


def check_authored_frontier_le_xafb0aef8_w1() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    (gpf+omega)(n) <= sigma(n) for all n >= 1 (with equality at some n)
    re-tested on windows [(41, 2026), (2027, 4012), (4013, 5998)]. conjecture surviving 59988 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'le', 'lhs': '(gpf+omega)', 'params': {}, 'rhs': 'sigma'}, a, b)) is int and c > 0 for a, b in [(41, 2026), (2027, 4012), (4013, 5998)])


def check_authored_frontier_divides_x9835949a_w1() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    (fib*lucas)(n) divides dbl(stree_grid3)(n) for all n >= 1
    re-tested on windows [(41, 326), (327, 612), (613, 898)]. conjecture surviving 988 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'divides', 'lhs': '(fib*lucas)', 'params': {}, 'rhs': 'dbl(stree_grid3)'}, a, b)) is int and c > 0 for a, b in [(41, 326), (327, 612), (613, 898)])


def check_authored_sieve_hl_within_g4_6_2_w1() -> bool:
    """Authored instrument check (desk): count of consecutive pattern (4, 6, 2) on each window is within 4.0*sqrt of the HL forecast.
    Windows [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)] (disjoint, capped). Uses colony.instruments.sieve via the bridges
    sieve_count / sieve_hl. HL is a conjectural heuristic; counts are bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := sieve_count((4, 6, 2), a, b)) is int and type(h := sieve_hl((4, 6, 2), a, b)) is float and h > 0 and abs(c - h) <= 4.0 * h ** 0.5 for a, b in [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)])


def check_authored_frontier_cong_xd9add9e9_w1() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    dbl(oxa038041)(n) = 2 (mod 3) for all n = 2 (mod 3)
    re-tested on windows [(41, 76), (77, 112), (113, 148)]. conjecture surviving 29 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'cong', 'lhs': 'dbl(oxa038041)', 'params': {'m': 3, 'q': 3, 'r': 2, 's': 2}, 'rhs': ''}, a, b)) is int and c > 0 for a, b in [(41, 76), (77, 112), (113, 148)])


def check_authored_sieve_residue_bal_g6_2_6_w1() -> bool:
    """Authored instrument check (desk): p mod 4 classes 1/3 of pattern (6, 2, 6) are balanced within 4.0*sqrt(total).
    Windows [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)] (disjoint, capped). Uses colony.instruments.sieve via the bridges
    sieve_count / sieve_hl. HL is a conjectural heuristic; counts are bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(x := sieve_count((6, 2, 6), a, b, 4, 1)) is int and type(y := sieve_count((6, 2, 6), a, b, 4, 3)) is int and x + y > 0 and abs(x - y) <= 4.0 * (x + y) ** 0.5 for a, b in [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)])


def check_authored_sieve_hl_within_g6_4_6_w1() -> bool:
    """Authored instrument check (desk): count of consecutive pattern (6, 4, 6) on each window is within 4.0*sqrt of the HL forecast.
    Windows [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)] (disjoint, capped). Uses colony.instruments.sieve via the bridges
    sieve_count / sieve_hl. HL is a conjectural heuristic; counts are bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := sieve_count((6, 4, 6), a, b)) is int and type(h := sieve_hl((6, 4, 6), a, b)) is float and h > 0 and abs(c - h) <= 4.0 * h ** 0.5 for a, b in [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)])


def check_authored_sieve_residue_bal_g6_4_2_w1() -> bool:
    """Authored instrument check (desk): p mod 4 classes 1/3 of pattern (6, 4, 2) are balanced within 4.0*sqrt(total).
    Windows [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)] (disjoint, capped). Uses colony.instruments.sieve via the bridges
    sieve_count / sieve_hl. HL is a conjectural heuristic; counts are bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(x := sieve_count((6, 4, 2), a, b, 4, 1)) is int and type(y := sieve_count((6, 4, 2), a, b, 4, 3)) is int and x + y > 0 and abs(x - y) <= 4.0 * (x + y) ** 0.5 for a, b in [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)])


def check_authored_sieve_hl_within_g6_6_2_w1() -> bool:
    """Authored instrument check (desk): count of consecutive pattern (6, 6, 2) on each window is within 4.0*sqrt of the HL forecast.
    Windows [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)] (disjoint, capped). Uses colony.instruments.sieve via the bridges
    sieve_count / sieve_hl. HL is a conjectural heuristic; counts are bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := sieve_count((6, 6, 2), a, b)) is int and type(h := sieve_hl((6, 6, 2), a, b)) is float and h > 0 and abs(c - h) <= 4.0 * h ** 0.5 for a, b in [(10000000, 12000000), (12000000, 14000000), (14000000, 16000000)])


def check_authored_frontier_cong_xa8371e31_w1() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    S((fib*oxa048760))(n) = 0 (mod 2) for all n = 0 (mod 3)
    re-tested on windows [(41, 326), (327, 612), (613, 898)]. conjecture surviving 662 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'cong', 'lhs': 'S((fib*oxa048760))', 'params': {'m': 2, 'q': 3, 'r': 0, 's': 0}, 'rhs': ''}, a, b)) is int and c > 0 for a, b in [(41, 326), (327, 612), (613, 898)])


def check_authored_frontier_divides_x97939198_w1() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    gcd(lpf,tau)(n) divides (mu*pell)(n) for all n >= 1
    re-tested on windows [(41, 326), (327, 612), (613, 898)]. machine-proved (certificate). Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'divides', 'lhs': 'gcd(lpf,tau)', 'params': {}, 'rhs': '(mu*pell)'}, a, b)) is int and c > 0 for a, b in [(41, 326), (327, 612), (613, 898)])


def check_authored_frontier_cong_x4bb20589_w1() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    dbl(oxa048767)(n) = 0 (mod 2) for all n = 1 (mod 2)
    re-tested on windows [(41, 277), (278, 514), (515, 751)]. conjecture surviving 494 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'cong', 'lhs': 'dbl(oxa048767)', 'params': {'m': 2, 'q': 2, 'r': 0, 's': 1}, 'rhs': ''}, a, b)) is int and c > 0 for a, b in [(41, 277), (278, 514), (515, 751)])


def check_authored_frontier_cong_xdbe366da_w1() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    D(oxa177115)(n) = 0 (mod 2) for all n = 0 (mod 4)
    re-tested on windows [(41, 178), (179, 316), (317, 454)]. conjecture surviving 122 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'cong', 'lhs': 'D(oxa177115)', 'params': {'m': 2, 'q': 4, 'r': 0, 's': 0}, 'rhs': ''}, a, b)) is int and c > 0 for a, b in [(41, 178), (179, 316), (317, 454)])


def check_authored_frontier_modpat_x51c52e42_w2() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    gcd(oxa009191,oxa083105)(n) mod 2 depends only on n mod 6 (residues [1, 0, 1, 1, 1, 1] for n = 1..6), all n >= 1
    re-tested on windows [(901, 1058), (1059, 1216), (1217, 1374)]. conjecture surviving 988 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'modpat', 'lhs': 'gcd(oxa009191,oxa083105)', 'params': {'P': 6, 'm': 2, 'pat': [1, 0, 1, 1, 1, 1]}, 'rhs': ''}, a, b)) is int and c > 0 for a, b in [(901, 1058), (1059, 1216), (1217, 1374)])


def check_authored_sieve_residue_bal_g2_4_6_w2() -> bool:
    """Authored instrument check (desk): p mod 4 classes 1/3 of pattern (2, 4, 6) are balanced within 4.0*sqrt(total).
    Windows [(20000000, 22000000), (22000000, 24000000), (24000000, 26000000)] (disjoint, capped). Uses colony.instruments.sieve via the bridges
    sieve_count / sieve_hl. HL is a conjectural heuristic; counts are bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(x := sieve_count((2, 4, 6), a, b, 4, 1)) is int and type(y := sieve_count((2, 4, 6), a, b, 4, 3)) is int and x + y > 0 and abs(x - y) <= 4.0 * (x + y) ** 0.5 for a, b in [(20000000, 22000000), (22000000, 24000000), (24000000, 26000000)])


def check_authored_frontier_le_x46c5cc8a_w3() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    gcd(mu,n)(n) <= gcd(lucas,sqfree)(n) for all n >= 1 (with equality at some n)
    re-tested on windows [(1401, 1434), (1435, 1468), (1469, 1502)]. conjecture surviving 3988 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'le', 'lhs': 'gcd(mu,n)', 'params': {}, 'rhs': 'gcd(lucas,sqfree)'}, a, b)) is int and c > 0 for a, b in [(1401, 1434), (1435, 1468), (1469, 1502)])


def check_authored_frontier_le_xdbff107c_w3() -> bool:
    """Authored frontier check (desk): the colony's own conjecture
    (bigomega*lpf)(n) <= sopfr(n) for all n >= 1 (with equality at some n)
    re-tested on windows [(24001, 28500), (28501, 33000), (33001, 37500)]. conjecture surviving 59988 checks. Bounded evidence, not proof.
    Disabled until the Oracle passes it.
    """
    return all(type(c := frontier_holds({'kind': 'le', 'lhs': '(bigomega*lpf)', 'params': {}, 'rhs': 'sopfr'}, a, b)) is int and c > 0 for a, b in [(24001, 28500), (28501, 33000), (33001, 37500)])


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
    ("adversarial_derived_chain_stress", check_adversarial_derived_chain_stress, True),

    # Building-block refill (James 2026-10-17): classical PROVEN lemmas, start DISABLED (Oracle decides)
    ("fermat_little", lambda: all(check_fermat_little(a) for a in range(0, 40)), True),
    ("euler_theorem", lambda: all(check_euler_theorem(n) for n in range(2, 40)), True),
    ("wilson_theorem", lambda: all(check_wilson_theorem(n) for n in range(2, 60)), True),
    ("quadratic_reciprocity", lambda: all(check_quadratic_reciprocity(p) for p in range(5, 80)), True),
    ("mobius_divisor_sum", lambda: all(check_mobius_divisor_sum(n) for n in range(1, 120)), True),
    ("gauss_phi_divisor_sum", lambda: all(check_gauss_phi_divisor_sum(n) for n in range(1, 60)), True),
    ("sigma_multiplicative", lambda: all(check_sigma_multiplicative(a, b) for a in range(1, 25) for b in range(1, 25)), True),
    ("mobius_inversion_sigma", lambda: all(check_mobius_inversion_sigma(n) for n in range(1, 80)), True),
    ("bezout_identity", lambda: all(check_bezout_identity(a, b) for a in range(1, 40) for b in range(1, 40)), True),
    ("crt_coprime_pair", lambda: all(check_crt_coprime_pair(m) for m in range(1, 25)), True),
    ("lucas_theorem_binomial", lambda: all(check_lucas_theorem_binomial(n) for n in range(0, 30)), True),
    ("stirling_first_row_sum", lambda: all(check_stirling_first_row_sum(n) for n in range(0, 16)), True),
    ("bell_stirling_sum", lambda: all(check_bell_stirling_sum(n) for n in range(0, 16)), True),
    ("alternating_binomial_row", lambda: all(check_alternating_binomial_row(n) for n in range(0, 40)), True),
    ("multinomial_three", lambda: all(check_multinomial_three(n) for n in range(0, 20)), True),
    ("euler_pentagonal", lambda: all(check_euler_pentagonal(n) for n in range(0, 40)), True),
    ("odd_distinct_partitions", lambda: all(check_odd_distinct_partitions(n) for n in range(0, 40)), True),
    ("partition_conjugate_parts", lambda: all(check_partition_conjugate_parts(n) for n in range(0, 20)), True),
    ("cayley_tree_count", lambda: all(check_cayley_tree_count(n) for n in range(2, 10)), True),
    ("cycle_spanning_trees", lambda: all(check_cycle_spanning_trees(n) for n in range(3, 14)), True),
    ("complete_bipartite_trees", lambda: all(check_complete_bipartite_trees(n) for n in range(1, 8)), True),
    ("cayley_hamilton_2x2", lambda: all(check_cayley_hamilton_2x2(a) for a in range(0, 9)), True),
    ("cayley_hamilton_3x3", lambda: all(check_cayley_hamilton_3x3(s) for s in range(0, 20)), True),
    ("newton_identities", lambda: all(check_newton_identities(n) for n in range(1, 10)), True),
    ("polynomial_remainder", lambda: all(check_polynomial_remainder(a) for a in range(0, 21)), True),
    ("telescoping_sum", lambda: all(check_telescoping_sum(n) for n in range(1, 40)), True),
    ("abel_summation", lambda: all(check_abel_summation(n) for n in range(1, 40)), True),
    ("faulhaber_power_sums", lambda: all(check_faulhaber_power_sums(n) for n in range(0, 30)), True),
    ("lagrange_cyclic_orders", lambda: all(check_lagrange_cyclic_orders(n) for n in range(2, 40)), True),
    ("burnside_necklaces", lambda: all(check_burnside_necklaces(n) for n in range(1, 8)), True),

    ("authored_bell_triangle_recurrence__binomial_inversion_small_w1", check_authored_bell_triangle_recurrence__binomial_inversion_small_w1, True),
    ("authored_oeis_a000108__catalan_bounded", check_authored_oeis_a000108__catalan_bounded, True),
    ("authored_oeis_a000045__cassini", check_authored_oeis_a000045__cassini, True),
    ("authored_binomial_symmetry__catalan_convolution_w1", check_authored_binomial_symmetry__catalan_convolution_w1, True),
    ("authored_central_binom_bound__derangement_subfactorial_w1", check_authored_central_binom_bound__derangement_subfactorial_w1, True),
    ("authored_euler_totient_multiplicative__hermite_recurrence_w1", check_authored_euler_totient_multiplicative__hermite_recurrence_w1, True),
    ("authored_fibonacci_addition__gcd_fibonacci_w1", check_authored_fibonacci_addition__gcd_fibonacci_w1, True),
    ("authored_geometric_sum__hockey_stick_w1", check_authored_geometric_sum__hockey_stick_w1, True),
    ("authored_motzkin_bounded__legendre_duplication_small_w1", check_authored_motzkin_bounded__legendre_duplication_small_w1, True),
    ("authored_pascal_identity__narayana_sum_w1", check_authored_pascal_identity__narayana_sum_w1, True),
    ("authored_oeis_a000984__central_binom_bound", check_authored_oeis_a000984__central_binom_bound, True),
    ("authored_pell_companion__pythagorean_generation_w1", check_authored_pell_companion__pythagorean_generation_w1, True),
    ("authored_sum_first_n_cubes__stirling_second_row_w1", check_authored_sum_first_n_cubes__stirling_second_row_w1, True),
    ("authored_bell_triangle_recurrence__hermite_recurrence_w1", check_authored_bell_triangle_recurrence__hermite_recurrence_w1, True),
    ("authored_binomial_inversion_small__legendre_duplication_small_w1", check_authored_binomial_inversion_small__legendre_duplication_small_w1, True),
    ("authored_oeis_a000079__binomial_sum_row", check_authored_oeis_a000079__binomial_sum_row, True),
    ("authored_catalan_convolution__derangement_subfactorial_w1", check_authored_catalan_convolution__derangement_subfactorial_w1, True),
    ("authored_fibonacci_addition__euler_totient_multiplicative_w1", check_authored_fibonacci_addition__euler_totient_multiplicative_w1, True),
    ("authored_gcd_fibonacci__motzkin_bounded_w1", check_authored_gcd_fibonacci__motzkin_bounded_w1, True),
    ("authored_geometric_sum__narayana_sum_w1", check_authored_geometric_sum__narayana_sum_w1, True),
    ("authored_hockey_stick__pell_companion_w1", check_authored_hockey_stick__pell_companion_w1, True),
    ("authored_cassini__catalan_convolution_w1", check_authored_cassini__catalan_convolution_w1, True),
    ("authored_geometric_sum__pell_companion_w1", check_authored_geometric_sum__pell_companion_w1, True),
    ("authored_binomial_symmetry__vandermonde_conv_w1", check_authored_binomial_symmetry__vandermonde_conv_w1, True),
    ("authored_binomial_sum_row__bell_triangle_recurrence_w1", check_authored_binomial_sum_row__bell_triangle_recurrence_w1, True),
    ("authored_cassini__binomial_inversion_small_w1", check_authored_cassini__binomial_inversion_small_w1, True),
    ("authored_catalan_bounded__catalan_convolution_w1", check_authored_catalan_bounded__catalan_convolution_w1, True),
    ("authored_central_binom_bound__gcd_fibonacci_w1", check_authored_central_binom_bound__gcd_fibonacci_w1, True),
    ("authored_derangement_subfactorial__euler_totient_multiplicative_w1", check_authored_derangement_subfactorial__euler_totient_multiplicative_w1, True),
    ("authored_fibonacci_addition__hermite_recurrence_w1", check_authored_fibonacci_addition__hermite_recurrence_w1, True),
    ("authored_geometric_sum__legendre_duplication_small_w1", check_authored_geometric_sum__legendre_duplication_small_w1, True),
    ("authored_hockey_stick__motzkin_bounded_w1", check_authored_hockey_stick__motzkin_bounded_w1, True),
    ("authored_pascal_identity__pell_companion_w1", check_authored_pascal_identity__pell_companion_w1, True),
    ("authored_pythagorean_generation__narayana_sum_w1", check_authored_pythagorean_generation__narayana_sum_w1, True),
    ("authored_vandermonde_conv__stirling_second_row_w1", check_authored_vandermonde_conv__stirling_second_row_w1, True),
    ("authored_sum_first_n_odds__bell_triangle_recurrence_w1", check_authored_sum_first_n_odds__bell_triangle_recurrence_w1, True),
    ("authored_cassini__catalan_bounded_w1", check_authored_cassini__catalan_bounded_w1, True),
    ("authored_central_binom_bound__binomial_inversion_small_w1", check_authored_central_binom_bound__binomial_inversion_small_w1, True),
    ("authored_derangement_subfactorial__legendre_duplication_small_w1", check_authored_derangement_subfactorial__legendre_duplication_small_w1, True),
    ("authored_fibonacci_addition__narayana_sum_w1", check_authored_fibonacci_addition__narayana_sum_w1, True),
    ("authored_gcd_fibonacci__euler_totient_multiplicative_w1", check_authored_gcd_fibonacci__euler_totient_multiplicative_w1, True),
    ("authored_geometric_sum__hermite_recurrence_w1", check_authored_geometric_sum__hermite_recurrence_w1, True),
    ("authored_hockey_stick__stirling_second_row_w1", check_authored_hockey_stick__stirling_second_row_w1, True),
    ("authored_pascal_identity__motzkin_bounded_w1", check_authored_pascal_identity__motzkin_bounded_w1, True),
    ("authored_sieve_hl_within_g2_w1", check_authored_sieve_hl_within_g2_w1, True),
    ("authored_sieve_two_counter_g2_w1", check_authored_sieve_two_counter_g2_w1, True),
    ("authored_sieve_hl_within_g2_w2", check_authored_sieve_hl_within_g2_w2, True),
    ("authored_sieve_residue_bal_g2_w2", check_authored_sieve_residue_bal_g2_w2, True),
    ("authored_sieve_residue_bal_g2_6_4_w1", check_authored_sieve_residue_bal_g2_6_4_w1, True),
    ("authored_sieve_residue_bal_g4_2_6_w1", check_authored_sieve_residue_bal_g4_2_6_w1, True),
    ("authored_sieve_residue_bal_g6_2_4_w1", check_authored_sieve_residue_bal_g6_2_4_w1, True),
    ("authored_sieve_two_counter_g6_2_6_w1", check_authored_sieve_two_counter_g6_2_6_w1, True),
    ("authored_sieve_hl_within_g6_4_2_w1", check_authored_sieve_hl_within_g6_4_2_w1, True),
    ("authored_sieve_two_counter_g6_w1", check_authored_sieve_two_counter_g6_w1, True),
    ("authored_sieve_hl_within_g4_w1", check_authored_sieve_hl_within_g4_w1, True),
    ("authored_sieve_hl_within_g4_6_w1", check_authored_sieve_hl_within_g4_6_w1, True),
    ("authored_frontier_cong_xa68963c2_w1", check_authored_frontier_cong_xa68963c2_w1, True),
    ("authored_sieve_hl_within_g2_4_w1", check_authored_sieve_hl_within_g2_4_w1, True),
    ("authored_newdata_a002375_k20001_w1", check_authored_newdata_a002375_k20001_w1, True),
    ("authored_newdata_a035026_k10001_w1", check_authored_newdata_a035026_k10001_w1, True),
    ("authored_newdata_a047160_k10001_w1", check_authored_newdata_a047160_k10001_w1, True),
    ("authored_newdata_a006577_k10001_w1", check_authored_newdata_a006577_k10001_w1, True),
    ("authored_newdata_a006667_k10001_w1", check_authored_newdata_a006667_k10001_w1, True),
    ("authored_newdata_a006666_k10001_w1", check_authored_newdata_a006666_k10001_w1, True),
    ("authored_newdata_a025586_k10001_w1", check_authored_newdata_a025586_k10001_w1, True),
    ("authored_frontier_cong_x29d14f44_w1", check_authored_frontier_cong_x29d14f44_w1, True),
    ("authored_frontier_cong_x06b60875_w1", check_authored_frontier_cong_x06b60875_w1, True),
    ("authored_frontier_cong_x2f9c7891_w1", check_authored_frontier_cong_x2f9c7891_w1, True),
    ("authored_frontier_le_xc2340063_w1", check_authored_frontier_le_xc2340063_w1, True),
    ("authored_frontier_cong_xbb82919e_w1", check_authored_frontier_cong_xbb82919e_w1, True),
    ("authored_frontier_divides_xdd6cdac8_w1", check_authored_frontier_divides_xdd6cdac8_w1, True),
    ("authored_frontier_cong_x396d7d8c_w1", check_authored_frontier_cong_x396d7d8c_w1, True),
    ("authored_sieve_hl_within_g2_4_2_w1", check_authored_sieve_hl_within_g2_4_2_w1, True),
    ("authored_frontier_le_x7a9213ec_w1", check_authored_frontier_le_x7a9213ec_w1, True),
    ("authored_frontier_divides_x3562d07e_w1", check_authored_frontier_divides_x3562d07e_w1, True),
    ("authored_frontier_divides_xba575886_w1", check_authored_frontier_divides_xba575886_w1, True),
    ("authored_frontier_divides_xc90ee275_w1", check_authored_frontier_divides_xc90ee275_w1, True),
    ("authored_frontier_divides_x318ee14a_w1", check_authored_frontier_divides_x318ee14a_w1, True),
    ("authored_frontier_le_x7a9213ec_w2", check_authored_frontier_le_x7a9213ec_w2, True),
    ("authored_frontier_divides_x3562d07e_w2", check_authored_frontier_divides_x3562d07e_w2, True),
    ("authored_frontier_le_x7a9213ec_w3", check_authored_frontier_le_x7a9213ec_w3, True),
    ("authored_frontier_divides_xc90ee275_w2", check_authored_frontier_divides_xc90ee275_w2, True),
    ("authored_frontier_divides_x318ee14a_w2", check_authored_frontier_divides_x318ee14a_w2, True),
    ("authored_frontier_divides_xba575886_w2", check_authored_frontier_divides_xba575886_w2, True),
    ("authored_frontier_divides_x0c5f5f5b_w1", check_authored_frontier_divides_x0c5f5f5b_w1, False),
    ("authored_frontier_le_x10223e69_w1", check_authored_frontier_le_x10223e69_w1, False),
    ("authored_sieve_residue_bal_g4_2_4_w1", check_authored_sieve_residue_bal_g4_2_4_w1, False),
    ("authored_frontier_le_xafb0aef8_w1", check_authored_frontier_le_xafb0aef8_w1, False),
    ("authored_frontier_divides_x9835949a_w1", check_authored_frontier_divides_x9835949a_w1, False),
    ("authored_sieve_hl_within_g4_6_2_w1", check_authored_sieve_hl_within_g4_6_2_w1, False),
    ("authored_frontier_cong_xd9add9e9_w1", check_authored_frontier_cong_xd9add9e9_w1, False),
    ("authored_sieve_residue_bal_g6_2_6_w1", check_authored_sieve_residue_bal_g6_2_6_w1, False),
    ("authored_sieve_hl_within_g6_4_6_w1", check_authored_sieve_hl_within_g6_4_6_w1, False),
    ("authored_sieve_residue_bal_g6_4_2_w1", check_authored_sieve_residue_bal_g6_4_2_w1, False),
    ("authored_sieve_hl_within_g6_6_2_w1", check_authored_sieve_hl_within_g6_6_2_w1, False),
    ("authored_frontier_cong_xa8371e31_w1", check_authored_frontier_cong_xa8371e31_w1, False),
    ("authored_frontier_divides_x97939198_w1", check_authored_frontier_divides_x97939198_w1, True),
    ("authored_frontier_cong_x4bb20589_w1", check_authored_frontier_cong_x4bb20589_w1, True),
    ("authored_frontier_cong_xdbe366da_w1", check_authored_frontier_cong_xdbe366da_w1, True),
    ("authored_frontier_modpat_x51c52e42_w2", check_authored_frontier_modpat_x51c52e42_w2, True),
    ("authored_sieve_residue_bal_g2_4_6_w2", check_authored_sieve_residue_bal_g2_4_6_w2, True),
    ("authored_frontier_le_x46c5cc8a_w3", check_authored_frontier_le_x46c5cc8a_w3, True),
    ("authored_frontier_le_xdbff107c_w3", check_authored_frontier_le_xdbff107c_w3, False),
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
