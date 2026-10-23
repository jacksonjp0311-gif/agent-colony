"""Fast evaluators for searching OEIS conjectures beyond the b-file (colony/oeis_conjectures.py).

For a C-finite definition (rational g.f. or constant-coefficient linear recurrence, re-checked against
the whole b-file before use):
  path A  iter_mod / iter_exact: plain forward iteration of the recurrence (residues or integers);
  path B  kitamasa: a(n) from x^m mod the characteristic polynomial (binary powering), a different
          algorithm, used to recompute every term a claimed counterexample touches.
Claims are tested on residues only when that is sound: the claim must be a ring expression in the
terms (a(.) never inside floor / ilog2 / binomial / an exponent / a denominator), so the value of
every side is congruent to its value on residues. Then
  * a congruence mod m is decided exactly by residues mod m (holds and fails);
  * an identity '=' FAILS for sure when a difference is nonzero modulo a prime; it only 'holds mod p'
    otherwise (reported as a modular check, never as exact verification).
Inequalities and properties (prime, positive, ...) use exact integers (digit-capped)."""
from __future__ import annotations

import time
from fractions import Fraction
from typing import Any

from colony import oeis_eval_b as B

P1 = (1 << 61) - 1
P2 = (1 << 31) - 1
MAX_N = 10 ** 7
EXACT_BITS = 40000


class NotCFinite(Exception):
    pass


def cfinite(defn: dict[str, Any] | None, off: int, terms: list[int]) -> dict[str, Any]:
    """{'s0', 'seed', 'c'}: a(t) = sum_i c[i-1] a(t-i) for t >= s0 + len(seed); seed = a(s0 ..)."""
    if not defn:
        raise NotCFinite("no definition")
    if defn["kind"] == "gf":
        num, den = B.rational(B.compile_expr(defn["expr"]))
        while len(den) > 1 and den[-1] == 0:
            den = den[:-1]
        while len(num) > 1 and num[-1] == 0:
            num = num[:-1]
        k = 0
        while den[k] == 0:
            k += 1
        num, den = num[k:], den[k:]
        K = len(den) - 1
        if K == 0:
            raise NotCFinite("polynomial")
        R = max(len(num), K)
        seed = B.series(num, den, R)
        c = [-den[i] / den[0] for i in range(1, K + 1)]
        return {"s0": 0, "seed": seed, "c": c}
    lin = defn.get("linear")
    if defn["kind"] != "rec" or not lin:
        raise NotCFinite("not a constant-coefficient recurrence")
    lin = {int(k): Fraction(v) for k, v in lin.items()}
    K = max(lin)
    if len(terms) < K:
        raise NotCFinite("short")
    return {"s0": off, "seed": [Fraction(v) for v in terms[:K]], "c": [lin.get(i, Fraction(0)) for i in range(1, K + 1)]}


def _modf(v: Fraction, M: int) -> int:
    if v.denominator % M == 0 if M > 1 else False:
        raise ZeroDivisionError("denominator divisible by modulus")
    return v.numerator * pow(v.denominator, -1, M) % M if v.denominator != 1 else v.numerator % M


def iter_mod(cf: dict[str, Any], hi: int, M: int, seconds: float = 1e9) -> list[int]:
    """Path A: residues of a(s0), ..., a(hi) mod M by forward iteration."""
    seed = [_modf(v, M) for v in cf["seed"]]
    c = [_modf(v, M) for v in cf["c"]]
    K = len(c)
    xs = seed[:]
    t0 = time.time()
    nz = [(i + 1, ci) for i, ci in enumerate(c) if ci]
    while cf["s0"] + len(xs) <= hi:
        L = len(xs)
        xs.append(sum(ci * xs[L - i] for i, ci in nz) % M)
        if (L & 4095) == 0 and time.time() - t0 > seconds:
            break
    return xs


