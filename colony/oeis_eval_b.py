"""Second, independent evaluator for OEIS conjecture statements (code path B).

colony.oeis_conjectures normalises a quoted OEIS statement into a small canonical text grammar
  numbers, n, x, + - * / ^, parentheses, a(.), A######(.), floor, ilog2, binomial, fib, lucas, fact,
  sigma, tau, phi, prime
and evaluates it with a Python-ast walker (path A). This module re-parses the SAME canonical text
with its own tokenizer and shunting-yard parser into reverse Polish notation and evaluates the RPN
with its own arithmetic helpers (path B). A counterexample earns credit only when both paths agree,
and the proof checker (colony.proof_check.check_oeis) uses only this path. No network, no state.
"""
from __future__ import annotations

import math
import re
from fractions import Fraction
from typing import Any, Callable

FUNCS1 = {"a", "floor", "ilog2", "fib", "lucas", "fact", "sigma", "tau", "phi", "prime", "sqrt"}
FUNCS2 = {"binomial"}
_TOK = re.compile(r"\s*(?:(\d+)|(A\d{6})|([a-z][a-z0-9]*)|(<=|>=|!=|==|[-+*/^(),=<>]))")
PREC = {"+": 1, "-": 1, "*": 2, "/": 2, "neg": 3, "^": 4}
RIGHT = {"^", "neg"}


class Missing(Exception):
    """A referenced term is outside the available range."""


class Bad(Exception):
    """The text is outside the grammar."""


def tokens(s: str) -> list[tuple[str, str]]:
    out, i = [], 0
    s = s.strip()
    while i < len(s):
        m = _TOK.match(s, i)
        if not m or m.end() == i:
            raise Bad("token at %d: %r" % (i, s[i:i + 8]))
        i = m.end()
        num, anum, name, op = m.groups()
        if num is not None:
            out.append(("num", num))
        elif anum is not None:
            out.append(("seq", anum))
        elif name is not None:
            out.append(("name", name))
        else:
            out.append(("op", op))
    return out


def rpn(toks: list[tuple[str, str]]) -> list[tuple[str, Any]]:
    """Shunting-yard. Functions are ('fn', name, argc); sequences ('fn', 'A######', 1)."""
    out: list[tuple[str, Any]] = []
    ops: list[Any] = []
    argc: list[int] = []
    prev = None  # None / 'val' / 'op' / '(' / ','
    for k, (t, v) in enumerate(toks):
        if t == "num":
            out.append(("num", int(v)))
            prev = "val"
        elif t == "seq" or (t == "name" and v in FUNCS1 | FUNCS2):
            if k + 1 >= len(toks) or toks[k + 1] != ("op", "("):
                raise Bad("function without '(': " + v)
            ops.append(("fn", v))
            prev = "fn"
        elif t == "name":
            if v not in ("n", "x"):
                raise Bad("unknown name " + v)
            out.append(("var", v))
            prev = "val"
        elif v == "(":
            if prev == "val":
                raise Bad("implicit multiplication")
            if ops and isinstance(ops[-1], tuple) and ops[-1][0] == "fn" and prev == "fn":
                argc.append(1)
                ops.append("(f")
            else:
                ops.append("(")
            prev = "("
        elif v == ",":
            while ops and ops[-1] not in ("(", "(f"):
                out.append(("op", ops.pop()))
            if not ops or ops[-1] != "(f":
                raise Bad("comma outside call")
            argc[-1] += 1
            prev = ","
        elif v == ")":
            while ops and ops[-1] not in ("(", "(f"):
                out.append(("op", ops.pop()))
            if not ops:
                raise Bad("unbalanced )")
            top = ops.pop()
            if top == "(f":
                fn = ops.pop()
                out.append(("fn", fn[1], argc.pop()))
            prev = "val"
        elif v in PREC:
            op = v
            if v == "-" and prev in (None, "(", ",", "op"):
                op = "neg"
            elif v == "+" and prev in (None, "(", ",", "op"):
                prev = "op"
                continue
            elif prev not in ("val",):
                raise Bad("operator position")
            while ops and ops[-1] in PREC and (PREC[ops[-1]] > PREC[op] or
                                               (PREC[ops[-1]] == PREC[op] and op not in RIGHT)):
                out.append(("op", ops.pop()))
            ops.append(op)
            prev = "op"
        else:
            raise Bad("relation inside expression: " + v)
    while ops:
        o = ops.pop()
        if o in ("(", "(f"):
            raise Bad("unbalanced (")
        out.append(("op", o))
    for t in out:
        if t[0] == "fn":
            want = 2 if t[1] in FUNCS2 else 1
            if t[2] != want:
                raise Bad("arity " + t[1])
    return out


