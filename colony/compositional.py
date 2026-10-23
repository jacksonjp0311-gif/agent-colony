"""Compositional triviality check (James-approved 2026-10-23). COLONY_COMPOSITIONAL=live|shadow|off.

A frontier claim that combines sequences with operators (gcd, a(2n), shifts, + - *) is decomposed
and each component is tested against facts that hold for it on its own:

  automatic words (baum, tm, rs, pfold, pdbl): EXACT residue reachability. Each word is a finite
      automaton reading n in binary (least significant digit first); a breadth-first search over
      (automaton state, n mod M, 2^i mod M) gives exactly which values the word can take on each
      residue class n = t (mod M). Example: Baum-Sweet is never 1 at n = 2 (mod 3).
      Every automaton is checked against the colony's own table before use (fail closed).
  every other primitive: a residue fact mod m, the Berlekamp-Massey linear recurrence over GF(p)
      (C-finite reduction; for prime m) or a pure period of the residues, confirmed on all of the
      data the colony has for it with at least 3 full repetitions. These are data facts: a
      recurrence/period confirmed on the table is evidence about the component, the same standard
      the existing implied_parts rule uses.

On each refined residue class the words that are provably constant are replaced by that constant
and the expression is simplified (gcd(0, y) = |y|, gcd(1, y) = 1, 0*y = 0, 1*y = y). If what is left
is built only from components with residue facts, the claim's residues are periodic and the claim
is decided by one period: when it holds there, the claim is IMPLIED BY COMPONENT FACTS
(known in principle) and earns no surprise credit. Nothing here is the Oracle, P or the 0.70 bar.

Regression (VERDICT.md, 2026-10-23): dbl(gcd(baum, oxa072856)) = 0 (mod 2) for n = 1 (mod 3):
2n = 2 (mod 3) so baum(2n) = 0 and gcd(0, y) = y = A072856(2n); A072856 mod 2 has period 9
((1+x)/(1+x^9) over GF(2)); 2n mod 9 is in {2, 5, 8}, where A072856 is even.
"""
from __future__ import annotations

import math
import os
from functools import lru_cache
from typing import Any

MODES = ("live", "shadow", "off")
BM_TERMS = 600          # residues used for Berlekamp-Massey
BM_MAX_ORDER = 60
PERIOD_MAX = 2000
REFINE = (1, 2, 4, 8, 3, 6, 12, 16)
MAX_CLASS_MOD = 192
MAX_CHECK = 60000       # one full period of the reduced claim must fit in this many n


def mode() -> str:
    m = os.environ.get("COLONY_COMPOSITIONAL", "shadow").strip().lower()
    return m if m in MODES else "shadow"


def live() -> bool:
    return mode() == "live"


# ----------------------------------------------------------------------------- automatic words
# LSB-first automata: (start, delta[state][bit], output[state]); n >= 1, top bit is 1.
WORDS: dict[str, tuple[str, dict[str, tuple[str, str]], dict[str, int]]] = {
    "tm": ("e", {"e": ("e", "o"), "o": ("o", "e")}, {"e": 0, "o": 1}),
    # rs: parity of '11' blocks; state = (last bit, parity)
    "rs": ("s", {"s": ("00", "10"), "00": ("00", "10"), "10": ("00", "11"),
                 "01": ("01", "11"), "11": ("01", "10")}, {"s": 0, "00": 0, "10": 0, "01": 1, "11": 1}),
    # pfold: n = 2^k m, value 1 iff m = 1 (mod 4): after the lowest 1, the next bit decides
    "pfold": ("z", {"z": ("z", "a"), "a": ("v1", "v0"), "v1": ("v1", "v1"), "v0": ("v0", "v0")},
              {"z": 0, "a": 1, "v1": 1, "v0": 0}),
    # pdbl: v2(n) mod 2
    "pdbl": ("z0", {"z0": ("z1", "d0"), "z1": ("z0", "d1"), "d0": ("d0", "d0"), "d1": ("d1", "d1")},
             {"z0": 0, "z1": 0, "d0": 0, "d1": 1}),
    # baum: no block of 0s of odd length (trailing zeros are a block)
    "baum": ("e", {"e": ("o", "e"), "o": ("e", "x"), "x": ("x", "x")}, {"e": 1, "o": 0, "x": 0}),
}