def iter_exact(cf: dict[str, Any], hi: int, seconds: float = 1e9, bits: int = EXACT_BITS) -> list[int]:
    seed = list(cf["seed"])
    c = list(cf["c"])
    if any(v.denominator != 1 for v in c + seed):
        xs = seed
        integral = False
    else:
        xs = [int(v) for v in seed]
        c = [int(v) for v in c]
        integral = True
    nz = [(i + 1, ci) for i, ci in enumerate(c) if ci]
    t0 = time.time()
    while cf["s0"] + len(xs) <= hi:
        L = len(xs)
        v = sum(ci * xs[L - i] for i, ci in nz)
        xs.append(v)
        if (L & 255) == 0 and (time.time() - t0 > seconds or abs(int(v)).bit_length() > bits):
            break
    if not integral:
        if any(Fraction(v).denominator != 1 for v in xs):
            raise NotCFinite("non-integer terms")
        xs = [int(v) for v in xs]
    return xs


def _polymulmod(p, q, chi_c, M):
    K = len(chi_c)
    r = [0] * (2 * K - 1)
    for i, a in enumerate(p):
        if a:
            for j, b in enumerate(q):
                if b:
                    r[i + j] += a * b
    for d in range(len(r) - 1, K - 1, -1):  # x^K = sum_i c_i x^(K-i)
        v = r[d]
        if v:
            r[d] = 0
            for i, ci in enumerate(chi_c, 1):
                r[d - i] += v * ci
        if M:
            r[d - 1] %= M
    r = r[:K]
    return [v % M for v in r] if M else r


def kitamasa(cf: dict[str, Any], n: int, M: int | None = None):
    """Path B: a(n) (mod M if given; exact otherwise) by x^m mod chi."""
    s0, seed, c = cf["s0"], cf["seed"], cf["c"]
    K, L = len(c), len(seed)
    if n < s0:
        raise B.Missing("a")
    if n - s0 < L:
        v = seed[n - s0]
        return _modf(v, M) if M else v
    T = s0 + L - K
    base = [seed[L - K + j] for j in range(K)]
    if M:
        cc = [_modf(v, M) for v in c]
        base = [_modf(v, M) for v in base]
    else:
        cc = list(c)
    m = n - T
    res = [1] + [0] * (K - 1)
    pw = [0, 1] + [0] * (K - 2) if K > 1 else [cc[0] % M if M else cc[0]]
    while m:
        if m & 1:
            res = _polymulmod(res, pw, cc, M)
        m >>= 1
        if m:
            pw = _polymulmod(pw, pw, cc, M)
    v = sum(r * b for r, b in zip(res, base))
    if M:
        return v % M
    v = Fraction(v)
    return v


def ring_safe(code) -> bool:
    """True when every a(.) value enters the expression only through + - * and positive integer
    powers with an a-free exponent (so residues give the residue of the value)."""
    st: list[bool] = []
    for t in code:
        if t[0] in ("num", "var"):
            st.append(False)
        elif t[0] == "op":
            if t[1] == "neg":
                continue
            y, x = st.pop(), st.pop()
            if t[1] == "/" and y:
                return False
            if t[1] == "^" and y:
                return False
            st.append(x or y)
        else:
            args = [st.pop() for _ in range(t[2])]
            if t[1] == "a" or t[1].startswith("A"):
                if args[0]:
                    return False  # a(a(n)): the index needs the exact value
                st.append(True)
            elif any(args):
                return False
            else:
                st.append(False)
    return len(st) == 1