def split_rel(s: str) -> tuple[list[str], list[str]]:
    """Split canonical text at top-level relations into parts and relations."""
    parts, rels, depth, cur, i = [], [], 0, "", 0
    while i < len(s):
        c = s[i]
        two = s[i:i + 2]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        if depth == 0 and two in ("<=", ">=", "!=", "=="):
            parts.append(cur)
            rels.append(two)
            cur, i = "", i + 2
            continue
        if depth == 0 and c in "=<>":
            parts.append(cur)
            rels.append(c)
            cur, i = "", i + 1
            continue
        cur += c
        i += 1
    parts.append(cur)
    return [p.strip() for p in parts], rels


# ----------------------------------------------------------------------------- arithmetic


def _int(v: Fraction) -> int:
    if v.denominator != 1:
        raise Bad("non-integer argument")
    return v.numerator


def _fib_pair(k: int) -> tuple[int, int]:
    if k == 0:
        return 0, 1
    f, g = _fib_pair(k // 2)
    c = f * (2 * g - f)
    d = f * f + g * g
    return (d, c + d) if k % 2 else (c, d)


def fib(k: int) -> int:
    if k < 0:
        return (-1) ** (k + 1) * fib(-k)
    return _fib_pair(k)[0]


def lucas(k: int) -> int:
    if k < 0:
        return (-1) ** k * lucas(-k)
    f, g = _fib_pair(k)
    return 2 * g - f


def _factor(m: int) -> dict[int, int]:
    out, p = {}, 2
    while p * p <= m:
        while m % p == 0:
            out[p] = out.get(p, 0) + 1
            m //= p
        p += 1 if p == 2 else 2
    if m > 1:
        out[m] = out.get(m, 0) + 1
    return out


def sigma(m: int) -> int:
    if m <= 0:
        raise Bad("sigma domain")
    r = 1
    for p, e in _factor(m).items():
        r *= (p ** (e + 1) - 1) // (p - 1)
    return r


def tau(m: int) -> int:
    if m <= 0:
        raise Bad("tau domain")
    r = 1
    for e in _factor(m).values():
        r *= e + 1
    return r


def phi(m: int) -> int:
    if m <= 0:
        raise Bad("phi domain")
    r = m
    for p in _factor(m):
        r = r // p * (p - 1)
    return r


def is_prime(m: int) -> bool:
    if m < 2:
        return False
    if m < 4:
        return True
    if m % 2 == 0:
        return False
    # deterministic Miller-Rabin for m < 3.3e24, probabilistic-strong bases beyond
    d, s = m - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for b in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41):
        if b % m == 0:
            continue
        x = pow(b, d, m)
        if x in (1, m - 1):
            continue
        for _ in range(s - 1):
            x = x * x % m
            if x == m - 1:
                break
        else:
            return False
    return True


_PR: list[int] = [2]


def prime(k: int) -> int:
    if k < 1 or k > 200000:
        raise Bad("prime index")
    c = _PR[-1]
    while len(_PR) < k:
        c += 1
        if is_prime(c):
            _PR.append(c)
    return _PR[k - 1]


def binomial(p: int, q: int) -> int:
    if q < 0 or p < 0 or q > p:
        if p < 0 <= q:
            return (-1) ** q * math.comb(q - p - 1, q)
        return 0
    return math.comb(p, q)


