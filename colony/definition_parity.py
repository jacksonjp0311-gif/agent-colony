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
  multiplicative definition  an OEIS name that defines a(n) from the prime factorization, in one of
        three vetted shapes: "If n = Product (p_j^k_j) then a(n) = Product ( ... )",
        "multiplicative with a(p^e) = ...", or "completely multiplicative with a(p) = ...".
        The formula is parsed, never executed, and used only when it reproduces the table.
        The keyword "mult" alone is not a definition. On a residue class whose argument is always
        p^e times a coprime cofactor, an even a(p^e) makes every value even.
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
# Moduli past 2. A p-kernel fitted to a prefix is confirmed on that range, not a proof.
SMALL_PRIMES = (3, 5, 7)
REFINE = (1, 2, 4, 8, 3, 6, 12, 16, 24)
MAX_Q = 192
ANY = frozenset((0, 1))

_AUT: dict[tuple, Any] = {}
_REACH: dict[tuple, dict[int, frozenset[int]]] = {}
_PRIMEV: dict[tuple, Any] = {}
_DEF: dict[tuple, Any] = {}
_MULT: dict[tuple, Any] = {}
_SPF: list[int] = []
_PRIMES: list[int] = []


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


def _run_p(aut: tuple, n: int, p: int) -> int:
    s, d, out = aut
    while n:
        s = d[s][n % p]
        n //= p
    v = out[s]
    if v is None:
        raise _Unknown("automaton output undefined")
    return int(v) % p


def _verify_p(aut: tuple, vals: list[int], p: int) -> bool:
    try:
        return all(_run_p(aut, n, p) == vals[n] % p for n in range(1, len(vals)))
    except _Unknown:
        return False


def prime_kernel(vals: list[int], p: int) -> tuple | None:
    """LSB-first automaton for vals[n] mod p from its p-kernel, or None.

    The same construction as the 2-kernel, with base-p digits. Agreement on a finite prefix
    does not prove the sequence is p-automatic for every n."""
    if p not in SMALL_PRIMES or len(vals) < KERNEL_MIN_TERMS:
        return None
    residues = [v % p for v in vals]

    def elem(k: int, r: int) -> dict[int, int]:
        step = p ** k
        if step <= 0 or step >= len(vals):
            return {}
        out: dict[int, int] = {}
        m = 0 if r else 1
        while r + m * step < len(vals):
            out[m] = residues[r + m * step]
            m += 1
            if m > len(vals):
                break
        return out

    reps = [(0, 0)]
    data = [elem(0, 0)]
    outs: list[int | None] = [None]
    delta: dict[int, list[int]] = {}
    q = [0]
    while q:
        s = q.pop(0)
        k, r = reps[s]
        delta[s] = [0] * p
        for b in range(p):
            ck, cr = k + 1, r + b * (p ** k)
            cd = elem(ck, cr)
            hit = None
            for t, td in enumerate(data):
                common = [m_ for m_ in cd if m_ in td]
                if 0 in cd and outs[t] is not None and outs[t] != cd[0]:
                    continue
                if len(common) >= CMP_MIN and all(cd[m_] == td[m_] for m_ in common):
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
    return aut if _verify_p(aut, vals, p) else None