def _run(word: str, n: int) -> int:
    s, d, out = WORDS[word]
    while n:
        s = d[s][n & 1]
        n >>= 1
    return out[s]


_VERIFIED: dict[str, bool] = {}


def word_ok(word: str, T: Any) -> bool:
    """The automaton reproduces the colony's own table (n = 1..5000); otherwise it is not used."""
    if word not in _VERIFIED:
        tab = (getattr(T, "t", {}) or {}).get(word)
        _VERIFIED[word] = bool(tab) and len(tab) > 100 and all(
            _run(word, n) == tab[n] for n in range(1, min(len(tab), 5001)))
    return _VERIFIED[word]


@lru_cache(maxsize=4096)
def reachable(word: str, M: int) -> dict[int, frozenset[int]]:
    """{t: values the word takes at some n >= 1 with n = t (mod M)} (exact)."""
    s0, d, out = WORDS[word]
    seen = set()
    stack = [(s0, 0, 1 % M, 0)]
    vals: dict[int, set[int]] = {}
    while stack:
        st = stack.pop()
        if st in seen:
            continue
        seen.add(st)
        s, r, pw, last = st
        if last:
            vals.setdefault(r, set()).add(out[s])
        for bit in (0, 1):
            stack.append((d[s][bit], (r + bit * pw) % M, (2 * pw) % M, bit))
    return {t: frozenset(v) for t, v in vals.items()}


# ----------------------------------------------------------------------------- residue facts
def _bm_gf(seq: list[int], p: int) -> list[int] | None:
    """Berlekamp-Massey over GF(p): connection polynomial C (C[0] = 1) or None."""
    C, B = [1], [1]
    L, m, b = 0, 1, 1
    for n in range(len(seq)):
        d = seq[n]
        for i in range(1, L + 1):
            d = (d + C[i] * seq[n - i]) % p
        if d == 0:
            m += 1
            continue
        coef = d * pow(b, p - 2, p) % p
        T_ = list(C)
        C = C + [0] * (len(B) + m - len(C))
        for i, x in enumerate(B):
            C[i + m] = (C[i + m] - coef * x) % p
        if 2 * L <= n:
            L, B, b, m = n + 1 - L, T_, d, 1
        else:
            m += 1
    return C[:L + 1]


def _isprime(m: int) -> bool:
    return m > 1 and all(m % d for d in range(2, int(m ** 0.5) + 1))


_FACTS: dict[tuple[str, int, int], dict[str, Any] | None] = {}


def residue_fact(name: str, m: int, T: Any) -> dict[str, Any] | None:
    """A fact giving name(n) mod m for every n >= 1, or None.

    {'kind': 'period', 'pre': t0, 'P': P, 'vals': [...]}  residues periodic from n = t0
    Built from a Berlekamp-Massey recurrence over GF(m) (m prime) or a pure period, confirmed on
    the whole table with >= 3 repetitions."""
    tab = (getattr(T, "t", {}) or {}).get(name)
    if not tab:
        return None
    key = (name, m, len(tab))
    if key in _FACTS:
        return _FACTS[key]
    res = None
    if name == "one" or name.startswith("_c"):
        res = {"kind": "period", "pre": 1, "P": 1, "how": "constant", "vals": {1: tab[1] % m}}
    elif name == "n":
        res = {"kind": "period", "pre": 1, "P": m, "how": "n mod m", "vals": {t: t % m for t in range(1, m + 1)}}
    else:
        r = [x % m for x in tab[1:min(len(tab), 20001)]]   # r[i] = a(i+1) mod m
        N = len(r)
        res = _period_of(r, m)
        if res is None and _isprime(m) and N >= 60:
            res = _bm_period(r, m)
    _FACTS[key] = res
    return res


