"""Item 105: reopen OEIS targets that held on the published range only, by widening the
definitions the desk can compute (James 2026-11-16: "Begin that plan. Evolve and expand the swarms").

Three sources, in this order of trust (``provenance`` on every definition):
  * ``name``     the entry's own NAME, parsed by a wider grammar: Sum_{k=a..b} / Product_{k=a..b},
                 binomial, floor / ceiling, n!, Catalan / Fibonacci / Lucas / Motzkin / 2^n aliases,
                 explicit recursions in a(k) with stated initial values. It IS the definition, so
                 it is sound once it reproduces the b-file.
  * ``formula``  a non-conjectural line of the entry's own FORMULA section (fetched text, cached in
                 society/frontier/oeis_formula_cache.json by scripts/item105_fetch_formula_cache.py):
                 a closed form / recursion (same grammar) or a P-recursive (D-finite) recurrence
                 sum_i p_i(n) a(n-i) = 0. Lines that mention a conjecture, an empirical fit,
                 "apparently", or the target's own quoted claim are never used.
  * ``guessed``  colony.oeis_guess.guess_cfinite / guess_holonomic on a prefix of the b-file
                 (overdetermined by SLACK equations), then iterated over the WHOLE stored b-file.
                 HEURISTIC: a guess fitted to the data is not the definition.
Acceptance rule, for every source: both evaluators below reproduce EVERY stored b-file term.
No fetched program (LODA, PROG, Maple, Mathematica) is ever read or run: OEIS text is parsed into
this module's own small AST and evaluated by this module's own code.

Evaluators (path A / path B, used by oeis_conjectures.extend):
  * xexpr: A = recursive evaluator over fractions.Fraction, sums in increasing order;
           B = independent integer-pair rational arithmetic (own gcd normalisation), sums and
           products evaluated in decreasing order.
  * holo:  A = integer recurrence iteration (exact division, a non-integer quotient rejects);
           B = Fraction iteration of the same recurrence.

Honesty labels (oeis_conjectures): only ``name`` definitions count toward the verified scoreboard
(extensions / counterexamples). ``formula`` and ``guessed`` results are recorded as conditional
(``conditional_extensions``, status ``counterexample_conditional``) and earn no selection credit:
a guessed recurrence tested against a conjectured recurrence is circular, and a stated formula is
an author's claim, not the definition.

Switch ``COLONY_OEIS_DEF_WIDEN`` = live (default) | off; always off on the control arm.
``COLONY_OEIS_DEF_GUESS`` = off (default) | live: a guessed recurrence is stored as a candidate but
reopens a target only when this is live (it can only give conditional results).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
FORMULA_CACHE = ROOT / "society" / "frontier" / "oeis_formula_cache.json"
DEFS = ROOT / "society" / "systems" / "oeis_widened_definitions.json"
VERSION = 1
PROV_NAME, PROV_FORMULA, PROV_GUESS = "name", "formula", "guessed"
SOUND = frozenset({PROV_NAME})
KINDS = ("xexpr", "holo")
MAX_SEEDS = 8           # initial values taken from the b-file when the recursion reaches below the offset
MAX_STATED_SEEDS = 64   # "for n > K" stated starting index
MIN_CHECKED = 30        # stored terms past the seeds the definition must reproduce
SUM_CAP = 60000         # one Sum/Product range
EXP_CAP = 200000
FACT_CAP = 30000


def enabled() -> bool:
    try:
        from colony.arm import self_mod_enabled
        if not self_mod_enabled():
            return False
    except Exception:  # noqa: BLE001
        return False
    return (os.environ.get("COLONY_OEIS_DEF_WIDEN") or "live").strip().lower() == "live"


class ParseError(Exception):
    pass


class EvalError(Exception):
    pass


class Missing(Exception):
    pass


class Timeout(Exception):
    pass


# ----------------------------------------------------------------------------- built-in sequences

def _fib(k: int) -> int:
    if k < 0:
        v = _fib(-k)
        return v if (-k) % 2 else -v
    a, b = 0, 1
    for bit in bin(k)[2:]:
        c = a * (2 * b - a)
        d = a * a + b * b
        a, b = (d, c + d) if bit == "1" else (c, d)
    return a


def _lucas(k: int) -> int:
    if k < 0:
        return _lucas(-k) * (1 if k % 2 == 0 else -1)
    return 2 * _fib(k + 1) - _fib(k)


_MOTZ: list[int] = [1, 1]


def _motzkin(k: int) -> int:
    if k < 0:
        raise EvalError("motzkin(<0)")
    if k > FACT_CAP:
        raise EvalError("motzkin cap")
    while len(_MOTZ) <= k:
        m = len(_MOTZ)
        _MOTZ.append(((2 * m + 1) * _MOTZ[m - 1] + (3 * m - 3) * _MOTZ[m - 2]) // (m + 2))
    return _MOTZ[k]


def _binomial(p: int, q: int) -> int:
    if q < 0:
        return 0
    if p < 0:
        return (-1) ** q * math.comb(q - p - 1, q)
    if q > p:
        return 0
    return math.comb(p, q)


def _fact(k: int) -> int:
    if k < 0 or k > FACT_CAP:
        raise EvalError("factorial out of range")
    return math.factorial(k)


def _catalan(k: int) -> int:
    if k < 0 or k > FACT_CAP:
        raise EvalError("catalan out of range")
    return math.comb(2 * k, k) // (k + 1)


INT_FUNCS: dict[str, tuple[int, Callable[..., int]]] = {
    "binomial": (2, _binomial), "fact": (1, _fact), "catalan": (1, _catalan), "fib": (1, _fib),
    "lucas": (1, _lucas), "motzkin": (1, _motzkin), "pow2": (1, lambda k: 2 ** k if 0 <= k <= EXP_CAP else _bad()),
    "cbinom": (1, lambda k: math.comb(2 * k, k) if k >= 0 else 0),
}
FRAC_FUNCS = {"floor": 1, "ceiling": 1}
ALIASES = {
    "A000108": "catalan", "Catalan": "catalan", "catalan": "catalan",
    "A000045": "fib", "Fibonacci": "fib", "fibonacci": "fib", "Fib": "fib",
    "A000032": "lucas", "Lucas": "lucas", "A000142": "fact", "A000079": "pow2",
    "A001006": "motzkin", "Motzkin": "motzkin", "A000984": "cbinom",
    "binomial": "binomial", "Binomial": "binomial", "floor": "floor", "Floor": "floor",
    "ceiling": "ceiling", "Ceiling": "ceiling", "ceil": "ceiling", "fact": "fact", "factorial": "fact",
}


def _bad():
    raise EvalError("out of range")


# ----------------------------------------------------------------------------- text -> AST

_TOK = re.compile(
    r"\s*(?:(?P<sum>(?P<op2>Sum|Product)_\{\s*(?P<v>[a-z])\s*=\s*(?P<lo>[^{}]+?)\s*\.\.\s*(?P<hi>[^{}]+?)\s*\})"
    r"|(?P<num>\d+)|(?P<name>A\d{6}|[A-Za-z][A-Za-z0-9]*)|(?P<op>[-+*/^(),!]))")


def _clean(s: str) -> str:
    s = (s.replace("\u2212", "-").replace("\u00d7", "*").replace("\u00b7", "*").replace("\u00a0", " ")
         .replace("**", "^"))
    return s.strip()


def tokenize(s: str) -> list[tuple[str, Any]]:
    s = _clean(s)
    out: list[tuple[str, Any]] = []
    i = 0
    while i < len(s):
        if s[i].isspace():
            i += 1
            continue
        m = _TOK.match(s, i)
        if not m or m.end() == i:
            raise ParseError("bad character at %d: %r" % (i, s[i:i + 12]))
        if m.group("sum"):
            out.append(("sum", (m.group("op2"), m.group("v"), m.group("lo"), m.group("hi"))))
        elif m.group("num"):
            out.append(("num", int(m.group("num"))))
        elif m.group("name"):
            out.append(("name", m.group("name")))
        else:
            out.append(("op", m.group("op")))
        i = m.end()
    return out


class _Parser:
    def __init__(self, toks: list[tuple[str, Any]], bound: frozenset[str]):
        self.t = toks
        self.i = 0
        self.bound = bound

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else ("eof", None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def expect(self, op: str):
        tok = self.take()
        if tok != ("op", op):
            raise ParseError("expected %r got %r" % (op, tok))

    def parse(self):
        node = self.expr()
        if self.peek()[0] != "eof":
            raise ParseError("trailing %r" % (self.peek(),))
        return node

    def expr(self):
        node = self.term()
        while self.peek() in (("op", "+"), ("op", "-")):
            op = self.take()[1]
            rhs = self.term()
            node = ("add" if op == "+" else "sub", node, rhs)
        return node

    def _starts_atom(self, tok) -> bool:
        return tok[0] in ("num", "name", "sum") or tok == ("op", "(")

    def term(self):
        node = self.unary()
        while True:
            tok = self.peek()
            if tok in (("op", "*"), ("op", "/")):
                self.take()
                rhs = self.unary()
                node = ("mul" if tok[1] == "*" else "div", node, rhs)
            elif self._starts_atom(tok):
                rhs = self.unary()
                node = ("mul", node, rhs)
            else:
                return node

    def unary(self):
        tok = self.peek()
        if tok == ("op", "-"):
            self.take()
            return ("neg", self.unary())
        if tok == ("op", "+"):
            self.take()
            return self.unary()
        if tok[0] == "sum":
            self.take()
            op2, v, lo, hi = tok[1]
            if v == "n" or v in self.bound:
                raise ParseError("rebinding %s" % v)
            lo_n = _Parser(tokenize(lo), self.bound).parse()
            hi_n = _Parser(tokenize(hi), self.bound).parse()
            inner = _Parser(self.t, self.bound | {v})
            inner.i = self.i
            body = inner.term()
            self.i = inner.i
            return ("sum" if op2 == "Sum" else "prod", v, lo_n, hi_n, body)
        return self.power()

    def power(self):
        base = self.postfix()
        if self.peek() == ("op", "^"):
            self.take()
            ex = self.unary()
            return ("pow", base, ex)
        return base

    def postfix(self):
        node = self.atom()
        while self.peek() == ("op", "!"):
            self.take()
            if self.peek() == ("op", "!"):
                raise ParseError("double factorial")
            node = ("call", "fact", [node])
        return node

    def atom(self):
        tok = self.take()
        if tok[0] == "num":
            return ("num", tok[1])
        if tok == ("op", "("):
            node = self.expr()
            self.expect(")")
            return node
        if tok[0] == "name":
            nm = tok[1]
            if nm == "n" or nm in self.bound:
                return ("var", nm)
            if nm == "a" and self.peek() == ("op", "("):
                self.take()
                arg = self.expr()
                self.expect(")")
                return ("a", arg)
            fn = ALIASES.get(nm)
            if fn and self.peek() == ("op", "("):
                self.take()
                args = [self.expr()]
                while self.peek() == ("op", ","):
                    self.take()
                    args.append(self.expr())
                self.expect(")")
                want = INT_FUNCS[fn][0] if fn in INT_FUNCS else FRAC_FUNCS[fn]
                if len(args) != want:
                    raise ParseError("%s takes %d args" % (fn, want))
                return ("call", fn, args)
            raise ParseError("unknown name %r" % nm)
        raise ParseError("unexpected %r" % (tok,))


def parse_expr(s: str) -> Any:
    return _Parser(tokenize(s), frozenset()).parse()


def has_a(node) -> bool:
    if not isinstance(node, tuple):
        return False
    if node[0] == "a":
        return True
    return any(has_a(x) for x in node[1:] if isinstance(x, tuple)) or any(
        has_a(x) for x in (node[2] if node[0] == "call" else []))


# ----------------------------------------------------------------------------- path A (Fraction)

def eval_a(node, env: dict[str, int], seq: Callable[[int], int], deadline: float) -> Fraction:
    k = node[0]
    if k == "num":
        return Fraction(node[1])
    if k == "var":
        return Fraction(env[node[1]])
    if k == "neg":
        return -eval_a(node[1], env, seq, deadline)
    if k in ("add", "sub", "mul", "div"):
        x = eval_a(node[1], env, seq, deadline)
        y = eval_a(node[2], env, seq, deadline)
        if k == "add":
            return x + y
        if k == "sub":
            return x - y
        if k == "mul":
            return x * y
        if y == 0:
            raise EvalError("division by zero")
        return x / y
    if k == "pow":
        x = eval_a(node[1], env, seq, deadline)
        y = eval_a(node[2], env, seq, deadline)
        if y.denominator != 1 or abs(y.numerator) > EXP_CAP:
            raise EvalError("exponent")
        if y < 0 and x == 0:
            raise EvalError("0^-k")
        return x ** int(y)
    if k == "a":
        i = eval_a(node[1], env, seq, deadline)
        if i.denominator != 1:
            raise EvalError("non-integer index")
        return Fraction(seq(int(i)))
    if k == "call":
        vals = [eval_a(x, env, seq, deadline) for x in node[2]]
        fn = node[1]
        if fn == "floor":
            return Fraction(math.floor(vals[0]))
        if fn == "ceiling":
            return Fraction(math.ceil(vals[0]))
        if any(v.denominator != 1 for v in vals):
            raise EvalError("non-integer argument")
        return Fraction(INT_FUNCS[fn][1](*[int(v) for v in vals]))
    if k in ("sum", "prod"):
        _, v, lo, hi, body = node
        a = eval_a(lo, env, seq, deadline)
        b = eval_a(hi, env, seq, deadline)
        if a.denominator != 1 or b.denominator != 1:
            raise EvalError("non-integer bound")
        a, b = int(a), int(b)
        if b - a > SUM_CAP:
            raise EvalError("range cap")
        acc = Fraction(0 if k == "sum" else 1)
        e2 = dict(env)
        for j in range(a, b + 1):
            if (j & 255) == 0 and time.time() > deadline:
                raise Timeout()
            e2[v] = j
            t = eval_a(body, e2, seq, deadline)
            acc = acc + t if k == "sum" else acc * t
        return acc
    raise EvalError("node %r" % (k,))


# ----------------------------------------------------------------------------- path B (int pairs)

def _norm(p: int, q: int) -> tuple[int, int]:
    if q == 0:
        raise EvalError("division by zero")
    if q < 0:
        p, q = -p, -q
    g = math.gcd(p, q)
    return (p // g, q // g) if g > 1 else (p, q)


def _floor_pair(p: int, q: int) -> int:
    return p // q


def eval_b(node, env: dict[str, int], seq: Callable[[int], int], deadline: float) -> tuple[int, int]:
    k = node[0]
    if k == "num":
        return (int(node[1]), 1)
    if k == "var":
        return (int(env[node[1]]), 1)
    if k == "neg":
        p, q = eval_b(node[1], env, seq, deadline)
        return (-p, q)
    if k in ("add", "sub", "mul", "div"):
        p1, q1 = eval_b(node[1], env, seq, deadline)
        p2, q2 = eval_b(node[2], env, seq, deadline)
        if k == "add":
            return _norm(p1 * q2 + p2 * q1, q1 * q2)
        if k == "sub":
            return _norm(p1 * q2 - p2 * q1, q1 * q2)
        if k == "mul":
            return _norm(p1 * p2, q1 * q2)
        if p2 == 0:
            raise EvalError("division by zero")
        return _norm(p1 * q2, q1 * p2)
    if k == "pow":
        p, q = eval_b(node[1], env, seq, deadline)
        ep, eq = eval_b(node[2], env, seq, deadline)
        if eq != 1 or abs(ep) > EXP_CAP:
            raise EvalError("exponent")
        if ep >= 0:
            return (p ** ep, q ** ep)
        if p == 0:
            raise EvalError("0^-k")
        return _norm(q ** (-ep), p ** (-ep))
    if k == "a":
        p, q = eval_b(node[1], env, seq, deadline)
        if q != 1:
            raise EvalError("non-integer index")
        return (int(seq(p)), 1)
    if k == "call":
        vals = [eval_b(x, env, seq, deadline) for x in node[2]]
        fn = node[1]
        if fn == "floor":
            return (_floor_pair(*vals[0]), 1)
        if fn == "ceiling":
            p, q = vals[0]
            return (-((-p) // q), 1)
        if any(q != 1 for _, q in vals):
            raise EvalError("non-integer argument")
        return (int(INT_FUNCS[fn][1](*[p for p, _ in vals])), 1)
    if k in ("sum", "prod"):
        _, v, lo, hi, body = node
        a, aq = eval_b(lo, env, seq, deadline)
        b, bq = eval_b(hi, env, seq, deadline)
        if aq != 1 or bq != 1:
            raise EvalError("non-integer bound")
        if b - a > SUM_CAP:
            raise EvalError("range cap")
        P, Q = (0, 1) if k == "sum" else (1, 1)
        e2 = dict(env)
        for j in range(b, a - 1, -1):      # reverse order: a different summation path
            if (j & 255) == 0 and time.time() > deadline:
                raise Timeout()
            e2[v] = j
            p, q = eval_b(body, e2, seq, deadline)
            P, Q = _norm(P * q + p * Q, Q * q) if k == "sum" else _norm(P * p, Q * q)
        return (P, Q)
    raise EvalError("node %r" % (k,))


# ----------------------------------------------------------------------------- definitions from text

_ATTR = re.compile(r"\s+-\s+_|\s+\[_|\s+\(_|\s+From\s+_")
_COND = re.compile(r"conjectur|empiric|apparent|probabl|seems|guess|it appears|appears to|presumab|"
                   r"numerical|observ|heuristic|\?", re.I)


def _strip_text(s: str) -> str:
    s = _ATTR.split(s)[0].strip()
    s = re.sub(r"\s*\(End\)\s*$", "", s)
    return s.rstrip(" .;,").strip()


def _split_conditions(s: str) -> tuple[str, dict[int, int], int | None]:
    """'<body>, a(0) = 0, a(1) = 1, for n > 4' -> (body, {0: 0, 1: 1}, 5)."""
    init: dict[int, int] = {}
    start: int | None = None
    while True:
        m = re.search(r"(?:,|;|\s)\s*(?:with\s+|and\s+|where\s+)?a\(\s*(-?\d+)\s*\)\s*=\s*(-?\d+)\s*\.?\s*$", s)
        if m:
            init[int(m.group(1))] = int(m.group(2))
            s = s[:m.start()].rstrip(" ,;")
            s = re.sub(r"\s*(,|;)?\s*(with|and)\s*$", "", s)
            continue
        m = re.search(r"(?:,|;|\s)\s*(?:for\s+)?n\s*(>=|>|\u2265)\s*(-?\d+)\s*\.?\s*$", s)
        if m:
            k = int(m.group(2)) + (1 if m.group(1) == ">" else 0)
            start = k if start is None else max(start, k)
            s = s[:m.start()].rstrip(" ,;")
            s = re.sub(r"\s*(,|;)?\s*(for)\s*$", "", s)
            continue
        break
    return s.strip(), init, start


def _xexpr_from(text: str) -> dict[str, Any] | None:
    s = _strip_text(text)
    m = re.search(r"(?:^|:\s*|\s)a\(n\)\s*=\s*(.+)$", s)
    if not m:
        return None
    body, init, start = _split_conditions(m.group(1))
    if "=" in body or not body:
        return None   # chained equalities: only the first form is a definition candidate
    try:
        tree = parse_expr(body)
    except (ParseError, RecursionError):
        return None
    return {"kind": "xexpr", "expr": body, "tree": tree, "init": {str(k): v for k, v in init.items()},
            "start": start, "recursive": has_a(tree)}


def _poly_interp(xs: list[int], ys: list[Fraction]) -> list[Fraction]:
    """Coefficients (ascending) of the interpolating polynomial (Newton form expanded)."""
    n = len(xs)
    coef = list(ys)
    for j in range(1, n):
        for i in range(n - 1, j - 1, -1):
            coef[i] = (coef[i] - coef[i - 1]) / (xs[i] - xs[i - j])
    poly = [Fraction(0)] * n
    for i in range(n - 1, -1, -1):
        # poly = poly * (x - xs[i]) + coef[i]
        new = [Fraction(0)] * n
        for d in range(n - 1):
            new[d + 1] += poly[d]
            new[d] -= poly[d] * xs[i]
        new[0] += coef[i]
        poly = new
    while len(poly) > 1 and poly[-1] == 0:
        poly.pop()
    return poly


def _peval(c: list, n: int):
    v = 0
    for k in range(len(c) - 1, -1, -1):
        v = v * n + c[k]
    return v


def _holo_from(text: str) -> dict[str, Any] | None:
    """'D-finite with recurrence n*a(n) + (3-4n)*a(n-1) = 0' -> polys {lag: [ints ascending]}."""
    s = _strip_text(text)
    s = re.sub(r"^\s*(the sequence (is|satisfies)\s+)?(D-finite|P-recursive|holonomic)\s+(with\s+)?(the\s+)?"
               r"(recurrence|recursion)\s*:?\s*", "", s, flags=re.I)
    s = re.sub(r"^\s*(recurrence|recursion)\s*:?\s*", "", s, flags=re.I)
    body, init, start = _split_conditions(s)
    if body.count("=") != 1:
        return None
    lhs, rhs = body.split("=")
    try:
        L = parse_expr(lhs)
        R = parse_expr(rhs)
    except (ParseError, RecursionError):
        return None
    tree = ("sub", L, R)
    lags: set[int] = set()

    def walk(nd):
        if not isinstance(nd, tuple):
            return
        if nd[0] == "a":
            vals = []
            for nn in (100, 101):
                try:
                    vals.append(eval_a(nd[1], {"n": nn}, lambda i: 0, time.time() + 1))
                except Exception:  # noqa: BLE001
                    raise ParseError("index")
            if vals[1] - vals[0] != 1 or vals[0].denominator != 1:
                raise ParseError("index not n-c")
            lags.add(int(100 - vals[0]))
            if has_a(nd[1]):
                raise ParseError("nested a")
            return
        for x in nd[1:]:
            if isinstance(x, tuple):
                walk(x)
            elif isinstance(x, list):
                for y in x:
                    walk(y)
        if nd[0] in ("sum", "prod"):
            raise ParseError("sum in a recurrence")
    try:
        walk(tree)
    except ParseError:
        return None
    if len(lags) < 2:
        return None
    lo = min(lags)
    D = 14
    samples = list(range(40, 40 + D + 4))
    polys: dict[int, list[Fraction]] = {}
    try:
        base = [eval_a(tree, {"n": nn}, lambda i: 0, time.time() + 2) for nn in samples]
        if any(v != 0 for v in base):
            return None     # inhomogeneous: not a pure P-recursive operator
        for c in sorted(lags):
            ys = []
            for nn in samples:
                ys.append(eval_a(tree, {"n": nn}, (lambda i, _t=nn - c: 1 if i == _t else 0), time.time() + 2))
            # shift to m = n - lo, lag c - lo
            p = _poly_interp([nn - lo for nn in samples[:D]], ys[:D])
            if any(_peval(p, nn - lo) != y for nn, y in zip(samples[D:], ys[D:])):
                return None   # not polynomial of degree < D in n
            polys[c - lo] = p
    except (EvalError, ParseError, ZeroDivisionError, Timeout):
        return None
    if 0 not in polys or not any(polys[0]):
        return None
    den = 1
    for p in polys.values():
        for q in p:
            den = den * q.denominator // math.gcd(den, q.denominator)
    ip = {k: [int(q * den) for q in p] for k, p in polys.items()}
    g = 0
    for p in ip.values():
        for q in p:
            g = math.gcd(g, q)
    if g > 1:
        ip = {k: [q // g for q in p] for k, p in ip.items()}
    return {"kind": "holo", "polys": {str(k): v for k, v in sorted(ip.items())}, "text": body,
            "start": start, "init": {str(k): v for k, v in init.items()}}


# ----------------------------------------------------------------------------- evaluation

def _seed_count_holo(defn: dict[str, Any], off: int) -> int:
    polys = {int(k): v for k, v in defn["polys"].items()}
    r = max(polys)
    s = r
    p0 = polys[0]
    # every n where the leading coefficient vanishes must be a seed
    for j in range(0, MAX_STATED_SEEDS + r + 1):
        if _peval(p0, off + j) == 0:
            s = max(s, j + 1)
    if defn.get("start") is not None:
        s = max(s, int(defn["start"]) - off)
    return s


def holo_terms(defn: dict[str, Any], off: int, seed: list[int], hi: int, path: str, seconds: float,
               bits: int) -> tuple[list[int], str | None]:
    polys = {int(k): v for k, v in defn["polys"].items()}
    rest = [(i, c) for i, c in sorted(polys.items()) if i]
    p0 = polys[0]
    t0 = time.time()
    if path == "A":
        xs = [int(v) for v in seed]
        while off + len(xs) <= hi:
            n = off + len(xs)
            d = _peval(p0, n)
            if d == 0:
                raise EvalError("leading coefficient vanishes at %d" % n)
            s_ = -sum(_peval(c, n) * xs[n - off - i] for i, c in rest)
            if s_ % d:
                raise EvalError("non-integer term")
            xs.append(s_ // d)
            if (n & 63) == 0:
                if abs(xs[-1]).bit_length() > bits:
                    return xs, "digit_cap"
                if time.time() - t0 > seconds:
                    return xs, "time_cap"
        return xs, None
    vals = [Fraction(v) for v in seed]
    while off + len(vals) <= hi:
        n = off + len(vals)
        den = Fraction(sum(Fraction(ck) * n ** k for k, ck in enumerate(p0)))
        if den == 0:
            raise EvalError("leading coefficient vanishes")
        num = Fraction(0)
        for i, c in rest:
            num -= Fraction(sum(ck * n ** k for k, ck in enumerate(c))) * vals[n - off - i]
        v = num / den
        if v.denominator != 1:
            raise EvalError("non-integer term")
        vals.append(v)
        if (n & 63) == 0:
            if abs(v.numerator).bit_length() > bits:
                break
            if time.time() - t0 > seconds:
                break
    return [int(v) for v in vals], None


def xexpr_terms(defn: dict[str, Any], off: int, terms: list[int], want: int, path: str, seconds: float,
                bits: int) -> tuple[list[int], str | None]:
    tree = defn.get("tree") or parse_expr(defn["expr"])
    init = {int(k): int(v) for k, v in (defn.get("init") or {}).items()}
    start = defn.get("start")
    deadline = time.time() + seconds
    out: list[int] = []
    seeds_used = 0
    for j in range(want):
        n = off + j
        if n in init:
            out.append(init[n])
            continue
        if start is not None and n < int(start):
            if j >= len(terms) or j >= MAX_STATED_SEEDS:
                raise EvalError("stated start beyond the stored terms")
            out.append(int(terms[j]))
            continue

        def seq(i, _n=n):
            if i >= _n:
                raise EvalError("self reference a(%d) at n=%d" % (i, _n))
            if i < off:
                raise Missing(i)
            return out[i - off]
        try:
            if path == "A":
                v = eval_a(tree, {"n": n}, seq, deadline)
                if v.denominator != 1:
                    raise EvalError("non-integer term at %d" % n)
                out.append(int(v))
            else:
                p, q = eval_b(tree, {"n": n}, seq, deadline)
                if q != 1:
                    raise EvalError("non-integer term at %d" % n)
                out.append(int(p))
        except Missing:
            if j < len(terms) and seeds_used < MAX_SEEDS and j == len(out) and j < MAX_SEEDS:
                out.append(int(terms[j]))
                seeds_used += 1
                continue
            raise EvalError("needs a value below the offset")
        except Timeout:
            return out, "time_cap"
        if j >= len(terms) and abs(out[-1]).bit_length() > bits:
            return out, "digit_cap"
        if j >= len(terms) and time.time() > deadline:
            return out, "time_cap"
    return out, None


def seeds_of(defn: dict[str, Any], off: int) -> int:
    if defn.get("kind") == "holo":
        return _seed_count_holo(defn, off)
    st = defn.get("start")
    return max(0, int(st) - off) if st is not None else 0


def extend_widened(defn: dict[str, Any], off: int, terms: list[int], want: int, path: str, seconds: float,
                   bits: int) -> tuple[list[int] | None, str | None]:
    """Terms off..off+want-1 from a widened definition, or (None, None) when it does not apply.
    The caller still checks the stored terms against the prefix."""
    try:
        if defn.get("kind") == "holo":
            s = _seed_count_holo(defn, off)
            if s > MAX_STATED_SEEDS or s >= len(terms):
                return None, None
            init = {int(k): int(v) for k, v in (defn.get("init") or {}).items()}
            seed = [init.get(off + j, terms[j]) for j in range(s)]
            xs, cap = holo_terms(defn, off, seed, off + want - 1, path, seconds, bits)
            return xs[:want], cap
        if defn.get("kind") == "xexpr":
            xs, cap = xexpr_terms(defn, off, terms, want, path, seconds, bits)
            return xs, cap
    except (EvalError, ParseError, ZeroDivisionError, OverflowError, RecursionError, ValueError, KeyError):
        return None, None
    return None, None


def reproduces(defn: dict[str, Any], off: int, terms: list[int], seconds: float = 20.0) -> tuple[bool, str]:
    """Both paths reproduce EVERY stored term, with at least MIN_CHECKED terms past the seeds."""
    terms = [int(t) for t in terms]
    if len(terms) - seeds_of(defn, off) < MIN_CHECKED:
        return False, "too few checked terms past the seeds"
    for path in ("A", "B"):
        got, cap = extend_widened(defn, off, terms, len(terms), path, seconds, 10 ** 9)
        if got is None:
            return False, "path %s does not evaluate" % path
        if cap is not None or len(got) < len(terms):
            return False, "path %s stopped at %s before the end of the b-file" % (path, cap)
        if got[:len(terms)] != terms:
            bad = next(i for i, (x, y) in enumerate(zip(got, terms)) if x != y)
            return False, "path %s differs at n=%d" % (path, off + bad)
    return True, "both paths reproduce all %d stored terms" % len(terms)


# ----------------------------------------------------------------------------- candidates per entry

def load_formula_cache() -> dict[str, Any]:
    try:
        return json.loads(FORMULA_CACHE.read_text())
    except (OSError, ValueError):
        return {"entries": {}}


def _norm_text(s: str) -> str:
    return re.sub(r"\s+", "", _clean(s)).lower()


def candidates(e: dict[str, Any], cache: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Text candidates in trust order: NAME first, then non-conjectural FORMULA lines."""
    out: list[dict[str, Any]] = []
    name = str(e.get("name") or "")
    for part in re.split(r";\s+|\.\s+(?=[A-Z])", name)[:2]:
        d = _xexpr_from(part)
        if d:
            d["provenance"], d["source"] = PROV_NAME, part[:300]
            out.append(d)
            break
    cache = cache if cache is not None else load_formula_cache()
    row = (cache.get("entries") or {}).get(str(e.get("anum") or "")) or {}
    claim_txt = _norm_text(str(e.get("text") or ""))
    in_block = False
    for line in row.get("formula") or []:
        low = line.lower()
        if "(start)" in low and _COND.search(line):
            in_block = True
        if in_block:
            if "(end)" in low:
                in_block = False
            continue
        if _COND.search(line):
            continue
        core = _norm_text(_strip_text(line))
        if not core or (claim_txt and (core in claim_txt or claim_txt.find(core[:40]) >= 0)):
            continue
        d = _holo_from(line) if re.search(r"D-finite|recurrence|recursion|=\s*0\s*\.?", line, re.I) else None
        if d is None:
            d = _xexpr_from(line)
        if d is None:
            d = _holo_from(line)
        if d:
            d["provenance"], d["source"] = PROV_FORMULA, _strip_text(line)[:300]
            out.append(d)
    return out