def _explain_small_prime(c: dict[str, Any], T: Any) -> dict[str, Any] | None:
    """Mod 3, 5 and 7. An affine function of n is exact. Anything proved only by a p-kernel
    fitted to the table is confirmed on that range, not for all n."""
    kind = c.get("kind")
    prm = c.get("params") or {}
    m = int(prm.get("m") or 0)
    if kind not in ("cong", "modpat") or c.get("_re") is not None or m not in SMALL_PRIMES:
        return None
    e = c.get("_le")
    if not isinstance(e, tuple):
        return None
    q, s = (int(prm["q"]), int(prm["s"]) % int(prm["q"])) if kind == "cong" else (1, 0)
    Pm = int(prm["P"]) if kind == "modpat" else 1
    aff = _affine(e)
    if aff and aff[0] == "n":
        _w, a, b = aff
        base = q * Pm // math.gcd(q, Pm)
        for f in REFINE:
            Q = base * f
            if Q > MAX_Q:
                break
            if (a * Q) % m != 0:
                continue
            ok = True
            for t in range(Q):
                if t % q != s:
                    continue
                got = (a * t + b) % m
                want = int(prm["r"]) % m if kind == "cong" else int(prm["pat"][(t - 1) % Pm]) % m
                if got != want:
                    ok = False
                    break
            if ok:
                return {"label": "known_in_principle(definition_parity)", "classes_mod": Q,
                        "facts": [f"n mod {m} is fixed by the residue class"],
                        "scope": f"implied for all n >= 1: the expression is an affine function of n, reduced mod {m}"}
        return None
    try:
        from colony.frontier_conjectures import evaluate, holds, max_n
        N = max_n(e, T, 4000)
        vals = evaluate(e, N, T) if N else None
    except Exception:  # noqa: BLE001
        return None
    if not vals or len(vals) < KERNEL_MIN_TERMS - 1:
        return None
    aut = prime_kernel([0] + vals, m)
    if aut is None or not holds(kind, prm, vals, None)[0]:
        return None
    fact = (f"{m}-kernel with {len(aut[1])} states fitted to {len(vals)} terms; "
            f"confirmed on that range, not a proof for all n")
    return {"label": "confirmed on range", "classes_mod": q, "facts": [fact],
            "scope": "confirmed on range: " + fact}


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


# ----------------------------------------------------------------------------- multiplicative definitions
# Vetted shapes only. The OEIS sentence is parsed into these operations; it is never executed.
_MULT_FUN = {"prime", "pi"}


def _balanced_inside(s: str, open_at: int) -> str | None:
    """Text inside the parenthesis that starts at open_at, or None when the parens do not balance."""
    if open_at >= len(s) or s[open_at] != "(":
        return None
    depth = 0
    for j in range(open_at, len(s)):
        if s[j] == "(":
            depth += 1
        elif s[j] == ")":
            depth -= 1
            if depth == 0:
                return s[open_at + 1:j]
    return None


def _tokenize_formula(s: str) -> list[str] | None:
    out: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isdigit():
            j = i + 1
            while j < len(s) and s[j].isdigit():
                j += 1
            out.append(s[i:j])
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i + 1
            while j < len(s) and (s[j].isalnum() or s[j] == "_"):
                j += 1
            out.append(s[i:j])
            i = j
            continue
        if ch in "()+-*^":
            out.append(ch)
            i += 1
            continue
        return None
    return out


def _parse_formula(src: str, variables: set[str]) -> tuple | None:
    """Arithmetic formula in the given variables, prime() and pi(). None if anything else appears."""
    toks = _tokenize_formula(src)
    if not toks:
        return None
    pos = [0]

    def peek() -> str | None:
        return toks[pos[0]] if pos[0] < len(toks) else None

    def take(x: str | None = None) -> str:
        t = peek()
        if t is None or (x is not None and t != x):
            raise ValueError(src)
        pos[0] += 1
        return t

    def expr() -> tuple:
        e = term()
        while peek() in ("+", "-"):
            op = take()
            e = (op, e, term())
        return e

    def term() -> tuple:
        e = power()
        while peek() == "*":
            take()
            e = ("*", e, power())
        return e

    def power() -> tuple:
        e = atom()
        if peek() == "^":
            take()
            e = ("^", e, power())
        return e

    def atom() -> tuple:
        t = take()
        if t == "(":
            e = expr()
            take(")")
            return e
        if t.isdigit():
            return ("num", int(t))
        if t in _MULT_FUN and peek() == "(":
            take("(")
            arg = expr()
            take(")")
            return (t, arg)
        if t in variables:
            return ("var", t)
        raise ValueError(src)

    try:
        e = expr()
        return e if pos[0] == len(toks) else None
    except (ValueError, IndexError):
        return None