def _period_of(r: list[int], m: int) -> dict[str, Any] | None:
    N = len(r)
    for t0 in (0, 2, 8, 20):
        if t0 >= N // 4:
            break
        for P in range(1, min(PERIOD_MAX, (N - t0) // 3) + 1):
            if all(r[i] == r[i + P] for i in range(t0, N - P)):
                vals = {t0 + 1 + j: r[t0 + j] for j in range(P)}
                return {"kind": "period", "pre": t0 + 1, "P": P, "vals": vals,
                        "how": f"residues mod {m} periodic (period {P} from n={t0 + 1}), confirmed on {N} terms"}
    return None


def _bm_period(r: list[int], p: int) -> dict[str, Any] | None:
    use = r[:BM_TERMS]
    C = _bm_gf(use, p)
    if C is None:
        return None
    L = len(C) - 1
    if L == 0 or L > BM_MAX_ORDER or 2 * L + 20 > len(use):
        return None
    # confirm the recurrence on ALL data
    for n in range(L, len(r)):
        if sum(C[i] * r[n - i] for i in range(L + 1)) % p:
            return None
    # extend by the recurrence until the state repeats -> exact period of the recurrence
    seen: dict[tuple, int] = {}
    seq = list(r[:L])
    i = 0
    while True:
        st = tuple(seq[i:i + L])
        if st in seen:
            pre, P = seen[st], i - seen[st]
            break
        seen[st] = i
        nxt = (-sum(C[j] * seq[i + L - j] for j in range(1, L + 1))) % p
        seq.append(nxt)
        i += 1
        if i > 200000:
            return None
    vals = {pre + 1 + j: seq[pre + j] for j in range(P)}
    return {"kind": "period", "pre": pre + 1, "P": P, "vals": vals,
            "how": f"C-finite mod {p}: order-{L} recurrence over GF({p}) (Berlekamp-Massey, confirmed on "
                   f"{len(r)} terms), period {P}"}


def _at(f: dict[str, Any], n: int) -> int | None:
    pre, P = f["pre"], f["P"]
    if n < pre:
        return None          # before the periodic part: no fact (those n are checked on data)
    return f["vals"][pre + (n - pre) % P]


# ----------------------------------------------------------------------------- decomposition
def _affine(e: tuple) -> tuple[str, int, int] | None:
    """('p', w) under sh / dbl -> (w, a, b): value w(a n + b)."""
    if e[0] == "p":
        return e[1], 1, 0
    if e[0] in ("sh", "dbl"):
        x = _affine(e[1])
        if x is None:
            return None
        w, a, b = x
        return (w, a, a + b) if e[0] == "sh" else (w, 2 * a, b)
    return None


def _words_in(e: tuple, out: list) -> None:
    x = _affine(e)
    if x is not None:
        if x[0] in WORDS:
            out.append((e, x))
        return
    if e[0] in ("+", "-", "*", "gcd"):
        for s in e[1:]:
            _words_in(s, out)


def _subst_consts(e: tuple, consts: dict[str, int]) -> tuple:
    from colony.frontier_conjectures import canon
    k = canon(e)
    if k in consts:
        return ("c", consts[k])
    if e[0] in ("+", "-", "*", "gcd"):
        return (e[0],) + tuple(_subst_consts(s, consts) for s in e[1:])
    return e


def _simplify(e: tuple) -> tuple:
    if e[0] not in ("+", "-", "*", "gcd"):
        return e
    a, b = _simplify(e[1]), _simplify(e[2])
    ca = a[1] if a[0] == "c" else None
    cb = b[1] if b[0] == "c" else None
    if ca is not None and cb is not None:
        return ("c", {"+": ca + cb, "-": ca - cb, "*": ca * cb, "gcd": math.gcd(ca, cb)}[e[0]])
    if e[0] == "*" and 0 in (ca, cb):
        return ("c", 0)
    if e[0] == "*" and ca == 1:
        return b
    if e[0] == "*" and cb == 1:
        return a
    if e[0] == "gcd" and (ca in (1, -1) or cb in (1, -1)):
        return ("c", 1)
    if e[0] == "gcd" and ca == 0:
        return ("abs", b)
    if e[0] == "gcd" and cb == 0:
        return ("abs", a)
    if e[0] in ("+", "-") and cb == 0:
        return a
    if e[0] == "+" and ca == 0:
        return b
    return (e[0], a, b)


class _Undecided(Exception):
    pass


def _expand(e: tuple) -> tuple:
    """D(x) = sh(x) - x when x is a primitive under shifts / a(2n), so the words inside are visible."""
    if e[0] == "D" and _affine(e[1]) is not None:
        x = _expand(e[1])
        return ("-", ("sh", x), x)
    if e[0] in ("+", "-", "*", "gcd"):
        return (e[0],) + tuple(_expand(s) for s in e[1:])
    if e[0] in ("S", "D", "sh", "dbl"):
        return (e[0], _expand(e[1]))
    return e


def _lcm(a: int, b: int) -> int:
    return a * b // math.gcd(a, b)


class _Ctx:
    def __init__(self, m: int, T: Any):
        self.m, self.T, self.facts = m, T, {}

    def fact(self, w: str) -> dict[str, Any]:
        if w in WORDS:
            raise _Undecided("word not resolved by its residue class")
        if w not in self.facts:
            f = residue_fact(w, self.m, self.T)
            if f is None:
                raise _Undecided(w)
            self.facts[w] = f
        return self.facts[w]

    def shape(self, e: tuple) -> tuple[int, int]:
        """(pre, P): the residues of e mod m are periodic with period P for n >= pre."""
        if e[0] == "c":
            return 1, 1
        x = _affine(e)
        if x is not None:
            w, a, b = x
            f = self.fact(w)
            return max(1, -(-(f["pre"] - b) // a)), f["P"]
        op = e[0]
        if op == "abs":
            return self.shape(e[1])
        if op in ("sh", "dbl", "D", "S"):
            pre, P = self.shape(e[1])
            if op == "sh":
                return max(1, pre - 1), P
            if op == "dbl":
                return max(1, -(-pre // 2)), P
            if op == "D":
                return pre, P
            return pre, P * self.m          # S(n + mP) = S(n) + m * (sum over a period)
        if op in ("+", "-", "*") or (op == "gcd" and self.m == 2):
            (p1, q1), (p2, q2) = self.shape(e[1]), self.shape(e[2])
            return max(p1, p2), _lcm(q1, q2)
        raise _Undecided(op)   # gcd mod m > 2, composition o, ...

    def values(self, e: tuple, N: int) -> list[int]:
        """[e(1), ..., e(N)] mod m, exact: real data before each fact's periodic part, the fact after."""
        m = self.m
        if e[0] == "c":
            return [e[1] % m] * N
        x = _affine(e)
        if x is not None:
            w, a, b = x
            f, tab = self.fact(w), self.T.t[w]
            out = []
            for n in range(1, N + 1):
                i = a * n + b
                if i >= f["pre"]:
                    out.append(f["vals"][f["pre"] + (i - f["pre"]) % f["P"]])
                elif 0 <= i < len(tab):
                    out.append(tab[i] % m)
                else:
                    raise _Undecided("index")
            return out
        op = e[0]
        if op == "abs":
            return self.values(e[1], N)
        if op == "sh":
            return self.values(e[1], N + 1)[1:]
        if op == "dbl":
            v = self.values(e[1], 2 * N)
            return [v[2 * n - 1] for n in range(1, N + 1)]
        if op == "D":
            v = self.values(e[1], N + 1)
            return [(v[i + 1] - v[i]) % m for i in range(N)]
        if op == "S":
            v, s, out = self.values(e[1], N), 0, []
            for x_ in v:
                s = (s + x_) % m
                out.append(s)
            return out
        a_, b_ = self.values(e[1], N), self.values(e[2], N)
        if op == "gcd":   # m = 2: gcd(x, y) is even iff x and y are both even (gcd(0, 0) = 0)
            return [1 if (x_ or y_) else 0 for x_, y_ in zip(a_, b_)]
        return [{"+": x_ + y_, "-": x_ - y_, "*": x_ * y_}[op] % m for x_, y_ in zip(a_, b_)]


def _abs_safe(e: tuple, m: int, T: Any) -> bool:
    """|y| = y (mod m) is only safe when m = 2 or y >= 0 on all data."""
    from colony.frontier_conjectures import evaluate, max_n
    stack = [e]
    while stack:
        x = stack.pop()
        if x[0] == "abs" and m != 2:
            N = max_n(x[1], T, 5000)
            v = evaluate(x[1], N, T) if N else None
            if not v or min(v) < 0:
                return False
        stack += [s for s in x[1:] if isinstance(s, tuple)]
    return True


def explain(c: dict[str, Any], T: Any) -> dict[str, Any] | None:
    """{'label': 'known_in_principle(...)', 'facts': [...], ...} when the congruence / residue pattern
    is implied by component facts, or (mod 2) by the components' definitions reduced mod 2 and
    elementary prime / divisor parity facts (colony.definition_parity), else None."""
    ex = _explain_components(c, T)
    if ex is None:
        try:
            from colony import definition_parity as _DPAR
            ex = _DPAR.explain(c, T)
        except Exception:  # noqa: BLE001
            ex = None
    return ex


def _explain_components(c: dict[str, Any], T: Any) -> dict[str, Any] | None:
    """Automaton-word / residue-fact decomposition (the 2026-10-23 compositional check)."""
    from colony.frontier_conjectures import _push, canon
    kind = c.get("kind")
    if kind not in ("cong", "modpat") or c.get("_re") is not None:
        return None
    prm = c.get("params") or {}
    m = int(prm.get("m") or 0)
    if m < 2:
        return None
    e = _expand(_push(c["_le"]))
    q, s = (int(prm["q"]), int(prm["s"]) % int(prm["q"])) if kind == "cong" else (1, 0)
    occ: list = []
    _words_in(e, occ)
    if any(not word_ok(w[1][0], T) for w in occ):
        return None
    branches, Q = None, q
    for f in REFINE:
        Q = q * f
        if Q > MAX_CLASS_MOD:
            return None
        br, ok = [], True
        for t in range(Q):
            if t % q != s:
                continue
            consts = {}
            for sub, (w, a, b) in occ:
                M = a * Q
                vs = reachable(w, M).get((a * t + b) % M, frozenset())
                if len(vs) > 1:
                    ok = False
                    break
                if vs:
                    consts[canon(sub)] = next(iter(vs))
            if not ok:
                break
            br.append((t, consts))
        if ok:
            branches = br
            break
    if branches is None:
        return None
    ctx = _Ctx(m, T)
    Pm = int(prm["P"]) if kind == "modpat" else 1
    try:
        plan = []
        for t, consts in branches:
            r_e = _simplify(_subst_consts(e, consts))
            if not _abs_safe(r_e, m, T):
                return None
            pre, P = ctx.shape(r_e)
            per = _lcm(_lcm(P, Q), Pm)
            if pre + per > MAX_CHECK:
                return None
            plan.append((t, consts, r_e, pre + per))
        span = 0
        for t, consts, r_e, N in plan:
            v = ctx.values(r_e, N)
            for n in range(1, N + 1):
                if n % Q != t:
                    continue
                want = int(prm["r"]) % m if kind == "cong" else int(prm["pat"][(n - 1) % Pm]) % m
                if v[n - 1] != want:
                    return None      # the component facts say the claim fails somewhere
            span = max(span, N)
    except _Undecided:
        return None
    facts = []
    for sub, (w, a, b) in occ:
        idx = "n" if (a, b) == (1, 0) else f"{a}n{'+' + str(b) if b else ''}"
        facts.append(f"{w}({idx}) is constant on each class n mod {Q} where the claim uses it "
                     f"(exact automaton residue reachability, mod {a * Q})")
    for p, f_ in sorted(ctx.facts.items()):
        facts.append(f"{p}: " + str(f_.get("how", "")))
    return {"label": "known_in_principle(component_facts)", "facts": sorted(set(facts)),
            "classes_mod": Q, "word_constants": {str(t): k for t, k in branches if k},
            "checked_n": span,
            "scope": "implied for all n >= 1: the claim's residues are periodic once every component's are, "
                     "and one full period plus the pre-period was checked from the component facts and data"}