def guess(e: dict[str, Any], prefix: int = 160) -> list[dict[str, Any]]:
    from colony import oeis_guess as G
    off = int(e.get("offset") or 0)
    terms = [int(t) for t in e.get("terms") or []]
    xs = terms[:prefix]
    out = []
    try:
        c = G.guess_cfinite(xs)
    except Exception:  # noqa: BLE001
        c = None
    if c:
        den = 1
        for q in c:
            den = den * q.denominator // math.gcd(den, q.denominator)
        polys = {"0": [den]}
        for i, q in enumerate(c, 1):
            if q:
                polys[str(i)] = [int(-q * den)]
        out.append({"kind": "holo", "polys": polys, "text": "C-finite guess (order %d)" % len(c),
                    "provenance": PROV_GUESS, "source": "oeis_guess.guess_cfinite on %d terms" % len(xs)})
    try:
        g = G.guess_holonomic(xs, off)
    except Exception:  # noqa: BLE001
        g = None
    if g:
        out.append({"kind": "holo", "polys": {str(k): list(v) for k, v in g["polys"].items()},
                    "text": G.recurrence_text(g) + " = 0", "provenance": PROV_GUESS,
                    "source": "oeis_guess.guess_holonomic (order %d, degree %d) on %d terms"
                              % (g["order"], g["degree"], len(xs))})
    return out


