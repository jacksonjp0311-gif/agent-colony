"""Definition-parity and elementary-fact check (James-approved 2026-10-23 11:57 ET).

Part of the known-in-principle / compositional check (colony.compositional, COLONY_COMPOSITIONAL):
a mod-2 congruence that follows mechanically from the DEFINITIONS of its components reduced mod 2,
or from elementary facts about primes and divisors, is labelled known in principle and earns no
surprise credit. Report-only label; nothing here is the Oracle, P or the 0.70 bar.

Component facts, each giving the set of parities a component takes on a residue class n = t (mod Q):

  definition automaton   the OEIS name gives a self-convolution recurrence
        a(n+1) = sum(a(p)*a(n-p) + k, p=0..n) + l.  Mod 2 the convolution's symmetric terms cancel
        in pairs and only the middle square a(m)^2 = a(m) survives, so a(2m) = l and
        a(2m+1) = a(m) + k + l (mod 2): an LSB-first automaton, derived from the definition and
        checked against the colony's table before use (fail closed).
  automatic residues     Christol: an algebraic generating function over GF(2) (Catalan-type
        transforms, convolution recurrences) has 2-automatic coefficients. The 2-kernel of the
        residues mod 2 is built from the data; it must close in at most KERNEL_MAX states and
        reproduce every tabulated term (data-confirmed, the same standard as the C-finite / period
        facts in colony.compositional). Automatic sequences are closed under + - *, shifts, a(2n)
        and partial sums, so S(x) etc. get their own kernel when every part has an automatic fact.
  definition substitution  an OEIS name 'a(n) = <expression>' in colony primitives (gcd, n,
        d(n) or tau(n), sigma(n), phi(n)), checked against the table, is substituted.
  prime-valued           the OEIS name says the terms are primes and every tabulated term is a prime
        >= 3: each value is odd, never a square nor twice a square, and its residue mod P is a unit
        or a prime dividing P. A form 'k*B^m + C ... k < B^m' in the name adds: every value larger
        than B^(2j) + C is = C (mod B^j); the finitely many smaller ones are read from the data.
  elementary parity      tau(k) odd iff k is a square; sigma(k) odd iff k is a square or twice a
        square (decided on the class with quadratic residues); the textbook threshold rules of
        frontier_conjectures._parity_tables (prime(k) odd for k >= 2, phi(k) even for k >= 3, record
        prime gaps and Collatz maxima even for k >= 2, ...); gaps between odd primes are even; exact
        automatic words; periodic residue facts mod 2.

Operators: + and - add parities, * multiplies, gcd(x, y) is odd iff x or y is odd, shifts and a(2n)
move the residue class, outer composition f[g](n) = f(g(n)) goes through the facts about g's values.
When every class of the claim gets one parity and it is the claimed one, the claim is implied.

Regression (2026-10-23 surprises): dbl(A177115) even, dbl(A177122) odd, S(A157100) odd at even n,
prime/maxgap/cmax/ple3 of Proth primes, gcd(2n, tau(2n)) even for n = 4 (mod 6).
"""
from __future__ import annotations

import math
import re
from typing import Any

KERNEL_MAX = 16
KERNEL_MIN_TERMS = 400
CMP_MIN = 8
REFINE = (1, 2, 4, 8, 3, 6, 12, 16, 24)
MAX_Q = 192
ANY = frozenset((0, 1))

_AUT: dict[tuple, Any] = {}
_REACH: dict[tuple, dict[int, frozenset[int]]] = {}
_PRIMEV: dict[tuple, Any] = {}
_DEF: dict[tuple, Any] = {}


class _Unknown(Exception):
    pass


# ----------------------------------------------------------------------------- helpers
def _entry(w: str) -> dict[str, Any] | None:
    try:
        from colony import obscure_pool as OP
        for e in OP._ENTRIES:
            if OP.prim_name(e["anum"]) == w:
                return e
    except Exception:  # noqa: BLE001
        pass
    return None


def _isprime(n: int) -> bool:
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    if n < 9:
        return True
    d = n - 1
    s = 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if a % n == 0:
            continue
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


def _tab(w: str, T: Any) -> list[int] | None:
    return (getattr(T, "t", {}) or {}).get(w)


def _run(aut: tuple, n: int) -> int:
    s, d, out = aut
    while n:
        s = d[s][n & 1]
        n >>= 1
    v = out[s]
    if v is None:
        raise _Unknown("automaton output undefined")
    return v