def parse_multiplicative_name(name: str) -> dict[str, Any] | None:
    """A vetted multiplicative formula from an OEIS name, or None.

    Shapes: the Product (p_j^k_j) form, 'multiplicative with a(p^e) = ...', and
    'completely multiplicative with a(p) = ...'. The keyword 'mult' is not a formula.
    """
    text = name or ""
    prod = re.search(
        r"if\s+n\s*=\s*product\s*\(\s*p_j\s*\^\s*k_j\s*\)\s*then\s*a\(n\)\s*=\s*product\s*\(",
        text, re.I)
    if prod:
        inner = _balanced_inside(text, prod.end() - 1)
        node = _parse_formula(inner or "", {"p_j", "k_j"})
        if node is None:
            return None
        return {"kind": "product", "node": node, "expr": (inner or "").strip(),
                "env": {"p_j": "p", "k_j": "e"}}
    spec = re.search(
        r"(completely\s+)?multiplicative\s+with\s+a\(\s*p\s*(?:\^\s*([A-Za-z]))?\s*\)\s*=\s*([^.;]+)",
        text, re.I)
    if not spec:
        return None
    completely = bool(spec.group(1))
    exp_var = spec.group(2)
    expr = spec.group(3).strip()
    if completely and not exp_var:
        node = _parse_formula(expr, {"p"})
        if node is None:
            return None
        return {"kind": "completely", "node": node, "expr": expr, "env": {"p": "p"}}
    if exp_var:
        node = _parse_formula(expr, {"p", exp_var})
        if node is None:
            return None
        return {"kind": "at_power", "node": node, "expr": expr,
                "env": {"p": "p", exp_var: "e"}}
    return None