def claim_is_recurrence(e: dict[str, Any]) -> bool:
    """True when a recurrence fitted to the b-file would test the claim circularly: the claim is a
    relation / g.f. in a(.) and n only (a recurrence, a closed form or a g.f. identity), which a guessed
    operator matching the same data satisfies by construction or by the same fitting."""
    claim = e.get("claim") or {}
    form = str(claim.get("form") or "")
    if re.search(r"D-finite|recurrence", str(e.get("text") or ""), re.I):
        return True
    if form not in ("relation", "gf"):
        return False
    txt = " ".join(str(p) for p in claim.get("parts") or []) + " " + str(claim.get("expr") or "")
    names = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", txt)) - {"a", "n", "x", "floor", "binomial", "fact"}
    return not names


def terms_sha(e: dict[str, Any]) -> str:
    h = hashlib.sha256(json.dumps([e.get("offset"), e.get("terms")], separators=(",", ":")).encode())
    return h.hexdigest()[:16]


def source_sha(e: dict[str, Any], cache: dict[str, Any] | None = None) -> str:
    """Hash of the text the candidates come from (NAME, claim text and cached FORMULA lines)."""
    cache = cache if cache is not None else load_formula_cache()
    row = (cache.get("entries") or {}).get(str(e.get("anum") or "")) or {}
    blob = json.dumps([e.get("name"), e.get("text"), row.get("formula") or []], separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def public_defn(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if k != "tree"}


def find_definition(e: dict[str, Any], cache: dict[str, Any] | None = None, seconds: float = 20.0,
                    use_guess: bool = True) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """The first candidate (trust order) that reproduces the whole stored b-file, plus the reject log."""
    off = int(e.get("offset") or 0)
    terms = [int(t) for t in e.get("terms") or []]
    tried: list[dict[str, Any]] = []
    cands = candidates(e, cache)
    if use_guess and not claim_is_recurrence(e):
        cands += guess(e)
    elif use_guess:
        tried.append({"provenance": PROV_GUESS, "kind": "holo", "source": "", "ok": False,
                      "why": "skipped: the claim is itself a recurrence, so a recurrence fitted to the same "
                             "data would test it circularly"})
    for d in cands:
        ok, why = reproduces(d, off, terms, seconds)
        tried.append({"provenance": d["provenance"], "kind": d["kind"], "source": d.get("source", "")[:160],
                      "ok": ok, "why": why})
        if ok:
            acc = public_defn(d)
            acc["verified"] = why
            acc["sound"] = d["provenance"] in SOUND
            return acc, tried
    return None, tried


# ----------------------------------------------------------------------------- persistent table

def load_defs() -> dict[str, Any]:
    try:
        return json.loads(DEFS.read_text())
    except (OSError, ValueError):
        return {"version": VERSION, "entries": {}}


_MEMO: dict[str, Any] = {}


def definition_for(e: dict[str, Any]) -> dict[str, Any] | None:
    """Accepted widened definition for a menu entry (read-only), or None. Treatment only."""
    if not enabled():
        return None
    if "table" not in _MEMO:
        _MEMO["table"] = load_defs()
    row = (_MEMO["table"].get("entries") or {}).get(str(e.get("id") or ""))
    if not row or row.get("terms_sha") != terms_sha(e) or not row.get("definition"):
        return None
    d = dict(row["definition"])
    if d.get("provenance") == PROV_GUESS and not guesses_reopen():
        return None   # recorded as a candidate, but a fitted guess does not reopen a target by default
    return d


def guesses_reopen() -> bool:
    """COLONY_OEIS_DEF_GUESS = off (default) | live: let a guessed recurrence reopen a target."""
    return (os.environ.get("COLONY_OEIS_DEF_GUESS") or "off").strip().lower() == "live"


def build(menu: list[dict[str, Any]], only: set[str] | None = None, seconds: float = 20.0,
          cache: dict[str, Any] | None = None) -> dict[str, Any]:
    """Recompute the table for entries without a menu definition. Deterministic (same menu, same cache)."""
    table = load_defs()
    entries = table.setdefault("entries", {})
    cache = cache if cache is not None else load_formula_cache()
    for e in menu:
        eid = str(e.get("id") or "")
        if e.get("definition") or (only is not None and eid not in only):
            continue
        sha = terms_sha(e)
        src = source_sha(e, cache)
        old = entries.get(eid)
        if old and old.get("terms_sha") == sha and old.get("version") == VERSION and old.get("source_sha") == src:
            continue
        d, tried = find_definition(e, cache, seconds)
        entries[eid] = {"anum": e.get("anum"), "terms_sha": sha, "source_sha": src, "version": VERSION,
                        "definition": d, "tried": tried[:12]}
    table["version"] = VERSION
    table["note"] = ("Item 105 widened definitions. Accepted only when both evaluators reproduce every "
                     "stored b-file term. provenance name = sound; formula / guessed = conditional.")
    _MEMO.pop("table", None)
    return table


def save_defs(table: dict[str, Any]) -> None:
    DEFS.parent.mkdir(parents=True, exist_ok=True)
    DEFS.write_text(json.dumps(table, indent=1, sort_keys=True) + "\n")
    _MEMO.pop("table", None)


def refresh(menu: list[dict[str, Any]], budget_s: float = 20.0) -> int:
    """In-loop: try entries never tried (new supply), one at a time, within a time budget. Treatment only."""
    if not enabled():
        return 0
    entries = load_defs().get("entries") or {}
    todo = [e for e in menu if not e.get("definition")
            and (entries.get(str(e.get("id") or ""), {}).get("terms_sha") != terms_sha(e))]
    if not todo:
        return 0
    t0 = time.time()
    done = 0
    for e in todo:
        left = budget_s - (time.time() - t0)
        if left <= 1.0:
            break
        save_defs(build(menu, only={str(e.get("id") or "")}, seconds=min(10.0, left)))
        done += 1
    return done


# ----------------------------------------------------------------------------- deep-search generator

def holo_gen(defn: dict[str, Any], off: int, terms: list[int]):
    """oeis_deep.Holo-compatible generator for a widened P-recursive definition (seeds may exceed the order)."""
    from colony import oeis_deep as D
    s = _seed_count_holo(defn, off)
    if s > MAX_STATED_SEEDS or s >= len(terms):
        return None
    init = {int(k): int(v) for k, v in (defn.get("init") or {}).items()}
    seed = [init.get(off + j, int(terms[j])) for j in range(s)]
    g = D.Holo.__new__(D.Holo)
    from colony import oeis_guess as G
    g.G = G
    g.polys = {int(k): list(v) for k, v in defn["polys"].items()}
    g.r = max(g.polys)
    g.s0 = off
    g.seed = seed
    g.start = off + len(seed)
    return g


# ----------------------------------------------------------------------------- honesty labels

def label_result(defn: dict[str, Any] | None, res: dict[str, Any]) -> dict[str, Any]:
    """Mark an attempt that used a widened definition. Only a sound (NAME) definition can count."""
    if not defn or defn.get("kind") not in KINDS:
        return res
    prov = str(defn.get("provenance") or "")
    res["definition_provenance"] = prov
    res["definition_source"] = str(defn.get("source") or "")[:200]
    if prov in SOUND:
        return res
    res["conditional"] = True
    if res.get("status") == "counterexample_verified":
        res["status"] = "counterexample_conditional"
        res["conditional_why"] = ("the terms past the b-file come from a %s definition, not the entry's own "
                                  "definition; needs a human check" % prov)
    return res