def evaluate(code: list[tuple[str, Any]], env: dict[str, Any], seq: Callable[[str, int], int]) -> Fraction:
    """Evaluate RPN. env: {'n': int}. seq(name, i) returns a term (name 'a' or 'A######') or raises Missing."""
    st: list[Fraction] = []
    for t in code:
        if t[0] == "num":
            st.append(Fraction(t[1]))
        elif t[0] == "var":
            if t[1] not in env:
                raise Bad("free variable " + t[1])
            st.append(Fraction(env[t[1]]))
        elif t[0] == "op":
            o = t[1]
            if o == "neg":
                st.append(-st.pop())
                continue
            y, x = st.pop(), st.pop()
            if o == "+":
                st.append(x + y)
            elif o == "-":
                st.append(x - y)
            elif o == "*":
                st.append(x * y)
            elif o == "/":
                if y == 0:
                    raise Bad("division by zero")
                st.append(x / y)
            else:
                e = _int(y)
                if abs(e) > 100000 or (x == 0 and e < 0):
                    raise Bad("power")
                if abs(x.numerator) > 1 and abs(e) * math.log2(abs(x.numerator) + 1) > 200000:
                    raise Bad("power too large")
                st.append(x ** e)
        else:
            name, k = t[1], t[2]
            args = [st.pop() for _ in range(k)][::-1]
            if name == "binomial":
                st.append(Fraction(binomial(_int(args[0]), _int(args[1]))))
                continue
            v = args[0]
            if name == "sqrt":
                raise Bad("sqrt outside a g.f.")
            if name == "floor":
                st.append(Fraction(v.numerator // v.denominator))
            elif name == "ilog2":
                f = v.numerator // v.denominator
                if f < 1:
                    raise Bad("log domain")
                st.append(Fraction(f.bit_length() - 1))
            elif name == "a" or name.startswith("A"):
                st.append(Fraction(seq(name, _int(v))))
            else:
                i = _int(v)
                fn = {"fib": fib, "lucas": lucas, "sigma": sigma, "tau": tau, "phi": phi, "prime": prime,
                      "fact": lambda m: math.factorial(m) if 0 <= m <= 5000 else (_ for _ in ()).throw(Bad("fact"))}[name]
                st.append(Fraction(fn(i)))
    if len(st) != 1:
        raise Bad("stack")
    return st[0]


def compile_expr(s: str) -> list[tuple[str, Any]]:
    return rpn(tokens(s))


# ----------------------------------------------------------------------------- polynomial / series domains


def _padd(p, q, sign=1):
    r = [Fraction(0)] * max(len(p), len(q))
    for i, c in enumerate(p):
        r[i] += c
    for i, c in enumerate(q):
        r[i] += sign * c
    while len(r) > 1 and r[-1] == 0:
        r.pop()
    return r


def _pmul(p, q):
    r = [Fraction(0)] * (len(p) + len(q) - 1)
    for i, c in enumerate(p):
        if c:
            for j, d in enumerate(q):
                r[i + j] += c * d
    while len(r) > 1 and r[-1] == 0:
        r.pop()
    return r


def rational(code: list[tuple[str, Any]]) -> tuple[list[Fraction], list[Fraction]]:
    """Evaluate RPN in x as a rational function (num, den) with polynomial coefficient lists.
    Only numbers, x, + - * / and integer powers. Not reduced (callers cross-multiply)."""
    st: list[tuple[list[Fraction], list[Fraction]]] = []
    one = [Fraction(1)]
    for t in code:
        if t[0] == "num":
            st.append(([Fraction(t[1])], one))
        elif t[0] == "var":
            if t[1] != "x":
                raise Bad("rational: variable " + t[1])
            st.append(([Fraction(0), Fraction(1)], one))
        elif t[0] == "op":
            o = t[1]
            if o == "neg":
                p, q = st.pop()
                st.append(([-c for c in p], q))
                continue
            (p2, q2), (p1, q1) = st.pop(), st.pop()
            if o in "+-":
                st.append((_padd(_pmul(p1, q2), _pmul(p2, q1), 1 if o == "+" else -1), _pmul(q1, q2)))
            elif o == "*":
                st.append((_pmul(p1, p2), _pmul(q1, q2)))
            elif o == "/":
                if all(c == 0 for c in p2):
                    raise Bad("rational: division by zero")
                st.append((_pmul(p1, q2), _pmul(q1, p2)))
            else:
                if len(p2) != 1 or q2 != one or p2[0].denominator != 1:
                    raise Bad("rational: exponent")
                e = p2[0].numerator
                if not 0 <= abs(e) <= 64:
                    raise Bad("rational: exponent size")
                p, q = (p1, q1) if e >= 0 else (q1, p1)
                rp, rq = one, one
                for _ in range(abs(e)):
                    rp, rq = _pmul(rp, p), _pmul(rq, q)
                st.append((rp, rq))
        else:
            raise Bad("rational: function " + str(t[1]))
    if len(st) != 1:
        raise Bad("stack")
    return st[0]


def series(num: list[Fraction], den: list[Fraction], L: int) -> list[Fraction]:
    """First L power-series coefficients of num/den (den must not vanish at a common x^k factor)."""
    k = 0
    while k < len(den) and den[k] == 0:
        k += 1
    if k == len(den):
        raise Bad("zero denominator")
    if any(c != 0 for c in num[:k]):
        raise Bad("pole at 0")
    num, den = num[k:], den[k:]
    out: list[Fraction] = []
    for i in range(L):
        s = num[i] if i < len(num) else Fraction(0)
        for j in range(1, min(i, len(den) - 1) + 1):
            s -= den[j] * out[i - j]
        out.append(s / den[0])
    return out


def _smul(a: list[Fraction], b: list[Fraction], L: int) -> list[Fraction]:
    r = [Fraction(0)] * L
    bz = [(j, y) for j, y in enumerate(b[:L]) if y]
    for i, x in enumerate(a[:L]):
        if x:
            for j, y in bz:
                if i + j >= L:
                    break
                r[i + j] += x * y
    return r


def _sdiv(a: list[Fraction], b: list[Fraction], L: int) -> list[Fraction]:
    """a / b by long division of coefficients (b[0] != 0)."""
    if b[0] == 0:
        raise Bad("series division")
    q: list[Fraction] = []
    bz = [(j, y) for j, y in enumerate(b[:L]) if y and j]
    for i in range(L):
        s = a[i] if i < len(a) else Fraction(0)
        for j, y in bz:
            if j > i:
                break
            s -= y * q[i - j]
        q.append(s / b[0])
    return q


def _ssqrt(c: list[Fraction], L: int) -> list[Fraction]:
    """sqrt of a series with c[0] = 1, from the first-order ODE  C s' = (1/2) C' s  (s(0) = 1):
    (n+1) s_{n+1} = (1/2) sum_k (k+1) c_{k+1} s_{n-k} - sum_{k>=1} c_k (n-k+1) s_{n-k+1}."""
    if not c or c[0] != 1:
        raise Bad("sqrt needs constant term 1")
    c = (list(c) + [Fraction(0)] * (L + 1))[:L + 1]
    cz = [(k, ck) for k, ck in enumerate(c) if ck and k]
    s = [Fraction(1)]
    for n in range(L - 1):
        t = Fraction(0)
        for k, ck in cz:
            if k - 1 <= n:
                t += Fraction(k, 2) * ck * s[n - k + 1]
            if 1 <= k <= n:
                t -= ck * (n - k + 1) * s[n - k + 1]
        s.append(t / (n + 1))
    return s[:L]


def series_expr(code: list[tuple[str, Any]], L: int) -> list[Fraction]:
    """First L coefficients of an algebraic g.f. in RPN: numbers, x, + - * /, integer powers,
    p^(k/2) and sqrt(p) with p(0) = 1. Poles at 0 are not allowed (no x^-k shifts)."""
    W = L + 8
    st: list[Any] = []
    for t in code:
        if t[0] == "num":
            st.append(("c", Fraction(t[1])))
        elif t[0] == "var":
            if t[1] != "x":
                raise Bad("series: variable")
            st.append(("s", [Fraction(0), Fraction(1)] + [Fraction(0)] * (W - 2)))
        elif t[0] == "fn":
            if t[1] != "sqrt":
                raise Bad("series: function " + t[1])
            st.append(("s", _ssqrt(_as(st.pop(), W), W)))
        else:
            o = t[1]
            if o == "neg":
                k, v = st.pop()
                st.append((k, -v if k == "c" else [-z for z in v]))
                continue
            y, x = st.pop(), st.pop()
            if x[0] == "c" and y[0] == "c":
                if o == "^":
                    if y[1].denominator != 1 or abs(y[1]) > 64:
                        raise Bad("series: constant power")
                    st.append(("c", x[1] ** int(y[1])))
                else:
                    st.append(("c", {"+": x[1] + y[1], "-": x[1] - y[1], "*": x[1] * y[1],
                                     "/": x[1] / y[1] if y[1] else None}[o]))
                    if st[-1][1] is None:
                        raise Bad("division by zero")
                continue
            if o == "^":
                if y[0] != "c" or y[1].denominator not in (1, 2) or abs(y[1]) > 64:
                    raise Bad("series: exponent")
                e = y[1]
                base = _as(x, W)
                if e.denominator == 2:
                    base = _ssqrt(base, W)
                    e = e * 2
                k = int(abs(e))
                r = [Fraction(1)] + [Fraction(0)] * (W - 1)
                for _ in range(k):
                    r = _smul(r, base, W)
                if e < 0:
                    r = _sdiv([Fraction(1)], r, W)
                st.append(("s", r))
                continue
            a, b = _as(x, W), _as(y, W)
            if o == "+":
                st.append(("s", [u + v for u, v in zip(a, b)]))
            elif o == "-":
                st.append(("s", [u - v for u, v in zip(a, b)]))
            elif o == "*":
                st.append(("s", _smul(a, b, W)))
            else:
                k = 0
                while k < W and b[k] == 0:
                    k += 1
                if k == W or any(a[:k]):
                    raise Bad("series: pole")
                st.append(("s", _sdiv(a[k:] + [Fraction(0)] * k, b[k:] + [Fraction(0)] * k, W)))
    if len(st) != 1:
        raise Bad("stack")
    return _as(st[0], W)[:L]


def _as(v, W):
    return v[1] if v[0] == "s" else [v[1]] + [Fraction(0)] * (W - 1)


def poly_eq(p: list[Fraction], q: list[Fraction]) -> bool:
    return all(c == 0 for c in _padd(p, q, -1))


def pmul(p, q):
    return _pmul(p, q)


# ----------------------------------------------------------------------------- linear forms


def linear(code: list[tuple[str, Any]]) -> dict[Any, Fraction]:
    """Evaluate RPN as a constant-coefficient linear form in a(n - i): {i: coef, None: constant}.
    Raises Bad if not linear with constant coefficients (no n outside the a(n - i) indices)."""
    st: list[Any] = []
    for t in code:
        if t[0] == "num":
            st.append(("c", Fraction(t[1])))
        elif t[0] == "var":
            if t[1] != "n":
                raise Bad("linear: variable")
            st.append(("n", None))
        elif t[0] == "op":
            o = t[1]
            if o == "neg":
                k, v = st.pop()
                if k == "c":
                    st.append(("c", -v))
                elif k == "L":
                    st.append(("L", {i: -c for i, c in v.items()}))
                elif k == "i":
                    st.append(("i", (-v[0], -v[1])))
                else:
                    st.append(("i", (Fraction(-1), Fraction(0))))
                continue
            (k2, v2), (k1, v1) = st.pop(), st.pop()
            idx = {"n": (Fraction(1), Fraction(0))}

            def asidx(k, v):
                if k == "n":
                    return (Fraction(1), Fraction(0))
                if k == "c":
                    return (Fraction(0), v)
                if k == "i":
                    return v
                return None
            del idx
            i1, i2 = asidx(k1, v1), asidx(k2, v2)
            if i1 is not None and i2 is not None and o in "+-":
                s = 1 if o == "+" else -1
                r = (i1[0] + s * i2[0], i1[1] + s * i2[1])
                st.append(("c", r[1]) if r[0] == 0 else ("i", r))
                continue
            if k1 == "c" and k2 == "c":
                if o == "^":
                    st.append(("c", v1 ** _int(v2)))
                else:
                    st.append(("c", {"+": v1 + v2, "-": v1 - v2, "*": v1 * v2,
                                     "/": v1 / v2 if v2 else (_ for _ in ()).throw(Bad("div0"))}[o]))
                continue

            def asL(k, v):
                if k == "L":
                    return v
                if k == "c":
                    return {None: v}
                raise Bad("linear: n outside an index")
            if o in "+-":
                a1, a2 = asL(k1, v1), asL(k2, v2)
                r = dict(a1)
                for i, c in a2.items():
                    r[i] = r.get(i, Fraction(0)) + (c if o == "+" else -c)
                st.append(("L", r))
            elif o == "*" and (k1 == "c" or k2 == "c"):
                c, L = (v1, asL(k2, v2)) if k1 == "c" else (v2, asL(k1, v1))
                st.append(("L", {i: c * w for i, w in L.items()}))
            elif o == "/" and k2 == "c" and v2 != 0:
                st.append(("L", {i: w / v2 for i, w in asL(k1, v1).items()}))
            else:
                raise Bad("linear: nonlinear operation")
        else:
            if t[1] != "a":
                raise Bad("linear: function " + t[1])
            k, v = st.pop()
            if k != "i" or v[0] != 1:
                raise Bad("linear: index must be n - i")
            sh = -v[1]
            if sh.denominator != 1 or sh <= 0:
                raise Bad("linear: index must be n - i, i >= 1")
            st.append(("L", {int(sh): Fraction(1)}))
    if len(st) != 1:
        raise Bad("stack")
    k, v = st[0]
    if k == "c":
        return {None: v}
    if k != "L":
        raise Bad("linear: not a form")
    return v
