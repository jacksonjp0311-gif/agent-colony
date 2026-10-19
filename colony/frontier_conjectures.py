"""Frontier conjecture generator — the colony forms its OWN conjectures from data it computes.

COLONY_FRONTIER=live|shadow|off (code default shadow). REPORT-ONLY in shadow: it never touches
scores, P, the Oracle, the 0.70 bar, desk decisions, the charter, TributeKeeper or Ceiling.

Mechanism (no hardcoded targets — a menu of target KINDS; the colony picks the instances):
1. Expressions. A small grammar over integer sequences a(n), n >= 1: primitives (n, 1, phi,
   sigma, tau, omega, bigomega, mu, rad, lpf, gpf, sopfr, digit sum, popcount, pi, prime(n),
   squarefree indicator, 2^n, Fibonacci, Lucas, Pell, partitions) and operators (prefix sum S,
   difference D, shift a(n+1), a(2n), +, -, *, gcd, composition f(g(n))). The colony samples
   expressions with its own UCB weights over primitives/operators: weight grows with how often a
   choice produced a surviving, unknown claim and with how little it was tried (state file).
2. Conjecture kinds fitted on n = 1..FIT_N only: identity E1 = E2; divisibility E1 | E2;
   tight inequality E1 <= E2 (some equality and some strict points); congruence
   E = r (mod m) on a residue class n = s (mod q); linear recurrence of order <= 4.
3. Filters before testing: trivial rewrites (formal identities — still true when every primitive
   is replaced by independent random sequences; or "shuffle-null": still true when each
   primitive's values are shuffled, i.e. it does not depend on arithmetic at all) and
   duplicates (canonical form AND fitted-value signature) are dropped and counted.
4. Pre-registration: before a claim is tested its predicted survival probability (Beta-smoothed
   survival rate of that kind so far) is recorded; calibration is scored (Brier).
5. Falsification Oracle: the claim is tested on held-out n far beyond the fit range (dense,
   to HELD_CHEAP / HELD_EXP). Survivors are "conjecture surviving N checks", never "proved".
   Survivors are re-tested on a farther range in later cycles; a surprise that later fails is a
   FALSE SURPRISE and is reported.
6. Proof path where decidable: identities / recurrences between C-finite expressions (built from
   n, 1, 2^n, Fibonacci, Lucas, Pell with +, -, *, S, D, shifts, a(2n)) are machine-checked by
   the order bound (a C-finite sequence of order <= d that vanishes on d consecutive terms is
   zero); congruences of such sequences by exhausting the periodic state space mod m. These are
   labelled "machine-checked (certificate)"; everything else stays "survives testing".
7. Surprise = survived held-out AND not trivial AND not a duplicate AND no involved derived
   sequence is in the OEIS (local stripped.gz index; "OEIS unchecked" when absent — then it is
   NOT counted as a surprise). Hunt value = surprise * K/(s+K) (s = earlier surprises of the same
   family = kind + primitive set; K = colony.hunt_shadow.K_PRIOR).
State: society/systems/frontier_conjectures.json (overwritten; bounded registry; counts history).
"""
from __future__ import annotations

import json
import math
import os
import random
import hashlib
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "society" / "systems" / "frontier_conjectures.json"
CALIBRATION = ROOT / "colony" / "frontier_calibration.json"
MODES = ("live", "shadow", "off")

FIT_N_DEFAULT = 30
HELD_CHEAP = 20000      # dense held-out for arithmetic-only claims
HELD_EXP = 2000         # dense held-out when exponential-growth primitives are involved
RETEST_CHEAP = 60000
RETEST_EXP = 4000
LIM = 400000            # arithmetic primitives tabulated to here
N_EXPR = 260
PAIR_BUDGET = 4000
MAX_TEST = 40
REGISTRY_CAP = 150
RETEST_PER_CYCLE = 25
KEEP_CYCLES = 30
SIG_CAP = 2000
MODS = (2, 3, 4, 5, 6, 7, 8, 9, 10, 12)
QS = (1, 2, 3, 4, 6)
MAX_REC = 4
PERIOD = 12  # parts periodic mod m with this period make a congruence a rewrite

ARITH = ("n", "one", "phi", "sigma", "tau", "omega", "bigomega", "mu", "rad", "lpf", "gpf", "sopfr",
         "digsum", "popcount", "pi", "prime", "sqfree")
# Wider menu (COLONY_FRONTIER_MENU=wide): sequences from open problems, as generator ingredients only.
# Nothing definable from the base menu is added (prime gaps are D(prime), aliquot s(n) is sigma - n),
# so no definitional identity can masquerade as a find.
WIDE = ("csteps", "cmax", "maxgap", "gold", "cheb4", "cheb3", "ds3", "rev")
ARITH = ARITH + WIDE
EXPO = ("pow2", "fib", "lucas", "pell", "part")
# New ingredients (COLONY_FRONTIER_INGREDIENTS; colony/frontier_ingredients.py): graph invariants,
# restricted partitions, matrix sequences. Tabulated always; sampled only when active().
from colony import frontier_ingredients as _ING  # noqa: E402
ARITH = ARITH + _ING.CHEAP
EXPO = EXPO + _ING.EXPO_NEW
PRIMS = ARITH + EXPO
WIDE_QS = (5, 7, 11)     # residue classes for Ramanujan-type congruences
WIDE_MODS = (11,)
CONG_FIT_PER_CLASS = 6   # wide menu: congruence on n = s (mod q) fitted on 6 members of the class
MODPAT_MODS = (2, 3, 4, 5)
MODPAT_MAX_P = 12
CF_ORDER = {"n": 2, "one": 1, "pow2": 1, "fib": 2, "lucas": 2, "pell": 2} | _ING.CF_ORDER_NEW
OPS = ("p", "S", "D", "sh", "dbl", "+", "-", "*", "gcd", "o")
POSITIVE = {"n", "one", "phi", "sigma", "tau", "rad", "lpf", "gpf", "prime", "digsum", "popcount",
            "cmax", "maxgap", "ds3", "rev"} | set(_ING.POSITIVE_NEW)


def menu() -> str:
    """COLONY_FRONTIER_MENU: base (old ingredients) | wide (adds WIDE primitives, residue classes
    mod 5/7/11 and the mod-m pattern claim kind). The filter and the Oracle are the same for both."""
    v = os.environ.get("COLONY_FRONTIER_MENU", "base").strip().lower()
    return "wide" if v == "wide" else "base"


def menu_prims() -> tuple[str, ...]:
    ps = PRIMS if menu() == "wide" else tuple(k for k in PRIMS if k not in WIDE)
    return ps if _ING.active() else tuple(k for k in ps if k not in _ING.NEW)


def mode() -> str:
    m = os.environ.get("COLONY_FRONTIER", "shadow").strip().lower()
    return m if m in MODES else "shadow"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_calibration(path: Path = CALIBRATION) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def fit_n() -> int:
    try:
        return int(load_calibration().get("FIT_N") or FIT_N_DEFAULT)
    except Exception:  # noqa: BLE001
        return FIT_N_DEFAULT


# ----------------------------------------------------------------------------- primitives

