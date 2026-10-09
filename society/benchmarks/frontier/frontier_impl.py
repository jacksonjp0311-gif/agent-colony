"""Frontier checkers — BOUNDED EVIDENCE on open statements. NOT PROOFS.

Every function here checks an open / conjectural statement on a FINITE range. Passing means
"no counterexample in [lo, hi]" — never that the statement is true. Nothing in this module
is part of the lemma microbench or any proof-scored tier.

Each family has two independent implementations:

* a fast primary checker ``check_<family>(lo, hi, deadline)`` that walks the window in
  order, stops at the time budget, and reports the contiguous verified prefix, and
* an independent single-point re-verifier ``holds_<family>(n)`` built on a different method
  (Miller-Rabin vs sieve, trial-division factorisation vs segmented sieve, exact Fraction
  arithmetic, a separate Collatz loop with a larger cap). Range extensions are spot-checked
  with it; any counterexample/anomaly from the primary is re-checked with it before anything
  is recorded — and even then it is only flagged for human review, never claimed.

Pure Python, stdlib only, no I/O.
"""
from __future__ import annotations

import math
import time
from fractions import Fraction
from typing import Any

LABEL = "bounded evidence, not proof"


class Deadline:
    """Wall-clock budget. ``hit()`` is checked inside every primary loop."""

    def __init__(self, budget_s: float) -> None:
        self.budget_s = float(budget_s)
        self.t0 = time.perf_counter()
        self.t_end = self.t0 + self.budget_s

    def hit(self) -> bool:
        return time.perf_counter() >= self.t_end

    def elapsed(self) -> float:
        return round(time.perf_counter() - self.t0, 4)


# --------------------------------------------------------------------------- primes

def sieve(n: int) -> bytearray:
    """is_prime table for 0..n (sieve of Eratosthenes)."""
    n = max(1, int(n))
    s = bytearray([1]) * (n + 1)
    s[0] = 0
    s[1] = 0
    for p in range(2, math.isqrt(n) + 1):
        if s[p]:
            s[p * p:: p] = bytearray(len(range(p * p, n + 1, p)))
    return s


