"""Stage 4 proof certificates: the small trusted kernel and the separate CHECKER.

colony.proof_path (the prover) searches for a proof of a surviving frontier conjecture and records
every step; this module re-verifies a certificate step by step without running the search:
  * the value algebra (kernel): a value is c + sum(coef * atom) (mod d), d = 0 meaning exact;
    atoms stand for unknown sequence values at a point a*n + b ("phi@1,0");
  * LEMMAS: classical facts, each a named theorem with its condition (phi(x) even for x >= 3,
    casting out nines, sigma(x) = 0 mod k when x = -1 mod k for k | 24 with 3|k or 4|k, Ramanujan's
    partition congruences, multiplicativity rewrites f(2x) in terms of f(x), periodicity of
    C-finite sequences mod m computed from their defining recurrence, basic inequalities, ...).
    Every lemma is also re-validated numerically on the tables (a guard against a mis-typed lemma);
  * check(cert, T): walks the derivation tree of every residue class, re-derives each node from its
    children with the kernel / lemma functions, checks node expressions are the right
    sub-expressions at the right points, recomputes the running-sum anchor values and the direct
    finite check below N0 from the tables, and checks the conclusion follows.
Certificates are 'machine-proved (certificate)': correct relative to the kernel, the lemma table
(textbook theorems) and the tables used for the finite part. The Collatz lemma is stated for
bounded trajectories (cmax defined), which the colony's tables assume.
"""
from __future__ import annotations

import math
from typing import Any

N0 = 64            # facts marked 'big' are used only for points >= N0; n < N0 is checked directly
NONNEG = {"n", "one", "phi", "sigma", "tau", "omega", "bigomega", "rad", "lpf", "gpf", "sopfr", "digsum",
          "popcount", "pi", "prime", "sqfree", "csteps", "cmax", "maxgap", "gold", "ds3", "rev",
          "pow2", "fib", "lucas", "pell", "part"}
POS = {"n", "one", "phi", "sigma", "tau", "rad", "lpf", "gpf", "prime", "digsum", "popcount", "cmax",
       "maxgap", "ds3", "rev", "pow2", "fib", "lucas", "pell", "part"}


# ----------------------------------------------------------------------------- kernel

def V(c: int = 0, a: dict[str, int] | None = None, d: int = 0) -> dict[str, Any]:
    d = abs(int(d))
    a = {k: int(v) for k, v in (a or {}).items()}
    if d:
        c %= d
        a = {k: v % d for k, v in a.items()}
    a = {k: v for k, v in sorted(a.items()) if v}
    if d == 1:
        c, a = 0, {}
    return {"c": int(c), "a": a, "d": d}


def pure(v: dict[str, Any]) -> bool:
    return not v["a"]


def add(u, v, sign: int = 1):
    a = dict(u["a"])
    for k, x in v["a"].items():
        a[k] = a.get(k, 0) + sign * x
    return V(u["c"] + sign * v["c"], a, math.gcd(u["d"], v["d"]))


def scale(u, k: int):
    return V(k * u["c"], {a: k * x for a, x in u["a"].items()}, k * u["d"])


def mul(u, v):
    if pure(u) and pure(v):
        return V(u["c"] * v["c"], {}, math.gcd(math.gcd(u["d"] * v["d"], u["c"] * v["d"]), v["c"] * u["d"]))
    if not pure(u) and pure(v):
        u, v = v, u
    if pure(u):
        return V(u["c"] * v["c"], {k: u["c"] * x for k, x in v["a"].items()}, math.gcd(u["d"], u["c"] * v["d"]))
    if u["d"] == 0 and v["d"] == 0:   # exact polynomial product; monomials are '*'-joined atoms
        out: dict[str, int] = {}
        tu = [("", u["c"])] + list(u["a"].items())
        tv = [("", v["c"])] + list(v["a"].items())
        for k1, c1 in tu:
            for k2, c2 in tv:
                k = "*".join(sorted([x for x in k1.split("*") + k2.split("*") if x]))
                out[k] = out.get(k, 0) + c1 * c2
        c = out.pop("", 0)
        return V(c, out, 0)
    return None


def reduce_mod(v, M: int):
    """c + sum(coef * atom) with every coef = 0 (mod M) and d = 0 (mod M) is just c (mod M)."""
    if M and (v["d"] == 0 or v["d"] % M == 0) and v["a"] and all(x % M == 0 for x in v["a"].values()):
        return V(v["c"], {}, M)
    return v


