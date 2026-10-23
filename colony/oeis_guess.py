"""Guessers for OEIS data (HEURISTIC: a guess is only a candidate until proof_check certifies it).

guess_cfinite   - Berlekamp-Massey over Q: shortest constant-coefficient recurrence fitting the data,
                  accepted as a guess only if it is overdetermined by >= SLACK extra terms.
guess_holonomic - smallest (order, degree) polynomial-coefficient recurrence sum_i p_i(n) a(n-i) = 0
                  whose solution space on the data is one-dimensional with >= SLACK spare equations.
certified_recurrence - guess from an algebraic/rational definition's own series, then run
                  proof_check.check_holonomic (sound); only a certified result is used for computation."""
from __future__ import annotations

from fractions import Fraction
from typing import Any

SLACK = 12


def guess_cfinite(xs: list[int], max_order: int = 30) -> list[Fraction] | None:
    """Berlekamp-Massey; returns c with a(n) = sum c[i-1] a(n-i), or None."""
    s = [Fraction(v) for v in xs]
    C, Bp = [Fraction(1)], [Fraction(1)]
    L, m, b = 0, 1, Fraction(1)
    for n in range(len(s)):
        d = s[n] + sum(C[i] * s[n - i] for i in range(1, L + 1))
        if d == 0:
            m += 1
            continue
        T = C[:]
        coef = d / b
        C = C + [Fraction(0)] * max(0, len(Bp) + m - len(C))
        for i, v in enumerate(Bp):
            C[i + m] -= coef * v
        if 2 * L <= n:
            L, Bp, b, m = n + 1 - L, T, d, 1
        else:
            m += 1
    if L == 0 or L > max_order or len(s) < 2 * L + SLACK:
        return None
    return [-C[i] for i in range(1, L + 1)]


def _nullspace(rows: list[list[Fraction]], ncols: int) -> list[list[Fraction]]:
    A = [r[:] for r in rows]
    piv, r = [], 0
    for c in range(ncols):
        p = next((i for i in range(r, len(A)) if A[i][c] != 0), None)
        if p is None:
            continue
        A[r], A[p] = A[p], A[r]
        inv = 1 / A[r][c]
        A[r] = [v * inv for v in A[r]]
        for i in range(len(A)):
            if i != r and A[i][c] != 0:
                f = A[i][c]
                A[i] = [x - f * y for x, y in zip(A[i], A[r])]
        piv.append(c)
        r += 1
        if r == len(A):
            break
    free = [c for c in range(ncols) if c not in piv]
    basis = []
    for fc in free:
        v = [Fraction(0)] * ncols
        v[fc] = Fraction(1)
        for i, pc in enumerate(piv):
            v[pc] = -A[i][fc]
        basis.append(v)
    return basis


def guess_holonomic(xs: list[int], off: int, max_order: int = 4, max_deg: int = 4) -> dict[str, Any] | None:
    """{'order', 'degree', 'polys': {i: [c0, c1, ...]}} (p_i(n) = sum c_k n^k), or None."""
    for tot in range(1, max_order + max_deg + 1):
        for r in range(1, max_order + 1):
            d = tot - r
            if d < 0 or d > max_deg:
                continue
            nun = (r + 1) * (d + 1)
            rows = []
            for j in range(r, len(xs)):
                n = off + j
                rows.append([Fraction(n ** k * xs[j - i]) for i in range(r + 1) for k in range(d + 1)])
            if len(rows) < nun + SLACK:
                continue
            ns = _nullspace(rows, nun)
            if len(ns) != 1:
                continue
            v = ns[0]
            den = 1
            for q in v:
                den = den * q.denominator // __import__("math").gcd(den, q.denominator)
            v = [int(q * den) for q in v]
            g = 0
            for q in v:
                g = __import__("math").gcd(g, q)
            v = [q // g for q in v] if g else v
            polys = {i: v[i * (d + 1):(i + 1) * (d + 1)] for i in range(r + 1)}
            if not any(polys[0]) or not any(polys[r]):
                continue
            return {"order": r, "degree": d, "polys": polys}
    return None


def _pstr(c: list[int]) -> str:
    t = []
    for k, v in enumerate(c):
        if v:
            t.append("(%d)" % v + ("*n^%d" % k if k else ""))
    return "+".join(t) or "0"


def recurrence_text(g: dict[str, Any]) -> str:
    return "+".join("(%s)*a(n%s)" % (_pstr(c), "-%d" % i if i else "") for i, c in g["polys"].items() if any(c))


def certified_recurrence(def_expr: str, off: int, terms: list[int], S: int = 140) -> dict[str, Any] | None:
    """Guess a recurrence from the definition's own series and certify it with proof_check."""
    from colony import oeis_eval_b as B
    from colony import proof_check as PC
    try:
        ser = B.series_expr(B.compile_expr(def_expr), off + S)
    except B.Bad:
        return None
    if any(c.denominator != 1 for c in ser):
        return None
    xs = [int(c) for c in ser[off:]]
    g = guess_holonomic(xs, off) or guess_holonomic(xs, off, max_order=6, max_deg=6)
    if g is None:
        return None
    txt = recurrence_text(g)
    n0 = off + g["order"]
    ok, why = PC.check_holonomic(def_expr, off, [txt, "0"], ["="], n0, terms)
    if not ok:
        return None
    return {"polys": g["polys"], "order": g["order"], "text": txt + " = 0", "n0": n0, "certificate": why,
            "seed": xs[:max(g["order"], 1) + 64]}


def peval(c: list[int], n: int) -> int:
    v = 0
    for k in range(len(c) - 1, -1, -1):
        v = v * n + c[k]
    return v