class Tables:
    """Primitive values a[0..L] (index 0 unused, kept as 0)."""

    def __init__(self, lim: int = LIM, exp_n: int = 2 * RETEST_EXP + 4):
        self.lim, self.exp_n = lim, exp_n
        self.t: dict[str, list[int]] = {}
        self._arith(lim)
        self._expo(exp_n)
        _ING.extend(self)

    def _arith(self, L: int) -> None:
        spf = list(range(L + 1))
        for i in range(2, int(L ** 0.5) + 1):
            if spf[i] == i:
                for j in range(i * i, L + 1, i):
                    if spf[j] == j:
                        spf[j] = i
        names = ("phi", "sigma", "tau", "omega", "bigomega", "mu", "rad", "lpf", "gpf", "sopfr", "sqfree")
        out = {k: [0] * (L + 1) for k in names}
        for k in names:
            out[k][1] = 1 if k in ("phi", "sigma", "tau", "mu", "rad", "lpf", "gpf", "sqfree") else 0
        for n in range(2, L + 1):
            m, phi, sig, tau, om, bom, rad, sop, mu, sq, gp = n, n, 1, 1, 0, 0, 1, 0, 1, 1, 1
            while m > 1:
                p, e = spf[m], 0
                while m % p == 0:
                    m //= p
                    e += 1
                phi = phi // p * (p - 1)
                sig *= (p ** (e + 1) - 1) // (p - 1)
                tau *= e + 1
                om += 1
                bom += e
                rad *= p
                sop += p * e
                gp = p
                if e > 1:
                    mu, sq = 0, 0
                else:
                    mu = -mu
            row = (phi, sig, tau, om, bom, mu, rad, spf[n], gp, sop, sq)
            for k, v in zip(names, row):
                out[k][n] = v
        self.t.update(out)
        self.t["n"] = list(range(L + 1))
        self.t["one"] = [0] + [1] * L
        self.t["digsum"] = [sum(map(int, str(i))) for i in range(L + 1)]
        self.t["popcount"] = [bin(i).count("1") for i in range(L + 1)]
        pi, c = [0] * (L + 1), 0
        for i in range(2, L + 1):
            if spf[i] == i:
                c += 1
            pi[i] = c
        self.t["pi"] = pi
        # prime(n) needs primes beyond L: plain sieve to ~ L*15
        P = int(L * 15)
        s = bytearray([1]) * (P + 1)
        s[0:2] = b"\x00\x00"
        for i in range(2, int(P ** 0.5) + 1):
            if s[i]:
                s[i * i::i] = bytearray(len(range(i * i, P + 1, i)))
        primes = [i for i in range(P + 1) if s[i]]
        self.t["prime"] = [0] + primes[:L]
        self._wide(L, s, primes)

    def _wide(self, L: int, sieve: bytearray, primes: list[int]) -> None:
        """Open-problem-derived ingredients, n = 1..L (index 0 unused)."""
        cs, cm = [0] * (L + 1), [0] * (L + 1)   # Collatz total stopping time, max excursion
        cs[1], cm[1] = 0, 1
        for n in range(2, L + 1):
            v, k, mx = n, 0, n
            while v >= n:
                v = v // 2 if v % 2 == 0 else 3 * v + 1
                k += 1
                if v > mx:
                    mx = v
            cs[n], cm[n] = k + cs[v], max(mx, cm[v])
        mg, best = [0] * (L + 1), 0                # record prime gap among the first n+1 primes
        for n in range(1, L + 1):
            best = max(best, primes[n] - primes[n - 1])
            mg[n] = best
        try:                                       # Goldbach: #{p <= q primes : p + q = 2n}
            import numpy as _np
            M = 2 * L + 1
            ind = _np.frombuffer(bytes(sieve[:M]), dtype=_np.uint8).astype(_np.float64)
            sz = 1 << (2 * M - 1).bit_length()
            f = _np.fft.rfft(ind, sz)
            conv = _np.rint(_np.fft.irfft(f * f, sz)[:M]).astype(_np.int64)
            gold = [0] * (L + 1)
            for n in range(1, L + 1):
                gold[n] = int((conv[2 * n] + sieve[n]) // 2)
        except Exception:  # noqa: BLE001
            G = min(L, 30000)
            ps = [p for p in primes if p <= 2 * G]
            gold = [0] * (G + 1)
            for i, p in enumerate(ps):
                for q in ps[i:]:
                    if p + q > 2 * G:
                        break
                    if (p + q) % 2 == 0:
                        gold[(p + q) // 2] += 1
        c4, c3, a4, a3 = [0] * (L + 1), [0] * (L + 1), 0, 0   # prime races: #(3 mod 4) - #(1 mod 4) etc.
        for n in range(1, L + 1):
            if sieve[n]:
                a4 += 1 if n % 4 == 3 else (-1 if n % 4 == 1 else 0)
                a3 += 1 if n % 3 == 2 else (-1 if n % 3 == 1 else 0)
            c4[n], c3[n] = a4, a3

        def ds3(n: int) -> int:
            t = 0
            while n:
                t += n % 3
                n //= 3
            return t
        self.t.update({"csteps": cs, "cmax": cm, "maxgap": mg, "gold": gold, "cheb4": c4, "cheb3": c3,
                       "ds3": [ds3(i) for i in range(L + 1)], "rev": [int(str(i)[::-1]) for i in range(L + 1)]})

    def _expo(self, N: int) -> None:
        f, l, pe, p2 = [0, 1, 1], [0, 1, 3], [0, 1, 2], [0, 2]
        for i in range(3, N + 1):
            f.append(f[-1] + f[-2])
            l.append(l[-1] + l[-2])
            pe.append(2 * pe[-1] + pe[-2])
        for i in range(2, N + 1):
            p2.append(p2[-1] * 2)
        part = [1] + [0] * N  # p(0..N) by Euler pentagonal recurrence
        for n in range(1, N + 1):
            s, k = 0, 1
            while True:
                g1 = k * (3 * k - 1) // 2
                if g1 > n:
                    break
                sg = 1 if k % 2 else -1
                s += sg * part[n - g1]
                g2 = k * (3 * k + 1) // 2
                if g2 <= n:
                    s += sg * part[n - g2]
                k += 1
            part[n] = s
        self.t.update({"fib": f[:N + 1], "lucas": l[:N + 1], "pell": pe[:N + 1], "pow2": p2[:N + 1],
                       "part": part[:N + 1]})

    def size(self, name: str) -> int:
        return len(self.t[name]) - 1


_TABLES: Tables | None = None


def tables() -> Tables:
    global _TABLES
    if _TABLES is None:
        _TABLES = Tables()
    return _TABLES


# ----------------------------------------------------------------------------- expressions
# e = ("p", name) | (op1, e) for S D sh dbl | (op2, e1, e2) for + - * gcd | ("o", outer_name, e)

def canon(e: tuple) -> str:
    op = e[0]
    if op == "p":
        return e[1]
    if op in ("S", "D", "sh", "dbl"):
        return f"{op}({canon(e[1])})"
    if op == "o":
        return f"{e[1]}[{canon(e[2])}]"
    a, b = canon(e[1]), canon(e[2])
    if op in ("+", "*", "gcd") and b < a:
        a, b = b, a
    return f"({a}{op}{b})" if op != "gcd" else f"gcd({a},{b})"


def prims_of(e: tuple) -> set[str]:
    if e[0] == "p":
        return {e[1]}
    if e[0] == "o":
        return {e[1]} | prims_of(e[2])
    return set().union(*(prims_of(x) for x in e[1:]))


def size(e: tuple) -> int:
    if e[0] == "p":
        return 1
    if e[0] == "o":
        return 2 + size(e[2])
    return 1 + sum(size(x) for x in e[1:])


def is_expo(e: tuple) -> bool:
    return bool(prims_of(e) & set(EXPO))


def cf_order(e: tuple) -> int | None:
    """Upper bound on the C-finite order, None when not provably C-finite."""
    op = e[0]
    if op == "p":
        return 1 if e[1].startswith("_c") else CF_ORDER.get(e[1])
    if op in ("o", "gcd"):
        return None
    if op in ("S",):
        d = cf_order(e[1])
        return None if d is None else d + 1
    if op in ("D", "sh", "dbl"):
        return cf_order(e[1])
    a, b = cf_order(e[1]), cf_order(e[2])
    if a is None or b is None:
        return None
    return a + b if op in ("+", "-") else a * b


def evaluate(e: tuple, N: int, T: Any, tab: dict[str, list[int]] | None = None) -> list[int] | None:
    """[a(1)..a(N)] or None when out of tabulated range. ``tab`` overrides primitive tables."""
    t = tab if tab is not None else T.t
    op = e[0]
    if op == "p":
        arr = t[e[1]] if e[1] in t else T.t[e[1]]
        return None if len(arr) <= N else arr[1:N + 1]
    if op == "S":
        x = evaluate(e[1], N, T, tab)
        if x is None:
            return None
        out, s = [], 0
        for v in x:
            s += v
            out.append(s)
        return out
    if op in ("D", "sh"):
        x = evaluate(e[1], N + 1, T, tab)
        if x is None:
            return None
        return [x[i + 1] - x[i] for i in range(N)] if op == "D" else x[1:]
    if op == "dbl":
        x = evaluate(e[1], 2 * N, T, tab)
        return None if x is None else x[1::2]
    if op == "o":
        x = evaluate(e[2], N, T, tab)
        arr = t[e[1]] if e[1] in t else T.t[e[1]]
        if x is None or not x or min(x) < 1 or max(x) >= len(arr):
            return None
        return [arr[v] for v in x]
    a, b = evaluate(e[1], N, T, tab), evaluate(e[2], N, T, tab)
    if a is None or b is None:
        return None
    if op == "+":
        return [x + y for x, y in zip(a, b)]
    if op == "-":
        return [x - y for x, y in zip(a, b)]
    if op == "*":
        return [x * y for x, y in zip(a, b)]
    return [math.gcd(x, y) for x, y in zip(a, b)]


def max_n(e: tuple, T: Any, cap: int) -> int:
    """Largest N <= cap (from a short ladder) for which ``e`` evaluates."""
    for N in (cap, cap // 2, cap // 4, cap // 10, cap // 20, cap // 40):
        if N > 0 and evaluate(e, N, T) is not None:
            return N
    return 0


# ----------------------------------------------------------------------------- sampling

def ucb_weights(stats: dict[str, list[int]], keys: tuple[str, ...]) -> dict[str, float]:
    T = sum((stats.get(k) or [0, 0])[0] for k in keys) + 1
    out = {}
    for k in keys:
        tries, good = (stats.get(k) or [0, 0])[:2]
        out[k] = (good + 1) / (tries + 2) + 0.5 * math.sqrt(math.log(T + 1) / (tries + 1))
    return out


def _choice(rng: random.Random, w: dict[str, float], allowed: tuple[str, ...]) -> str:
    ks = [k for k in allowed if k in w]
    return rng.choices(ks, weights=[w[k] for k in ks])[0]


def sample_expressions(rng: random.Random, n: int, state: dict[str, Any]) -> list[tuple]:
    PRIMS = menu_prims()  # noqa: N806 (menu-limited ingredients)
    ARITH = tuple(k for k in globals()["ARITH"] if k in PRIMS)  # noqa: N806
    pw = ucb_weights(state.get("prim_stats") or {}, PRIMS)
    ow = ucb_weights(state.get("op_stats") or {}, OPS)
    seen, out = set(), []
    tries = 0
    while len(out) < n and tries < n * 20:
        tries += 1
        op = _choice(rng, ow, OPS)
        p = lambda allowed=PRIMS: ("p", _choice(rng, pw, allowed))  # noqa: E731
        if op == "p":
            e = p(tuple(k for k in PRIMS if k != "one"))
        elif op in ("S", "D", "sh", "dbl"):
            inner = p(tuple(k for k in PRIMS if k != "one"))
            if rng.random() < 0.3:
                op2 = _choice(rng, ow, ("+", "-", "*", "gcd"))
                inner = (op2, inner, p(PRIMS if op2 in ("+", "-") else tuple(k for k in PRIMS if k != "one")))
            e = (op, inner)
        elif op == "o":
            e = ("o", _choice(rng, pw, ARITH[2:]), p(tuple(k for k in POSITIVE if k != "one" and k in PRIMS)))
        else:
            second = PRIMS if op in ("+", "-") else tuple(k for k in PRIMS if k != "one")
            e = (op, p(tuple(k for k in PRIMS if k != "one")), p(second))
        c = canon(e)
        if c not in seen:
            seen.add(c)
            out.append(e)
    return out


# ----------------------------------------------------------------------------- claims

def holds(kind: str, params: dict[str, Any], a: list[int], b: list[int] | None, start: int = 1) -> tuple[bool, int]:
    """(holds on every point, number of checks). ``start`` = n of a[0]."""
    n_chk = 0
    if kind == "identity":
        for x, y in zip(a, b):
            n_chk += 1
            if x != y:
                return False, n_chk
        return True, n_chk
    if kind == "divides":
        for x, y in zip(a, b):
            n_chk += 1
            if x == 0 or y % x:
                return False, n_chk
        return True, n_chk
    if kind == "le":
        for x, y in zip(a, b):
            n_chk += 1
            if x > y:
                return False, n_chk
        return True, n_chk
    if kind == "cong":
        m, r, q, s = params["m"], params["r"], params["q"], params["s"]
        for i, x in enumerate(a):
            if (start + i) % q == s:
                n_chk += 1
                if x % m != r:
                    return False, n_chk
        return True, n_chk
    if kind == "modpat":
        m, P, pat = params["m"], params["P"], params["pat"]
        for i, x in enumerate(a):
            n_chk += 1
            if x % m != pat[(start + i - 1) % P]:
                return False, n_chk
        return True, n_chk
    if kind == "rec":
        c = params["c"]  # a(n+k) = sum c[i] a(n+i), integer coefficients
        k = len(c)
        for i in range(len(a) - k):
            n_chk += 1
            if a[i + k] != sum(ci * a[i + j] for j, ci in enumerate(c)):
                return False, n_chk
        return True, n_chk
    raise ValueError(kind)


def berlekamp_massey_int(x: list[int], max_order: int = MAX_REC) -> list[int] | None:
    """Shortest recurrence over Q; returned only when it has integer coefficients and order <= max."""
    s = [Fraction(v) for v in x]
    C, B = [Fraction(1)], [Fraction(1)]
    L, m, b = 0, 1, Fraction(1)
    for n in range(len(s)):
        d = s[n] + sum(C[i] * s[n - i] for i in range(1, L + 1))
        if d == 0:
            m += 1
            continue
        coef = d / b
        T_ = C[:]
        C = C + [Fraction(0)] * (len(B) + m - len(C))
        for i, bi in enumerate(B):
            C[i + m] -= coef * bi
        if 2 * L <= n:
            L, B, b, m = n + 1 - L, T_, d, 1
        else:
            m += 1
    if L == 0 or L > max_order or 2 * L + 6 > len(s):
        return None
    C = (C + [Fraction(0)] * (L + 1))[:L + 1]
    rec = [-C[L - j] for j in range(L)]  # a(n+L) = sum rec[j] a(n+j)
    if any(r.denominator != 1 for r in rec):
        return None
    return [int(r) for r in rec]


def _h(text: str) -> str:
    return hashlib.blake2b(text.encode(), digest_size=6).hexdigest()


def claim_id(kind: str, lhs: str, rhs: str, params: dict[str, Any]) -> str:
    ps = json.dumps(params, sort_keys=True)
    return f"{kind}|{lhs}|{rhs}|{ps}"


def statement(c: dict[str, Any]) -> str:
    k, L, R, p = c["kind"], c["lhs"], c["rhs"], c["params"]
    if k == "identity":
        return f"{L}(n) = {R}(n) for all n >= 1"
    if k == "divides":
        return f"{L}(n) divides {R}(n) for all n >= 1"
    if k == "le":
        return f"{L}(n) <= {R}(n) for all n >= 1 (with equality at some n)"
    if k == "cong":
        cls = "all n >= 1" if p["q"] == 1 else f"all n = {p['s']} (mod {p['q']})"
        return f"{L}(n) = {p['r']} (mod {p['m']}) for {cls}"
    if k == "modpat":
        return f"{L}(n) mod {p['m']} depends only on n mod {p['P']} (residues {p['pat']} for n = 1..{p['P']}), all n >= 1"
    if k == "rec":
        k_ = len(p["c"])
        terms = " + ".join(f"{ci}*a(n+{j})" for j, ci in enumerate(p["c"]) if ci)
        return f"a(n) = {L}(n) satisfies a(n+{k_}) = {terms or '0'}"
    return k


def _random_tables(rng: random.Random, T: Any, mode_: str) -> dict[str, list[int]]:
    """'random' = independent random sequences; 'shuffle' = each primitive's own values permuted."""
    out = {}
    for k, arr in T.t.items():
        if k.startswith("_c"):      # case-split constants stay constant
            out[k] = arr
            continue
        n = min(len(arr), 400)
        if mode_ == "random":
            out[k] = [0] + [rng.randint(1, 1000) for _ in range(n - 1)]
        else:
            vals = arr[1:n]
            vals = vals[:]
            rng.shuffle(vals)
            out[k] = [0] + vals
    return out


def _distribute(e: tuple) -> tuple:
    """Push a shift / a(2n) through + - *, and S / D through + -, so the parts are visible."""
    if e[0] in ("S", "D") and e[1][0] in ("+", "-"):   # linear operators split over + and -
        inner = e[1]
        return (inner[0], (e[0], inner[1]), (e[0], inner[2]))
    if e[0] in ("sh", "dbl") and e[1][0] in ("+", "-", "*"):
        inner = e[1]
        return (inner[0], (e[0], inner[1]), (e[0], inner[2]))
    return e


def _cong_implied_by_parts(c: dict[str, Any], T: Any, F: int) -> bool:
    """A congruence on A op B (op in + - *) is a rewrite when, on every refined residue class
    n = t (mod PERIOD) inside its class, it follows from the parts: each part is constant mod m
    there, or (product) one part is 0 mod m there."""
    if c["kind"] == "cong" and c["params"]["r"] == 0 and _push(c["_le"])[0] == "gcd":
        g = _push(c["_le"])                            # m | gcd(X, Y) iff m | X and m | Y
        m, q, s0 = c["params"]["m"], c["params"]["q"], c["params"]["s"]
        if all(_periodic_mod(x, m, T) for x in g[1:]):
            return True
    e = _distribute(c["_le"])
    if c["kind"] != "cong" or e[0] not in ("+", "-", "*"):
        return False
    m, q, s = c["params"]["m"], c["params"]["q"], c["params"]["s"]
    vals = [evaluate(sub, F, T) for sub in e[1:]]
    if any(v is None for v in vals):
        return False
    R = PERIOD * q // math.gcd(PERIOD, q)
    for t in range(R):
        if t % q != s % q:
            continue
        parts = [{x % m for i, x in enumerate(v) if (i + 1) % R == t} for v in vals]
        if not all(parts):
            continue
        if e[0] == "*" and any(p == {0} for p in parts):
            continue
        if all(len(p) == 1 for p in parts):
            continue
        return False
    return True


def _periodic_mod(e: tuple, m: int, T: Any, period: int = 240, span: int = 480) -> bool:
    """Every primitive of ``e`` is periodic mod m (period | 240, covers the Pisano periods for m <= 12) and ``e`` only uses + - * shifts,
    a(2n) and D: then e(n) mod m is a function of n mod a small period, so any congruence on it
    is a rewrite of the parts' periodic residues."""
    op = e[0]
    if op == "p":
        arr = T.t[e[1]]
        if len(arr) <= span + period:
            return False
        return all(arr[i] % m == arr[i + period] % m for i in range(1, span + 1))
    if op in ("sh", "dbl", "D"):
        return _periodic_mod(e[1], m, T, period, span)
    if op in ("+", "-", "*"):
        return _periodic_mod(e[1], m, T, period, span) and _periodic_mod(e[2], m, T, period, span)
    return False


def _divides_implied_by_parts(c: dict[str, Any], T: Any, F: int) -> bool:
    """E1 | A*B with E1 | A (or E1 | B), or E1 | A+-B with E1 dividing both: implied by the parts.
    Shifts / a(2n) are pushed through first; the part relation may fail at n = 1 (the claim itself
    was checked there), e.g. gpf(2n) | rad(n) for n >= 2."""
    if c["kind"] != "divides":
        return False
    r = _push(_distribute(c["_re"]))
    if r[0] not in ("+", "-", "*"):
        return False
    N = min(max_n(c["_le"], T, 400), *(max_n(x, T, 400) for x in r[1:]))
    N = max(N, 0) if N >= F else F
    a = evaluate(c["_le"], N, T)
    parts = [evaluate(x, N, T) for x in r[1:]]
    if a is None or any(p is None for p in parts):
        return False
    div = [all(x != 0 and y % x == 0 for x, y in zip(a[1:], p[1:])) for p in parts]
    if (any(div) if r[0] == "*" else all(div)):
        return True
    le = _push(c["_le"])
    if r[0] == "*" and le[0] == "*":                   # X*Y | A*B with X | A and Y | B (n >= 2)
        xs = [evaluate(x, N, T) for x in le[1:]]
        if any(x is None for x in xs):
            return False
        d = lambda u, w: all(x != 0 and y % x == 0 for x, y in zip(u[1:], w[1:]))
        return (d(xs[0], parts[0]) and d(xs[1], parts[1])) or (d(xs[0], parts[1]) and d(xs[1], parts[0]))
    return False


def _shared_operand(c: dict[str, Any]) -> bool:
    """Both sides apply the same operator to a common operand: the smaller claim is the real one."""
    a, b = c["_le"], c.get("_re")
    if b is None or a[0] != b[0] or a[0] not in ("+", "-", "*", "gcd"):
        return False
    if a[0] == "-":
        return a[1] == b[1] or a[2] == b[2]
    return bool({canon(x) for x in a[1:]} & {canon(x) for x in b[1:]})


SPLIT_N = 2000      # range used to find few-valued subterms and their joint values
SPLIT_MAX_VALUES = 3
SPLIT_MAX_TERMS = 3
SPLIT_MAX_BRANCHES = 12
SPLIT_F = 120       # branch claims are screened on a longer range (residue tests need samples)


class _WithConsts:
    """T plus constant sequences "_c<v>" (case-split branches)."""

    def __init__(self, T: Any, values: set[int]):
        self.t = dict(T.t)
        L = len(T.t["n"])
        for v in values:
            self.t[f"_c{v}"] = [v] * L


POINTWISE = ("+", "-", "*", "gcd")


def _subterms(e: tuple) -> list[tuple]:
    """Subterms evaluated at the same n as ``e`` (only through pointwise + - * gcd; S, D, shifts,
    a(2n) and composition look at other n, so a case split cannot reach inside them)."""
    out = [e]
    if e[0] in POINTWISE:
        for x in e[1:]:
            out += _subterms(x)
    return out


def _subst(e: tuple, key: str, rep: tuple) -> tuple:
    if canon(e) == key:
        return rep
    if e[0] in POINTWISE:
        return (e[0],) + tuple(_subst(x, key, rep) for x in e[1:])
    return e


def _push(e: tuple) -> tuple:
    """Exact rewrite that exposes pointwise parts: shifts / a(2n) distribute over + - * gcd, and
    D(x) = sh(x) - x. Values are unchanged; it only lets a case split see e.g. mu(2n)."""
    op = e[0]
    if op == "D" and e[1][0] in POINTWISE:
        return _push(("-", ("sh", e[1]), e[1]))
    if op in ("sh", "dbl") and e[1][0] in POINTWISE:
        return (e[1][0],) + tuple(_push((op, x)) for x in e[1][1:])
    if op in POINTWISE:
        return (op,) + tuple(_push(x) for x in e[1:])
    return e


def _simplify_consts(e: tuple, T: Any, N: int) -> tuple:
    """gcd(x, 0) = x when x >= 0, gcd(x, +-1) = 1 (exact on the tested range)."""
    if e[0] not in POINTWISE:
        return e
    e = (e[0],) + tuple(_simplify_consts(x, T, N) for x in e[1:])
    if e[0] == "gcd":
        for i, j in ((1, 2), (2, 1)):
            if e[i] in (("p", "_c1"), ("p", "_c-1")):
                return ("p", "_c1")
            if e[i] == ("p", "_c0"):
                v = evaluate(e[j], N, T)
                if v is not None and min(v) >= 0:
                    return e[j]
    return e


def _monotone_shift(c: dict[str, Any], T: Any, idx: list[int]) -> bool:
    """A <= A(n+1) or A <= A(2n) for a non-decreasing A: true by monotonicity alone."""
    if c["kind"] != "le" or c.get("_re") is None:
        return False
    A, B = c["_le"], c["_re"]
    if B[0] not in ("sh", "dbl") or canon(B[1]) != canon(A):
        return False
    N = max_n(A, T, 2 * SPLIT_N)
    a = evaluate(A, N, T) if N else None
    return bool(a) and all(x <= y for x, y in zip(a, a[1:]))


def _sides(c: dict[str, Any]) -> list[tuple]:
    return [c["_le"]] + ([c["_re"]] if c.get("_re") is not None else [])


def _dominates(c: dict[str, Any], T: Any, idx: list[int] | None = None) -> bool:
    """A <= B that holds only because of size: B grows exponentially while A stays polynomially
    bounded (huge gap on the tail), or A <= 0 <= B by sign. ``idx`` restricts to these n (1-based)."""
    if c["kind"] != "le" or c.get("_re") is None:
        return False
    A, B = c["_le"], c["_re"]
    N = min(max_n(A, T, HELD_EXP), max_n(B, T, HELD_EXP))
    if N < 40:
        return False
    a, b = evaluate(A, N, T), evaluate(B, N, T)
    ns = [n for n in (idx or range(1, N + 1)) if n <= N]
    if len(ns) < 10:
        return False
    if all(a[n - 1] <= 0 for n in ns) and all(b[n - 1] >= 0 for n in ns):
        return True
    if not is_expo(B) or is_expo(A):
        return False
    tail = [n for n in ns if n >= N // 2]
    if len(tail) < 5:
        return False
    poly = all(abs(a[n - 1]) <= n ** 5 + 10 for n in tail)
    gap = all(b[n - 1] > (abs(a[n - 1]) + 2) ** 3 for n in tail)
    return poly and gap


MULT_AT2 = {"phi": 1, "sigma": 3, "tau": 2, "mu": -1, "sqfree": 1, "rad": 2}


def _dbl_odd(e: tuple) -> tuple:
    if e[0] == "dbl" and e[1][0] == "p" and e[1][1] in MULT_AT2:
        return ("*", ("p", f"_c{MULT_AT2[e[1][1]]}"), e[1])
    if e[0] == "p" or e[0] == "o":
        return e
    if e[0] in POINTWISE:
        return (e[0],) + tuple(_dbl_odd(x) for x in e[1:])
    return e


def _case_split_trivial(c: dict[str, Any], T: Any, rng: random.Random, F: int) -> bool:
    """Few-valued parts (mu, the squarefree indicator, parity-like 0/1 or +-1 terms, any pointwise
    subterm with <= 3 values on the claim's domain, including ones constant there such as mu(4k)): split n by the joint values of those parts; the claim is a rewrite when on EVERY
    branch that actually occurs it reduces to something trivial (constant, formal / shuffle / idle
    part, or a pure growth / sign comparison)."""
    if c["kind"] == "rec":
        return False
    c = dict(c)
    c["_le"] = _push(c["_le"])
    if c.get("_re") is not None:
        c["_re"] = _push(c["_re"])
    sides = _sides(c)
    N = min([max_n(e, T, SPLIT_N) for e in sides])
    if N < 40:
        return False
    if c["kind"] == "cong":
        q, s0 = c["params"]["q"], c["params"]["s"]
        domain = [n for n in range(1, N + 1) if n % q == s0 % q]
    else:
        domain = list(range(1, N + 1))
    found: dict[str, tuple] = {}
    for e in sides:
        for sub in _subterms(e):
            if sub == ("p", "one") or canon(sub) in found:
                continue
            v = evaluate(sub, N, T)
            if v is not None and 1 <= len({v[n - 1] for n in domain}) <= SPLIT_MAX_VALUES:
                found[canon(sub)] = sub
    # keep maximal few-valued subterms only
    keys = [k for k in found if not any(k != o and k in {canon(x) for x in _subterms(found[o])} for o in found)]
    if not keys or len(keys) > SPLIT_MAX_TERMS:
        return False
    vals = {k: evaluate(found[k], N, T) for k in keys}
    combos: dict[tuple, list[int]] = {}
    for n in domain:
        combos.setdefault(tuple(vals[k][n - 1] for k in keys), []).append(n)
    if len(combos) > SPLIT_MAX_BRANCHES:
        return False
    Tc = _WithConsts(T, {v for combo in combos for v in combo} | set(MULT_AT2.values()))
    for combo, idx in combos.items():
        b = dict(c)
        for k, v in zip(keys, combo):
            b["_le"] = _subst(b["_le"], k, ("p", f"_c{v}"))
            if b.get("_re") is not None:
                b["_re"] = _subst(b["_re"], k, ("p", f"_c{v}"))
        if all(n % 2 for n in idx):                    # odd n only: f(2n) = f(2) f(n), f multiplicative
            b["_le"] = _dbl_odd(b["_le"])
            if b.get("_re") is not None:
                b["_re"] = _dbl_odd(b["_re"])
        b["_le"] = _simplify_consts(b["_le"], Tc, N)
        if b.get("_re") is not None:
            b["_re"] = _simplify_consts(b["_re"], Tc, N)
        live = {p for e in _sides(b) for p in prims_of(e)} - {"one"}
        if all(p.startswith("_c") or p == "n" for p in live):
            continue                                   # constant / elementary-in-n claim on this branch
        if _dominates(b, Tc, idx) or _monotone_shift(b, Tc, idx):
            continue
        if b["kind"] in ("le", "divides", "identity") and b.get("_re") is not None:
            va, vb = evaluate(b["_le"], N, Tc), evaluate(b["_re"], N, Tc)
            if va is not None and vb is not None and all(va[n - 1] == vb[n - 1] for n in idx):
                continue                               # the two sides coincide on this branch: X op X
        if _basic_inequality(b, Tc) or trivial_reason(b, Tc, rng, max(F, SPLIT_F), split=False):
            continue
        return False
    return True


# ----------------------------------------------------------------------------- textbook rules
PARITY_N = 2000
PARITY_SMALL = 24   # values of rule-less primitives up to here are kept (a finite check)
_PARITY: dict[str, list[int]] = {}


def _parity_tables(L: int) -> dict[str, list[int]]:
    """Textbook parity rules (value mod 2 as a function of n), n = 1..L (index 0 unused):
    phi(n) even for n >= 3; sigma(n) odd iff n is a square or twice a square; tau(n) odd iff n is
    a square; mu(n) odd iff n squarefree; rad(n), lpf(n) have the parity of n; gpf(n) even iff n is
    a power of 2 (> 1); prime(n) even iff n = 1; 2^n even; F(n), L(n) even iff 3 | n; Pell(n) even
    iff n even."""
    if _PARITY.get("_L") == [L]:
        return _PARITY
    import math as _m
    sq = [0] * (L + 1)
    for k in range(1, _m.isqrt(L) + 1):
        sq[k * k] = 1
    sq2 = [0] * (L + 1)
    for k in range(1, _m.isqrt(L // 2) + 1):
        sq2[2 * k * k] = 1
    pow2 = [0] * (L + 1)
    k = 2
    while k <= L:
        pow2[k] = 1
        k *= 2
    rng_ = range(L + 1)
    out = {
        "n": [n % 2 for n in rng_], "one": [1] * (L + 1),
        "phi": [1 if n <= 2 else 0 for n in rng_],
        "sigma": [1 if (sq[n] or sq2[n]) else 0 for n in rng_],
        "tau": [sq[n] for n in rng_],
        "rad": [n % 2 if n > 1 else 1 for n in rng_], "lpf": [n % 2 if n > 1 else 1 for n in rng_],
        "gpf": [0 if pow2[n] else 1 for n in rng_], "prime": [0 if n == 1 else 1 for n in rng_],
        "pow2": [0] * (L + 1), "fib": [0 if n % 3 == 0 else 1 for n in rng_],
        "lucas": [0 if n % 3 == 0 else 1 for n in rng_], "pell": [n % 2 for n in rng_],
        "maxgap": [1 if n <= 1 else 0 for n in rng_],   # record gaps after 2 -> 3 are even
        "ds3": [n % 2 for n in rng_],                     # base-b digit sum = n (mod b - 1)
        "cmax": [1 if n <= 1 else 0 for n in rng_],       # a Collatz maximum is never odd (3v+1 > v)
    }
    _PARITY.clear()
    _PARITY.update(out)
    _PARITY["_L"] = [L]
    return _PARITY


def _isprime_small(n: int) -> bool:
    return n > 1 and all(n % d for d in range(2, int(n ** 0.5) + 1))


def _has_op(e: tuple, op: str) -> bool:
    if e[0] == op:
        return True
    if e[0] == "p":
        return False
    return any(_has_op(x, op) for x in (e[2:] if e[0] == "o" else e[1:]))


def _parity_rules(c: dict[str, Any], T: Any, rng: random.Random) -> bool:
    """A mod-2 congruence that follows from textbook parity rules plus finitely many small cases:
    every primitive with a rule is replaced by its rule, mu by the squarefree indicator, and every
    other primitive by its true parity up to PARITY_SMALL and random parities beyond; if the claim
    still holds (3 draws), it is a consequence of the rules. Exact because + - * gcd S D shifts and
    a(2n) all respect parity; composition does not, so it is skipped."""
    if c["kind"] not in ("cong", "modpat") or c["params"]["m"] != 2 or _has_op(c["_le"], "o"):
        return False
    N = max_n(c["_le"], T, PARITY_N)
    if N < 200:
        return False
    L = min(len(T.t["n"]) - 1, 4 * PARITY_N + 8)
    rules = _parity_tables(L)
    for _ in range(3):
        tab = {}
        # primes > 2 are odd: pi, cheb4, cheb3 are counts over a random set of odd numbers (true
        # values up to PARITY_SMALL); cheb4 = pi - [n >= 2], cheb3 = pi - [n >= 3] (mod 2)
        ind = [0] * (L + 1)
        for i in range(2, L + 1):
            ind[i] = (1 if T.t["sqfree"][i] and _isprime_small(i) else 0) if i <= PARITY_SMALL else \
                (rng.randint(0, 1) if i % 2 else 0)
        pi_par, acc = [0] * (L + 1), 0
        for i in range(1, L + 1):
            acc ^= ind[i]
            pi_par[i] = acc
        counts = {"pi": pi_par, "cheb4": [(pi_par[i] - (i >= 2)) % 2 for i in range(L + 1)],
                  "cheb3": [(pi_par[i] - (i >= 3)) % 2 for i in range(L + 1)]}
        for k in prims_of(c["_le"]):
            if k in counts:
                tab[k] = counts[k]
            elif k in rules:
                tab[k] = rules[k]
            elif k in ("mu", "sqfree"):          # mu odd iff squarefree; the indicator is itself
                tab[k] = [x % 2 for x in T.t["sqfree"][:L + 1]]
            elif k.startswith("_c"):
                tab[k] = T.t[k][:L + 1]
            else:
                arr = T.t[k]
                tab[k] = [arr[i] % 2 if (i <= PARITY_SMALL and i < len(arr)) else rng.randint(0, 1)
                          for i in range(min(len(arr), L + 1))]
        a = evaluate(c["_le"], N, T, tab)
        if a is None or not holds(c["kind"], c["params"], a, None)[0]:
            return False
    return True


def _running_sum_tail(c: dict[str, Any], T: Any) -> bool:
    """A congruence on a running sum S(X) where X = 0 (mod m) from some small n0 on: the claim is
    just the finite sum of the first terms (the smaller claim X = 0 mod m is the real one)."""
    if c["kind"] != "cong":
        return False
    e = _push(c["_le"])
    terms = [e]
    while terms and terms[0][0] in ("+", "-") and len(terms) < 8:
        x = terms.pop(0)
        terms += [x[1], x[2]]
    sums = [t for t in terms if t[0] == "S"]
    if not sums or len(sums) != len(terms):
        return False
    m = c["params"]["m"]
    for t in sums:
        N = max_n(t[1], T, PARITY_N)
        if N < 500:
            return False
        v = evaluate(t[1], N, T)
        if not all(x % m == 0 for x in v[PARITY_SMALL:]):
            return False
    return True


# basic textbook inequalities between primitives, as linear forms that are >= 0 for n >= 2
BASIC_INEQ: tuple[dict[str, int], ...] = (
    {"tau": 1, "bigomega": -1, "_k": -1},   # tau(n) >= Omega(n) + 1
    {"tau": 1, "bigomega": -1, "omega": -1},  # tau(n) >= Omega(n) + omega(n)
    {"bigomega": 1, "omega": -1},           # Omega >= omega
    {"omega": 1, "_k": -1},                 # omega >= 1 (n >= 2)
    {"n": 1, "phi": -1}, {"phi": 1, "_k": -1}, {"phi": 1, "gpf": -1, "_k": 1},  # phi <= n; phi >= p - 1
    {"sigma": 1, "n": -1, "_k": -1}, {"sigma": 1, "tau": -1},
    {"n": 1, "rad": -1}, {"rad": 1, "gpf": -1}, {"gpf": 1, "lpf": -1}, {"lpf": 1, "_k": -2},
    {"n": 1, "tau": -1}, {"tau": 1, "_k": -2},
    {"n": 1, "sopfr": -1}, {"sopfr": 1, "gpf": -1},
    {"n": 1, "pi": -1}, {"pi": 1}, {"prime": 1, "n": -1}, {"prime": 1, "_k": -2},
    {"sqfree": 1}, {"_k": 1, "sqfree": -1}, {"mu": 1, "_k": 1}, {"_k": 1, "mu": -1},
    {"digsum": 1, "_k": -1}, {"n": 1, "digsum": -1}, {"popcount": 1, "_k": -1}, {"n": 1, "popcount": -1},
    {"n": 1, "_k": -2}, {"_k": 1},
    {"cmax": 1, "n": -1}, {"cmax": 1, "_k": -4}, {"csteps": 1, "_k": -1},   # Collatz: max >= n, >= 4 (n >= 2)
    {"maxgap": 1, "_k": -1}, {"prime": 1, "maxgap": -1}, {"gold": 1}, {"ds3": 1, "_k": -1}, {"n": 1, "ds3": -1},
    {"rev": 1, "_k": -1},
    {"pell": 1, "part": -1}, {"pow2": 1, "part": -1},
    {"sigma": 1, "gpf": -1, "_k": -1},   # sigma(n) >= n + 1 >= gpf(n) + 1   # p(n) <= 2^(n-1) (compositions) <= Pell(n)
)


DBL_MONO = ("n", "omega", "bigomega", "tau", "sigma", "phi", "rad", "sopfr", "pi", "prime", "gpf",
            "pow2", "fib", "lucas", "pell", "part", "maxgap", "cmax")   # f(2n) >= f(n) for n >= 2 (2n -> n)
SH_MONO = ("n", "pi", "prime", "pow2", "fib", "lucas", "pell", "part", "maxgap")  # non-decreasing


def _linear(e: tuple, coef: int, out: dict[str, int], atoms: dict[str, tuple]) -> None:
    if e[0] in ("+", "-"):
        _linear(e[1], coef, out, atoms)
        _linear(e[2], coef if e[0] == "+" else -coef, out, atoms)
        return
    if e == ("p", "one"):
        out["_k"] = out.get("_k", 0) + coef
        return
    if e[0] == "p" and e[1].startswith("_c"):
        out["_k"] = out.get("_k", 0) + coef * int(e[1][2:])
        return
    k = canon(e)
    atoms[k] = e
    out[k] = out.get(k, 0) + coef


def _basic_inequality(c: dict[str, Any], T: Any) -> bool:
    """A <= B that reduces, for n >= 2, to a known basic inequality (or a sum of a few): both sides
    are split into + - parts; parts that differ from a primitive by a constant (e.g. gpf(2n) = gpf(n),
    Omega(2n) = Omega(n) + 1 for n >= 2) are rewritten; what is left must be a non-negative
    combination of BASIC_INEQ plus a non-negative constant."""
    if c["kind"] != "le" or c.get("_re") is None:
        return False
    A, B = _push(c["_le"]), _push(c["_re"])
    form: dict[str, int] = {}
    atoms: dict[str, tuple] = {}
    _linear(B, 1, form, atoms)
    _linear(A, -1, form, atoms)
    N = min([max_n(x, T, 400) for x in atoms.values()] or [400])
    if N < 100:
        return False
    vals = {}
    for k, x in atoms.items():
        v = evaluate(x, N, T)
        if v is None:
            return False
        vals[k] = v
    red: dict[str, int] = {"_k": form.get("_k", 0)}
    for k, co in form.items():
        if k == "_k" or co == 0:
            continue
        x, v = atoms[k], vals[k]
        if len(set(v[1:])) == 1:                       # constant for n >= 2
            red["_k"] += co * v[1]
            continue
        base = None
        cands = [y for y in PRIMS if T.t.get(y) is not None]
        if x[0] == "p":
            base = (x[1], 0)
        else:
            for y in cands:
                w = evaluate(("p", y), N, T)
                if w is None:
                    continue
                d = {v[i] - w[i] for i in range(1, N)}
                if len(d) == 1:
                    base = (y, d.pop())
                    break
        if base is None and co > 0 and x[0] in ("dbl", "sh") and x[1][0] == "p" and \
                x[1][1] in (DBL_MONO if x[0] == "dbl" else SH_MONO):
            base = (x[1][1], 0)                        # f(2n) >= f(n) / f(n+1) >= f(n): drop the slack
        if base is None:
            return False
        red[base[0]] = red.get(base[0], 0) + co
        red["_k"] += co * base[1]
    red = {k: v for k, v in red.items() if v or k == "_k"}
    names = [k for k in red if k != "_k"]
    lib = [f for f in BASIC_INEQ if set(f) - {"_k"} <= set(names) or set(f) == {"_k"}]

    def ok(rem: dict[str, int], depth: int, start: int) -> bool:
        if all(v == 0 for k, v in rem.items() if k != "_k") and rem.get("_k", 0) >= 0:
            return True
        if depth == 0:
            return False
        for i in range(start, len(lib)):
            for lam in (1, 2):
                nxt = dict(rem)
                for k, v in lib[i].items():
                    nxt[k] = nxt.get(k, 0) - lam * v
                if ok(nxt, depth - 1, i + 1):
                    return True
        return False
    return ok(red, 3, 0)


def _rewrite_atoms(c: dict[str, Any], T: Any) -> dict[str, Any] | None:
    """Replace pointwise subterms that equal a constant or a primitive on n = 1..400 (e.g.
    pi(prime(n)) = n, lpf(2n) = 2, lpf(rad(n)) = lpf(n)); None when nothing changes."""
    def walk(e: tuple, consts: set[int], top: bool = False) -> tuple:
        if e[0] == "p":
            return e
        if top and c["kind"] == "identity":     # an identity's sides are the claim itself
            if e[0] in POINTWISE:
                return (e[0],) + tuple(walk(x, consts) for x in e[1:])
            if e[0] in ("S", "D", "sh", "dbl"):
                return (e[0], walk(e[1], consts))
            return e
        N = max_n(e, T, 400)
        v = evaluate(e, N, T) if N >= 200 else None
        if v is not None:
            if len(set(v)) == 1:
                consts.add(v[0])
                hit.append(1)
                return ("p", f"_c{v[0]}")
            for y in PRIMS:
                if y != "one" and T.t[y][1:N + 1] == v:
                    hit.append(1)
                    return ("p", y)
        if e[0] in POINTWISE:
            return (e[0],) + tuple(walk(x, consts) for x in e[1:])
        if e[0] in ("S", "D", "sh", "dbl"):
            return (e[0], walk(e[1], consts))
        return e
    consts: set[int] = set()
    hit: list[int] = []
    push = (lambda e: e) if c["kind"] == "identity" else _push
    le = walk(push(c["_le"]), consts, True)
    re_ = walk(push(c["_re"]), consts, True) if c.get("_re") is not None else None
    if not hit:
        return None
    out = dict(c)
    out["_le"], out["_re"], out["_consts"] = le, re_, consts
    return out


DIGIT_MOD = {"digsum": 9, "rev": 9, "ds3": 2}   # base-b digit sums / reversal keep n mod (b - 1)


def _digit_rule(c: dict[str, Any]) -> bool:
    """A congruence mod m | (b - 1) on digsum / rev / ds3 of something: those keep their argument
    mod b - 1, so the claim is a rewrite of the same claim on the argument (or on n)."""
    if c["kind"] not in ("cong", "modpat"):
        return False
    m = c["params"]["m"]

    def walk(e: tuple) -> bool:
        if e[0] == "p":
            return e[1] in DIGIT_MOD and DIGIT_MOD[e[1]] % m == 0
        if e[0] == "o":
            return (e[1] in DIGIT_MOD and DIGIT_MOD[e[1]] % m == 0) or False
        if e[0] in ("+", "-", "*"):
            return walk(e[1]) or walk(e[2])
        if e[0] in ("S", "D", "sh", "dbl"):
            return walk(e[1])
        return False
    return walk(c["_le"])


MONO_OUTER = ("prime", "pi", "pow2", "fib", "lucas", "pell", "part", "n")


def _monotone_outer(c: dict[str, Any], T: Any) -> bool:
    """f(X) <= f(Y) with f non-decreasing (f(n) counts as f(n)) reduces to X <= Y; trivial when that
    is a basic inequality."""
    if c["kind"] != "le" or c.get("_re") is None:
        return False
    def arg(e):
        if e[0] == "o" and e[1] in MONO_OUTER:
            return e[1], e[2]
        if e[0] == "p" and e[1] in MONO_OUTER:
            return e[1], ("p", "n")
        return None, None
    fa, xa = arg(c["_le"])
    fb, xb = arg(c["_re"])
    if fa is None or fa != fb or xa == xb:
        return False
    r = {"kind": "le", "params": {}, "_le": xa, "_re": xb}
    N = min(max_n(xa, T, 2000), max_n(xb, T, 2000))
    va, vb = evaluate(xa, N, T), evaluate(xb, N, T)
    if va is None or vb is None or not all(x <= y for x, y in zip(va, vb)):
        return False
    return _basic_inequality(r, T) or (xa[0] == "p" and xb[0] == "p" and xa[1] in ("one",))


OUTER_DIVIDES = ("gpf", "lpf", "rad")                       # g(x) | x for x >= 1
OUTER_LE = ("gpf", "lpf", "rad", "sopfr", "phi", "tau", "omega", "bigomega", "digsum", "popcount", "ds3")  # g(x) <= x


def _outer_self(c: dict[str, Any]) -> bool:
    """g(f(n)) | f(n) or g(f(n)) <= f(n) for g with g(x) | x (gpf, lpf, rad) or g(x) <= x: a
    property of g alone, true for every f (2026-10-19: gpf[pnot3] | pnot3 reached the registry)."""
    a, b = c["_le"], c.get("_re")
    if b is None or a[0] != "o" or canon(a[2]) != canon(b):
        return False
    return (c["kind"] == "divides" and a[1] in OUTER_DIVIDES) or (c["kind"] == "le" and a[1] in OUTER_LE)


def trivial_reason(c: dict[str, Any], T: Any, rng: random.Random, F: int, split: bool = True) -> str:
    """Why the claim is a rewrite rather than new, else ''.

    formal         still true when every primitive is an independent random sequence
    shuffle_null   still true when each primitive's own values are shuffled (no arithmetic used)
    idle_part      still true when ONE primitive is shuffled (that part carries nothing; the
                   smaller claim is the real one)
    implied_parts  congruence implied by (periodic) congruences of its parts
    shared_operand both sides share an operand under the same operator
    growth_dominance  A <= B only because B grows exponentially past a polynomially bounded A
                   (or A <= 0 <= B by sign)
    parity_rules   a mod-2 congruence that follows from textbook parity rules (sigma odd iff square
                   or twice a square, phi even for n >= 3, tau odd iff square, ...) + small cases
    running_sum_tail  a congruence on a running sum whose terms are 0 mod m from a small n on
    rewrite_closure  after replacing subterms that equal a constant / a primitive (pi(prime(n)) = n,
                   lpf(2n) = 2) a recurrence / congruence on C-finite parts: expected
    basic_inequality  A <= B reduces (n >= 2) to known basic inequalities such as tau >= Omega + 1
    case_split     on every branch of its few-valued parts (mu, squarefree indicator, parity...)
                   the claim reduces to one of the above or to a constant comparison
    """
    if _outer_self(c):
        return "outer_self"
    if _cong_implied_by_parts(c, T, F) or (c["kind"] in ("cong", "modpat") and _periodic_mod(c["_le"], c["params"]["m"], T)):
        return "implied_parts"
    if _divides_implied_by_parts(c, T, F):
        return "implied_parts"
    if not known_result(c) and _known_cong_parts(c, T, rng):
        return "implied_parts"
    if _digit_rule(c):
        return "digit_rule"
    if _monotone_outer(c, T):
        return "basic_inequality"
    if _shared_operand(c):
        return "shared_operand"
    if split and not c.get("_rewritten"):
        rw = _rewrite_atoms(c, T)
        if rw is not None:
            rw["_rewritten"] = True
            Tw = _WithConsts(T, rw.pop("_consts")) if not isinstance(T, _WithConsts) else T
            if rw["kind"] in ("rec", "cong") and all(cf_order(x) is not None for x in _sides(rw)) \
                    and not all(cf_order(x) is not None for x in _sides(c)):
                return "rewrite_closure"
            r = trivial_reason(rw, Tw, rng, F, split=True)
            if r:
                return r
    if split and _dominates(c, T):
        return "growth_dominance"
    if _parity_rules(c, T, rng):
        return "parity_rules"
    if _running_sum_tail(c, T):
        return "running_sum_tail"
    if _basic_inequality(c, T):
        return "basic_inequality"
    prims = sorted(p for p in prims_of(c["_le"]) | (prims_of(c["_re"]) if c.get("_re") is not None else set())
                   if not p.startswith("_c"))
    for mode_ in ("random", "shuffle") + tuple(f"one:{p}" for p in prims if len(prims) > 1 and p != "one"):
        held_all = True
        for _ in range(3):
            if mode_.startswith("one:"):
                tab = dict(T.t)
                tab[mode_[4:]] = _random_tables(rng, T, "shuffle")[mode_[4:]]
            else:
                tab = _random_tables(rng, T, mode_)
            a = evaluate(c["_le"], F, T, tab)
            b = evaluate(c["_re"], F, T, tab) if c.get("_re") is not None else None
            if a is None or (c.get("_re") is not None and b is None):
                held_all = False
                break
            ok, _ = holds(c["kind"], c["params"], a, b)
            if not ok:
                held_all = False
                break
        if held_all:
            return {"random": "formal", "shuffle": "shuffle_null"}.get(mode_, "idle_part")
    if split and _case_split_trivial(c, T, rng, F):
        return "case_split"
    return ""


def fit_claims(exprs: list[tuple], T: Any, F: int, rng: random.Random) -> list[dict[str, Any]]:
    wide = menu() == "wide"
    qs, mods = (QS + WIDE_QS, MODS + WIDE_MODS) if wide else (QS, MODS)
    LEN = max(F + MAX_REC + 2, CONG_FIT_PER_CLASS * max(qs), 4 * MODPAT_MAX_P) if wide else F + MAX_REC + 2
    vals = {}
    for e in exprs:
        v = evaluate(e, LEN, T)
        if v is not None and len(set(v)) > 1:
            vals[canon(e)] = (e, v)
    out: list[dict[str, Any]] = []

    def mk(kind, le, re_, params):
        L = canon(le)
        R = canon(re_) if re_ is not None else ""
        return {"kind": kind, "lhs": L, "rhs": R, "params": params, "_le": le, "_re": re_,
                "id": claim_id(kind, L, R, params)}

    # identities: same fitted values, different canonical forms
    groups: dict[tuple, list[tuple]] = {}
    for c, (e, v) in vals.items():
        groups.setdefault(tuple(v[:F]), []).append(e)
    for g in groups.values():
        if len(g) >= 2:
            g = sorted(g, key=lambda e: (size(e), canon(e)))
            out.append(mk("identity", g[0], g[1], {}))
    keys = list(vals)
    # pairs: divisibility / tight inequality
    for _ in range(min(PAIR_BUDGET, len(keys) * (len(keys) - 1))):
        i, j = rng.sample(range(len(keys)), 2)
        (ea, va), (eb, vb) = vals[keys[i]], vals[keys[j]]
        a, b = va[:F], vb[:F]
        if a == b:
            continue
        if all(x != 0 for x in a) and sum(1 for x in a if abs(x) >= 2) * 2 >= F:
            if all(y % x == 0 for x, y in zip(a, b)) and len({y // x for x, y in zip(a, b)}) > 1:
                out.append(mk("divides", ea, eb, {}))
        eq = sum(1 for x, y in zip(a, b) if x == y)
        late_eq = sum(1 for i, (x, y) in enumerate(zip(a, b)) if x == y and i >= F // 2)
        if all(x <= y for x, y in zip(a, b)) and eq >= 2 and F - eq >= 2 and late_eq >= 1 \
                and len(set(a)) >= 4 and len(set(b)) >= 4:
            out.append(mk("le", ea, eb, {}))
    # congruences and recurrences
    for c in keys:
        e, v = vals[c]
        a = v[:F]
        # at most one congruence per expression, on the coarsest class (q = 1 first): a claim on a
        # sub-class of a class that already works is implied, not new
        found = False
        for q in qs:
            w = v[:max(F, CONG_FIT_PER_CLASS * q)] if wide else a
            for s in range(q):
                sub = [x for i, x in enumerate(w) if (i + 1) % q == s]
                if len(sub) < 6:
                    continue
                for m in mods:
                    r = sub[0] % m
                    if all(x % m == r for x in sub) and len({x for x in sub}) > 2:
                        out.append(mk("cong", e, None, {"m": m, "r": r, "q": q, "s": s}))
                        found = True
                        break
                if found:
                    break
            if found:
                break
        rec = berlekamp_massey_int(a)
        if rec and any(rec):
            out.append(mk("rec", e, None, {"c": rec}))
        if wide and not found:   # mod-m pattern: residues depend only on n mod P (smallest P, 4 periods)
            mp = _fit_modpat(v)
            if mp:
                out.append(mk("modpat", e, None, mp))
    return out


def _fit_modpat(v: list[int]) -> dict[str, Any] | None:
    for m in MODPAT_MODS:
        r = [x % m for x in v]
        if len(set(r)) < 2:
            continue
        for P in range(2, MODPAT_MAX_P + 1):
            w = r[:max(4 * P, 24)]
            if len(w) < max(4 * P, 24):
                break
            if all(w[i] == w[i % P] for i in range(len(w))):
                pat = w[:P]
                if len(set(pat)) >= 2:
                    return {"m": m, "P": P, "pat": pat}
                break
    return None


# known results: recognized as known, never counted as surprises
RAMANUJAN = ((5, 4), (7, 5), (11, 6))   # p(Mk + d) = 0 (mod M)


def _affine_index(e: tuple) -> tuple[str, int, int] | None:
    """e = primitive under shifts / a(2n) only -> (primitive, a, b) with e(n) = prim(a n + b)."""
    if e[0] == "p":
        return e[1], 1, 0
    if e[0] in ("sh", "dbl"):
        r = _affine_index(e[1])
        if r is None:
            return None
        k, a, b = r
        return (k, a, a + b) if e[0] == "sh" else (k, 2 * a, b)
    return None


def _known_cong_parts(c: dict[str, Any], T: Any, rng: random.Random) -> bool:
    """A congruence / mod pattern on an expression in p(n) that follows from Ramanujan's congruences
    plus periodic residues of the other parts: p(n) is replaced by random values that only keep
    p(Mk + d) = 0 (mod M) for the M | m; parts periodic mod m keep their true values, every other
    part is random (3 draws). Still holding means the claim is implied by known congruences."""
    if c["kind"] not in ("cong", "modpat") or "part" not in prims_of(c["_le"]) or _has_op(c["_le"], "o"):
        return False
    m = c["params"]["m"]
    Ms = [(M, d) for M, d in RAMANUJAN if m % M == 0]
    if not Ms:
        return False
    N = max_n(c["_le"], T, 600)
    if N < 100:
        return False
    for _ in range(3):
        tab = {}
        for k in prims_of(c["_le"]):
            arr = T.t[k]
            L = min(len(arr), 2 * N + 4)
            if k == "part":
                tab[k] = [0] + [(0 if any(i % M == d for M, d in Ms) else rng.randint(1, 10 ** 6)) * 1
                                for i in range(1, L)]
                tab[k] = [v if v == 0 else v for v in tab[k]]
                for M, d in Ms:      # keep the class residue 0 mod M but random beyond it
                    tab[k] = [v if (i % M != d) else M * rng.randint(0, 10 ** 5) for i, v in enumerate(tab[k])]
            elif k.startswith("_c") or _periodic_mod(("p", k), m, T):
                tab[k] = arr[:L]
            else:
                tab[k] = [0] + [rng.randint(0, 10 ** 6) for _ in range(1, L)]
        a = evaluate(c["_le"], N, T, tab)
        if a is None or not holds(c["kind"], c["params"], a, None)[0]:
            return False
    return True


def known_result(c: dict[str, Any]) -> str:
    """Name of a known theorem / famous open problem the claim is an instance of, else ''."""
    k, prm = c["kind"], c.get("params") or {}
    ps = prims_of(c["_le"]) | (prims_of(c["_re"]) if c.get("_re") is not None else set())
    if k == "cong" and prm.get("r") == 0:
        ai = _affine_index(_push(c["_le"]))
        if ai and ai[0] == "part":
            _k, a, b = ai
            q, s0 = prm["q"], prm["s"] % prm["q"]
            for M, d in RAMANUJAN:
                if prm["m"] % M == 0 and prm["m"] == M and (a * q) % M == 0 and (a * s0 + b) % M == d:
                    return f"Ramanujan congruence p({M}k+{d}) = 0 (mod {M})"
    if k == "modpat" and "part" in ps:
        ai = _affine_index(_push(c["_le"]))
        if ai and ai[0] == "part" and prm["m"] in (5, 7, 11):
            return "partition residues (Ramanujan-type congruences; known)"
    if ps & {"cheb3", "cheb4"} and k == "le":
        return ("Chebyshev bias (prime races: the leader changes far out, e.g. mod 4 first at 26861, "
                "mod 3 first near 6.08e11); finite checks cannot separate")
    re_ps = prims_of(c["_re"]) if c.get("_re") is not None else set()
    if k == "le" and "gold" in re_ps:
        return "lower bound on Goldbach counts (Goldbach / Hardy-Littlewood: famously open, verified far beyond here)"
    if k == "le" and "maxgap" in prims_of(c["_le"]):
        return "upper bound on prime gaps (Bertrand / Legendre / Cramer: known or famously open)"
    return ""


# ----------------------------------------------------------------------------- proofs

def prove(c: dict[str, Any], T: Any) -> dict[str, Any] | None:
    """Machine-checked certificate when decidable by a C-finite argument, else None."""
    le, re_ = c["_le"], c.get("_re")
    dl = cf_order(le)
    if dl is None:
        return None
    if c["kind"] == "identity":
        dr = cf_order(re_) if re_ is not None else None
        if dr is None:
            return None
        d = dl + dr
        a, b = evaluate(le, d, T), evaluate(re_, d, T)
        if a is None or b is None or a != b:
            return None
        return {"method": "C-finite order bound", "order_bound": d, "checked_terms": d,
                "argument": f"both sides are C-finite (orders <= {dl}, {dr}); their difference has order "
                            f"<= {d} and vanishes on n = 1..{d}, hence everywhere"}
    if c["kind"] == "rec":
        k = len(c["params"]["c"])
        a = evaluate(le, dl + k, T)
        if a is None or not holds("rec", c["params"], a, None)[0]:
            return None
        return {"method": "C-finite order bound", "order_bound": dl, "checked_terms": dl,
                "argument": f"the residual of the recurrence is C-finite of order <= {dl} and vanishes on "
                            f"{dl} consecutive terms, hence everywhere"}
    if c["kind"] == "cong":
        # integer monic recurrence of the expression itself (proved as above) -> periodic mod m
        a = evaluate(le, 4 * dl + 8, T)
        rec = berlekamp_massey_int(a, max_order=dl) if a else None
        if not rec:
            return None
        a2 = evaluate(le, dl + len(rec), T)
        if a2 is None or not holds("rec", {"c": rec}, a2, None)[0]:
            return None
        m, r, q, s = (c["params"][x] for x in ("m", "r", "q", "s"))
        k = len(rec)
        state = tuple(x % m for x in a[:k])
        seen, n = {}, 1
        while (n % q, state) not in seen:
            if len(seen) > 2_000_000:
                return None
            seen[(n % q, state)] = n
            if n % q == s and state[0] != r:
                return None
            nxt = sum(ci * state[j] for j, ci in enumerate(rec)) % m
            state = state[1:] + (nxt,)
            n += 1
        return {"method": "periodic state space mod m", "recurrence": rec, "states_checked": len(seen),
                "argument": f"a(n) satisfies a proved integer recurrence of order {k}; the pair (n mod {q}, "
                            f"state mod {m}) repeats after {len(seen)} steps and the congruence held on all of them"}
    return None


# ----------------------------------------------------------------------------- state

def load_state(path: Path = STATE) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def family(c: dict[str, Any]) -> str:
    ps = sorted(prims_of(c["_le"]) | (prims_of(c["_re"]) if c.get("_re") is not None else set()))
    return f"{c['kind']}:{'+'.join(ps)}"


def predict(kind: str, state: dict[str, Any]) -> float:
    tried, surv = (state.get("kind_stats") or {}).get(kind, [0, 0])[:2]
    return (surv + 1) / (tried + 2)


def _sig(c: dict[str, Any], T: Any, F: int) -> str:
    a = evaluate(c["_le"], F, T) or []
    b = evaluate(c["_re"], F, T) if c.get("_re") is not None else []
    raw = json.dumps([c["kind"], c["params"], a, b or []], sort_keys=True)
    return hashlib.blake2b(raw.encode(), digest_size=8).hexdigest()


def oeis_status(e: tuple, T: Any, lookup: Callable | None) -> dict[str, Any]:
    if e[0] == "p" and e[1] in PRIMS:
        return {"status": "primitive"}
    if lookup is None:
        return {"status": "unchecked"}
    v = evaluate(e, 24, T)
    if v is None:
        return {"status": "unchecked"}
    try:
        return lookup(v)
    except Exception:  # noqa: BLE001
        return {"status": "unchecked"}


def default_lookup() -> Callable | None:
    try:
        from colony import oeis_terms
        return oeis_terms.lookup if oeis_terms.available() else None
    except Exception:  # noqa: BLE001
        return None


def test_claim(c: dict[str, Any], T: Any, lo: int, cap_cheap: int, cap_exp: int) -> dict[str, Any]:
    cap = cap_exp if (is_expo(c["_le"]) or (c.get("_re") is not None and is_expo(c["_re"]))) else cap_cheap
    N = min(max_n(c["_le"], T, cap), max_n(c["_re"], T, cap) if c.get("_re") is not None else cap)
    if N <= lo:
        return {"tested": False, "N": N}
    a = evaluate(c["_le"], N, T)
    b = evaluate(c["_re"], N, T) if c.get("_re") is not None else None
    start = lo + 1
    if c["kind"] == "rec":
        k = len(c["params"]["c"])
        ok, n = holds("rec", c["params"], a[lo - k:], None, start=start - k)
    else:
        ok, n = holds(c["kind"], c["params"], a[lo:], b[lo:] if b is not None else None, start=start)
    out = {"tested": True, "survived": ok, "checks": n, "range": [start, N]}
    if c["kind"] == "le" and ok:
        # tight only if equality keeps recurring beyond twice the fit range
        out["loose"] = not any(x == y for x, y in zip(a[2 * lo:], b[2 * lo:]))
    return out


def run_cycle(cycle_id: str = "", *, state_path: Path = STATE, T: Any = None, lookup: Any = "default",
              write: bool = True, seed: str | None = None, F: int | None = None,
              k_prior: float | None = None, tally: dict | None = None) -> dict[str, Any]:
    if mode() == "off":
        return {"skipped": "COLONY_FRONTIER=off"}
    live_tally = tally is None and _ING.mode() == "live" and write
    if live_tally:
        tally = _ING.new_tally()
    _pr = lambda c: prims_of(c["_le"]) | (prims_of(c["_re"]) if c.get("_re") is not None else set())  # noqa: E731
    T = T or tables()
    F = F or fit_n()
    if lookup == "default":
        lookup = default_lookup()
    if k_prior is None:
        from colony.hunt_shadow import K_PRIOR as k_prior
    st = load_state(state_path)
    for k in ("prim_stats", "op_stats", "kind_stats", "family_surprises"):
        st.setdefault(k, {})
    st.setdefault("registry", {})
    st.setdefault("signatures", [])
    st.setdefault("predictions", {"n": 0, "brier_sum": 0.0, "bins": {}})
    st.setdefault("totals", {})
    rng = random.Random(f"frontier:{seed or cycle_id}")
    exprs = sample_expressions(rng, N_EXPR, st)
    cands = fit_claims(exprs, T, F, rng)
    sigs = set(st["signatures"])
    seen_ids = {_h(i) for i in st["registry"]} | set(st.get("rejected_ids") or [])
    counts = {"expressions": len(exprs), "fitted": len(cands), "duplicate": 0, "trivial_formal": 0,
              "trivial_shuffle_null": 0, "trivial_idle_part": 0,
              "trivial_implied_parts": 0, "trivial_shared_operand": 0,
              "trivial_growth_dominance": 0, "trivial_case_split": 0, "trivial_parity_rules": 0,
              "trivial_running_sum_tail": 0, "trivial_basic_inequality": 0,
              "trivial_rewrite_closure": 0, "trivial_digit_rule": 0, "expected_by_closure": 0,
              "loose_inequality": 0, "tested": 0, "survived": 0, "falsified": 0, "machine_checked": 0,
              "surprises": 0, "known_result": 0, "oeis_known": 0, "oeis_unchecked": 0, "retested": 0, "false_surprises": 0}
    fresh: list[dict[str, Any]] = []
    for c in cands:
        _ING.mark(tally, _pr(c), "produced")
        if _h(c["id"]) in seen_ids:
            counts["duplicate"] += 1
            continue
        sg = _sig(c, T, F)
        if sg in sigs:
            counts["duplicate"] += 1
            continue
        sigs.add(sg)
        seen_ids.add(_h(c["id"]))
        c["sig"] = sg
        fresh.append(c)
        _ING.mark(tally, _pr(c), "fresh")
    # colony's own priority for what to test first: unexplored families, then kind survival
    fam_s = st["family_surprises"]
    rng.shuffle(fresh)
    fresh.sort(key=lambda c: -(k_prior / (fam_s.get(family(c), 0) + k_prior)) * predict(c["kind"], st))
    tested: list[dict[str, Any]] = []
    _rc_net = None
    per_kind: dict[str, int] = {}
    kinds_present = {c["kind"] for c in fresh} or {"x"}
    cap_kind = max(4, MAX_TEST // len(kinds_present))
    for c in fresh:
        if len(tested) >= MAX_TEST:
            break
        if per_kind.get(c["kind"], 0) >= cap_kind:
            continue
        tr = trivial_reason(c, T, rng, F)
        if tr:
            counts[f"trivial_{tr}"] = counts.get(f"trivial_{tr}", 0) + 1
            continue
        per_kind[c["kind"]] = per_kind.get(c["kind"], 0) + 1
        _ING.mark(tally, _pr(c), "passed_filter")
        c["prediction"] = round(predict(c["kind"], st), 4)          # pre-registered BEFORE testing
        c["predicted_at"] = _utc()
        res = test_claim(c, T, F, HELD_CHEAP, HELD_EXP)
        if not res["tested"]:
            continue
        c.update(res)
        counts["tested"] += 1
        _ING.mark(tally, _pr(c), "tested")
        y = 1.0 if res["survived"] else 0.0
        P = st["predictions"]
        P["n"] += 1
        P["brier_sum"] = round(P["brier_sum"] + (c["prediction"] - y) ** 2, 6)
        b = str(min(9, int(c["prediction"] * 10)))
        bb = P["bins"].setdefault(b, [0, 0.0, 0])  # n, sum predicted, survived
        bb[0] += 1
        bb[1] = round(bb[1] + c["prediction"], 4)
        bb[2] += int(y)
        ks = st["kind_stats"].setdefault(c["kind"], [0, 0])
        ks[0] += 1
        ks[1] += int(y)
        tested.append(c)
        if not res["survived"]:
            counts["falsified"] += 1
            continue
        counts["survived"] += 1
        _ING.mark(tally, _pr(c), "survived")
        sides = [c["_le"]] + ([c["_re"]] if c.get("_re") is not None else [])
        oe = [oeis_status(e, T, lookup) for e in sides]
        c["oeis"] = [o.get("status") for o in oe]
        c["oeis_anums"] = sorted({a for o in oe for a in (o.get("anums") or [])})[:4]
        derived = [o.get("status") for o in oe if o.get("status") != "primitive"]
        closure = c["kind"] in ("rec", "cong", "modpat") and cf_order(c["_le"]) is not None
        known = known_result(c)
        if known:
            counts["known_result"] = counts.get("known_result", 0) + 1
            c["unknown"] = False
            c["unknown_reason"] = f"known: {known}"
        elif closure:
            # C-finite sequences always satisfy a recurrence and are periodic mod m: expected
            counts["expected_by_closure"] += 1
            c["unknown"] = False
            c["unknown_reason"] = "expected (C-finite closure: a recurrence / periodic residues always exist)"
        elif c.get("loose"):
            counts["loose_inequality"] += 1
            c["unknown"] = False
            c["unknown_reason"] = "loose: equality only at small n (a growth-gap bound, not a tight relation)"
        elif any(s == "unchecked" for s in derived):
            counts["oeis_unchecked"] += 1
            c["unknown"] = False
            c["unknown_reason"] = "OEIS unchecked"
        elif not derived or all(s in ("found", "too_simple") for s in derived):
            counts["oeis_known"] += 1
            c["unknown"] = False
            c["unknown_reason"] = "involved sequences already in OEIS (relation may be known)"
        else:
            c["unknown"] = True
            c["unknown_reason"] = "survived held-out; not trivial; a derived sequence is not in OEIS"
        if c["unknown"]:
            # Stage 2: a surprise only if no reference explains it (colony.reference_check; the
            # filters above are the prefilter). shadow = label only; live = explained -> not a surprise
            try:
                from colony import reference_check as _rc
                if _rc.mode() != "off":
                    if _rc_net is None:
                        _rc_net = _rc.Net()
                    ref = _rc.check(c, T, _rc_net, lookup)
                    c["reference"] = ref["label"]
                    _ING.mark(tally, _pr(c), "explained_by_reference" if ref["explained"] else "no_reference_found")
                    if ref["explained"]:
                        counts["explained_by_reference"] = counts.get("explained_by_reference", 0) + 1
                        if _rc.mode() == "live":
                            c["unknown"] = False
                            c["unknown_reason"] = ref["label"]
                    else:
                        counts["no_reference_found"] = counts.get("no_reference_found", 0) + 1
            except Exception as exc:  # noqa: BLE001
                c["reference"] = f"reference check failed: {str(exc)[:80]}"
        cert = prove(c, T)
        c["label"] = "machine-checked (certificate)" if cert else f"conjecture surviving {c['checks']} checks"
        c["certificate"] = cert
        if cert:
            counts["machine_checked"] += 1
            _ING.mark(tally, _pr(c), "machine_checked")
        fam = family(c)
        s_prev = fam_s.get(fam, 0)
        c["family"] = fam
        c["hunt_value"] = round((k_prior / (s_prev + k_prior)) if c["unknown"] else 0.0, 4)
        if c["unknown"]:
            counts["surprises"] += 1
            fam_s[fam] = s_prev + 1
            _ING.mark(tally, _pr(c), "surprise")
    # learning signal for the colony's own sampling: primitives / operators of surprises
    for c in tested:
        good = int(bool(c.get("unknown")))
        for p in prims_of(c["_le"]) | (prims_of(c["_re"]) if c.get("_re") is not None else set()):
            ps = st["prim_stats"].setdefault(p, [0, 0])
            ps[0] += 1
            ps[1] += good
        for e in [c["_le"]] + ([c["_re"]] if c.get("_re") is not None else []):
            os_ = st["op_stats"].setdefault(e[0], [0, 0])
            os_[0] += 1
            os_[1] += good
    # re-test earlier survivors farther out (false-surprise measurement)
    reg = st["registry"]
    old = sorted(reg.values(), key=lambda r: r.get("retested_to", 0))[:RETEST_PER_CYCLE]
    for r in old:
        try:
            le = parse(r["lhs"])
            re_ = parse(r["rhs"]) if r.get("rhs") else None
        except Exception:  # noqa: BLE001
            continue
        c = {"kind": r["kind"], "params": r["params"], "_le": le, "_re": re_}
        lo = int(r.get("retested_to") or (r.get("range") or [0, 0])[1])
        res = test_claim(c, T, lo, RETEST_CHEAP, RETEST_EXP)
        if not res["tested"]:
            r["retest_exhausted"] = True
            continue
        counts["retested"] += 1
        r["retests"] = int(r.get("retests") or 0) + 1
        r["retested_to"] = res["range"][1]
        r["checks"] = int(r.get("checks") or 0) + res["checks"]
        if not res["survived"]:
            r["falsified_later"] = True
            r["label"] = "falsified on re-test"
            if r.get("unknown"):
                counts["false_surprises"] += 1
                st["totals"]["false_surprises"] = st["totals"].get("false_surprises", 0) + 1
        elif not r.get("certificate"):
            r["label"] = f"conjecture surviving {r['checks']} checks"
    for c in tested:
        if c.get("survived"):
            reg[c["id"]] = {k: c.get(k) for k in ("kind", "lhs", "rhs", "params", "label", "certificate", "checks", "loose",
                                                   "range", "oeis", "oeis_anums", "unknown", "unknown_reason",
                                                   "family", "hunt_value", "prediction", "sig", "reference")} | {
                "statement": statement(c), "found_cycle": cycle_id, "found_at": _utc()}
    if len(reg) > REGISTRY_CAP:  # keep surprises / certified first, then most recent
        keep = sorted(reg.items(), key=lambda kv: (not kv[1].get("unknown"), not kv[1].get("certificate"),
                                                   kv[1].get("found_at", "")), reverse=False)
        st["registry"] = reg = dict(keep[:REGISTRY_CAP])
    st["signatures"] = sorted(sigs)[-SIG_CAP:]
    st["rejected_ids"] = sorted({_h(c["id"]) for c in tested if not c.get("survived")}
                                | set(st.get("rejected_ids") or []))[-SIG_CAP:]
    for k, v in counts.items():
        if k not in ("expressions", "fitted"):
            st["totals"][k] = st["totals"].get(k, 0) + v if k != "false_surprises" else st["totals"].get(k, 0)
    summary = {"ts": _utc(), "cycle_id": cycle_id, "mode": mode(), "fit_n": F, "counts": counts,
               "oeis_index": "available" if lookup else "absent (OEIS unchecked)",
               "brier": round(st["predictions"]["brier_sum"] / st["predictions"]["n"], 4)
               if st["predictions"]["n"] else None,
               "new_survivors": [{"statement": statement(c), "label": c["label"], "unknown": c["unknown"],
                                  "oeis": c.get("oeis"), "hunt_value": c["hunt_value"],
                                  "prediction": c["prediction"]} for c in tested if c.get("survived")][:12]}
    hist = (st.get("history") or []) + [{"ts": summary["ts"], "cycle_id": cycle_id, **counts}]
    st["history"] = hist[-KEEP_CYCLES:]
    st["last"] = summary
    st["mode"] = mode()
    st["note"] = ("Self-chosen conjectures checked on held-out ranges. 'conjecture surviving N checks' is bounded "
                  "evidence, never proof; 'machine-checked' carries a decidable certificate. Report-only unless "
                  "COLONY_FRONTIER=live. See colony/frontier_conjectures.py.")
    if write:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(st, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        if live_tally:
            try:
                _ING.record(cycle_id, "live", tally, summary)
            except Exception:  # noqa: BLE001
                pass
    return summary


# ----------------------------------------------------------------------------- parse canon strings

def parse(s: str) -> tuple:
    s = s.strip()
    if s in PRIMS:
        return ("p", s)
    for op in ("S", "D", "sh", "dbl"):
        if s.startswith(op + "(") and s.endswith(")") and _balanced(s[len(op) + 1:-1]):
            return (op, parse(s[len(op) + 1:-1]))
    if s.startswith("gcd(") and s.endswith(")"):
        a, b = _split_top(s[4:-1], ",")
        return ("gcd", parse(a), parse(b))
    if "[" in s and s.endswith("]"):
        i = s.index("[")
        if s[:i] in PRIMS:
            return ("o", s[:i], parse(s[i + 1:-1]))
    if s.startswith("(") and s.endswith(")"):
        inner = s[1:-1]
        for op in ("+", "-", "*"):
            try:
                a, b = _split_top(inner, op)
                return (op, parse(a), parse(b))
            except ValueError:
                continue
    raise ValueError(s)


def _balanced(s: str) -> bool:
    d = 0
    for ch in s:
        d += ch in "([" 
        d -= ch in ")]"
        if d < 0:
            return False
    return d == 0


def _split_top(s: str, sep: str) -> tuple[str, str]:
    d = 0
    for i, ch in enumerate(s):
        if ch in "([":
            d += 1
        elif ch in ")]":
            d -= 1
        elif ch == sep and d == 0 and i > 0:
            return s[:i], s[i + 1:]
    raise ValueError(s)


def markdown_section(st: dict[str, Any] | None = None, top: int = 8) -> str:
    st = st if st is not None else load_state()
    if not st.get("last"):
        return ""
    L = st["last"]
    c = L["counts"]
    tot = st.get("totals") or {}
    reg = list((st.get("registry") or {}).values())
    sur = [r for r in reg if r.get("unknown") and not r.get("falsified_later")]
    mc = [r for r in reg if r.get("certificate")]
    lines = ["## Frontier conjectures (self-chosen; " + ("LIVE" if st.get("mode") == "live" else "report-only") + ")", "",
             f"Mode `{st.get('mode')}`. Last cycle: {c['tested']} tested, {c['survived']} survived held-out, "
             f"{c['falsified']} falsified, {c['machine_checked']} machine-checked, {c['surprises']} surprises; "
             f"dropped {c['duplicate']} duplicates, {sum(v for k, v in c.items() if k.startswith('trivial_'))} trivial rewrites. "
             f"OEIS index: {L['oeis_index']}. Pre-registration Brier: {L.get('brier')}.",
             f"Totals: tested {tot.get('tested', 0)}, survived {tot.get('survived', 0)}, surprises "
             f"{tot.get('surprises', 0)}, false surprises (failed later re-test) {tot.get('false_surprises', 0)}.",
             f"Reference check (Stage 2, `{os.environ.get('COLONY_REFCHECK') or 'shadow'}`): last cycle "
             f"{c.get('explained_by_reference', 0)} explained by a reference, {c.get('no_reference_found', 0)} with no reference found.",
             "", "| Statement | Label | Reference check | OEIS | Hunt v |", "|---|---|---|---|---|"]
    show = sorted(sur, key=lambda r: -(r.get("hunt_value") or 0))[:top] + mc[: max(0, top // 2)]
    for r in show:
        lines.append(f"| {r['statement']} | {r['label']} | {(r.get('reference') or '')[:160]} "
                     f"| {','.join(r.get('oeis') or [])} | {r.get('hunt_value')} |")
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------- bench bridge

BRIDGE_LIM = 50000
BRIDGE_EXP = 2004
_BRIDGE_T: Any = None


def holds_on(claim: dict[str, Any], lo: int, hi: int) -> int:
    """Number of checks when the claim holds on n in [lo, hi], else 0 (small tables; bench-safe)."""
    global _BRIDGE_T
    if _BRIDGE_T is None:
        _BRIDGE_T = Tables(lim=BRIDGE_LIM, exp_n=BRIDGE_EXP)
    le = parse(claim["lhs"])
    re_ = parse(claim["rhs"]) if claim.get("rhs") else None
    lo, hi = int(lo), int(hi)
    a = evaluate(le, hi, _BRIDGE_T)
    b = evaluate(re_, hi, _BRIDGE_T) if re_ is not None else None
    if a is None or (re_ is not None and b is None) or lo < 1 or hi <= lo:
        return 0
    kind, params = claim["kind"], claim.get("params") or {}
    if kind == "rec":
        k = len(params["c"])
        lo2 = max(1, lo - k)
        ok, n = holds("rec", params, a[lo2 - 1:], None, start=lo2)
    else:
        ok, n = holds(kind, params, a[lo - 1:], b[lo - 1:] if b is not None else None, start=lo)
    return n if ok and n > 0 else 0