def segment_sieve(a: int, b: int) -> bytearray:
    """is_prime table for a..b (index i ↔ a+i), base primes <= sqrt(b). Memory O(b - a)."""
    a = max(0, int(a))
    seg = bytearray([1]) * (b - a + 1)
    for v in range(a, min(b, 1) + 1):
        seg[v - a] = 0
    base = sieve(math.isqrt(b) + 1)
    for p in range(2, len(base)):
        if not base[p]:
            continue
        start = max(p * p, ((a + p - 1) // p) * p)
        if start > b:
            continue
        seg[start - a:: p] = bytearray(len(range(start, b + 1, p)))
    return seg


def primes_upto(n: int) -> list[int]:
    s = sieve(n)
    return [i for i in range(2, n + 1) if s[i]]


_MR_BASES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)  # deterministic for n < 3.3e24


def is_prime_mr(n: int) -> bool:
    """Deterministic Miller-Rabin (independent of the sieve)."""
    if n < 2:
        return False
    for p in _MR_BASES:
        if n % p == 0:
            return n == p
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for a in _MR_BASES:
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def is_prime_trial(n: int) -> bool:
    """Trial division (a third, slow, independent primality test)."""
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    r = math.isqrt(n)
    f = 3
    while f <= r:
        if n % f == 0:
            return False
        f += 2
    return True


def _result(lo: int, hi: int, checked_hi: int, *, counterexample: int | None = None,
            anomaly: int | None = None, data: dict[str, Any] | None = None,
            deadline: Deadline | None = None) -> dict[str, Any]:
    return {
        "lo": lo,
        "hi": hi,
        "checked_hi": checked_hi,          # last n of the contiguous checked prefix (lo-1 if none)
        "complete": checked_hi >= hi,
        "counterexample": counterexample,  # primary says the statement FAILS here (unverified)
        "anomaly": anomaly,                # primary could not decide within its limits
        "seconds": deadline.elapsed() if deadline else None,
        "budget_hit": bool(deadline and deadline.hit() and checked_hi < hi),
        "data": data or {},
        "label": LABEL,
        "proof": False,
    }


# --------------------------------------------------------------------------- Goldbach

GOLDBACH_P = 20_000  # least-prime search bound (observed least primes stay in the hundreds here)

def check_goldbach(lo: int, hi: int, deadline: Deadline) -> dict[str, Any]:
    """Every even n in [lo, hi] (n >= 4) is a sum of two primes.

    Least-prime search p <= GOLDBACH_P; n - p is looked up in a segmented sieve of the window.
    A miss is only a *primary* counterexample — it is re-verified independently by the caller.
    """
    start = max(4, lo + (lo % 2))
    if start > hi:
        return _result(lo, hi, hi, deadline=deadline)
    a = max(2, start - GOLDBACH_P)
    seg = segment_sieve(a, hi)
    small = primes_upto(GOLDBACH_P)
    checked = lo - 1
    max_min_p = 0
    for i, n in enumerate(range(start, hi + 1, 2)):
        if i % 256 == 0 and deadline.hit():
            return _result(lo, hi, checked, data={"max_least_prime": max_min_p}, deadline=deadline)
        found = 0
        for p in small:
            if p > n // 2:
                break
            if seg[n - p - a]:
                found = p
                break
        if not found:
            return _result(lo, hi, n - 1, counterexample=n, data={"max_least_prime": max_min_p}, deadline=deadline)
        max_min_p = max(max_min_p, found)
        checked = min(n + 1, hi)
    return _result(lo, hi, hi, data={"max_least_prime": max_min_p}, deadline=deadline)


def holds_goldbach(n: int) -> bool:
    if n < 4 or n % 2:
        return True  # statement only concerns even n >= 4
    return any(is_prime_mr(p) and is_prime_mr(n - p) for p in range(2, n // 2 + 1))


# --------------------------------------------------------------------------- Collatz

COLLATZ_CAP = 100_000


def check_collatz(lo: int, hi: int, deadline: Deadline) -> dict[str, Any]:
    """Every n in [lo, hi] drops below n (so, inductively from 1, reaches 1).

    Requires every m < lo already verified (the catalog only ever extends contiguously from 1).
    Records the largest stopping time (steps until the value first drops below n).
    """
    checked = lo - 1
    record = (0, 0)
    for n in range(max(lo, 2), hi + 1):
        if (n & 255) == 0 and deadline.hit():
            return _result(lo, hi, checked, data={"max_stopping_time": record[0], "argmax": record[1]}, deadline=deadline)
        x, steps = n, 0
        while x >= n:
            x = x // 2 if x % 2 == 0 else 3 * x + 1
            steps += 1
            if steps > COLLATZ_CAP:
                return _result(lo, hi, n - 1, anomaly=n,
                               data={"max_stopping_time": record[0], "argmax": record[1]}, deadline=deadline)
        if steps > record[0]:
            record = (steps, n)
        checked = n
    return _result(lo, hi, hi, data={"max_stopping_time": record[0], "argmax": record[1]}, deadline=deadline)


def holds_collatz(n: int, cap: int = 10_000_000) -> bool:
    """Independent: full trajectory to 1 (bit ops), much larger cap."""
    x, steps = n, 0
    while x != 1:
        x = (x >> 1) if not (x & 1) else (3 * x + 1)
        steps += 1
        if steps > cap:
            return False
    return True


# --------------------------------------------------------------------------- Legendre

def _first_prime_in(a: int, b: int) -> int:
    """Smallest prime in (a, b) via Miller-Rabin, or 0."""
    m = a + 1
    while m < b:
        if is_prime_mr(m):
            return m
        m += 1
    return 0


def check_legendre(lo: int, hi: int, deadline: Deadline) -> dict[str, Any]:
    """For every n in [lo, hi] (n >= 1) there is a prime strictly between n^2 and (n+1)^2."""
    checked = lo - 1
    max_gap = 0
    for n in range(max(lo, 1), hi + 1):
        if (n & 63) == 0 and deadline.hit():
            return _result(lo, hi, checked, data={"max_first_prime_offset": max_gap}, deadline=deadline)
        p = _first_prime_in(n * n, (n + 1) * (n + 1))
        if not p:
            return _result(lo, hi, n - 1, counterexample=n, data={"max_first_prime_offset": max_gap}, deadline=deadline)
        max_gap = max(max_gap, p - n * n)
        checked = n
    return _result(lo, hi, hi, data={"max_first_prime_offset": max_gap}, deadline=deadline)


def holds_legendre(n: int) -> bool:
    """Independent: segmented sieve of (n^2, (n+1)^2) (no Miller-Rabin)."""
    a, b = n * n + 1, (n + 1) * (n + 1) - 1
    if b < a:
        return False
    return any(segment_sieve(a, b))


# --------------------------------------------------------------------------- Lehmer totient

def check_lehmer_totient(lo: int, hi: int, deadline: Deadline) -> dict[str, Any]:
    """No composite n in [lo, hi] has phi(n) | n - 1 (Lehmer's totient problem).

    Segmented factorisation over the window with primes <= sqrt(hi).
    """
    lo = max(lo, 2)
    if hi < lo:
        return _result(lo, hi, hi, deadline=deadline)
    ps = primes_upto(math.isqrt(hi) + 1)
    size = hi - lo + 1
    rem = list(range(lo, hi + 1))
    phi = list(range(lo, hi + 1))
    for j, p in enumerate(ps):
        if j % 64 == 0 and deadline.hit():
            return _result(lo, hi, lo - 1, deadline=deadline)  # factorisation incomplete → nothing verified
        first = ((lo + p - 1) // p) * p
        for m in range(first, hi + 1, p):
            i = m - lo
            phi[i] = phi[i] // p * (p - 1)
            r = rem[i]
            while r % p == 0:
                r //= p
            rem[i] = r
    for i in range(size):
        if rem[i] > 1:
            q = rem[i]
            phi[i] = phi[i] // q * (q - 1)
    for i in range(size):
        n = lo + i
        if phi[i] != n - 1 and (n - 1) % phi[i] == 0:
            return _result(lo, hi, n - 1, counterexample=n, deadline=deadline)
    return _result(lo, hi, hi, deadline=deadline)


def _phi_trial(n: int) -> int:
    result, m, f = n, n, 2
    while f * f <= m:
        if m % f == 0:
            while m % f == 0:
                m //= f
            result -= result // f
        f += 1
    if m > 1:
        result -= result // m
    return result


def holds_lehmer_totient(n: int) -> bool:
    """Independent: trial-division totient. True when n is NOT a Lehmer counterexample."""
    if n < 2:
        return True
    ph = _phi_trial(n)
    return ph == n - 1 or (n - 1) % ph != 0


# --------------------------------------------------------------------------- Erdős–Straus

ES_X_SPAN = 400


def _factor_small(n: int) -> dict[int, int]:
    out: dict[int, int] = {}
    f = 2
    while f * f <= n:
        while n % f == 0:
            out[f] = out.get(f, 0) + 1
            n //= f
        f += 1
    if n > 1:
        out[n] = out.get(n, 0) + 1
    return out


def _divisors_from(fac: dict[int, int]) -> list[int]:
    ds = [1]
    for p, e in fac.items():
        ds = [d * p ** k for d in ds for k in range(e + 1)]
    return ds


def erdos_straus_triple(n: int, x_span: int = ES_X_SPAN) -> tuple[int, int, int] | None:
    """Some (x, y, z) with 4/n = 1/x + 1/y + 1/z, or None within the search limit."""
    if n == 2:
        return (1, 2, 2)
    for x in range(n // 4 + 1, n // 4 + 1 + x_span):
        a, b = 4 * x - n, n * x
        if a <= 0:
            continue
        g = math.gcd(a, b)
        a, b = a // g, b // g
        # 1/y + 1/z = a/b  ⇔  y = (b + m)/a, z = b(b + m)/(a m) for a divisor m of b^2
        fac = _factor_small(b)
        for m in sorted(_divisors_from({p: 2 * e for p, e in fac.items()})):
            if (b + m) % a or (b * (b + m)) % (a * m):
                continue
            y, z = (b + m) // a, b * (b + m) // (a * m)
            if y > 0 and z > 0:
                return (x, y, z)
    return None


def check_erdos_straus(lo: int, hi: int, deadline: Deadline) -> dict[str, Any]:
    """4/n = 1/x + 1/y + 1/z has a positive solution for every n in [lo, hi] (n >= 2).

    Primes suffice (a solution for p scales to every multiple of p), so the window's primes
    are searched; every certificate is re-checked with exact Fraction arithmetic.
    """
    a = max(2, lo)
    if a > hi:
        return _result(lo, hi, hi, deadline=deadline)
    s = segment_sieve(a, hi)
    checked = lo - 1
    certs = 0
    for n in range(a, hi + 1):
        if (n & 127) == 0 and deadline.hit():
            return _result(lo, hi, checked, data={"certificates": certs}, deadline=deadline)
        if s[n - a]:
            t = erdos_straus_triple(n)
            if t is None:
                return _result(lo, hi, n - 1, anomaly=n, data={"certificates": certs}, deadline=deadline)
            x, y, z = t
            if Fraction(4, n) != Fraction(1, x) + Fraction(1, y) + Fraction(1, z):
                return _result(lo, hi, n - 1, anomaly=n, data={"certificates": certs, "bad_cert": [x, y, z]},
                               deadline=deadline)
            certs += 1
        checked = n
    return _result(lo, hi, hi, data={"certificates": certs}, deadline=deadline)


def holds_erdos_straus(n: int) -> bool:
    """Independent: reduce to a prime factor, wider search, exact Fraction check."""
    if n < 2:
        return True
    p = min(_factor_small(n))
    t = erdos_straus_triple(p, x_span=20 * ES_X_SPAN)
    if t is None:
        return False
    x, y, z = t
    k = n // p
    return Fraction(4, n) == Fraction(1, x * k) + Fraction(1, y * k) + Fraction(1, z * k)


# --------------------------------------------------------------------------- twin primes vs Hardy–Littlewood

TWIN_C2 = 0.6601618158468696  # twin prime constant (numeric constant; used only for the estimate)
TWIN_TOL = 0.05               # flag (never "disprove") when |count/estimate - 1| exceeds this past 1e5


def _li2(x: float, steps: int = 20000) -> float:
    """∫_2^x dt / ln(t)^2 (Simpson)."""
    a, b = 2.0, float(x)
    if b <= a:
        return 0.0
    n = steps if steps % 2 == 0 else steps + 1
    h = (b - a) / n
    f = lambda t: 1.0 / (math.log(t) ** 2)  # noqa: E731
    s = f(a) + f(b) + sum((4 if i % 2 else 2) * f(a + i * h) for i in range(1, n))
    return s * h / 3.0


def twin_pairs_in(lo: int, hi: int) -> int:
    """#{p : lo <= p <= hi - 2, p and p+2 prime} via a segmented sieve."""
    if hi - 2 < max(lo, 3):
        return 0
    a = max(lo, 3)
    seg = segment_sieve(a, hi)
    return sum(1 for p in range(a, hi - 1) if seg[p - a] and seg[p + 2 - a])


def check_twin_hl(lo: int, hi: int, deadline: Deadline, prior_count: int = 0) -> dict[str, Any]:
    """Consistency of π₂(x) with 2·C₂·Li₂(x) at x = hi, counting only the new segment.

    ``prior_count`` is π₂(lo + 1) carried in the catalog (pairs with p <= lo - 1).
    A deviation past TWIN_TOL is flagged as an anomaly — never a counterexample (asymptotic claim).
    """
    seg_count = twin_pairs_in(max(lo - 2, 1), hi)  # p in [lo-2, hi-2]: contiguous with the prior x = lo-1
    cnt = int(prior_count) + seg_count
    est = 2 * TWIN_C2 * _li2(hi)
    ratio = cnt / est if est else 0.0
    data = {"x": hi, "pi2": cnt, "segment_pairs": seg_count, "hl_estimate": round(est, 2), "ratio": round(ratio, 6)}
    if deadline.hit():
        return _result(lo, hi, lo - 1, data=data, deadline=deadline)
    dev = hi >= 100_000 and abs(ratio - 1) > TWIN_TOL
    return _result(lo, hi, hi, anomaly=hi if dev else None, data=data, deadline=deadline)


def twin_pairs_in_mr(lo: int, hi: int) -> int:
    """Independent segment count with Miller-Rabin (no sieve)."""
    return sum(1 for p in range(max(lo, 3) | 1, hi - 1, 2) if is_prime_mr(p) and is_prime_mr(p + 2))


def holds_twin_hl(n: int) -> bool:
    """Single-point form is not meaningful for a counting statement; segment recounts are used."""
    return True


# --------------------------------------------------------------------------- OEIS: colony-fitted recurrence

def _solve(rows: list[list[Fraction]], rhs: list[Fraction]) -> list[Fraction] | None:
    n = len(rhs)
    m = [r[:] + [v] for r, v in zip(rows, rhs)]
    for c in range(n):
        piv = next((r for r in range(c, n) if m[r][c] != 0), None)
        if piv is None:
            return None
        m[c], m[piv] = m[piv], m[c]
        for r in range(n):
            if r != c and m[r][c] != 0:
                f = m[r][c] / m[c][c]
                m[r] = [a - f * b for a, b in zip(m[r], m[c])]
    return [m[i][n] / m[i][i] for i in range(n)]


def fit_recurrence(terms: list[int], order: int) -> list[Fraction] | None:
    """Coefficients c with a(n) = c1 a(n-1) + ... + cd a(n-d) + c0, fitted on the first 2d+1 rows."""
    d = order
    need = 2 * d + 2
    if len(terms) < need + 1:
        return None
    rows, rhs = [], []
    for n in range(d, d + d + 1):
        rows.append([Fraction(terms[n - k]) for k in range(1, d + 1)] + [Fraction(1)])
        rhs.append(Fraction(terms[n]))
    return _solve(rows, rhs)


def predict(terms: list[int], coeffs: list[Fraction], n: int) -> Fraction:
    d = len(coeffs) - 1
    return sum(coeffs[k - 1] * terms[n - k] for k in range(1, d + 1)) + coeffs[d]


def check_oeis_recurrence(terms: list[int], deadline: Deadline, max_order: int = 6,
                          min_unused: int = 6) -> dict[str, Any]:
    """Fit the lowest-order linear recurrence (rational coefficients + constant) on the FIRST terms;
    test it on every later term it never saw. Evidence about OEIS's own listed terms only — the
    OEIS formula text is never parsed or executed."""
    for d in range(1, max_order + 1):
        if deadline.hit():
            break
        c = fit_recurrence(terms, d)
        if c is None:
            continue
        fit_end = 2 * d + 1  # rows d..2d used for the fit → terms[0..2d] seen
        unused = list(range(fit_end + 1, len(terms)))
        if len(unused) < min_unused:
            break
        if all(predict(terms, c, n) == terms[n] for n in range(d, fit_end + 1)) and \
                all(predict(terms, c, n) == terms[n] for n in unused):
            return {"order": d, "coeffs": [str(x) for x in c], "fit_terms": fit_end + 1,
                    "unused_verified": len(unused), "holds": True, "label": LABEL, "proof": False,
                    "seconds": deadline.elapsed()}
    return {"order": None, "holds": False, "unused_verified": 0, "label": LABEL, "proof": False,
            "note": "no low-order recurrence fits (a negative result about the colony's search, not about OEIS)",
            "seconds": deadline.elapsed()}


def reverify_oeis_recurrence(terms: list[int], order: int, coeffs: list[str]) -> bool:
    """Independent: integer cross-multiplied check of every term with the stated coefficients."""
    cs = [Fraction(c) for c in coeffs]
    den = 1
    for c in cs:
        den = den * c.denominator // math.gcd(den, c.denominator)
    ic = [int(c * den) for c in cs]
    for n in range(order, len(terms)):
        lhs = den * terms[n]
        rhs = sum(ic[k - 1] * terms[n - k] for k in range(1, order + 1)) + ic[order]
        if lhs != rhs:
            return False
    return True


FAMILIES = {
    "goldbach": (check_goldbach, holds_goldbach),
    "collatz": (check_collatz, holds_collatz),
    "legendre": (check_legendre, holds_legendre),
    "lehmer_totient": (check_lehmer_totient, holds_lehmer_totient),
    "erdos_straus": (check_erdos_straus, holds_erdos_straus),
    "twin_hl": (check_twin_hl, holds_twin_hl),
}