def _reach(key: Any, aut: tuple, M: int) -> dict[int, frozenset[int]]:
    """{t: parities the automaton gives at n >= 1 with n = t (mod M)} (exact)."""
    k = (key, M)
    if k in _REACH:
        return _REACH[k]
    s0, d, out = aut
    seen: set = set()
    stack = [(s0, 0, 1 % M, 0)]
    vals: dict[int, set[int]] = {}
    while stack:
        st = stack.pop()
        if st in seen:
            continue
        seen.add(st)
        s, r, pw, last = st
        if last:
            if out[s] is None:
                vals.setdefault(r, set()).update((0, 1))
            else:
                vals.setdefault(r, set()).add(out[s] % 2)
        for bit in (0, 1):
            stack.append((d[s][bit], (r + bit * pw) % M, (2 * pw) % M, bit))
    res = {t: frozenset(v) for t, v in vals.items()}
    _REACH[k] = res
    return res


def _verify(aut: tuple, vals: list[int]) -> bool:
    try:
        return all(_run(aut, n) == vals[n] % 2 for n in range(1, len(vals)))
    except _Unknown:
        return False


# ----------------------------------------------------------------------------- definition automaton
_CONV = re.compile(r"a\(n\+1\)\s*=\s*sum\(\s*a\(p\)\s*\*\s*a\(n-p\)\s*([+-]\s*k)?\s*,\s*p\s*=\s*0\s*\.\.\s*n\s*\)"
                   r"\s*([+-]\s*l)?\s*for\s+n\s*>=\s*1.*?a\(0\)\s*=\s*(-?\d+)\s*,\s*a\(1\)\s*=\s*(-?\d+)"
                   r"(?:\s*,\s*k\s*=\s*(-?\d+))?(?:\s*(?:,|and)\s*l\s*=\s*(-?\d+))?", re.I | re.S)


def conv_automaton(name: str) -> tuple | None:
    """Mod-2 automaton of a(n+1) = sum(a(p)a(n-p) + k, p=0..n) + l (n >= 1), from the definition.
    a(N) = conv(N-1) + N k + l. N even: conv(odd) = 0 (pairs cancel) -> a(N) = l.  N = 2m+1 >= 3:
    conv(2m) = a(m)^2 = a(m) -> a(N) = a(m) + k + l. LSB first: a trailing 0 ends with l + acc;
    every 1 adds c = k + l; the top bit is N = 1 itself (a(1), given)."""
    mt = _CONV.search(name or "")
    if not mt:
        return None
    a1 = int(mt.group(4)) % 2
    k = int(mt.group(5) or 0) if mt.group(1) else 0
    l_ = int(mt.group(6) or 0) if mt.group(2) else 0
    c, l_ = (k + l_) % 2, l_ % 2
    # states: ('r', acc) while reading 1s; ('d', v) after the lowest 0 (absorbing)
    d = {("r", 0): (("d", l_), ("r", c)), ("r", 1): (("d", (l_ + 1) % 2), ("r", (1 + c) % 2)),
         ("d", 0): (("d", 0), ("d", 0)), ("d", 1): (("d", 1), ("d", 1))}
    # input ends in ('r', acc): all bits were 1, the last (top) one is N = 1 -> a(1) + acc - c
    out = {("r", 0): (a1 + c) % 2, ("r", 1): (a1 + 1 + c) % 2, ("d", 0): 0, ("d", 1): 1}
    return (("r", 0), d, out)


