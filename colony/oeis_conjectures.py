"""OEIS conjectures as direct colony targets (James 2026-10-23 12:50 PM ET). COLONY_OEIS_CONJ=off|shadow|live.

A mechanism, not a pick:
  * MENU (society/frontier/oeis_conjectures.json, built by tools/build_oeis_conjectures.py from free
    OEIS JSON + b-files): real stated conjectures, each with its source A-number, the EXACT quoted
    OEIS line, the parsed testable form (relation / congruence / inequality / g.f. / property), the
    b-file terms and the b-files of any referenced A-numbers. Entries whose text says the conjecture
    was proved, is true, false or has a counterexample are skipped by the builder.
  * ACTIONS the colony takes on targets it picks from the menu each cycle:
      attempt_disprove  test the parsed form on every available term (b-file; beyond it when the
                        entry's own definition is computable and reproduces the whole b-file);
                        a failure is re-verified by an independent code path (colony.oeis_eval_b:
                        own tokenizer, shunting-yard parser, RPN evaluator, and a fresh b-file
                        fetch / own recomputation of extended terms) before it counts;
      attempt_prove     when the entry's definition is C-finite (rational g.f. or constant-
                        coefficient linear recurrence) and the claim is an identity of C-finite
                        terms or a rational g.f.: a certificate checked by the separate checker
                        colony.proof_check.check_oeis (order bound + finite check / polynomial
                        identity), which uses only path B.
  * CREDIT (selection layer only; never fitness, P, the Oracle, the 0.70 bar, charter, TributeKeeper,
    Ceiling or Athanor): CREDIT_RESOLVE for a counterexample confirmed by both paths beyond the DATA
    range, or a proof accepted by the checker; CREDIT_EXTEND (small, log-scaled) for testing beyond the
    range tested before; 0 otherwise. A failure inside the DATA range (terms the author saw) is
    recorded as 'fails_in_data' (almost always a misparse or an unstated initial condition) and earns
    nothing. Every resolved item is flagged for James's review (society/frontier/OEIS_CONJECTURE_REVIEW.md);
    nothing is authorized, submitted or posted.
  * shadow (code default): attempts run and are reported (society/systems/oeis_conjectures_report.json)
    but no state or credit is kept; live: state, credit and the review flags are written and the
    colony's target choice uses its own past credit.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import random
import re
import time
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

from colony import oeis_eval_b as B

ROOT = Path(__file__).resolve().parent.parent
MENU = ROOT / "society" / "frontier" / "oeis_conjectures.json"
STATE = ROOT / "society" / "systems" / "oeis_conjecture_state.json"
REPORT = ROOT / "society" / "systems" / "oeis_conjectures_report.json"
REVIEW = ROOT / "society" / "frontier" / "OEIS_CONJECTURE_REVIEW.md"
MODES = ("off", "shadow", "live")
PICKS = 4                 # targets per cycle
CREDIT_RESOLVE = 1.0      # verified counterexample or checked proof
CREDIT_EXTEND = 0.05      # max for extending the tested range (log-scaled)
DEEP_N = 20000            # extension cap (terms) when the definition is computable
DEEP_SECONDS = 8.0
DEEP_DIGITS = 3000
GF_TERMS = 1200
MIN_TESTED = 8


def mode() -> str:
    m = os.environ.get("COLONY_OEIS_CONJ", "shadow").strip().lower()
    return m if m in MODES else "shadow"


# ----------------------------------------------------------------------------- normalisation

ALIAS_SEQ = {"A000045": "fib", "A000032": "lucas", "A000203": "sigma", "A000005": "tau", "A000010": "phi",
             "A000040": "prime", "A000142": "fact"}
ALLOWED_NAMES = {"n", "x", "a", "floor", "ilog2", "binomial", "fib", "lucas", "fact", "sigma", "tau", "phi", "prime"}
FUNCS = {"a", "floor", "ilog2", "binomial", "fib", "lucas", "fact", "sigma", "tau", "phi", "prime", "sqrt"}
PROPS = ("prime", "odd", "even", "squarefree", "nonzero", "positive", "composite")
RESOLVED = re.compile(
    r"(conjectur\w*[^.]{0,120}\b(is|are|was|were)\s+(now\s+)?(true|correct|false|incorrect|wrong|proved|proven|confirmed|refuted|disproved))"
    r"|((proved|proven|proof|disproved|refuted|counterexample|counter-example)[^.]{0,80}conjectur)"
    r"|(conjectur\w*[^.]{0,80}(follows?|holds) (easily |immediately )?from)"
    r"|(above conjectur\w* (is|are) (true|correct|incorrect|false))"
    r"|(conjectured,? (in)?correctly|(in)?correctly conjectured|conjecture (verified|confirmed|proved)"
    r"|(was|were|is|are|been) (proved|proven|confirmed|disproved|refuted)|walnut)", re.I)
CONJ = re.compile(r"conjectur", re.I)


class Unparsed(Exception):
    pass


def _strip_attr(s: str) -> str:
    s = re.split(r"\s+-\s+_[A-Z]", s)[0]
    s = re.sub(r"\[\s*Conjectur[^\]]*\]", "", s)
    s = re.sub(r"\(\s*(conjecture[sd]?|conjectured[^)]*)\s*\)", "", s, flags=re.I)
    s = re.sub(r"^\s*(Conjectur\w*)(\s+\d+)?(\s*\([^)]*\))?(\s+from\s+_[^_]+_[^:]*)?\s*:?\s*", "", s)
    s = re.sub(r"^\s*(It is|We) conjecture[d]? that\s+", "", s, flags=re.I)
    s = re.sub(r"^\s*(the sequence is\s+)?(D-finite|P-recursive|holonomic)\s+with\s+(the\s+)?recurrence\s*:?\s*", "", s, flags=re.I)
    s = re.sub(r"\s*\(End\)\s*$", "", s)
    return s.strip().rstrip(".;, ").strip()


def _ins_mul(s: str) -> str:
    tok = re.findall(r"\d+|A\d{6}|[A-Za-z_][A-Za-z0-9_]*|<=|>=|!=|==|\S", s)
    out: list[str] = []
    for t in tok:
        if out:
            p = out[-1]
            p_val = bool(re.fullmatch(r"\d+", p)) or p == ")" or (re.fullmatch(r"[A-Za-z_]\w*", p) and p not in FUNCS
                                                                   and not re.fullmatch(r"A\d{6}", p))
            t_start = bool(re.fullmatch(r"\d+|A\d{6}|[A-Za-z_]\w*", t)) or t == "("
            if p_val and t_start and not (t == "(" and p in FUNCS):
                out.append("*")
        out.append(t)
    return "".join(x if x not in ("<=", ">=", "!=", "==") else x for x in out)


def normalize(text: str) -> dict[str, Any]:
    """Quoted OEIS statement -> testable claim dict, or raise Unparsed(reason)."""
    s = _strip_attr(text)
    s = (s.replace("\u2212", "-").replace("\u2264", "<=").replace("\u2265", ">=").replace("\u2261", "==")
         .replace("\u00d7", "*").replace("\u00b7", "*").replace("\u2260", "!=").replace("\u00a0", " "))
    if not s:
        raise Unparsed("empty")
    m = re.fullmatch(r"(\d+) is the only prime (term )?in (this|the) sequence", s, re.I)
    if m:
        return {"form": "only_prime", "p": int(m.group(1))}
    m = re.fullmatch(r"(?:a\(n\) is (?:always )?|(?:all|every) terms? (?:are|is) (?:)?)(prime|odd|even|squarefree|nonzero|positive|composite)s?"
                     r"(?: numbers?)?(?: for (?:all )?n\s*(>=|>)\s*(\d+))?", s, re.I)
    if m:
        n0 = None if not m.group(2) else int(m.group(3)) + (1 if m.group(2) == ">" else 0)
        return {"form": "property", "prop": m.group(1).lower(), "n0": n0}
    aliases: dict[str, str] = {}
    w = re.search(r",?\s*where\s+(.*)$", s)
    if w:
        rest = w.group(1)
        for mm in re.finditer(r"\b([A-Za-z]\w*)(?:\(n\))?\s*=\s*(A\d{6})(?:\s*\([^)]*\))?", rest):
            aliases[mm.group(1)] = mm.group(2)
        left = re.sub(r"\b([A-Za-z]\w*)(?:\(n\))?\s*=\s*(A\d{6})(?:\s*\([^)]*\))?", "", rest)
        left = re.sub(r"\b(and|that is|i\.e\.)\b|[,.;]", " ", left).strip()
        if left:
            raise Unparsed("where-clause: " + left[:40])
        s = s[:w.start()]
    s = re.sub(r",?\s*with\s+a\(\d+\)\s*=\s*-?\d+((\s*(,|and)\s*)a\(\d+\)\s*=\s*-?\d+)*", "", s)
    n0 = None
    m = re.search(r",?\s*for (?:all )?n\s*(>=|>|=>)\s*(-?\d+)\s*$", s)
    if m:
        n0 = int(m.group(2)) + (1 if m.group(1) == ">" else 0)
        s = s[:m.start()]
    s = re.sub(r",?\s*for (?:all|every) (?:n|integers? n|positive n)\s*$", "", s)
    if re.search(r"\bfor\b|\bif\b|\bwhen\b|\biff\b", s):
        raise Unparsed("conditional")
    mod = None
    m = re.search(r"\(?\s*mod(?:ulo)?\s+(\d+)\s*\)?\s*$", s)
    if m:
        mod = int(m.group(1))
        s = s[:m.start()]
    gf = re.match(r"^(?:Conjectured\s+)?G\.f\.\s*(?:A\(x\)\s*)?(?:=|:)?\s*(.*)$", s)
    for k, v in aliases.items():
        target = ALIAS_SEQ.get(v, v)
        s = re.sub(r"\b%s\(" % re.escape(k), target + "(", s)
    s = re.sub(r"\bfloor\(\s*log_2\(", "ilog2((", s)
    s = re.sub(r"\bFibonacci\(", "fib(", s)
    s = re.sub(r"\bLucas\(", "lucas(", s)
    s = re.sub(r"\bsigma_1\(", "sigma(", s)
    s = re.sub(r"\b(\w)!", r"fact(\1)", s)
    s = re.sub(r"\b(A\d{6})\(", lambda mm: ALIAS_SEQ.get(mm.group(1), mm.group(1)) + "(", s)
    if gf:
        body = _ins_mul(gf.group(1) if gf else s)
        for nm in re.findall(r"[A-Za-z_]\w*", body):
            if nm != "x":
                raise Unparsed("g.f. name " + nm)
        B.rational(B.compile_expr(body))
        return {"form": "gf", "expr": body}
    if re.search(r"[\[\]{}~|!]|\.\.|Sum|Product|lim|Integral|sqrt|log|exp|Pi|round|ceiling|mod|\?", s.replace("!=", "")):
        raise Unparsed("outside grammar")
    s = _ins_mul(s)
    for nm in re.findall(r"[A-Za-z_]\w*", s):
        if nm not in ALLOWED_NAMES and not re.fullmatch(r"A\d{6}", nm):
            raise Unparsed("name " + nm)
    parts, rels = B.split_rel(s)
    if not rels:
        raise Unparsed("no relation")
    if mod is not None and rels != ["=="] and rels != ["="]:
        raise Unparsed("congruence shape")
    for p in parts:
        if not p:
            raise Unparsed("empty side")
        B.compile_expr(p)
    if "a(" not in s:
        raise Unparsed("no a(.)")
    return {"form": "relation", "parts": parts, "rels": ["=" if r == "==" else r for r in rels], "mod": mod, "n0": n0}


def refs(claim: dict[str, Any]) -> list[str]:
    txt = json.dumps(claim)
    return sorted(set(re.findall(r"A\d{6}", txt)))


# ----------------------------------------------------------------------------- path A evaluator (python ast)


class _A:
    def __init__(self, src: str):
        self.tree = ast.parse(src.replace("^", "**"), mode="eval").body
        self._check(self.tree)

    def _check(self, nd):
        ok = (ast.BinOp, ast.UnaryOp, ast.Call, ast.Name, ast.Constant, ast.Add, ast.Sub, ast.Mult, ast.Div,
              ast.Pow, ast.USub, ast.UAdd, ast.Load)
        for x in ast.walk(nd):
            if not isinstance(x, ok):
                raise Unparsed("ast node " + type(x).__name__)
            if isinstance(x, ast.Constant) and not isinstance(x.value, int):
                raise Unparsed("constant")
            if isinstance(x, ast.Call) and not isinstance(x.func, ast.Name):
                raise Unparsed("call")

    def ev(self, nd, n, seq):
        if isinstance(nd, ast.Constant):
            return Fraction(nd.value)
        if isinstance(nd, ast.Name):
            if nd.id == "n":
                return Fraction(n)
            raise B.Bad("name " + nd.id)
        if isinstance(nd, ast.UnaryOp):
            v = self.ev(nd.operand, n, seq)
            return -v if isinstance(nd.op, ast.USub) else v
        if isinstance(nd, ast.BinOp):
            x, y = self.ev(nd.left, n, seq), self.ev(nd.right, n, seq)
            if isinstance(nd.op, ast.Add):
                return x + y
            if isinstance(nd.op, ast.Sub):
                return x - y
            if isinstance(nd.op, ast.Mult):
                return x * y
            if isinstance(nd.op, ast.Div):
                if y == 0:
                    raise B.Bad("div0")
                return x / y
            if y.denominator != 1 or abs(y) > 100000 or (x == 0 and y < 0):
                raise B.Bad("pow")
            if abs(x.numerator) > 1 and abs(int(y)) * math.log2(abs(x.numerator) + 1) > 200000:
                raise B.Bad("pow size")
            return x ** int(y)
        f = nd.func.id
        args = [self.ev(a, n, seq) for a in nd.args]
        for a in args:
            if a.denominator != 1 and f not in ("floor", "ilog2"):
                raise B.Bad("non-integer argument")
        if f == "floor":
            return Fraction(math.floor(args[0]))
        if f == "ilog2":
            v = math.floor(args[0])
            if v < 1:
                raise B.Bad("log")
            return Fraction(int(v).bit_length() - 1)
        if f == "binomial":
            p, q = int(args[0]), int(args[1])
            if q < 0:
                return Fraction(0)
            if p >= 0:
                return Fraction(math.comb(p, q) if q <= p else 0)
            return Fraction((-1) ** q * math.comb(q - p - 1, q))
        i = int(args[0])
        if f == "a" or re.fullmatch(r"A\d{6}", f):
            return Fraction(seq(f, i))
        return Fraction(_builtin_a(f, i))


def _fibA(k: int) -> int:
    if k < 0:
        return (-1) ** (k + 1) * _fibA(-k)
    a, b = 0, 1
    for _ in range(k):
        a, b = b, a + b
    return a


_PRA: list[int] = []


def _builtin_a(f: str, i: int) -> int:
    import sympy
    if f == "fib":
        if abs(i) > 100000:
            raise B.Bad("fib size")
        return _fibA(i)
    if f == "lucas":
        if abs(i) > 100000:
            raise B.Bad("lucas size")
        return _fibA(i - 1) + _fibA(i + 1)
    if f == "fact":
        if not 0 <= i <= 5000:
            raise B.Bad("fact")
        return math.factorial(i)
    if i <= 0:
        raise B.Bad(f + " domain")
    if f == "sigma":
        return int(sympy.divisor_sigma(i))
    if f == "tau":
        return int(sympy.divisor_count(i))
    if f == "phi":
        return int(sympy.totient(i))
    if f == "prime":
        if i > 200000:
            raise B.Bad("prime index")
        return int(sympy.prime(i))
    raise B.Bad("function " + f)


def _prop_ok(prop: str, v: int, path: str) -> bool:
    if prop in ("prime", "composite", "squarefree"):
        if path == "A":
            import sympy
            if prop == "prime":
                return bool(sympy.isprime(v))
            if prop == "composite":
                return v > 1 and not sympy.isprime(v)
            return v != 0 and all(e == 1 for e in sympy.factorint(abs(v)).values()) if abs(v) < 10 ** 30 else True
        if prop == "prime":
            return B.is_prime(v)
        if prop == "composite":
            return v > 1 and not B.is_prime(v)
        return v != 0 and (abs(v) >= 10 ** 12 or all(e == 1 for e in B._factor(abs(v)).values()))
    return {"odd": v % 2 == 1, "even": v % 2 == 0, "nonzero": v != 0, "positive": v > 0}[prop]


# ----------------------------------------------------------------------------- testing


class Tables:
    """Terms by name: 'a' (target) and referenced A-numbers; dict name -> (offset, list[int])."""

    def __init__(self, tabs: dict[str, tuple[int, list[int]]]):
        self.t = tabs

    def get(self, name: str, i: int) -> int:
        if name not in self.t:
            raise B.Missing(name)
        off, xs = self.t[name]
        j = i - off
        if j < 0 or j >= len(xs):
            raise B.Missing(name)
        return xs[j]

    def hi(self, name: str = "a") -> int:
        off, xs = self.t[name]
        return off + len(xs) - 1


def _rel(x: Fraction, y: Fraction, r: str, mod: int | None) -> bool:
    if mod:
        d = x - y
        return d.denominator == 1 and d.numerator % mod == 0
    return {"=": x == y, "<": x < y, "<=": x <= y, ">": x > y, ">=": x >= y, "!=": x != y}[r]


def test_claim(claim: dict[str, Any], T: Tables, path: str = "A", n_max: int | None = None) -> dict[str, Any]:
    """Test the claim at every n where all referenced terms are available.
    Returns tested count, lo/hi n tested, fails (first 5 n with values) and holds_from."""
    off, xs = T.t["a"]
    hi_a = off + len(xs) - 1
    seq = T.get
    tested, lo, hi, fails, undefined = 0, None, None, [], 0
    last_fail = None
    form = claim["form"]
    if form == "gf":
        L = min(len(xs) + off, GF_TERMS)
        if path == "A":
            co = _series_A(claim["expr"], L)
        else:
            num, den = B.rational(B.compile_expr(claim["expr"]))
            co = B.series(num, den, L)
        for n in range(off, L):
            v = T.get("a", n)
            tested += 1
            lo = n if lo is None else lo
            hi = n
            if co[n] != v:
                last_fail = n
                if len(fails) < 5:
                    fails.append({"n": n, "lhs": str(co[n]), "a(n)": str(v)})
        return _summ(tested, lo, hi, fails, last_fail, undefined)
    n0 = claim.get("n0")
    start = off if n0 is None else max(off, n0)
    if form == "relation":
        ev = [(_A(p) if path == "A" else B.compile_expr(p)) for p in claim["parts"]]
        top = 2 * hi_a + 64
    else:
        top = hi_a
    if n_max is not None:
        top = min(top, n_max)
    miss_run = 0
    for n in range(start, top + 1):
        try:
            if form == "relation":
                vals = [(e.ev(e.tree, n, seq) if path == "A" else B.evaluate(e, {"n": n}, seq)) for e in ev]
                ok = all(_rel(vals[i], vals[i + 1], r, claim.get("mod")) for i, r in enumerate(claim["rels"]))
                shown = [str(v) for v in vals]
            elif form == "property":
                v = seq("a", n)
                ok = _prop_ok(claim["prop"], v, path)
                shown = [str(v)]
            elif form == "only_prime":
                v = seq("a", n)
                isp = (B.is_prime(v) if path == "B" else __import__("sympy").isprime(v))
                ok = (not isp) or v == claim["p"]
                shown = [str(v)]
            else:
                raise Unparsed(form)
        except B.Missing:
            miss_run += 1
            if n > hi_a and miss_run > 64:
                break
            continue
        except (B.Bad, ZeroDivisionError, OverflowError, ValueError):
            undefined += 1
            continue
        miss_run = 0
        tested += 1
        lo = n if lo is None else lo
        hi = n
        if not ok:
            last_fail = n
            if len(fails) < 5:
                fails.append({"n": n, "values": [s if len(s) < 80 else s[:38] + "..." + s[-38:] for s in shown]})
    return _summ(tested, lo, hi, fails, last_fail, undefined)


def _summ(tested, lo, hi, fails, last_fail, undefined):
    return {"tested": tested, "lo": lo, "hi": hi, "fails": fails, "first_fail": fails[0]["n"] if fails else None,
            "holds_from": None if last_fail is None else last_fail + 1, "undefined": undefined}


class _Ser:
    def __init__(self, c, L):
        self.c, self.L = (list(c) + [Fraction(0)] * L)[:L], L

    def __add__(self, o):
        o = _ser(o, self.L)
        return _Ser([a + b for a, b in zip(self.c, o.c)], self.L)

    __radd__ = __add__

    def __neg__(self):
        return _Ser([-a for a in self.c], self.L)

    def __sub__(self, o):
        return self + (-_ser(o, self.L))

    def __rsub__(self, o):
        return _ser(o, self.L) - self

    def __mul__(self, o):
        o = _ser(o, self.L)
        r = [Fraction(0)] * self.L
        nz = [(j, b) for j, b in enumerate(o.c) if b]
        for i, a in enumerate(self.c):
            if a:
                for j, b in nz:
                    if i + j >= self.L:
                        break
                    r[i + j] += a * b
        return _Ser(r, self.L)

    __rmul__ = __mul__

    def inv(self):
        if self.c[0] == 0:
            raise B.Bad("series inverse")
        r = [Fraction(0)] * self.L
        r[0] = 1 / self.c[0]
        nz = [(j, b) for j, b in enumerate(self.c) if b and j]
        for i in range(1, self.L):
            s = Fraction(0)
            for j, b in nz:
                if j > i:
                    break
                s += b * r[i - j]
            r[i] = -s / self.c[0]
        return _Ser(r, self.L)


    def sqrt(self):
        """s with s*s = self, s(0) = 1 (squaring recurrence; path B uses the ODE recurrence)."""
        if self.c[0] != 1:
            raise B.Bad("sqrt needs constant term 1")
        r = [Fraction(1)] + [Fraction(0)] * (self.L - 1)
        for n in range(1, self.L):
            t = self.c[n]
            for k in range(1, (n + 1) // 2):
                t -= 2 * r[k] * r[n - k]
            if n % 2 == 0:
                t -= r[n // 2] * r[n // 2]
            r[n] = t / 2
        return _Ser(r, self.L)


def _ser(v, L):
    return v if isinstance(v, _Ser) else _Ser([Fraction(v)], L)


def _series_A(expr: str, L: int) -> list[Fraction]:
    """Path A g.f. expansion: ast walk in truncated series (with an x^k shift for poles at 0)."""
    tree = ast.parse(expr.replace("^", "**"), mode="eval").body
    X = _Ser([0, 1], L + 40)

    def ev(nd):
        if isinstance(nd, ast.Constant):
            return _Ser([Fraction(nd.value)], L + 40)
        if isinstance(nd, ast.Name) and nd.id == "x":
            return X
        if isinstance(nd, ast.UnaryOp):
            v = ev(nd.operand)
            return -v if isinstance(nd.op, ast.USub) else v
        if isinstance(nd, ast.BinOp):
            a, b = ev(nd.left), ev(nd.right)
            if isinstance(nd.op, ast.Add):
                return a + b
            if isinstance(nd.op, ast.Sub):
                return a - b
            if isinstance(nd.op, ast.Mult):
                return a * b
            if isinstance(nd.op, ast.Div):
                k = next((i for i, c in enumerate(b.c) if c), None)
                if k is None:
                    raise B.Bad("div0")
                if any(a.c[:k]):
                    raise B.Bad("pole")
                return _Ser(a.c[k:], a.L) * _Ser(b.c[k:], b.L).inv()
            hx = _half_exp(nd.right) if isinstance(nd.op, ast.Pow) else None
            if hx is not None:
                r = _Ser([1], L + 40)
                rt = a.sqrt()
                for _ in range(abs(hx)):
                    r = r * rt
                return r if hx > 0 else _Ser([1], L + 40) * r.inv()
            if isinstance(nd.op, ast.Pow) and isinstance(nd.right, ast.Constant) and 0 <= nd.right.value <= 64:
                r = _Ser([1], L + 40)
                for _ in range(nd.right.value):
                    r = r * a
                return r
            if (isinstance(nd.op, ast.Pow) and isinstance(nd.right, ast.UnaryOp)
                    and isinstance(nd.right.operand, ast.Constant) and nd.right.operand.value <= 64):
                r = _Ser([1], L + 40)
                for _ in range(nd.right.operand.value):
                    r = r * a
                return _Ser([1], L + 40) * r.inv()
        if (isinstance(nd, ast.Call) and isinstance(nd.func, ast.Name) and nd.func.id == "sqrt"
                and len(nd.args) == 1 and not nd.keywords):
            return ev(nd.args[0]).sqrt()
        raise B.Bad("g.f. node")
    return ev(tree).c[:L]


def _half_exp(nd) -> int | None:
    """k for an exponent written k/2 (k odd, |k| <= 63), e.g. (1/2), (-1/2), (3/2)."""
    sg = 1
    if isinstance(nd, ast.UnaryOp) and isinstance(nd.op, ast.USub):
        sg, nd = -1, nd.operand
    if (isinstance(nd, ast.BinOp) and isinstance(nd.op, ast.Div) and isinstance(nd.left, ast.Constant)
            and isinstance(nd.right, ast.Constant) and nd.right.value == 2 and isinstance(nd.left.value, int)
            and nd.left.value % 2 == 1 and abs(nd.left.value) <= 63):
        return sg * nd.left.value
    return None


# ----------------------------------------------------------------------------- definitions (computable / C-finite)


def parse_definition(name: str) -> dict[str, Any] | None:
    """The entry's own definition, when it is a formula in the grammar:
    'a(n) = <expr>' (possibly recursive in a(n - i)) or 'Expansion of <rational g.f. in x>'."""
    s = re.split(r"[;]|\s+-\s+_", name)[0].strip().rstrip(".")
    s = re.sub(r",?\s*with\s+a\(\d+\)\s*=\s*-?\d+((\s*(,|and)\s*)a\(\d+\)\s*=\s*-?\d+)*\s*$", "", s)
    s = re.sub(r",?\s*(for )?n\s*>=?\s*\d+\s*$", "", s)
    m = re.match(r"^(?:Expansion of\s+(?:g\.f\.\s*)?|G\.f\.:?\s*)(.*)$", s)
    try:
        if m:
            body = _ins_mul(m.group(1).replace("\u2212", "-").replace("Sqrt[", "sqrt(").replace("]", ")"))
            if re.search(r"[A-Za-wyz_]", body.replace("sqrt", "")):
                return None
            if "sqrt" in body or re.search(r"\^\(\s*-?\d+\s*/\s*2\s*\)", body):
                # algebraic (one square root): both series paths must agree on a prefix
                try:
                    a = _series_A(body, 24)
                    b = B.series_expr(B.compile_expr(body), 24)
                    if a != b or any(not isinstance(c, Fraction) or c.denominator != 1 for c in a):
                        return None
                except (B.Bad, ZeroDivisionError, TypeError, AttributeError, ValueError, RecursionError):
                    return None
                return {"kind": "alg", "expr": body}
            num, den = B.rational(B.compile_expr(body))
            return {"kind": "gf", "expr": body}
        m = re.match(r"^a\(n\)\s*=\s*(.*)$", s)
        if not m:
            return None
        body = m.group(1)
        if re.search(r"\bwhere\b|\bfor\b|Sum|Product|\.\.|[\[\]{}]|mod|sqrt|log|=", body):
            return None
        body = re.sub(r"\b(\w)!", r"fact(\1)", body)
        body = re.sub(r"\b(A\d{6})\(", lambda mm: ALIAS_SEQ.get(mm.group(1), mm.group(1)) + "(", body)
        body = _ins_mul(body)
        for nm in re.findall(r"[A-Za-z_]\w*", body):
            if nm not in ALLOWED_NAMES - {"x"}:
                return None
        B.compile_expr(body)
        rec = bool(re.search(r"\ba\(", body))
        lin = None
        if rec:
            try:
                L = B.linear(B.compile_expr(body))
                if all(k is None or isinstance(k, int) for k in L) and L.get(None, 0) == 0:
                    lin = {str(k): str(v) for k, v in L.items() if k is not None}
            except B.Bad:
                lin = None
        return {"kind": "rec" if rec else "closed", "expr": body, "linear": lin}
    except (B.Bad, Unparsed, SyntaxError):
        return None


def extend(defn: dict[str, Any], off: int, terms: list[int], N: int, path: str = "A",
           seconds: float = DEEP_SECONDS) -> list[int] | None:
    """Compute terms from the definition (initial values from the b-file for a recursion), require
    that they reproduce EVERY b-file term, then continue to N terms (time/size capped)."""
    t0 = time.time()
    out: list[int] = []
    if defn["kind"] == "alg":
        return None  # computed through the certified recurrence (colony.oeis_deep.Holo)
    if defn["kind"] == "gf":
        L = min(N, GF_TERMS * 4) + off
        if path == "A":
            co = _series_A(defn["expr"], L)
        else:
            num, den = B.rational(B.compile_expr(defn["expr"]))
            co = B.series(num, den, L)
        if any(c.denominator != 1 for c in co):
            return None
        out = [int(c) for c in co[off:]]
    else:
        e = _A(defn["expr"]) if path == "A" else B.compile_expr(defn["expr"])
        K = 0
        if defn["kind"] == "rec":
            K = max([int(k) for k in (defn.get("linear") or {})] + [0]) or 0
            if not defn.get("linear"):
                K = 8
        for j in range(N):
            n = off + j
            if j < K and j < len(terms):
                out.append(terms[j])
                continue

            def seq(nm, i, _o=out):
                if nm != "a" or i < off or i >= n:
                    raise B.Missing(nm)
                return _o[i - off]
            try:
                v = e.ev(e.tree, n, seq) if path == "A" else B.evaluate(e, {"n": n}, seq)
            except B.Missing:
                if j < len(terms):
                    out.append(terms[j])
                    continue
                return None
            except (B.Bad, ZeroDivisionError, OverflowError, ValueError):
                return None
            if v.denominator != 1:
                return None
            out.append(int(v))
            if j >= len(terms) and (time.time() - t0 > seconds or abs(out[-1]).bit_length() > DEEP_DIGITS * 3.33):
                break
    if len(out) < len(terms) or out[:len(terms)] != terms:
        return None
    return out[:N]


# ----------------------------------------------------------------------------- the two actions


def _tables(e: dict[str, Any], terms: list[int] | None = None) -> Tables:
    tabs = {"a": (e["offset"], terms if terms is not None else e["terms"])}
    for k, v in (e.get("refs") or {}).items():
        tabs[k] = (v["offset"], v["terms"])
    return Tables(tabs)


def _fetch_b(anum: str) -> tuple[int, list[int]] | None:
    """Fresh b-file read for path B (cache or polite network via colony.new_data.Net)."""
    try:
        from colony import new_data as N
        txt = N.Net().get(f"https://oeis.org/{anum}/b{anum[1:]}.txt", f"b{anum[1:]}.txt")
    except Exception:  # noqa: BLE001
        return None
    if not txt:
        return None
    pairs = []
    for ln in txt.splitlines():
        p = ln.split("#")[0].split()
        if len(p) >= 2 and re.fullmatch(r"-?\d+", p[0]) and re.fullmatch(r"-?\d+", p[1]):
            pairs.append((int(p[0]), int(p[1])))
    if not pairs:
        return None
    o = pairs[0][0]
    xs = []
    for i, (k, v) in enumerate(pairs):
        if k != o + i:
            break
        xs.append(v)
    return o, xs


def attempt_disprove(e: dict[str, Any], prior_hi: int | None = None, fetch: bool = True) -> dict[str, Any]:
    claim = e["claim"]
    off, terms = e["offset"], e["terms"]
    data_hi = off + int(e.get("data_n") or 0) - 1
    deep = None
    if e.get("definition") and claim["form"] != "gf":
        deep = extend(e["definition"], off, terms, DEEP_N, "A")
    tA = test_claim(claim, _tables(e, deep or terms), "A")
    res: dict[str, Any] = {"action": "attempt_disprove", "id": e["id"], "anum": e["anum"], "tested": tA["tested"],
                           "range": [tA["lo"], tA["hi"]], "deep_terms": len(deep) if deep else 0,
                           "bfile_terms": len(terms), "bfile_hi": max(off + len(terms) - 1, e.get("published_hi") or 0), "data_hi": data_hi, "status": "holds_on_range"}
    if tA["tested"] < MIN_TESTED:
        res["status"] = "untestable_here"
        return res
    if tA["first_fail"] is None:
        _deep(e, tA, res, deep)
        top = max(tA["hi"] or 0, res.get("deep_hi") or 0)
        res["extended"] = max(0, top - max(prior_hi or 0, data_hi, off + len(terms) - 1))
        return res
    res["fails_A"] = tA["fails"]
    res["holds_from"] = tA["holds_from"]
    if tA["first_fail"] <= data_hi:
        res["status"] = "fails_in_data"   # terms the author saw: a misparse or an unstated initial condition
        return res
    # path B: own parser/evaluator, fresh b-files, own recomputation of any extended terms
    tabs = {}
    fb = _fetch_b(e["anum"]) if fetch else None
    o, xs = fb if fb else (off, terms)
    res["b_source"] = "fresh b-file" if fb else "menu terms (fresh fetch unavailable)"
    if deep and len(deep) > len(xs):
        dB = extend(e["definition"], o, xs, len(deep), "B", seconds=DEEP_SECONDS * 3)
        if dB is None or dB[:len(deep)] != deep[:len(dB)]:
            res["status"] = "path_disagreement"
            return res
        xs = dB
    tabs["a"] = (o, xs[:len(deep or terms)])  # same index range as path A
    for k, v in (e.get("refs") or {}).items():
        fr = _fetch_b(k) if fetch else None
        tabs[k] = fr if fr else (v["offset"], v["terms"])
    tB = test_claim(claim, Tables(tabs), "B")
    res["fails_B"] = tB["fails"]
    if tB["first_fail"] == tA["first_fail"] and tB["fails"][:1] == tA["fails"][:1]:
        res["status"] = "counterexample_verified"
        res["counterexample_n"] = tA["first_fail"]
    else:
        res["status"] = "path_disagreement"
    return res


_GEN_CACHE: dict[str, Any] = {}


def _deep(e: dict[str, Any], tA: dict[str, Any], res: dict[str, Any], deep) -> None:
    """Beyond-b-file search with the fast evaluators (colony.oeis_deep), after the definition has been
    re-checked against the WHOLE b-file. Sets deep_* fields; a failure needs path B to agree."""
    from colony import oeis_deep as D
    from colony import oeis_guess as G
    d = e.get("definition") or {}
    claim = e["claim"]
    if not d or claim["form"] == "gf":
        return
    off, terms = e["offset"], e["terms"]
    key = e["id"]
    if key not in _GEN_CACHE:
        g = None
        if d.get("kind") == "alg":
            cr = G.certified_recurrence(d["expr"], off, terms)
            if cr:
                g = D.Holo(cr, off)
                res["definition_recurrence"] = {"text": cr["text"], "certificate": cr["certificate"]}
        else:
            g = D.generator(e)
        if g is not None and not D.matches_bfile(g, off, terms):
            res["deep_note"] = "definition does not reproduce the b-file; no deep search"
            g = None
        _GEN_CACHE[key] = g
    g = _GEN_CACHE[key]
    if g is None:
        return
    bh = max(off + len(terms) - 1, e.get("published_hi") or 0)   # the published range, even if stored terms stop earlier
    lo = max(tA["hi"] or 0, bh) + 1
    parts = claim.get("parts") or []
    evA = [_A(p) for p in parts]
    evB = [B.compile_expr(p) for p in parts]
    out = D.deep_search(g, claim, lo, DEEP_SECONDS,
                        lambda k, n, sq: evA[k].ev(evA[k].tree, n, sq),
                        lambda k, n, sq: B.evaluate(evB[k], {"n": n}, sq))
    res["deep_mode"] = out.get("mode")
    res["deep_hi"] = out.get("hi")
    if out.get("fail_n") is not None:
        if out.get("path_b"):
            res["status"] = "counterexample_verified"
            res["counterexample_n"] = out["fail_n"]
            res["fails_A"] = [{"n": out["fail_n"], "modulus": out.get("modulus")}]
            res["fails_B"] = [{"n": out["fail_n"], "path": "independent recomputation (Kitamasa / Fraction recurrence)"}]
            res["b_source"] = "recomputed from the definition"
        else:
            res["status"] = "path_disagreement"
        res["deep_fail_n"] = out["fail_n"]


def attempt_prove(e: dict[str, Any]) -> dict[str, Any]:
    from colony import proof_check as PC
    res: dict[str, Any] = {"action": "attempt_prove", "id": e["id"], "anum": e["anum"], "status": "no_method"}
    d = e.get("definition")
    claim = e["claim"]
    if d and d["kind"] in ("gf", "alg") and claim["form"] == "relation" and not claim.get("mod") \
            and claim["rels"] == ["="] and len(claim["parts"]) == 2:
        try:
            PC.holonomic_form(claim["parts"], claim["rels"])
            holo = d["kind"] == "alg" or "n" in re.sub(r"a\([^()]*\)", "", " ".join(claim["parts"]))
        except (ValueError, TypeError, SyntaxError, Exception):  # noqa: BLE001
            holo = False
        if holo:
            cert = {"type": "holonomic_identity", "definition": d, "offset": e["offset"], "claim": claim,
                    "anum": e["anum"], "def_text": e["name"]}
            ok, why = PC.check_oeis(cert, e["terms"])
            res.update({"status": "proved_checked" if ok else "proof_rejected", "checker": why, "cert": cert})
            return res
    if not d or not (d["kind"] == "gf" or (d["kind"] == "rec" and d.get("linear"))):
        res["why"] = "definition is not C-finite or algebraic in the grammar"
        return res
    if claim["form"] == "gf":
        ctype = "gf_identity"
    elif claim["form"] == "relation" and not claim.get("mod") and all(r == "=" for r in claim["rels"]):
        ctype = "cfinite_identity"
    else:
        res["why"] = "claim form has no proof method (%s)" % claim["form"]
        return res
    cert = {"type": ctype, "definition": d, "offset": e["offset"], "claim": claim, "anum": e["anum"],
            "def_text": e["name"]}
    ok, why = PC.check_oeis(cert, e["terms"])
    res.update({"status": "proved_checked" if ok else "proof_rejected", "checker": why, "cert": cert})
    return res


# ----------------------------------------------------------------------------- menu, choice, credit, cycle


def load_menu() -> list[dict[str, Any]]:
    try:
        return json.loads(MENU.read_text()).get("entries") or []
    except (OSError, ValueError):
        return []


def _load(p: Path, default):
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return default


def provable(e: dict[str, Any]) -> bool:
    d = e.get("definition") or {}
    return bool(d) and (d.get("kind") in ("gf", "alg") or bool(d.get("linear"))) and e["claim"]["form"] in ("gf", "relation")


def choose(menu: list[dict[str, Any]], state: dict[str, Any], cycle_id: str, k: int = PICKS) -> list[dict[str, Any]]:
    """The colony's own choice: open targets scored by tractability and its credit history per form
    (a bandit (credit+1)/(attempts+2)), with an exploration bonus for untried targets; sampled
    without replacement with a cycle-seeded rng."""
    tg = state.get("targets", {})
    fam = state.get("families", {})
    rng = random.Random(int(hashlib.sha256(cycle_id.encode()).hexdigest()[:12], 16))
    scored = []
    for e in menu:
        st = tg.get(e["id"], {})
        if st.get("status") in ("counterexample_verified", "proved_checked", "fails_in_data", "untestable_here"):
            continue
        f = fam.get(e["claim"]["form"], {})
        bandit = (f.get("credit", 0.0) + 1.0) / (f.get("attempts", 0) + 2.0)
        tract = 1.0 if provable(e) else (0.8 if e.get("definition") else 0.4)
        fresh = 1.0 / (1 + st.get("attempts", 0))
        scored.append((tract * bandit * (0.25 + fresh) * (0.5 + rng.random()), e))
    scored.sort(key=lambda t: -t[0])
    return [e for _, e in scored[:k]]


def credit_of(res: dict[str, Any], prior_hi: int | None) -> float:
    if res.get("status") in ("counterexample_verified", "proved_checked"):
        return CREDIT_RESOLVE
    if res.get("action") == "attempt_disprove" and res.get("status") == "holds_on_range":
        hi = max((res.get("range") or [0, 0])[1] or 0, res.get("deep_hi") or 0)
        # only range beyond the OEIS b-file (already checked by OEIS contributors) counts as extension
        base = max(prior_hi or 0, res.get("data_hi") or 0, res.get("bfile_hi") or 0, 1)
        if hi > base:
            return round(CREDIT_EXTEND * min(1.0, math.log10(hi / base)), 4)
    return 0.0


def _flag(e: dict[str, Any], res: dict[str, Any], cid: str) -> None:
    if not REVIEW.exists():
        REVIEW.write_text("# OEIS conjecture results for James's review\n\nMachine results only. Nothing here "
                          "has been authorized, submitted to OEIS or posted. Each needs a human check of the "
                          "parse, the b-file and the literature.\n")
    lines = [f"\n## {e['anum']} — {res['status']} (cycle {cid})\n", f"OEIS text ({e['section']}): \"{e['text']}\"\n",
             f"Parsed claim: `{json.dumps(e['claim'])}`\n"]
    if res["status"] == "counterexample_verified":
        lines.append(f"First failure n = {res['counterexample_n']} (both code paths): A {res['fails_A'][:1]} | "
                     f"B {res['fails_B'][:1]}; b-file source for B: {res.get('b_source')}; DATA ends at n = "
                     f"{res['data_hi']}; deep terms {res['deep_terms']}.\n")
    else:
        lines.append(f"Checker: {res.get('checker')}\n")
    with REVIEW.open("a") as fh:
        fh.write("".join(lines))


def _score(state: dict[str, Any], e: dict[str, Any], acts: list[dict[str, Any]]) -> None:
    """Honest scoreboard: (a) counterexamples verified on two code paths, (b) proof_check-accepted proofs,
    (c) entries whose computable definition was checked beyond the published (b-file) range."""
    sb = state.setdefault("scoreboard", {"counterexamples": {}, "proofs": {}, "extensions": {}})
    for r in acts:
        if r["status"] == "counterexample_verified":
            sb["counterexamples"][e["id"]] = {"anum": e["anum"], "n": r.get("counterexample_n")}
        elif r["status"] == "proved_checked":
            routine = (e.get("definition") or {}).get("kind") == "alg"
            sb["proofs"][e["id"]] = {"anum": e["anum"], "checker": (r.get("checker") or "")[:120],
                                     # an algebraic g.f. is D-finite by a classical theorem; proving the stated
                                     # recurrence is a certificate, but the result is known in principle
                                     "routine": routine}
        elif r.get("action") == "attempt_disprove" and r["status"] == "holds_on_range":
            bh = r.get("bfile_hi") or 0
            top_exact = (r.get("range") or [0, 0])[1] or 0
            top = max(top_exact, r.get("deep_hi") or 0)
            if top > bh:
                old = sb["extensions"].get(e["id"], {})
                if top > old.get("to", 0):
                    modular = bool(r.get("deep_hi") and r["deep_hi"] > top_exact and "prime" in (r.get("deep_mode") or ""))
                    sb["extensions"][e["id"]] = {"anum": e["anum"], "bfile_hi": bh, "to": top,
                                                 "check": "modular (two primes)" if modular else "exact"}


def scoreboard(state: dict[str, Any]) -> dict[str, Any]:
    sb = state.get("scoreboard") or {"counterexamples": {}, "proofs": {}, "extensions": {}}
    a, b, c = len(sb["counterexamples"]), len(sb["proofs"]), len(sb["extensions"])
    return {"score": a + b + c, "counterexamples_verified": a, "proofs_checked": b,
            "proofs_routine_known_in_principle": sum(1 for v in sb["proofs"].values() if v.get("routine")),
            "beyond_published_range": c,
            "beyond_exact": sum(1 for v in sb["extensions"].values() if v.get("check") == "exact"),
            "max_depth": max([v["to"] for v in sb["extensions"].values()] or [0])}


def run_cycle(cycle_id: str, fetch: bool = True) -> dict[str, Any] | None:
    m = mode()
    if m == "off":
        return None
    menu = load_menu()
    if not menu:
        return None
    state = _load(STATE, {"targets": {}, "families": {}, "credit_total": 0.0})
    picks = choose(menu, state if m == "live" else {"targets": {}, "families": {}}, cycle_id)
    results = []
    for e in picks:
        st = state["targets"].get(e["id"], {})
        acts = []
        if provable(e):
            acts.append(attempt_prove(e))
        if not acts or acts[-1]["status"] != "proved_checked":
            acts.append(attempt_disprove(e, st.get("tested_hi"), fetch=fetch))
        for r in acts:
            r["credit"] = credit_of(r, st.get("tested_hi"))
            r.pop("cert", None) if r["status"] != "proved_checked" else None
            results.append(r)
        if m == "live":
            fin = next((r for r in acts if r["credit"] >= CREDIT_RESOLVE), acts[-1])
            st["attempts"] = st.get("attempts", 0) + 1
            st["status"] = fin["status"]
            hi = max([max((r.get("range") or [0, 0])[1] or 0, r.get("deep_hi") or 0) for r in acts]
                     + [st.get("tested_hi") or 0])
            st["tested_hi"] = hi
            st["credit"] = round(st.get("credit", 0.0) + sum(r["credit"] for r in acts), 4)
            state["targets"][e["id"]] = st
            f = state["families"].setdefault(e["claim"]["form"], {"attempts": 0, "credit": 0.0})
            f["attempts"] += 1
            f["credit"] = round(f["credit"] + sum(r["credit"] for r in acts), 4)
            state["credit_total"] = round(state.get("credit_total", 0.0) + sum(r["credit"] for r in acts), 4)
            for r in acts:
                if r["status"] in ("counterexample_verified", "proved_checked"):
                    _flag(e, r, cycle_id)
            _score(state, e, acts)
    rep = {"mode": m, "cycle": cycle_id, "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "menu_size": len(menu), "chosen": [{"id": e["id"], "anum": e["anum"], "text": e["text"]} for e in picks],
           "results": results, "scoreboard": scoreboard(state),
           "note": "selection-layer credit only; nothing authorized or posted"}
    hist = _load(REPORT, {"runs": []}).get("runs", [])[-24:]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"runs": hist + [rep]}, indent=1) + "\n")
    if m == "live":
        STATE.write_text(json.dumps(state, indent=1) + "\n")
    return rep