def crt(x, y):
    """Combine two pure facts about the same integer; None when inconsistent."""
    (r1, m1), (r2, m2) = (x["c"], x["d"]), (y["c"], y["d"])
    if m1 == 0 or m2 == 0:
        e, o = (x, y) if m1 == 0 else (y, x)
        return e if (o["d"] == 0 and o["c"] == e["c"]) or (o["d"] and (e["c"] - o["c"]) % o["d"] == 0) else None
    g = math.gcd(m1, m2)
    if (r2 - r1) % g:
        return None
    L = m1 // g * m2
    for k in range(m2 // g):
        r = r1 + k * m1
        if (r - r2) % m2 == 0:
            return V(r, {}, L)
    return None


def join(vals):
    """What all of several pure values have in common."""
    c0, d = vals[0]["c"], 0
    for v in vals:
        d = math.gcd(d, v["d"])
        d = math.gcd(d, v["c"] - c0)
    return V(c0, {}, d)


def gcd_val(u, v, u_nonneg: bool, v_nonneg: bool):
    """Value of gcd(x, y) from values of x and y (math.gcd: always >= 0)."""
    facts = []
    for x, y, yn in ((u, v, v_nonneg), (v, u, u_nonneg)):
        if pure(x) and x["d"] == 0:
            c = abs(x["c"])
            if c == 0:              # gcd(0, y) = |y|
                if yn:
                    return y
                if pure(y):
                    g = math.gcd(y["d"], 2)
                    return V(y["c"], {}, g)
                return None
            if c == 1:
                return V(1)
            if pure(y) and (y["d"] % c == 0):
                return V(math.gcd(c, y["c"]))
    for x, y in ((u, v), (v, u)):   # gcd(x, y) with y even has the parity of x
        if pure(y) and y["d"] and y["d"] % 2 == 0 and y["c"] % 2 == 0 and (x["d"] == 0 or x["d"] % 2 == 0) \
                and not pure(x):
            return V(x["c"], x["a"], 2)
    gs = []
    for x in (u, v):
        gs.append(math.gcd(x["c"], x["d"]) if pure(x) else None)
    if gs[0] is not None and gs[1] is not None and math.gcd(gs[0], gs[1]) > 1:
        facts.append(V(0, {}, math.gcd(gs[0], gs[1])))
    if any(pure(x) and x["d"] % 2 == 0 and x["c"] % 2 == 1 for x in (u, v)):
        facts.append(V(1, {}, 2))
    if not facts:
        return None
    out = facts[0]
    for f in facts[1:]:
        out = crt(out, f) or out
    return out


# ----------------------------------------------------------------------------- lemmas
# value lemmas: f(x) for x = r (mod d), x >= 1 (big: x >= N0). Return a pure value or None.

def _sqres(r: int, d: int) -> bool:
    return any((y * y - r) % d == 0 for y in range(d))


def _small_primes(lim: int = 12) -> list[int]:
    return [p for p in range(2, lim) if all(p % q for q in range(2, p))]


def _cfin_rec(name: str):
    return {"fib": ((1, 1), (1, 1)), "lucas": ((1, 3), (1, 1)), "pell": ((1, 2), (2, 1)),
            "pow2": ((2,), (2,))}.get(name)


def cfinite_mod(name: str, m: int) -> tuple[int, int, list[int]] | None:
    """(preperiod start index, period, residues r[1..start+period]) of a C-finite primitive mod m,
    computed from its DEFINING recurrence (fib, lucas: a(n+2) = a(n+1) + a(n); pell: a(n+2) =
    2a(n+1) + a(n); pow2: a(n+1) = 2a(n)): the state repeats (pigeonhole), so it is periodic."""
    spec = _cfin_rec(name)
    if spec is None or m < 2:
        return None
    init, coef = spec
    k = len(init)
    seq = [None] + [x % m for x in init]
    seen = {}
    n = 1
    while True:
        st = tuple(seq[n:n + k])
        if st in seen:
            s0 = seen[st]
            return s0, n - s0, seq
        seen[st] = n
        if len(seq) <= n + k:
            pass
        nxt = 0
        if k == 1:
            nxt = coef[0] * seq[n] % m
        else:
            nxt = (coef[0] * seq[n + 1] + coef[1] * seq[n]) % m
        seq.append(nxt)
        n += 1
        if n > 10 * m * m + 10:
            return None


def _cfin_fact(name: str, r: int, d: int, big: bool):
    best = None
    for pk in (16, 8, 4, 2, 27, 9, 3, 25, 5, 49, 7, 11, 13):
        if best is not None and math.gcd(best["d"], pk) > 1:
            continue
        cm = cfinite_mod(name, pk)
        if cm is None:
            continue
        s0, P, seq = cm
        lo = N0 if big else 1
        if d % P or s0 > lo:
            continue
        x = r % P
        while x < s0:
            x += P
        while len(seq) <= x:
            break
        if x >= len(seq):
            continue
        f = V(seq[x], {}, pk)
        best = f if best is None else (crt(best, f) or best)
    return best


def value_lemma(name: str, r: int, d: int, big: bool) -> tuple[str, dict[str, Any]] | None:
    """(lemma id, value) for f(x), x = r (mod d), d >= 1."""
    out: list[tuple[str, dict[str, Any]]] = []
    if name == "phi" and big:
        out.append(("phi(x) is even for x >= 3", V(0, {}, 2)))
    if name in ("digsum", "rev") and math.gcd(d, 9) > 1:
        g = math.gcd(d, 9)
        out.append((f"{name}(x) = x (mod 9) (casting out nines)", V(r, {}, g)))
    if name == "ds3" and d % 2 == 0:
        out.append(("base-3 digit sum = x (mod 2)", V(r, {}, 2)))
    if name == "prime" and big:
        out.append(("prime(x) is odd for x >= 2", V(1, {}, 2)))
    if name == "lpf":
        for p in _small_primes():
            if d % p == 0 and r % p == 0 and all(d % q == 0 and r % q for q in _small_primes(p)):
                out.append((f"lpf(x) = {p} when {p} | x and no smaller prime divides x", V(p)))
                break
    if name in ("lpf", "gpf", "rad") and d % 2 == 0 and r % 2 == 1:
        out.append((f"{name}(x) is odd for odd x", V(1, {}, 2)))
    if name == "rad":
        P = 1
        for p in _small_primes():
            if d % p == 0 and r % p == 0:
                P *= p
        if P > 1:
            out.append(("p | x implies p | rad(x)", V(0, {}, P)))
    if name in ("mu", "sqfree"):
        for p in (2, 3, 5, 7):
            if d % (p * p) == 0 and r % (p * p) == 0:
                out.append((f"{name}(x) = 0 when {p * p} | x", V(0)))
                break
    if name == "tau" and not _sqres(r, d):
        out.append(("tau(x) is odd iff x is a square", V(0, {}, 2)))
    if name == "tau":   # multiplicativity: x = p^k m with p not dividing m gives tau(x) = (k+1) tau(m)
        K_, why = 1, []
        for p in _small_primes():
            k = 0
            while d % p ** (k + 1) == 0 and r % p ** (k + 1) == 0:
                k += 1
            if k and d % p ** (k + 1) == 0:   # the class fixes the exact power p^k || x
                K_ *= k + 1
                why.append(f"{p}^{k}")
        if K_ > 1:
            out.append((f"tau is multiplicative: exact powers {'*'.join(why)} divide x, so tau(x) = 0 (mod {K_})",
                        V(0, {}, K_)))
    if name == "sigma":
        if not _sqres(r, d) and not any((2 * y * y - r) % d == 0 for y in range(d)):
            out.append(("sigma(x) is odd iff x is a square or twice a square", V(0, {}, 2)))
        for k in (24, 12, 8, 6, 4, 3):
            if d % k == 0 and (r + 1) % k == 0:
                out.append((f"sigma(x) = 0 (mod {k}) when x = -1 (mod {k}) (divisor pairs d, x/d with d^2 = 1 mod {k})",
                            V(0, {}, k)))
                break
    if name == "cmax" and ((d % 2 == 0 and r % 2 == 1) or (d % 3 == 0 and r % 3 == 1)):
        out.append(("Collatz: the maximum of a bounded trajectory from x is x itself or 3y+1 (y odd); "
                    "so it is 1 (mod 3) when x is odd or x = 1 (mod 3)", V(1, {}, 3)))
    if name == "part":
        for q, s in ((5, 4), (7, 5), (11, 6)):
            if d % q == 0 and r % q == s:
                out.append((f"Ramanujan: p({q}k+{s}) = 0 (mod {q})", V(0, {}, q)))
    if name in ("fib", "lucas", "pell", "pow2"):
        f = _cfin_fact(name, r, d, big)
        if f is not None:
            out.append((f"{name} is periodic mod {f['d']} (defining recurrence; state repeats)", f))
    if name == "one":
        out.append(("one(x) = 1", V(1)))
    if not out:
        return None
    lem, val = out[0]
    for l2, v2 in out[1:]:
        c = crt(val, v2)
        if c is not None:
            lem, val = lem + "; " + l2, c
    return lem, val


STEP_COUNTS = ("pi", "cheb4", "cheb3")   # prime counts / prime races: change only at primes


def _no_carry(r: int, d: int) -> bool:
    """x = r (mod d) never ends in the digit 9 (so digsum(x+1) = digsum(x) + 1)."""
    return (d % 10 == 0 and r % 10 != 9) or (d % 2 == 0 and r % 2 == 0)


def _composite_step(r: int, d: int) -> int | None:
    """A small prime p with p | x for every x = r (mod d) (x > p when x >= N0)."""
    for p in _small_primes():
        if d % p == 0 and r % p == 0:
            return p
    return None


def d_lemma(name: str, r: int, d: int, big: bool) -> tuple[str, dict[str, Any]] | None:
    """f(x+1) - f(x) for x = r (mod d)."""
    if name == "digsum" and _no_carry(r, d):
        return "digsum(x+1) = digsum(x) + 1 when x does not end in 9 (no carry; e.g. x even)", V(1)
    if name in STEP_COUNTS and big and _composite_step(r + 1, d):
        return (f"{name} changes only at primes; x+1 is a multiple of {_composite_step(r + 1, d)} "
                f"and > it, so {name}(x+1) = {name}(x)"), V(0)
    if name == "one":
        return "one is constant", V(0)
    return None


def step_lemma(name: str, r: int, d: int, big: bool) -> tuple[str, int] | None:
    """f(x) = f(x-1) + c for x = r (mod d) (a rewrite to the previous point)."""
    if name in STEP_COUNTS and big and _composite_step(r, d):
        return f"{name} changes only at primes; x is composite (a multiple of {_composite_step(r, d)})", 0
    if name == "digsum" and _no_carry(r - 1, d):
        return "digsum(x) = digsum(x-1) + 1 when x-1 does not end in 9 (no carry)", 1
    return None


PRIME_VALUED = {"lpf": "x >= 2", "gpf": "x >= 2", "prime": "x >= 1"}
PRIME_COMPOSE = {"tau": ({}, 2), "omega": ({}, 1), "bigomega": ({}, 1), "mu": ({}, -1), "sqfree": ({}, 1),
                 "phi": ({"g": 1}, -1), "sigma": ({"g": 1}, 1), "rad": ({"g": 1}, 0), "lpf": ({"g": 1}, 0),
                 "gpf": ({"g": 1}, 0), "sopfr": ({"g": 1}, 0)}


def compose_prime_lemma(f: str, g: str, big: bool) -> tuple[str, dict[str, int], int] | None:
    """f(g(x)) when g(x) is a prime p: tau(p) = 2, omega(p) = Omega(p) = 1, mu(p) = -1, phi(p) = p - 1,
    sigma(p) = p + 1, rad = lpf = gpf = sopfr = p."""
    if g in PRIME_VALUED and f in PRIME_COMPOSE and (big or g == "prime"):
        co, c = PRIME_COMPOSE[f]
        return f"{g}(x) is prime ({PRIME_VALUED[g]}); {f} of a prime p is {c:+d}{' + p' if co else ''}", co, c
    return None


def dbl_lemma(name: str, parity: int | None) -> tuple[str, dict[str, int], int] | None:
    """f(2x) = c + k * f(x) for x >= 2 (parity of x when needed): (lemma, {name: k}, c)."""
    always = {"lpf": ({}, 2), "bigomega": ({"bigomega": 1}, 1), "sopfr": ({"sopfr": 1}, 2),
              "gpf": ({"gpf": 1}, 0), "popcount": ({"popcount": 1}, 0)}
    odd = {"omega": ({"omega": 1}, 1), "phi": ({"phi": 1}, 0), "rad": ({"rad": 2}, 0), "mu": ({"mu": -1}, 0),
           "sqfree": ({"sqfree": 1}, 0), "sigma": ({"sigma": 3}, 0), "tau": ({"tau": 2}, 0)}
    even = {"omega": ({"omega": 1}, 0), "phi": ({"phi": 2}, 0), "rad": ({"rad": 1}, 0), "mu": ({}, 0),
            "sqfree": ({}, 0)}
    if name in always:
        f, c = always[name]
        return f"{name}(2x) in terms of {name}(x) (multiplicativity / binary digits)", f, c
    if parity == 1 and name in odd:
        f, c = odd[name]
        return f"{name}(2x) for odd x (multiplicativity, gcd(2, x) = 1)", f, c
    if parity == 0 and name in even:
        f, c = even[name]
        return f"{name}(2x) for even x", f, c
    return None


# inequality library (each valid for x >= N0; instantiated at any point a*n + b, a >= 1, b >= 0)
from colony.frontier_conjectures import BASIC_INEQ, DBL_MONO, SH_MONO  # noqa: E402

# sopfr is completely additive and phi(x) = prod p^(e-1) (p - 1), so
# sopfr(phi(x)) = sum[(e-1) p + sopfr(p-1)] <= sum[(e-1) p + p - 1] = sopfr(x) - omega(x),
# using sopfr(m) <= m for m = p - 1 (with sopfr(1) = 0).
DERIVED_INEQ = ({"sopfr[phi]": -1, "sopfr": 1, "omega": -1},)
INEQ = tuple(dict(f) for f in BASIC_INEQ) + DERIVED_INEQ


def atom(name: str, a: int, b: int) -> str:
    return f"{name}@{a},{b}"


def split_atom(k: str) -> tuple[str, int, int]:
    if "*" in k:
        raise ValueError("monomial")
    nm, pt = k.rsplit("@", 1)
    a, b = pt.split(",")
    return nm, int(a), int(b)


def ineq_instance(kind: str, idx: Any, a: int, b: int) -> dict[str, int]:
    """Linear form (>= 0) of a library inequality at point (a, b); '_k' = constant."""
    if kind == "basic":
        f = INEQ[idx]
        out = {}
        for k, v in f.items():
            if k == "_k":
                out["_k"] = out.get("_k", 0) + v
            elif k == "n":
                out["n@1,0"] = out.get("n@1,0", 0) + v * a
                out["_k"] = out.get("_k", 0) + v * b
            elif k == "one":
                out["_k"] = out.get("_k", 0) + v
            else:
                out[atom(k, a, b)] = out.get(atom(k, a, b), 0) + v
        return out
    if kind == "dbl_mono":
        if idx == "n":
            return {"n@1,0": a, "_k": b}
        return {atom(idx, 2 * a, 2 * b): 1, atom(idx, a, b): -1}
    if kind == "sh_mono":
        if idx == "n":
            return {"_k": 1}
        return {atom(idx, a, b + 1): 1, atom(idx, a, b): -1}
    raise ValueError(kind)


# ----------------------------------------------------------------------------- numeric lemma guard

_GUARD: dict[str, Any] = {}


def guard(T: Any, N: int = 3000) -> dict[str, Any]:
    """Re-validate every lemma family on the tables (a typo guard, not the proof)."""
    if _GUARD:
        return _GUARD
    t = T.t
    bad = []
    lim = min(N, len(t["n"]) - 1)
    for name in ("phi", "digsum", "rev", "ds3", "prime", "lpf", "gpf", "rad", "mu", "sqfree", "tau", "sigma", "cmax",
                 "part", "fib", "lucas", "pell", "pow2"):
        arr = t.get(name)
        if arr is None:
            continue
        L = min(lim, len(arr) - 1)
        for d in (2, 3, 4, 6, 8, 9, 10, 12, 24, 36):
            for r in range(d):
                for big in (False, True):
                    lv = value_lemma(name, r, d, big)
                    if lv is None:
                        continue
                    v = lv[1]
                    for x in range(N0 if big else 1, L + 1):
                        if x % d != r % d:
                            continue
                        if (v["d"] == 0 and arr[x] != v["c"]) or (v["d"] and (arr[x] - v["c"]) % v["d"]):
                            bad.append((name, r, d, big, x))
                            break
    for name in ("digsum", "pi"):
        arr = t[name]
        for d in (2, 10, 20):
            for r in range(d):
                lv = d_lemma(name, r, d, True)
                if lv is None:
                    continue
                for x in range(N0, lim):
                    if x % d == r and arr[x + 1] - arr[x] != lv[1]["c"]:
                        bad.append(("D" + name, r, d, x))
                        break
    for name in ("lpf", "bigomega", "sopfr", "gpf", "popcount", "omega", "phi", "rad", "mu", "sqfree", "sigma", "tau"):
        arr = t[name]
        for x in range(2, lim // 2):
            lm = dbl_lemma(name, x % 2)
            if lm is None:
                continue
            _l, f, c = lm
            if arr[2 * x] != c + sum(k * arr[x] for k in f.values()):
                bad.append(("dbl" + name, x))
                break
    for name in STEP_COUNTS + ("digsum",):
        arr = t.get(name)
        for d in (2, 3, 6, 10):
            for r in range(d):
                lv = step_lemma(name, r, d, True)
                if arr is None or lv is None:
                    continue
                for x in range(N0, lim):
                    if x % d == r and arr[x] != arr[x - 1] + lv[1]:
                        bad.append(("step" + name, r, d, x))
                        break
    for g in PRIME_VALUED:
        for f in PRIME_COMPOSE:
            lm = compose_prime_lemma(f, g, True)
            ga, fa = t.get(g), t.get(f)
            for x in range(2, lim):
                if ga[x] >= len(fa):
                    break
                want = lm[2] + sum(k * ga[x] for k in lm[1].values())
                if fa[ga[x]] != want:
                    bad.append(("compose", f, g, x))
                    break
    comp = {"sopfr[phi]": [0] + [t["sopfr"][t["phi"][x]] for x in range(1, lim + 1)]}
    for i, f in enumerate(INEQ):
        for x in range(N0, lim):
            s = f.get("_k", 0)
            ok = True
            for k, v in f.items():
                if k == "_k":
                    continue
                arr = comp.get(k) or (t.get(k) if k != "n" else t["n"])
                if arr is None or len(arr) <= x:
                    ok = False
                    break
                s += v * arr[x]
            if ok and s < 0:
                bad.append(("ineq", i, x))
                break
    _GUARD.update({"ok": not bad, "bad": bad[:10]})
    return _GUARD


# ----------------------------------------------------------------------------- the checker

def _expr_at(e: tuple, a: int, b: int):
    return e, a, b


def _class_of(cls: tuple[int, int], a: int, b: int) -> tuple[int, int]:
    t, Q = cls[0], cls[1]
    return (a * t + b) % (a * Q), a * Q


def check_node(nd: dict[str, Any], e: tuple, a: int, b: int, cls: tuple[int, int], big: bool, T: Any) -> dict[str, Any]:
    """Re-derive node ``nd`` for expression e at point a*n+b, n in class cls; returns its value or raises."""
    from colony.frontier_conjectures import canon
    if nd.get("e") != canon(e) or nd.get("pt") != [a, b]:
        raise ValueError(f"structure mismatch at {nd.get('e')} vs {canon(e)}")
    rule, val = nd["rule"], nd["val"]
    kids = nd.get("kids") or []
    op = e[0]
    r, d = _class_of(cls, a, b)

    def want(v):
        if nd.get("mod"):
            v = reduce_mod(v, int(nd["mod"]))
        if v != val:
            raise ValueError(f"{rule} at {canon(e)}: recorded {val} != derived {v}")
        return v

    if rule == "atom":
        return want(V(0, {f"{canon(e)}@{a},{b}": 1}))
    if op == "p":
        name = e[1]
        if rule == "n":
            if name != "n":
                raise ValueError("n rule on non-n")
            return want(V(b, {"n@1,0": a}))
        if rule == "nclass":
            if name != "n":
                raise ValueError("n rule on non-n")
            return want(V(r, {}, d))
        if rule == "lemma":
            lv = value_lemma(name, r, d, big)
            if lv is None or lv[0] != nd["lemma"]:
                raise ValueError(f"lemma not applicable: {nd.get('lemma')}")
            return want(lv[1])
        if rule == "step_rw":
            lv = step_lemma(name, r, d, big)
            if lv is None or lv[0] != nd["lemma"] or b < 1:
                raise ValueError("step lemma not applicable")
            return want(V(lv[1], {atom(name, a, b - 1): 1}))
        if rule == "branch":
            bv = branch_value(name, cls, a, b)
            if bv is None or bv[0] != nd["lemma"]:
                raise ValueError("branch value not applicable")
            return want(bv[1])
        if rule == "dbl_rw":
            if a % 2 or b % 2:
                raise ValueError("dbl rewrite needs an even point")
            a2, b2 = a // 2, b // 2
            r2, d2 = _class_of(cls, a2, b2)
            par = r2 % 2 if d2 % 2 == 0 else None
            lm = dbl_lemma(name, par)
            if lm is None or lm[0] != nd["lemma"] or not big:
                raise ValueError("dbl lemma not applicable")
            _l, f, c = lm
            return want(V(c, {atom(k, a2, b2): v for k, v in f.items()}))
        raise ValueError(rule)
    if op in ("+", "-", "*"):
        u = check_node(kids[0], e[1], a, b, cls, big, T)
        v = check_node(kids[1], e[2], a, b, cls, big, T)
        if rule == "arith":
            w = add(u, v, 1 if op == "+" else -1) if op != "*" else mul(u, v)
            if w is None:
                raise ValueError("product of two unknowns")
            return want(w)
        raise ValueError(rule)
    if op == "gcd":
        u = check_node(kids[0], e[1], a, b, cls, big, T)
        v = check_node(kids[1], e[2], a, b, cls, big, T)
        if rule == "gcd_tau":
            if gcd_tau_applies(e, a, b, cls, u, v):
                return want(V(1))
            raise ValueError("gcd_tau not applicable")
        w = gcd_val(u, v, nonneg(e[1]), nonneg(e[2]))
        if w is None:
            raise ValueError("gcd: no fact")
        return want(w)
    if op == "sh":
        return want(check_node(kids[0], e[1], a, b + 1, cls, big, T))
    if op == "dbl":
        return want(check_node(kids[0], e[1], 2 * a, 2 * b, cls, big, T))
    if op == "D":
        if rule == "Dlemma":
            if e[1][0] != "p":
                raise ValueError("D lemma needs a primitive")
            lv = d_lemma(e[1][1], r, d, big)
            if lv is None or lv[0] != nd["lemma"]:
                raise ValueError("D lemma not applicable")
            return want(lv[1])
        if rule == "Dsum":
            u = check_node(kids[0], ("D", e[1][1]), a, b, cls, big, T)
            v = check_node(kids[1], ("D", e[1][2]), a, b, cls, big, T)
            return want(add(u, v, 1 if e[1][0] == "+" else -1))
        if rule == "Dprod":
            A, B = e[1][1], e[1][2]
            da = check_node(kids[0], ("D", A), a, b, cls, big, T)
            db = check_node(kids[1], ("D", B), a, b, cls, big, T)
            va = check_node(kids[2], A, a, b, cls, big, T)
            vb = check_node(kids[3], B, a, b, cls, big, T)
            p1, p2, p3 = mul(da, db), mul(da, vb), mul(va, db)
            if None in (p1, p2, p3):
                raise ValueError("Dprod: product of unknowns")
            return want(add(add(p1, p2), p3))
        if rule == "Ddiff":
            u = check_node(kids[0], e[1], a, b + 1, cls, big, T)
            v = check_node(kids[1], e[1], a, b, cls, big, T)
            return want(add(u, v, -1))
        raise ValueError(rule)
    if op == "o" and rule == "pi_prime":
        if e[1] != "pi" or e[2] != ("p", "prime"):
            raise ValueError("pi_prime rule")
        return want(check_node(kids[0], ("p", "n"), a, b, cls, big, T))
    if op == "o" and rule == "o_prime":
        lm = compose_prime_lemma(e[1], e[2][1] if e[2][0] == "p" else "", big)
        if lm is None or lm[0] != nd["lemma"]:
            raise ValueError("o_prime not applicable")
        return want(V(lm[2], {atom(e[2][1], a, b): k for k in lm[1].values()}))
    if op == "o":
        g = check_node(kids[0], e[2], a, b, cls, big, T)
        if not pure(g):
            raise ValueError("composition of an unknown argument")
        if g["d"] == 0:
            arr = T.t[e[1]]
            if not (1 <= g["c"] < len(arr)):
                raise ValueError("argument out of table")
            return want(V(arr[g["c"]]))
        lv = value_lemma(e[1], g["c"], g["d"], False)
        if lv is None or lv[0] != nd["lemma"]:
            raise ValueError("composition lemma not applicable")
        return want(lv[1])
    if op == "S" and rule == "S2":
        Qj, de = nd["Qj"], nd["de"]
        r0, d0 = _class_of(cls, a, b)
        if d0 % 2 or r0 % 2 == 0 or Qj < 1 or de < 1:
            raise ValueError("S2 needs an odd point")
        if len(nd["blocks"]) != Qj:
            raise ValueError("S2 blocks")
        for u in range(Qj):
            w0 = check_node(nd["blocks"][u][0], e[1], 2, 0, (u, Qj), True, T)
            w1 = check_node(nd["blocks"][u][1], e[1], 2, 1, (u, Qj), True, T)
            w = reduce_mod(add(w0, w1), de)
            if not pure(w) or (w["d"] % de if w["d"] else False):
                raise ValueError("S2: block sum not known mod de")
        P = 2 * Qj * de
        L = d0 * P // math.gcd(d0, P)
        x = evaluate_prefix(e[1], T, N0 + L + 3)
        vals = []
        for j in range(L // d0):
            Ns = (r0 + j * d0) % L
            while Ns < N0 + 2:
                Ns += L
            vals.append(V(x[Ns - 1], {}, de))
        return want(join(vals))
    if op == "S":
        Qe, de = nd["Qe"], nd["de"]
        if a * cls[1] % Qe or de < 1:
            raise ValueError("S: class modulus")
        inner = nd["inner"]
        if len(inner) != Qe:
            raise ValueError("S: inner classes")
        for j in range(Qe):
            w = check_node(inner[j], e[1], 1, 0, (j, Qe), True, T)
            if not pure(w) or (w["d"] % de if w["d"] else False):
                raise ValueError("S: inner value not known mod de")
        P = Qe * de
        r0, d0 = _class_of(cls, a, b)
        L = d0 * P // math.gcd(d0, P)
        x = evaluate_prefix(e[1], T, N0 + L + 1)
        vals = []
        for j in range(L // d0):
            rr = (r0 + j * d0) % L
            Ns = rr
            while Ns < N0:
                Ns += L
            vals.append(V(x[Ns - 1], {}, de))
        return want(join(vals))
    raise ValueError(f"unknown op {op}")


def branch_value(name: str, cls: tuple, a: int, b: int):
    """Squarefree case split: cls[2] = 0 (sqfree(n) = 0) or 1 (sqfree(n) = 1); only at the point n."""
    br = cls[2] if len(cls) > 2 else None
    if br is None or (a, b) != (1, 0):
        return None
    if br == 0 and name in ("sqfree", "mu"):
        return f"case sqfree(n) = 0: {name}(n) = 0", V(0)
    if br == 1:
        if name == "sqfree":
            return "case sqfree(n) = 1", V(1)
        if name == "mu":
            return "case sqfree(n) = 1: mu(n) = +-1 is odd", V(1, {}, 2)
        if name == "rad":
            return "case sqfree(n) = 1: rad(n) = n", V(0, {"n@1,0": 1})
        if name == "tau":
            return "case sqfree(n) = 1: tau(n) = 2^omega(n) is even (n >= 2)", V(0, {}, 2)
    return None


def gcd_tau_applies(e: tuple, a: int, b: int, cls: tuple, u, v) -> bool:
    """case sqfree(n) = 1: tau(n) = 2^omega(n), so gcd(odd, tau(n)) = 1."""
    if len(cls) < 3 or cls[2] != 1 or (a, b) != (1, 0):
        return False
    for ex, y in ((e[1], v), (e[2], u)):   # ex = the tau operand, y = the other operand's value
        if ex == ("p", "tau") and pure(y) and y["d"] and y["d"] % 2 == 0 and y["c"] % 2 == 1:
            return True
    return False


def evaluate_prefix(e: tuple, T: Any, N: int) -> list[int]:
    from colony.frontier_conjectures import evaluate
    s = evaluate(("S", e), N, T)
    if s is None:
        raise ValueError("S anchor out of table")
    return s


def nonneg(e: tuple) -> bool:
    op = e[0]
    if op == "p":
        return e[1] in NONNEG
    if op == "gcd":
        return True
    if op in ("S", "sh", "dbl"):
        return nonneg(e[1])
    if op in ("+", "*"):
        return nonneg(e[1]) and nonneg(e[2])
    if op == "o":
        return e[1] in NONNEG
    return False


def positive(e: tuple) -> bool:
    op = e[0]
    if op == "p":
        return e[1] in POS
    if op == "gcd":
        return positive(e[1]) or positive(e[2])
    if op in ("sh", "dbl"):
        return positive(e[1])
    if op == "S":
        return positive(e[1])
    if op in ("+", "*"):
        return positive(e[1]) and positive(e[2])
    if op == "o":
        return e[1] in POS
    return False


def _finite(c: dict[str, Any], T: Any, lo: int, hi: int) -> bool:
    from colony.frontier_conjectures import evaluate, holds
    if hi < lo:
        return True
    if c["kind"] == "rec":
        k = len(c["params"]["c"])
        a = evaluate(c["_le"], hi + k, T)
        return a is not None and holds("rec", c["params"], a[lo - 1:], None, start=lo)[0]
    a = evaluate(c["_le"], hi, T)
    b = evaluate(c["_re"], hi, T) if c.get("_re") is not None else None
    if a is None or (c.get("_re") is not None and b is None):
        return False
    return holds(c["kind"], c["params"], a[lo - 1:], b[lo - 1:] if b is not None else None, start=lo)[0]


def _branches(node: dict[str, Any], cls: tuple):
    if node.get("split") == "sqfree":
        return [(node["b0"], (cls[0], cls[1], 0)), (node["b1"], (cls[0], cls[1], 1))]
    return [(node, cls)]


def divides_ok(u, v, lhs_positive: bool) -> bool:
    if pure(v) and v["d"] == 0 and v["c"] == 0 and lhs_positive:
        return True
    if pure(u) and u["d"] == 0 and u["c"] != 0 and pure(v) and v["c"] % u["c"] == 0 \
            and (v["d"] == 0 or v["d"] % u["c"] == 0):
        return True
    if u["d"] == 0 and v["d"] == 0 and u["a"] and lhs_positive:     # v = k * u exactly
        k0, x0 = next(iter(u["a"].items()))
        if v["a"].get(k0, 0) % x0 == 0:
            k = v["a"].get(k0, 0) // x0
            if scale(u, k) == v:
                return True
    return False


def check(cert: dict[str, Any], claim: dict[str, Any], T: Any) -> tuple[bool, str]:
    """Re-verify a Stage 4 certificate for ``claim`` (registry form: kind, lhs, rhs, params)."""
    from colony import frontier_conjectures as FC
    try:
        g = guard(T)
        if not g["ok"]:
            return False, f"lemma guard failed: {g['bad'][:2]}"
        c = {"kind": claim["kind"], "params": claim.get("params") or {}, "_le": FC.parse(claim["lhs"]),
             "_re": FC.parse(claim["rhs"]) if claim.get("rhs") else None}
        Q, method = int(cert["Q"]), cert["method"]
        if method == "recurrence residues":
            return _check_recres(cert, c, T)
        if cert.get("N0") != N0:
            return False, "N0 mismatch"
        p = c["params"]
        need = [t for t in range(Q) if c["kind"] != "cong" or t % p["q"] == p["s"]]
        if c["kind"] == "cong" and Q % p["q"]:
            return False, "Q must be a multiple of q"
        if sorted(int(k) for k in cert["classes"]) != need:
            return False, "classes do not cover the claim"
        for t in need:
            node = cert["classes"][str(t)]
            cls = (t, Q)
            if method == "periodic residues":
                if c["kind"] == "cong":
                    for sub, bcls in _branches(node, cls):
                        v = reduce_mod(check_node(sub["lhs"], c["_le"], 1, 0, bcls, True, T), p["m"])
                        if not pure(v) or (v["d"] and v["d"] % p["m"]) or (v["c"] - p["r"]) % p["m"]:
                            return False, f"class {t}: value {v} does not give {p['r']} mod {p['m']}"
                elif c["kind"] == "divides":
                    for sub, bcls in _branches(node, cls):
                        u = check_node(sub["lhs"], c["_le"], 1, 0, bcls, True, T)
                        v = check_node(sub["rhs"], c["_re"], 1, 0, bcls, True, T)
                        if not divides_ok(u, v, positive(c["_le"])):
                            return False, f"class {t}: divisibility not derived"
                else:
                    return False, "kind"
            elif method in ("basic-inequality derivation", "closed form (sympy)"):
                if c["kind"] == "le":
                    u = check_node(node["lhs"], c["_le"], 1, 0, cls, True, T)
                    v = check_node(node["rhs"], c["_re"], 1, 0, cls, True, T)
                    if u["d"] or v["d"]:
                        return False, "inequality needs exact values"
                    form = add(v, u, -1)
                    rem = dict(form["a"])
                    rem["_k"] = form["c"]
                    for kind, idx, a, b, lam in node["steps"]:
                        if a < 1 or b < 0 or lam < 0:
                            return False, "bad instance"
                        if kind == "basic" and not (0 <= idx < len(INEQ)):
                            return False, "bad lemma"
                        if kind == "dbl_mono" and idx not in DBL_MONO or kind == "sh_mono" and idx not in SH_MONO:
                            return False, "bad mono lemma"
                        for k, x in ineq_instance(kind, idx, a, b).items():
                            rem[k] = rem.get(k, 0) - lam * x
                    if any(x for k, x in rem.items() if k != "_k") or rem.get("_k", 0) < 0:
                        return False, f"class {t}: derivation leaves {rem}"
                else:
                    ok, why = _check_closed(c, node, cls, T)
                    if not ok:
                        return False, f"class {t}: {why}"
            else:
                return False, "method"
        start = 1
        if not _finite(c, T, start, N0 - 1):
            return False, "finite check below N0 failed"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"error: {str(exc)[:160]}"


# closed forms of C-finite atoms (sympy), used by method 'closed form (sympy)'
def closed_atom(name: str, a: int, b: int, n):
    import sympy as sp
    x = a * n + b
    s5, s2 = sp.sqrt(5), sp.sqrt(2)
    phi_, psi_ = (1 + s5) / 2, (1 - s5) / 2
    if name == "pow2":
        return sp.Integer(2) ** x
    if name == "fib":
        return (phi_ ** x - psi_ ** x) / s5
    if name == "lucas":
        return phi_ ** x + psi_ ** x
    if name == "pell":
        return ((1 + s2) ** x - (1 - s2) ** x) / (2 * s2)
    if name == "n":
        return x
    return None


def closed_value(v: dict[str, Any], n):
    import sympy as sp
    if v["d"]:
        return None
    out = sp.Integer(v["c"])
    for k, co in v["a"].items():
        term = sp.Integer(co)
        for part in k.split("*"):
            nm, a, b = split_atom(part)
            f = closed_atom(nm, a, b, n)
            if f is None:
                return None
            term *= f
        out += term
    return out


def sym_zero(expr) -> bool:
    import sympy as sp
    z = sp.simplify(sp.expand(sp.powsimp(sp.expand(expr), force=True)))
    if z == 0:
        return True
    z = sp.nsimplify(sp.simplify(sp.expand(sp.expand_power_base(sp.expand(expr), force=True))))
    return z == 0


def _check_closed(c: dict[str, Any], node: dict[str, Any], cls: tuple[int, int], T: Any) -> tuple[bool, str]:
    import sympy as sp
    n = sp.Symbol("n", integer=True, positive=True)
    if c["kind"] == "identity":
        u = check_node(node["lhs"], c["_le"], 1, 0, cls, True, T)
        v = check_node(node["rhs"], c["_re"], 1, 0, cls, True, T)
        cu, cv = closed_value(u, n), closed_value(v, n)
        if cu is None or cv is None:
            return False, "no closed form"
        return (True, "ok") if sym_zero(cu - cv) else (False, "closed forms differ")
    if c["kind"] == "rec":
        co = c["params"]["c"]
        k = len(co)
        vals = []
        for i in range(k + 1):
            vals.append(check_node(node["shifts"][i], c["_le"], 1, i, cls, True, T))
        cl = [closed_value(v, n) for v in vals]
        if any(x is None for x in cl):
            return False, "no closed form"
        res = cl[k] - sum(ci * cl[j] for j, ci in enumerate(co))
        return (True, "ok") if sym_zero(res) else (False, "recurrence residual is not 0")
    return False, "kind"


# ----------------------------------------------------------------------------- recurrence residues
# James 2026-10-23: a congruence / residue-pattern claim on sequences that satisfy a verified linear
# recurrence with integer coefficients is elementary. Mod m the recurrence state takes at most m^d
# values, so each part is eventually periodic (pigeonhole); + - * shifts, differences, a(2n) and
# partial sums keep that, with a computable preperiod and period, so checking every n below
# preperiod + lcm(period, q) settles the claim for all n. The checker recomputes everything from
# the stated recurrences and the tables; the certificate is relative to those recurrences holding
# for all n (each is an OEIS-listed signature or a defining recurrence, re-checked on the table).
RR_CAP = 200_000
RR_CERT_SOURCES = ("oeis", "defining")


def _rr_ok_tree(e: tuple, root: bool, kind: str, params: dict[str, Any]) -> bool:
    op = e[0]
    if op == "p":
        return True
    if op in ("S", "D", "sh", "dbl"):
        return _rr_ok_tree(e[1], False, kind, params)
    if op in ("+", "-", "*"):
        return _rr_ok_tree(e[1], False, kind, params) and _rr_ok_tree(e[2], False, kind, params)
    if op == "gcd":
        # m | gcd(a, b) iff m | a and m | b, so only "gcd(..) = 0 mod m" at the top is decided by residues
        return (root and kind == "cong" and int(params.get("r", -1)) == 0
                and _rr_ok_tree(e[1], False, kind, params) and _rr_ok_tree(e[2], False, kind, params))
    return False


def rec_fits(x: list[int], sig: list[int], k0: int) -> bool:
    d = len(sig)
    return (d > 0 and len(x) - k0 >= 3 * d + 20
            and all(x[i] == sum(sig[j] * x[i - 1 - j] for j in range(d)) for i in range(k0 + d, len(x))))


def rec_residues(x: list[int], sig: list[int], k0: int, m: int, cap: int = RR_CAP):
    """(u, pre, P): u[i] = x[i] mod m (0-based), eventually periodic from index pre with period P."""
    d = len(sig)
    u = [v % m for v in x[:k0 + d]]
    seen: dict[tuple, int] = {}
    i = k0 + d
    while i <= cap:
        st = tuple(u[i - d:i])
        if st in seen:
            j = seen[st]
            return u, j - d, i - j
        seen[st] = i
        u.append(sum(sig[t] * u[i - 1 - t] for t in range(d)) % m)
        i += 1
    return None


def _rr_shape(e: tuple, per: dict[str, tuple[int, int]], m: int) -> tuple[int, int]:
    """(first n from which e(n) mod m is periodic, period); n is 1-based."""
    op = e[0]
    if op == "p":
        return per[e[1]]
    if op in ("S", "D", "sh", "dbl"):
        a, P = _rr_shape(e[1], per, m)
        if op == "sh":
            return max(1, a - 1), P
        if op == "dbl":
            return max(1, (a + 1) // 2), P
        if op == "S":
            return a, P * m
        return a, P
    (a, P), (b, R) = _rr_shape(e[1], per, m), _rr_shape(e[2], per, m)
    return max(a, b), P * R // math.gcd(P, R)


def _rr_need(e: tuple, N: int, out: dict[str, int]) -> None:
    op = e[0]
    if op == "p":
        out[e[1]] = max(out.get(e[1], 0), N)
    elif op in ("D", "sh"):
        _rr_need(e[1], N + 1, out)
    elif op == "dbl":
        _rr_need(e[1], 2 * N, out)
    elif op == "S":
        _rr_need(e[1], N, out)
    else:
        _rr_need(e[1], N, out)
        _rr_need(e[2], N, out)


def recurrence_residues(c: dict[str, Any], T: Any, recs: dict[str, dict[str, Any]],
                        cap: int = RR_CAP) -> dict[str, Any] | None:
    """Settle a cong / modpat claim from its parts' linear recurrences: {'holds', 'first_fail',
    'period', 'pre', 'checked_to'}; None when the method does not apply."""
    from colony import frontier_conjectures as FC
    kind, p = c["kind"], c.get("params") or {}
    if kind not in ("cong", "modpat") or c.get("_re") is not None or not _rr_ok_tree(c["_le"], True, kind, p):
        return None
    m = int(p["m"])
    if m < 2:
        return None
    per: dict[str, tuple[int, int]] = {}
    res: dict[str, tuple[list[int], int, int]] = {}
    for name in FC.prims_of(c["_le"]):
        rc = recs.get(name)
        if not rc:
            return None
        x = [int(v) for v in (T.t.get(name) or [])[1:]]
        sig, k0 = [int(v) for v in rc["sig"]], int(rc["k0"])
        if not rec_fits(x, sig, k0):
            return None
        got = rec_residues(x, sig, k0, m, cap)
        if got is None:
            return None
        u, pre, P = got
        res[name] = got
        per[name] = (pre + 1, P)
    a, P = _rr_shape(c["_le"], per, m)
    q = int(p["q"]) if kind == "cong" else int(p["P"])
    L = P * q // math.gcd(P, q)
    N = a + L
    if N > cap:
        return None
    need: dict[str, int] = {}
    _rr_need(c["_le"], N, need)
    tab: dict[str, list[int]] = {}
    for name, L_n in need.items():
        u, pre, Pp = res[name]
        tab[name] = [0] + [u[i] if i < len(u) else u[pre + (i - pre) % Pp] for i in range(L_n + 1)]
    vals = FC.evaluate(c["_le"], N, T, tab=tab)
    if vals is None:
        return None
    ok, _ = FC.holds(kind, p, vals, None)
    first = None
    if not ok:
        for n in range(1, N + 1):
            if not FC.holds(kind, p, vals[n - 1:n], None, start=n)[0]:
                first = n
                break
    return {"holds": ok, "first_fail": first, "period": L, "pre": a, "checked_to": N}


def _check_recres(cert: dict[str, Any], c: dict[str, Any], T: Any) -> tuple[bool, str]:
    recs = cert.get("recurrences") or {}
    if not recs or any(not str(r.get("source", "")).startswith(RR_CERT_SOURCES) for r in recs.values()):
        return False, "recurrence source not citable"
    got = recurrence_residues(c, T, recs)
    if got is None:
        return False, "recurrence residues do not apply"
    if not got["holds"]:
        return False, f"fails at n = {got['first_fail']}"
    return True, "ok"


# ----------------------------------------------------------------------------- OEIS conjectures (C-finite)
# Separate checker for certificates from colony.oeis_conjectures.attempt_prove. It uses only the
# independent evaluator colony.oeis_eval_b (path B), never the prover's path-A code:
#   gf_identity       the definition's g.f. P/Q (rational g.f., or the g.f. of a constant-coefficient
#                     linear recurrence with the b-file initial terms) and the conjectured g.f. P2/Q2
#                     satisfy P*Q2 == P2*Q as polynomials;
#   cfinite_identity  every side of the conjectured identity is built from a(c*n+j), fib/lucas(c*n+j),
#                     n, constants, c^n with + - * (and / by constants); the difference is C-finite of
#                     order <= D (sum / product order bounds) on n >= S, so D consecutive zeros from S
#                     prove it for all n >= S; n0 <= n < S is checked term by term.
# Both require that the quoted OEIS definition re-parses to the certificate's definition and that the
# definition reproduces every b-file term handed in.


def _oe_def_terms(d: dict[str, Any], off: int, terms: list[int], L: int):
    from colony import oeis_eval_b as OB
    from fractions import Fraction
    if d["kind"] == "gf":
        num, den = OB.rational(OB.compile_expr(d["expr"]))
        if den[0] == 0:
            return None
        co = OB.series(num, den, off + L)
        if any(c.denominator != 1 for c in co):
            return None
        dn = len(num) - 1
        dd = len(den) - 1
        m0 = max(dn + 1, dd)
        return {"terms": [int(c) for c in co[off:]], "W": m0 - dd, "order": dd, "num": num, "den": den}
    lin = {int(k): Fraction(v) for k, v in (d.get("linear") or {}).items()}
    if not lin or d["kind"] != "rec":
        return None
    K = max(lin)
    xs = list(terms[:K])
    if len(xs) < K:
        return None
    while len(xs) < L:
        v = sum(c * xs[len(xs) - i] for i, c in lin.items())
        if v.denominator != 1:
            return None
        xs.append(int(v))
    den = [Fraction(1)] + [-lin.get(i, Fraction(0)) for i in range(1, K + 1)]
    A = [Fraction(0)] * off + [Fraction(v) for v in xs[:K + 1]]
    num = OB.pmul(A, den)[:off + K]
    return {"terms": xs, "W": off, "order": K, "num": num, "den": den}


def _oe_order(code, a_order: int, a_W: int):
    """(order bound D, start S) of an RPN expression, or None when outside the C-finite class."""
    st: list[tuple] = []
    for t in code:
        if t[0] == "num":
            st.append(("c", t[1]))
        elif t[0] == "var":
            if t[1] != "n":
                return None
            st.append(("i", (1, 0)))
        elif t[0] == "op":
            o = t[1]
            if o == "neg":
                k, v = st.pop()
                st.append((k, (-v[0], -v[1])) if k == "i" else (k, -v) if k == "c" else (k, v))
                continue
            (k2, v2), (k1, v1) = st.pop(), st.pop()

            def sq(k, v):
                if k == "c":
                    return (1, -10 ** 9)
                if k == "i":
                    return (2, -10 ** 9)
                return v
            if o in "+-":
                if k1 in "ci" and k2 in "ci":
                    i1 = v1 if k1 == "i" else (0, v1)
                    i2 = v2 if k2 == "i" else (0, v2)
                    s = 1 if o == "+" else -1
                    r = (i1[0] + s * i2[0], i1[1] + s * i2[1])
                    st.append(("c", r[1]) if r[0] == 0 else ("i", r))
                else:
                    (d1, s1), (d2, s2) = sq(k1, v1), sq(k2, v2)
                    st.append(("s", (d1 + d2, max(s1, s2))))
            elif o == "*":
                if k1 == "c" and k2 == "c":
                    st.append(("c", v1 * v2))
                elif k1 == "c" or k2 == "c":
                    c, (k, v) = (v1, (k2, v2)) if k1 == "c" else (v2, (k1, v1))
                    st.append(("i", (c * v[0], c * v[1])) if k == "i" else (k, v) if k == "s" else ("c", 0))
                else:
                    (d1, s1), (d2, s2) = sq(k1, v1), sq(k2, v2)
                    st.append(("s", (d1 * d2, max(s1, s2))))
            elif o == "/":
                if k2 != "c" or v2 == 0:
                    return None
                st.append(("s", sq(k1, v1)) if k1 != "c" else ("s", (1, -10 ** 9)))
            else:  # ^
                if k1 == "c" and k2 == "i" and v1 != 0 and v2[0] >= 0:
                    st.append(("s", (1, -10 ** 9)))
                elif k2 == "c" and 0 <= v2 <= 12:
                    if k1 == "c":
                        st.append(("c", v1 ** v2))
                    else:
                        d, s = sq(k1, v1)
                        st.append(("s", (d ** v2 if v2 else 1, s)))
                else:
                    return None
        else:
            name = t[1]
            if t[2] != 1:
                return None
            k, v = st.pop()
            if k == "c":
                v = (0, v)
            elif k != "i":
                return None
            c, j = v
            if c < 1:
                return None
            if name == "a":
                st.append(("s", (a_order, -((j - a_W) // c))))
            elif name in ("fib", "lucas"):
                st.append(("s", (2, -(j // c))))
            else:
                return None
    if len(st) != 1:
        return None
    k, v = st[0]
    if k == "c":
        return 1, -10 ** 9
    if k == "i":
        return 2, -10 ** 9
    return v


def check_oeis(cert: dict[str, Any], terms: list[int]) -> tuple[bool, str]:
    from colony import oeis_eval_b as OB
    from colony import oeis_conjectures as OC  # normaliser only (text -> canonical grammar)
    try:
        d = cert["definition"]
        if OC.parse_definition(cert["def_text"]) != d:
            return False, "definition does not re-parse from the quoted OEIS name"
        off = int(cert["offset"])
        claim = cert["claim"]
        if cert["type"] == "gf_identity":
            if claim.get("form") != "gf":
                return False, "claim is not a g.f."
            D = _oe_def_terms(d, off, terms, len(terms) + 8)
            if D is None or D["terms"][:len(terms)] != list(terms):
                return False, "definition does not reproduce the b-file"
            p2, q2 = OB.rational(OB.compile_expr(claim["expr"]))
            ok = OB.poly_eq(OB.pmul(D["num"], q2), OB.pmul(p2, D["den"]))
            return (True, "polynomial identity P*Q2 == P2*Q") if ok else (False, "g.f.s differ")
        if cert["type"] == "holonomic_identity":
            if d["kind"] not in ("gf", "alg"):
                return False, "holonomic certificate needs a g.f. definition"
            if claim.get("form") != "relation" or claim.get("mod"):
                return False, "claim is not an identity"
            return check_holonomic(d["expr"], off, claim["parts"], claim["rels"], claim.get("n0"), terms)
        if cert["type"] != "cfinite_identity":
            return False, "unknown certificate type"
        if claim.get("form") != "relation" or claim.get("mod") or any(r != "=" for r in claim["rels"]):
            return False, "claim is not an identity"
        D0 = _oe_def_terms(d, off, terms, len(terms) + 8)
        if D0 is None or D0["terms"][:len(terms)] != list(terms):
            return False, "definition does not reproduce the b-file"
        n0 = claim.get("n0")
        n0 = off if n0 is None else max(off, int(n0))
        codes = [OB.compile_expr(p) for p in claim["parts"]]
        bounds = [_oe_order(c, D0["order"], D0["W"] if d["kind"] == "gf" else off) for c in codes]
        if any(b is None for b in bounds):
            return False, "a side is outside the C-finite class"
        need_hi = 0
        plan = []
        for i in range(len(codes) - 1):
            Dd = bounds[i][0] + bounds[i + 1][0]
            S = max(n0, bounds[i][1], bounds[i + 1][1])
            plan.append((i, S, Dd))
            need_hi = max(need_hi, S + Dd)
        L = 4 * (need_hi + 8) + 64
        if L > 200000:
            return False, "order bound too large"
        xs = _oe_def_terms(d, off, terms, L)["terms"]

        def seq(nm, i):
            if nm != "a" or i < off or i - off >= len(xs):
                raise OB.Missing(nm)
            return xs[i - off]
        checked = 0
        for i, S, Dd in plan:
            for n in range(n0, S + Dd):
                try:
                    x = OB.evaluate(codes[i], {"n": n}, seq)
                    y = OB.evaluate(codes[i + 1], {"n": n}, seq)
                except OB.Missing:
                    if n >= S:
                        return False, "term needed for the finite check is missing"
                    continue
                if x != y:
                    return False, f"identity fails at n = {n}"
                checked += 1
        return True, f"C-finite order bounds {[(S, Dd) for _, S, Dd in plan]}; {checked} points checked"
    except (OB.Bad, KeyError, TypeError, ValueError, ZeroDivisionError) as ex:
        return False, "checker error: " + str(ex)[:80]


# ----------------------------------------------------------------------------- holonomic certificates
# For a g.f. f = U + V*s with s^2 = C, C(0) = 1 (one square root; rational g.f.s are V = 0), work in the
# ring Q(x)[s]/(s^2 - C) with derivation s' = C' s / (2C). A claimed recurrence
#     sum_i p_i(n) a(n - i) = 0        (polynomial p_i)
# has generating function R = sum_i p_i(theta)(x^i f), theta = x d/dx. If R reduces to u + v s with
# v == 0 and u a polynomial, the coefficient of x^n vanishes for every n > deg u: the recurrence holds
# there (sound: the map to power series, s -> the series sqrt(C) with constant 1, is a ring map that
# commutes with d/dx). The remaining n are checked directly on exact terms of the definition.

def _q2_parse(expr: str):
    import ast as _ast
    import sympy as sp
    X = sp.Symbol("x")
    Cbox: list[Any] = []

    def mul(a, b):
        C = Cbox[0] if Cbox else 0
        return (sp.cancel(a[0] * b[0] + a[1] * b[1] * C), sp.cancel(a[0] * b[1] + a[1] * b[0]))

    def inv(a):
        C = Cbox[0] if Cbox else 0
        nrm = sp.cancel(a[0] ** 2 - a[1] ** 2 * C)
        if nrm == 0:
            raise ValueError("zero divisor")
        return (sp.cancel(a[0] / nrm), sp.cancel(-a[1] / nrm))

    def root(a):
        if a[1] != 0:
            raise ValueError("nested radical")
        c = sp.cancel(a[0])
        if c.subs(X, 0) != 1:
            raise ValueError("sqrt needs constant term 1")
        if not Cbox:
            Cbox.append(c)
            return (sp.Integer(0), sp.Integer(1))
        r = sp.cancel(c / Cbox[0])
        if r == 1:
            return (sp.Integer(0), sp.Integer(1))
        raise ValueError("more than one radical")

    def pw(a, k):
        r = (sp.Integer(1), sp.Integer(0))
        b = a if k >= 0 else inv(a)
        for _ in range(abs(k)):
            r = mul(r, b)
        return r

    def ev(nd):
        if isinstance(nd, _ast.Constant) and isinstance(nd.value, int):
            return (sp.Integer(nd.value), sp.Integer(0))
        if isinstance(nd, _ast.Name) and nd.id == "x":
            return (X, sp.Integer(0))
        if isinstance(nd, _ast.UnaryOp):
            v = ev(nd.operand)
            return (-v[0], -v[1]) if isinstance(nd.op, _ast.USub) else v
        if isinstance(nd, _ast.Call) and isinstance(nd.func, _ast.Name) and nd.func.id == "sqrt" and len(nd.args) == 1:
            return root(ev(nd.args[0]))
        if isinstance(nd, _ast.BinOp):
            if isinstance(nd.op, _ast.Pow):
                e = nd.right
                sg = 1
                if isinstance(e, _ast.UnaryOp) and isinstance(e.op, _ast.USub):
                    sg, e = -1, e.operand
                if isinstance(e, _ast.Constant) and isinstance(e.value, int) and e.value <= 64:
                    return pw(ev(nd.left), sg * e.value)
                if (isinstance(e, _ast.BinOp) and isinstance(e.op, _ast.Div) and isinstance(e.left, _ast.Constant)
                        and isinstance(e.right, _ast.Constant) and e.right.value == 2 and isinstance(e.left.value, int)
                        and abs(e.left.value) <= 63):
                    return pw(root(ev(nd.left)), sg * e.left.value)
                raise ValueError("exponent")
            a, b = ev(nd.left), ev(nd.right)
            if isinstance(nd.op, _ast.Add):
                return (a[0] + b[0], a[1] + b[1])
            if isinstance(nd.op, _ast.Sub):
                return (a[0] - b[0], a[1] - b[1])
            if isinstance(nd.op, _ast.Mult):
                return mul(a, b)
            if isinstance(nd.op, _ast.Div):
                return mul(a, inv(b))
        raise ValueError("node outside the grammar")
    f = ev(_ast.parse(expr.replace("^", "**"), mode="eval").body)
    return f, (Cbox[0] if Cbox else sp.Integer(0)), X


def holonomic_form(parts: list[str], rels: list[str]):
    """Claim text (two sides, '=') -> {i: polynomial p_i(n) (sympy)} with sum_i p_i(n) a(n-i) = 0, or raise."""
    import re
    import sympy as sp
    if len(parts) != 2 or rels != ["="]:
        raise ValueError("not a single identity")
    nS = sp.Symbol("n")
    syms: dict[int, Any] = {}

    def conv(t: str):
        def rep(m):
            sgn, k = m.group(1), m.group(2)
            i = int(k) * (-1 if sgn == "+" else 1) if k else 0
            syms.setdefault(i, sp.Symbol("A_%d" % (i + 1000)))
            return "A_%d" % (i + 1000)
        t2 = re.sub(r"\ba\(\s*n\s*(?:([-+])\s*(\d+))?\s*\)", rep, t)
        if re.search(r"\ba\(|A\d{6}|[a-mo-z]\(", t2.replace("A_", "")):
            raise ValueError("term outside a(n-i)")
        return sp.sympify(t2.replace("^", "**"), locals={"n": nS, **{str(v): v for v in syms.values()}})
    E = sp.expand(sp.together(conv(parts[0]) - conv(parts[1])))
    num, den = sp.fraction(sp.together(E))
    num = sp.expand(num)
    coeffs = {}
    rest = num
    for i, A in syms.items():
        c = sp.expand(num).coeff(A, 1)
        coeffs[i] = sp.expand(c)
        rest = sp.expand(rest - c * A)
    if rest != 0 or any(c.has(*syms.values()) for c in coeffs.values()):
        raise ValueError("not linear homogeneous in a(n-i)")
    if not all(c.is_polynomial(nS) for c in coeffs.values()) or not den.is_polynomial(nS):
        raise ValueError("coefficients not polynomial")
    if den.free_symbols - {nS}:
        raise ValueError("denominator uses terms")
    return {i: sp.Poly(c, nS) for i, c in coeffs.items() if c != 0}, sp.Poly(den, nS)


def _q2_apply(ops, f, C, X):
    """R = sum_i p_i(theta)(x^i f) in Q(x)[s]/(s^2 - C)."""
    import sympy as sp
    dC = sp.diff(C, X) if C != 0 else 0

    def theta(g):
        u, v = g
        du = sp.diff(u, X)
        dv = sp.diff(v, X) + (v * dC / (2 * C) if C != 0 and v != 0 else 0)
        return (sp.cancel(X * du), sp.cancel(X * dv))
    R = (sp.Integer(0), sp.Integer(0))
    for i, p in ops.items():
        g = (sp.cancel(X ** i * f[0]), sp.cancel(X ** i * f[1]))
        acc = (sp.Integer(0), sp.Integer(0))
        coeffs = p.all_coeffs()[::-1]  # c_0 + c_1 n + ...
        cur = g
        for k, ck in enumerate(coeffs):
            if k:
                cur = theta(cur)
            if ck != 0:
                acc = (acc[0] + ck * cur[0], acc[1] + ck * cur[1])
        R = (R[0] + acc[0], R[1] + acc[1])
    return sp.cancel(R[0]), sp.cancel(R[1])


def check_holonomic(def_expr: str, off: int, parts: list[str], rels: list[str], n0: int | None,
                    terms: list[int], verify_terms: int = 250) -> tuple[bool, str]:
    """Sound check that the sequence a(n) = [x^n] def_expr (n >= off) satisfies the claimed
    polynomial-coefficient recurrence for all n >= n0."""
    import sympy as sp
    from colony import oeis_eval_b as OB
    try:
        f, C, X = _q2_parse(def_expr)
        ops, den = holonomic_form(parts, rels)
    except (ValueError, TypeError, SyntaxError, sp.SympifyError) as ex:
        return False, "outside the holonomic grammar: %s" % ex
    if not ops:
        return False, "empty recurrence"
    nS = sp.Symbol("n")
    K = max(ops)
    if min(ops) < 0:
        return False, "forward references"
    u, v = _q2_apply(ops, f, C, X)
    if v != 0:
        return False, "operator does not annihilate the radical part"
    if not sp.cancel(u).is_polynomial(X):
        return False, "residual is not a polynomial"
    degu = sp.degree(u, X) if u != 0 else -1
    start = off if n0 is None else max(off, int(n0))
    D = max(degu + 1, off + K, start)
    roots = [r for r in sp.Poly(den, nS).real_roots() if r.is_integer and r >= start] if den.degree() > 0 else []
    L = D + K + 4 - 0
    ser = OB.series_expr(OB.compile_expr(def_expr), max(L, off + min(len(terms), verify_terms)) + 1)
    if any(c.denominator != 1 for c in ser):
        return False, "definition has non-integer coefficients"
    a = [int(c) for c in ser]
    m = min(len(terms), verify_terms)
    if a[off:off + m] != list(terms[:m]):
        return False, "definition does not reproduce the b-file"
    for n in range(start, D):
        if n in roots:
            continue
        s = 0
        okn = True
        for i, p in ops.items():
            if n - i < off:
                okn = False
                break
            s += int(p.eval(n)) * a[n - i]
        if not okn:
            continue  # the claim references a term below the offset: not part of the claim
        if s != 0:
            return False, "recurrence fails at n = %d" % n
    return True, ("x-side residual is a polynomial of degree %d with zero radical part; recurrence holds for "
                  "n >= %d by the operator identity and is checked directly on %d..%d" % (degu, D, start, D - 1))