# ----------------------------------------------------------------------------- automatic residues
def kernel_automaton(vals: list[int]) -> tuple | None:
    """LSB-first automaton for vals[n] mod 2 (n >= 1) from its 2-kernel, or None. A state is a
    kernel element g(m) = x(2^k m + r); reading bit b goes to g(2m + b); the output is g(0)."""
    N = len(vals)
    if N < KERNEL_MIN_TERMS:
        return None
    par = [v % 2 for v in vals]

    def elem(k: int, r: int) -> dict[int, int]:
        return {m: par[(m << k) + r] for m in range(0 if r else 1, ((N - 1 - r) >> k) + 1)}

    reps = [(0, 0)]
    data = [elem(0, 0)]
    outs: list[int | None] = [None]
    delta: dict[int, list[int]] = {}
    q = [0]
    while q:
        s = q.pop(0)
        k, r = reps[s]
        delta[s] = [0, 0]
        for b in (0, 1):
            ck, cr = k + 1, r + (b << k)
            cd = elem(ck, cr)
            hit = None
            for t, td in enumerate(data):
                common = [m for m in cd if m in td]
                if 0 in cd and outs[t] is not None and outs[t] != cd[0]:
                    continue
                if len(common) >= CMP_MIN and all(cd[m] == td[m] for m in common):
                    hit = t
                    break
            if hit is None:
                if len(cd) < 2 * CMP_MIN or len(reps) >= KERNEL_MAX:
                    return None
                reps.append((ck, cr))
                data.append(cd)
                outs.append(cd.get(0))
                hit = len(reps) - 1
                q.append(hit)
            elif outs[hit] is None and 0 in cd:
                outs[hit] = cd[0]
            delta[s][b] = hit
    aut = (0, {s: tuple(v) for s, v in delta.items()}, dict(enumerate(outs)))
    return aut if _verify(aut, vals) else None


def prim_automaton(w: str, T: Any) -> tuple[tuple, str] | None:
    """(automaton, how) for primitive w mod 2: the definition first, then the automatic kernel."""
    tab = _tab(w, T)
    if not tab or len(tab) < 120:
        return None
    key = ("p", w, len(tab))
    if key not in _AUT:
        res = None
        e = _entry(w)
        if e:
            aut = conv_automaton(e.get("name", ""))
            if aut is not None and _verify(aut, tab):
                res = (aut, f"{e['anum']}: definition a(n+1)=sum(a(p)a(n-p)+k)+l reduced mod 2 (symmetric "
                            f"convolution terms cancel in pairs): a(2m)=l, a(2m+1)=a(m)+k+l; matches {len(tab) - 1} terms")
        if res is None:
            aut = kernel_automaton(tab[:20001])
            if aut is not None:
                nm = e["anum"] if e else w
                res = (aut, f"{nm} mod 2 is 2-automatic ({len(aut[1])}-state 2-kernel, Christol), "
                            f"confirmed on {len(tab) - 1} terms")
        _AUT[key] = res
    return _AUT[key]


# ----------------------------------------------------------------------------- definition substitution
_FN = {"d": "tau", "tau": "tau", "sigma": "sigma", "phi": "phi", "A000005": "tau", "A000203": "sigma",
       "A000010": "phi", "omega": "omega", "A001221": "omega", "A001222": "bigomega"}


def _parse_def(s: str) -> tuple | None:
    toks = re.findall(r"A\d{6}|[A-Za-z]+|\d+|[()+\-*,]", s)
    pos = [0]

    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else None

    def take(x=None):
        t = peek()
        if t is None or (x is not None and t != x):
            raise ValueError(s)
        pos[0] += 1
        return t

    def expr():
        e = term()
        while peek() in ("+", "-"):
            op = take()
            e = (op, e, term())
        return e

    def term():
        e = fac()
        while peek() == "*":
            take()
            e = ("*", e, fac())
        return e

    def fac():
        t = take()
        if t == "(":
            e = expr()
            take(")")
            return e
        if t == "n":
            return ("p", "n")
        if t == "gcd":
            take("(")
            a = expr()
            take(",")
            b = expr()
            take(")")
            return ("gcd", a, b)
        if t in _FN:
            take("(")
            a = expr()
            take(")")
            if a == ("p", "n"):
                return ("p", _FN[t])
            if a[0] == "p":
                return ("o", _FN[t], a)
            raise ValueError(s)
        raise ValueError(s)

    try:
        e = expr()
        return e if pos[0] == len(toks) else None
    except (ValueError, IndexError):
        return None


def definition_expr(w: str, T: Any) -> tuple[tuple, str] | None:
    """(expression, how) when w's OEIS name is 'a(n) = <expression in colony primitives>' and the
    expression reproduces w's table."""
    tab = _tab(w, T)
    if not tab:
        return None
    key = (w, len(tab))
    if key in _DEF:
        return _DEF[key]
    res = None
    e = _entry(w)
    mt = re.match(r"\s*a\(n\)\s*=\s*(.+?)(?:,\s*where|;|\.\s|\.$|$)", (e or {}).get("name", ""))
    if mt:
        x = _parse_def(mt.group(1))
        if x is not None:
            try:
                from colony.frontier_conjectures import evaluate
                N = min(len(tab) - 1, 5000)
                v = evaluate(x, N, T)
                if v is not None and v == tab[1:N + 1]:
                    res = (x, f"{e['anum']}: a(n) = {mt.group(1).strip()} (OEIS definition, matches {N} terms)")
            except Exception:  # noqa: BLE001
                res = None
    _DEF[key] = res
    return res