def _sieve(limit: int) -> None:
    """Extend the shared smallest-prime-factor table and the prime list up to limit."""
    global _SPF
    if limit < 2:
        return
    if len(_SPF) > limit:
        return
    start = max(len(_SPF), 2)
    spf = _SPF[:] if _SPF else [0, 1]
    if len(spf) <= limit:
        spf.extend(range(len(spf), limit + 1))
    root = int(limit ** 0.5) + 1
    for i in range(2, root):
        if spf[i] == i:
            for j in range(max(i * i, (start + i - 1) // i * i), limit + 1, i):
                if spf[j] == j:
                    spf[j] = i
    _SPF = spf
    if not _PRIMES or _PRIMES[-1] < limit:
        _PRIMES.clear()
        _PRIMES.extend(i for i in range(2, len(_SPF)) if _SPF[i] == i)


def _nth_prime(k: int) -> int | None:
    if k < 1 or k > 10000:
        return None
    bound = 32
    while len(_PRIMES) < k:
        bound *= 2
        if bound > 200000:
            return None
        _sieve(bound)
    return _PRIMES[k - 1] if len(_PRIMES) >= k else None


def _prime_pi(n: int) -> int | None:
    if n < 0 or n > 200000:
        return None
    if n < 2:
        return 0
    _sieve(n)
    return sum(1 for p in _PRIMES if p <= n)


def _eval_formula(node: tuple, env: dict[str, int]) -> int | None:
    op = node[0]
    if op == "num":
        return int(node[1])
    if op == "var":
        return env.get(node[1])
    if op == "prime":
        k = _eval_formula(node[1], env)
        return None if k is None else _nth_prime(k)
    if op == "pi":
        n = _eval_formula(node[1], env)
        return None if n is None else _prime_pi(n)
    if op in ("+", "-", "*", "^"):
        a = _eval_formula(node[1], env)
        b = _eval_formula(node[2], env)
        if a is None or b is None:
            return None
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if b < 0 or b > 10000 or (abs(a) > 1 and b > 10000):
            return None
        return a ** b
    return None


def _apk_fn(parsed: dict[str, Any]):
    """a(p^e) from a parsed formula. None when the formula does not give an integer."""
    node, mapping, kind = parsed["node"], parsed["env"], parsed["kind"]

    def apk(p: int, e: int) -> int | None:
        if p < 2 or e < 1:
            return None
        base_env = {"p": p, "e": e}
        env = {src: base_env[dst] for src, dst in mapping.items()}
        if kind == "completely":
            one = _eval_formula(node, env)
            if one is None:
                return None
            return one ** e
        return _eval_formula(node, env)

    return apk


def _factor_value(apk, n: int) -> int | None:
    """a(n) for n >= 1 from a(p^e), using multiplicativity. a(1) is the empty product, 1."""
    if n < 1:
        return None
    if n == 1:
        return 1
    if len(_SPF) <= n:
        _sieve(n)
    val = 1
    while n > 1:
        p = _SPF[n]
        e = 0
        while n % p == 0:
            n //= p
            e += 1
        piece = apk(p, e)
        if piece is None:
            return None
        val *= piece
    return val


def multiplicative_def(w: str, T: Any) -> dict[str, Any] | None:
    """The sequence's multiplicative definition, once it reproduces the table. None otherwise.

    A keyword of 'mult' with no parsed formula is refused. A formula that misses any tabulated
    term is refused. Nothing here runs code taken from OEIS.
    """
    tab = _tab(w, T)
    if not tab or len(tab) < 60:
        return None
    key = (w, len(tab))
    if key in _MULT:
        return _MULT[key]
    res = None
    entry = _entry(w)
    parsed = parse_multiplicative_name((entry or {}).get("name", "")) if entry else None
    if parsed is not None:
        apk = _apk_fn(parsed)
        N = min(len(tab) - 1, 2000)
        ok = N >= 60
        for n in range(1, N + 1):
            got = _factor_value(apk, n)
            if got is None or got != tab[n]:
                ok = False
                break
        if ok:
            anum = entry.get("anum") or w
            res = {
                "apk": apk,
                "how": (f"multiplicative definition ({anum}): a(n) is the product of "
                        f"a(p^e) = {parsed['expr']}; matches {N} tabulated terms"),
            }
    _MULT[key] = res
    return res


def _stable_powers(residue: int, modulus: int) -> list[tuple[int, int]]:
    """Prime powers p^e that divide every integer in the progression, with the valuation fixed.

    k ≡ residue (mod modulus) has v_p(k) = e for every k > 0 when v_p(residue) = e and
    v_p(modulus) > e. Then k = p^e * u with gcd(u, p) = 1.
    """
    if residue <= 0 or modulus <= 0:
        return []
    out: list[tuple[int, int]] = []
    n = residue

    def take(p: int, e: int) -> None:
        v = 0
        y = modulus
        while y % p == 0:
            y //= p
            v += 1
        if v > e:
            out.append((p, e))

    p = 2
    while p * p <= n:
        if n % p == 0:
            e = 0
            while n % p == 0:
                n //= p
                e += 1
            take(p, e)
        p = 3 if p == 2 else p + 2
    if n > 1:
        take(n, 1)
    return out


def _mult_class_parity(md: dict[str, Any], residue: int, modulus: int) -> tuple[int, str] | None:
    """(0, fact) when multiplicativity forces every value in the progression to be even."""
    for p, e in _stable_powers(residue, modulus):
        apk = md["apk"](p, e)
        if apk is None or apk % 2 != 0:
            continue
        shown = str(apk) if abs(apk) <= 10 ** 6 else "an even integer"
        return 0, (f"multiplicative: every such argument is {p}^{e} times a coprime cofactor, "
                   f"and a({p}^{e}) = {shown} is even, so the value is even")
    return None


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
            md = multiplicative_def(w, T) if k0 >= 1 else None
            if md is not None:
                bit = _mult_class_parity(md, c, cm)
                if bit is not None:
                    self.facts.add(md["how"])
                    self.facts.add(bit[1])
                    return frozenset((bit[0],))
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


# Textbook sequences that are integers >= 1 for every n >= 1. Used only to justify
# lpf(x) ≡ x (mod 2) and the one-way gpf fact. Not a list of claims.
_GE1 = {"n", "one", "phi", "sigma", "tau", "rad", "lpf", "gpf", "prime", "pow2", "fib", "lucas", "pell"}


def _gpf_target_odd(kind: str, prm: dict[str, Any]) -> bool:
    """True when every residue the claim asks for is odd. gpf may then use the one-way fact."""
    if kind == "cong":
        return int(prm.get("r") or 0) % 2 == 1
    pat = prm.get("pat") or []
    return bool(pat) and all(int(x) % 2 == 1 for x in pat)


def _ge1(e: tuple, T: Any) -> str | None:
    """'proof' when every leaf is an integer >= 1 for all n >= 1, 'range' when that is only
    true of the tabulated terms, None when a value below 1 is seen or the expression does not evaluate."""
    leaves = _prims(e)
    proofish = True
    for w in leaves:
        if w in _GE1 or w.startswith("_c"):
            continue
        if str(w).startswith("ox") and prime_valued(w, T):
            continue
        proofish = False
    try:
        from colony.frontier_conjectures import evaluate, max_n
        N = max_n(e, T, 400)
        vals = evaluate(e, N, T) if N else None
    except Exception:  # noqa: BLE001
        vals = None
    if not vals or min(vals) < 1:
        return None
    return "proof" if proofish else "range"


def peel_factor_parity(c: dict[str, Any], T: Any) -> dict[str, Any] | None:
    """Rewrite a mod-2 claim before the parity filters.

    lpf(x) ≡ x (mod 2) for every integer x >= 1, so lpf[seq] is replaced by seq.
    gpf(x) is even exactly when x is a power of 2. An odd integer x >= 1 does have odd gpf,
    so a claim that gpf is odd may be reduced to "seq is odd". The converse is false:
    gpf(6) = 3, so a claim that gpf is even is not the claim that seq is even.
    """
    kind = c.get("kind")
    prm = c.get("params") or {}
    if kind not in ("cong", "modpat") or int(prm.get("m") or 0) != 2 or c.get("_re") is not None:
        return None
    if c.get("_le") is None:
        return None
    gpf_odd = _gpf_target_odd(kind, prm)
    facts: list[str] = []
    strength = ["proof"]
    changed = [False]

    def walk(e: tuple) -> tuple:
        if e[0] == "o" and e[1] == "lpf":
            dom = _ge1(e[2], T)
            if dom is None:
                return ("o", "lpf", walk(e[2]))
            if dom == "range":
                strength[0] = "range"
            facts.append("lpf(x) is odd exactly when x is odd, for every integer x >= 1")
            changed[0] = True
            return walk(e[2])
        if e[0] == "o" and e[1] == "gpf" and gpf_odd:
            dom = _ge1(e[2], T)
            if dom is None:
                return ("o", "gpf", walk(e[2]))
            if dom == "range":
                strength[0] = "range"
            facts.append("an odd integer x >= 1 has odd gpf; gpf(x) is even exactly when x is a power of 2")
            changed[0] = True
            return walk(e[2])
        if e[0] == "p":
            return e
        return (e[0],) + tuple(walk(x) if isinstance(x, tuple) else x for x in e[1:])

    new_e = walk(c["_le"])
    if not changed[0]:
        return None
    return {"e": new_e, "facts": sorted(set(facts)), "strength": strength[0]}


def explain(c: dict[str, Any], T: Any) -> dict[str, Any] | None:
    """{'label': 'known_in_principle(definition_parity)', 'facts': [...]} when the mod-2 claim follows
    from definitions reduced mod 2 / elementary facts, else None."""
    if not c.get("_factor_peeled"):
        peeled = peel_factor_parity(c, T)
        if peeled is not None and peeled["e"] != c.get("_le"):
            ex = explain(dict(c, _le=peeled["e"], _factor_peeled=True), T)
            if ex:
                facts = sorted(set(ex.get("facts") or []) | set(peeled["facts"]))
                ex = dict(ex, facts=facts)
                if peeled["strength"] != "proof" or str(ex.get("label") or "").startswith("confirmed"):
                    ex["label"] = "confirmed on range"
                    ex["scope"] = "confirmed on range: " + peeled["facts"][0]
                else:
                    ex["scope"] = (str(ex.get("scope") or "") + " " + peeled["facts"][0]).strip()
                return ex
    from colony.frontier_conjectures import _push
    kind = c.get("kind")
    if kind not in ("cong", "modpat") or c.get("_re") is not None:
        return None
    prm = c.get("params") or {}
    if int(prm.get("m") or 0) != 2:
        return _explain_small_prime(c, T)
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
            facts = sorted(set(pre_facts) | ev.facts)
            # A 2-kernel fitted to a prefix is a check of those terms. A defining convolution
            # is worded as a definition, not as "confirmed on" a kernel, and stays a proof.
            if any("confirmed on" in f and "kernel" in f for f in facts):
                return {"label": "confirmed on range", "classes_mod": Q, "facts": facts,
                        "scope": "confirmed on range: a 2-kernel was fitted to the tabulated terms; "
                                 "not a proof for all n"}
            return {"label": "known_in_principle(definition_parity)", "classes_mod": Q, "facts": facts,
                    "scope": "implied for all n >= 1 by the components' definitions reduced mod 2 and elementary "
                             "parity facts"}
    return None