class Holo:
    """A certified polynomial-coefficient recurrence (oeis_guess.certified_recurrence) as a generator."""

    def __init__(self, cert: dict[str, Any], off: int):
        from colony import oeis_guess as G
        self.G = G
        self.polys = {int(k): v for k, v in cert["polys"].items()}
        self.r = max(self.polys)
        self.s0 = off
        self.seed = list(cert["seed"])[:self.r]
        self.start = off + self.r

    def exact(self, hi: int, seconds: float = 1e9, bits: int = EXACT_BITS) -> list[int]:
        xs = list(self.seed)
        p0 = self.polys[0]
        rest = [(i, c) for i, c in self.polys.items() if i]
        t0 = time.time()
        while self.s0 + len(xs) <= hi:
            n = self.s0 + len(xs)
            d = self.G.peval(p0, n)
            if d == 0:
                break
            s_ = -sum(self.G.peval(c, n) * xs[n - self.s0 - i] for i, c in rest)
            if s_ % d:
                raise NotCFinite("non-integer term from recurrence")
            xs.append(s_ // d)
            if (n & 127) == 0 and (time.time() - t0 > seconds or abs(xs[-1]).bit_length() > bits):
                break
        return xs

    def mod(self, M: int, hi: int, seconds: float = 1e9) -> list[int]:
        xs = [v % M for v in self.seed]
        p0 = self.polys[0]
        rest = [(i, c) for i, c in self.polys.items() if i]
        t0 = time.time()
        while self.s0 + len(xs) <= hi:
            n = self.s0 + len(xs)
            d = self.G.peval(p0, n) % M
            if d == 0:
                break
            s_ = -sum(self.G.peval(c, n) * xs[n - self.s0 - i] for i, c in rest)
            xs.append(s_ * pow(d, -1, M) % M)
            if (n & 4095) == 0 and time.time() - t0 > seconds:
                break
        return xs

    def b_value(self, n: int, M: int | None = None):
        """Path B: Fraction iteration written independently of exact()/mod() (no integer division)."""
        vals = [Fraction(v) for v in self.seed]
        for m in range(self.start, n + 1):
            num = Fraction(0)
            for i, c in self.polys.items():
                if i:
                    pv = Fraction(sum(ck * m ** k for k, ck in enumerate(c)))
                    num -= pv * vals[m - self.s0 - i]
            den = Fraction(sum(ck * m ** k for k, ck in enumerate(self.polys[0])))
            vals.append(num / den)
            if M is not None:
                vals[-1] = Fraction(_modf(vals[-1], M))  # residues keep the Fractions small
        v = vals[n - self.s0]
        return _modf(v, M) if M is not None else v


class CF:
    def __init__(self, cf: dict[str, Any]):
        self.cf, self.s0 = cf, cf["s0"]

    def exact(self, hi, seconds=1e9, bits=EXACT_BITS):
        return iter_exact(self.cf, hi, seconds, bits)

    def mod(self, M, hi, seconds=1e9):
        return iter_mod(self.cf, hi, M, seconds)

    def b_value(self, n, M=None):
        return kitamasa(self.cf, n, M)


def generator(e: dict[str, Any]):
    """Fast generator for the entry's definition, or None. The caller must check it against the b-file."""
    d = e.get("definition") or {}
    try:
        if d.get("kind") == "gf" or (d.get("kind") == "rec" and d.get("linear")):
            return CF(cfinite(d, e["offset"], e["terms"]))
        if d.get("kind") == "alg" and d.get("recurrence"):
            return Holo(d["recurrence"], e["offset"])
    except (NotCFinite, B.Bad, ZeroDivisionError, KeyError, ValueError):
        return None
    return None


def matches_bfile(g, off: int, terms: list[int], seconds: float = 20.0) -> bool:
    """Path A values for the whole b-file range must equal the b-file (offset aligned)."""
    try:
        xs = g.exact(off + len(terms) - 1, seconds=seconds, bits=10 ** 9)
    except (NotCFinite, ZeroDivisionError):
        return False
    k = off - g.s0
    return k >= 0 and xs[k:k + len(terms)] == list(terms)


def deep_search(g, claim: dict[str, Any], lo: int, seconds: float, evalA, evalB) -> dict[str, Any]:
    """Search n >= lo. evalA/evalB(code_index, n, seq) evaluate one side (path A / path B evaluator).
    A failure found on path A is recomputed on path B (b_value for every term, path B evaluator)."""
    form = claim["form"]
    out: dict[str, Any] = {"mode": None, "lo": lo, "hi": None, "fail_n": None}
    if form != "relation" and form != "property" and form != "only_prime":
        return out
    t0 = time.time()
    mod = claim.get("mod")
    parts = claim.get("parts") or []
    codes = [B.compile_expr(p) for p in parts] if form == "relation" else []
    safe = form == "relation" and all(ring_safe(c) for c in codes) and not any(
        t[0] == "fn" and t[1].startswith("A") for c in codes for t in c)
    if safe and (mod or all(r == "=" for r in claim["rels"])):
        mods = [mod] if mod else [P1, P2]
        out["mode"] = ("residues mod %d (exact for this congruence)" % mod) if mod else \
            "two 61/31-bit primes (a failure is exact; a pass is a modular check only)"
        hi = MAX_N
        tabs = []
        for M in mods:
            xs = g.mod(M, hi, seconds / (2 * len(mods)))
            hi = min(hi, g.s0 + len(xs) - 1)
            tabs.append(xs)
        last = None
        for n in range(lo, hi + 1):
            stop = False
            for M, xs in zip(mods, tabs):
                def seq(nm, i, _xs=xs):
                    if nm != "a" or i < g.s0 or i - g.s0 >= len(_xs):
                        raise B.Missing(nm)
                    return _xs[i - g.s0]
                try:
                    vals = [evalA(k, n, seq) for k in range(len(codes))]
                except B.Missing:
                    stop = True
                    break
                except (B.Bad, ZeroDivisionError, ValueError):
                    continue
                if _fails_mod(vals, M):
                    out.update(hi=n, fail_n=n, modulus=M)
                    out["path_b"] = _confirm_mod(g, codes, n, M, evalB)
                    return out
            if stop:
                break
            last = n
            if (n & 1023) == 0 and time.time() - t0 > seconds:
                break
        out["hi"] = last
        return out
    out["mode"] = "exact"
    xs = g.exact(MAX_N, seconds / 2)
    from colony import oeis_conjectures as OC
    r = OC.test_claim(claim, OC.Tables({"a": (g.s0, xs)}), "A")
    fails = [f for f in r["fails"] if f["n"] >= lo]
    if fails:
        n = fails[0]["n"]
        out.update(fail_n=n, hi=n)
        hiB = min(n + 8, g.s0 + len(xs) - 1)
        xsB = [int(g.b_value(i)) for i in range(g.s0, hiB + 1)] if hiB - g.s0 < 3000 else None
        if xsB is None:
            xsB = xs[:hiB - g.s0 + 1]
            for i in range(max(g.s0, n - 12), hiB + 1):
                xsB[i - g.s0] = int(g.b_value(i))
        rB = OC.test_claim(claim, OC.Tables({"a": (g.s0, xsB)}), "B")
        out["path_b"] = bool(rB["first_fail"] is not None and [f for f in rB["fails"] if f["n"] == n])
    else:
        out["hi"] = r["hi"] if r["hi"] is not None and r["hi"] >= lo else None
    return out


def _fails_mod(vals, M) -> bool:
    for i in range(len(vals) - 1):
        d = vals[i] - vals[i + 1]
        if d.denominator % M == 0:
            return False
        if _modf(d, M) != 0:
            return True
    return False


def _confirm_mod(g, codes, n, M, evalB) -> bool:
    cache: dict[int, int] = {}

    def seq(nm, i):
        if nm != "a" or i < g.s0:
            raise B.Missing(nm)
        if i not in cache:
            cache[i] = g.b_value(i, M)
        return cache[i]
    try:
        vals = [evalB(k, n, seq) for k in range(len(codes))]
    except (B.Missing, B.Bad, ZeroDivisionError, ValueError):
        return False
    return _fails_mod(vals, M)