def _subst_defs(e: tuple, T: Any, facts: list[str]) -> tuple:
    if e[0] == "p":
        d = definition_expr(e[1], T) if e[1].startswith("ox") else None
        if d:
            facts.append(d[1])
            return d[0]
        return e
    if e[0] == "o":
        return e
    return (e[0],) + tuple(_subst_defs(x, T, facts) if isinstance(x, tuple) else x for x in e[1:])


# ----------------------------------------------------------------------------- prime-valued
_FORM = re.compile(r"k\s*\*\s*(\d+)\s*\^\s*m\s*\+\s*(\d+).*?k\s*<\s*\1\s*\^\s*m", re.I | re.S)


def prime_valued(w: str, T: Any) -> dict[str, Any] | None:
    """{'min': least value, 'form': (B, C) or None, 'small': sorted values, 'how': ...} when the OEIS
    name says the terms are primes and every tabulated term (n >= 1) is a prime >= 3."""
    tab = _tab(w, T)
    if not tab or len(tab) < 120:
        return None
    key = (w, len(tab))
    if key in _PRIMEV:
        return _PRIMEV[key]
    res = None
    e = _entry(w)
    name = (e or {}).get("name", "") if e else ""
    if e and re.search(r"\bprimes?\b", name, re.I) and all(v >= 3 and _isprime(v) for v in tab[1:]):
        fm = _FORM.search(name)
        res = {"min": min(tab[1:]), "max_seen": max(tab[1:]), "vals": sorted(set(tab[1:])),
               "form": (int(fm.group(1)), int(fm.group(2))) if fm else None,
               "how": f"{e['anum']} terms are primes >= 3 (OEIS name; all {len(tab) - 1} tabulated terms "
                      f"prime): odd, never a square or twice a square"}
    _PRIMEV[key] = res
    return res


def prime_residues(pv: dict[str, Any], P: int) -> set[int] | None:
    """Residues mod P that the prime values can take (all n), or None when undecidable."""
    allowed = {r for r in range(P) if math.gcd(r, P) == 1} | {q for q in range(3, P + 1) if P % q == 0 and _isprime(q)}
    allowed = {r % P for r in allowed}
    if pv["form"]:
        B, C = pv["form"]
        j, Bj = 0, 1
        while P % (Bj * B) == 0:
            j, Bj = j + 1, Bj * B
        if j:
            bound = B ** (2 * j) + C        # values k*B^m + C with k < B^m and m < j are below this
            if pv["max_seen"] < bound:
                return None
            small = {v % P for v in pv["vals"] if v < bound}
            allowed = {r for r in allowed if r % Bj == C % Bj} | small
    return allowed


# ----------------------------------------------------------------------------- leaves
def _affine(e: tuple) -> tuple[str, int, int] | None:
    if e[0] == "p":
        return e[1], 1, 0
    if e[0] in ("sh", "dbl"):
        x = _affine(e[1])
        if x is None:
            return None
        w, a, b = x
        return (w, a, a + b) if e[0] == "sh" else (w, 2 * a, b)
    return None


def _squares(M: int) -> set[int]:
    return {x * x % M for x in range(M)}


def _threshold(f: str) -> tuple[int, int] | None:
    """(K, parity) when the textbook rule gives f(k) a constant parity for all k >= K."""
    from colony.frontier_conjectures import _parity_tables
    rules = _parity_tables(4000)
    if f not in rules or f == "_L":
        return None
    r = rules[f]
    tail = r[-1]
    if any(x != tail for x in r[len(r) // 2:]):
        return None
    K = len(r) - 1
    while K > 1 and r[K - 1] == tail:
        K -= 1
    return K, tail


class _Ev:
    def __init__(self, T: Any):
        self.T = T
        self.facts: set[str] = set()

    def leaf(self, w: str, a: int, b: int, t: int, Q: int) -> frozenset[int]:
        from colony import compositional as CP
        T = self.T
        cm = a * Q
        c = (a * t + b) % cm
        n0 = t if t >= 1 else Q
        k0 = a * n0 + b
        if w in CP.WORDS and CP.word_ok(w, T):
            vs = CP.reachable(w, cm).get(c, frozenset())
            self.facts.add(f"{w}: exact automaton")
            return frozenset(v % 2 for v in vs) or ANY
        if w == "n":
            return frozenset((c % 2,)) if cm % 2 == 0 else ANY
        if w == "one":
            return frozenset((1,))
        if w.startswith("_c"):
            return frozenset((_tab(w, T)[1] % 2,))
        if w in ("tau", "sigma"):
            sq = _squares(cm)
            bad = sq | ({(2 * s) % cm for s in _squares(cm)} if w == "sigma" else set())
            # 2*x^2 mod cm: x^2 mod cm determines 2x^2 mod cm
            if c not in bad:
                self.facts.add(f"{w}(k) is odd only when k is a square{' or twice a square' if w == 'sigma' else ''}; "
                               f"no such k is = {c} (mod {cm})")
                return frozenset((0,))
            return ANY  # the class contains squares (tau, sigma odd) and non-squares
        th = _threshold(w)
        if th and k0 >= th[0]:
            self.facts.add(f"{w}(k) has parity {th[1]} for k >= {th[0]} (textbook rule)")
            return frozenset((th[1],))
        if w in ("rad", "lpf") and k0 >= 2 and cm % 2 == 0:
            return frozenset((c % 2,))
        if w.startswith("ox"):
            pv = prime_valued(w, T)
            if pv:
                self.facts.add(pv["how"])
                return frozenset((1,))
            pa = prim_automaton(w, T)
            if pa:
                self.facts.add(pa[1])
                return _reach(("p", w), pa[0], cm).get(c, ANY)
        f = CP.residue_fact(w, 2, T)
        if f is not None:
            P, pre = f["P"], f["pre"]
            L = cm * P // math.gcd(cm, P)
            tab = _tab(w, T)
            out = set()
            k = k0
            while k < max(pre, k0) + L or k < pre:
                if (k - c) % cm == 0:
                    if k < pre:
                        if k >= len(tab):
                            raise _Unknown(w)
                        out.add(tab[k] % 2)
                    else:
                        out.add(CP._at(f, k) % 2)
                k += 1
            self.facts.add(f"{w}: " + str(f.get("how", "periodic residues")))
            return frozenset(out) or ANY
        if w.startswith("ox") is False:
            pa = prim_automaton(w, T)
            if pa:
                self.facts.add(pa[1])
                return _reach(("p", w), pa[0], cm).get(c, ANY)
        raise _Unknown(w)

    def outer(self, f: str, inner: tuple, t: int, Q: int) -> frozenset[int]:
        from colony import compositional as CP
        x = _affine(inner)
        if x is None or not x[0].startswith("ox"):
            raise _Unknown(f)
        pv = prime_valued(x[0], self.T)
        if not pv:
            raise _Unknown(f)
        self.facts.add(pv["how"])
        if f in ("tau", "sigma"):
            self.facts.add(f"{f}(p) = {'2' if f == 'tau' else 'p+1'} is even for an odd prime p")
            return frozenset((0,))
        if f in ("rad", "lpf", "gpf", "n"):
            return frozenset((1,))
        th = _threshold(f)
        if th and pv["min"] >= th[0]:
            self.facts.add(f"{f}(k) has parity {th[1]} for k >= {th[0]} (textbook rule"
                           + ("; gaps between odd primes are even)" if f == "maxgap" else ")"))
            return frozenset((th[1],))
        fact = CP.residue_fact(f, 2, self.T)
        if fact is not None and fact["pre"] <= pv["min"]:
            P = fact["P"]
            res = prime_residues(pv, P)
            if res is None:
                raise _Unknown(f)
            out = set()
            for r in res:
                k = pv["min"] + ((r - pv["min"]) % P)
                out.add(CP._at(fact, k) % 2)
            self.facts.add(f"{f}: " + str(fact.get("how", "")) + f"; prime values lie in residues {sorted(res)} mod {P}")
            return frozenset(out)
        raise _Unknown(f)

    def node_automaton(self, e: tuple, t: int, Q: int) -> frozenset[int]:
        """S / D / shifted compound nodes: automatic when every primitive inside is (closure)."""
        from colony.frontier_conjectures import canon, evaluate, max_n
        for w in _prims(e):
            pa = prim_automaton(w, self.T)
            if not pa:
                raise _Unknown(w)
            self.facts.add(pa[1])
        key = ("e", canon(e))
        if key not in _AUT:
            N = max_n(e, self.T, 20000)
            v = evaluate(e, N, self.T) if N else None
            aut = kernel_automaton([0] + v) if v else None
            _AUT[key] = (aut, f"{canon(e)} mod 2 is 2-automatic (closure of automatic sequences under + - * shifts "
                              f"a(2n) and partial sums; {len(aut[1]) if aut else 0}-state 2-kernel, confirmed on {N} terms)") if aut else None
        if not _AUT[key]:
            raise _Unknown("node")
        self.facts.add(_AUT[key][1])
        return _reach(key, _AUT[key][0], Q).get(t % Q, ANY)

    def par(self, e: tuple, t: int, Q: int) -> frozenset[int]:
        op = e[0]
        if op in ("+", "-", "*", "gcd"):
            # absorbing values: an odd operand makes gcd odd, an even factor makes the product even
            absorb = {"gcd": frozenset((1,)), "*": frozenset((0,))}.get(op)
            for i, j in ((1, 2), (2, 1)):
                if absorb is not None:
                    try:
                        if self.par(e[i], t, Q) == absorb:
                            return absorb
                    except _Unknown:
                        pass
            A, B = self.par(e[1], t, Q), self.par(e[2], t, Q)
            if op in ("+", "-"):
                return frozenset((x + y) % 2 for x in A for y in B)
            if op == "*":
                return frozenset(x * y for x in A for y in B)
            return frozenset(x | y for x in A for y in B)
        x = _affine(e)
        if x is not None:
            return self.leaf(x[0], x[1], x[2], t, Q)
        if op == "o":
            return self.outer(e[1], e[2], t, Q)
        if op == "D":  # D(x)(n) = x(n+1) - x(n)
            from colony.frontier_conjectures import _push
            try:
                return self.par(_push(("-", ("sh", e[1]), e[1])), t, Q)
            except _Unknown:
                pass
        if op in ("S", "D", "sh", "dbl"):
            return self.node_automaton(e, t, Q)
        raise _Unknown(op)


def _prims(e: tuple) -> set[str]:
    if e[0] == "p":
        return {e[1]}
    if e[0] == "o":
        return {e[1]} | _prims(e[2])
    out: set[str] = set()
    for x in e[1:]:
        if isinstance(x, tuple):
            out |= _prims(x)
    return out


def explain(c: dict[str, Any], T: Any) -> dict[str, Any] | None:
    """{'label': 'known_in_principle(definition_parity)', 'facts': [...]} when the mod-2 claim follows
    from definitions reduced mod 2 / elementary facts, else None."""
    from colony.frontier_conjectures import _push
    kind = c.get("kind")
    if kind not in ("cong", "modpat") or c.get("_re") is not None:
        return None
    prm = c.get("params") or {}
    if int(prm.get("m") or 0) != 2:
        return None
    q, s = (int(prm["q"]), int(prm["s"]) % int(prm["q"])) if kind == "cong" else (1, 0)
    Pm = int(prm["P"]) if kind == "modpat" else 1
    pre_facts: list[str] = []
    try:
        e = _push(_subst_defs(c["_le"], T, pre_facts))
        e = _push(e)
    except Exception:  # noqa: BLE001
        return None
    base = q * Pm // math.gcd(q, Pm)
    for f in REFINE:
        Q = base * f
        if Q > MAX_Q:
            break
        ev = _Ev(T)
        ok = True
        try:
            for t in range(Q):
                if t % q != s:
                    continue
                want = int(prm["r"]) % 2 if kind == "cong" else int(prm["pat"][(t - 1) % Pm]) % 2
                got = ev.par(e, t, Q)
                if got != frozenset((want,)):
                    ok = False
                    break
        except _Unknown:
            return None
        except Exception:  # noqa: BLE001
            return None
        if ok:
            return {"label": "known_in_principle(definition_parity)", "classes_mod": Q,
                    "facts": sorted(set(pre_facts) | ev.facts),
                    "scope": "implied for all n >= 1 by the components' definitions reduced mod 2 and elementary "
                             "parity facts (automatic-kernel facts are data-confirmed)"}
    return None
