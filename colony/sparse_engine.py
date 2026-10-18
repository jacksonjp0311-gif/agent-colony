"""Computable families for sparse new-data targets (Stage 1b), each with two independent methods.

Every item is a function f(k), k = 1..N, computed by
- method A over a whole range (fast, usually numpy), and
- method B over a whole range by a different algorithm / arithmetic (used to verify every new term
  and every claimed record / first occurrence), plus a point evaluator ``bp`` (used by the Oracle
  bridge to recompute a single claimed value from scratch).

Families (general and safe; nothing here reads the network or writes files):
- collatz:  3x+1 trajectory statistics (steps, tripling / halving steps, maximum, squares visited,
            stopping time). A: numpy batch iteration. B: memoized Python walk to the first smaller value.
- divisor:  d(k), sigma(k) and neighbour combinations (min of d over k, k+1[, k+2], sums, products).
            A: additive divisor-pair sieve. B: multiplicative trial-division factorization.
- goldbach: representation counts of 2n as p + q (unordered / ordered) with p, q in a restricted
            prime set (all, odd, twin members, lesser twins, Sophie Germain, safe, residue classes),
            and Lemoine counts 2n+1 = p + 2q. A: floating-point FFT. B: exact number-theoretic transform.
- pattern:  prime k-tuple counts (twin, cousin, sexy, two triplet shapes, quadruplets) with start (or
            all members) in [n^2, (n+1)^2) or in (n, 2n]. A: numpy sieve. B: Python bytearray odd sieve.
- subset:   number of subsets of {1..n} / first n primes / first n odd numbers whose sum is prime /
            a square. A: list DP. B: big-integer generating function (Kronecker substitution).
"""
from __future__ import annotations

import math
import re
from typing import Any, Callable

import numpy as np

# ----------------------------------------------------------------------------- shared arithmetic
def np_sieve(L: int) -> np.ndarray:
    s = np.ones(L + 1, dtype=bool)
    s[: min(2, L + 1)] = False
    for i in range(2, math.isqrt(L) + 1):
        if s[i]:
            s[i * i::i] = False
    return s


def ba_sieve(L: int) -> bytearray:
    """Odd-only bytearray sieve, expanded (independent of np_sieve)."""
    half = bytearray([1]) * (L // 2 + 1)      # half[i] <-> 2i+1
    half[0] = 0
    i = 1
    while (2 * i + 1) ** 2 <= L:
        if half[i]:
            p = 2 * i + 1
            start = (p * p) // 2
            half[start::p] = bytes(len(range(start, L // 2 + 1, p)))
        i += 1
    out = bytearray(L + 1)
    if L >= 2:
        out[2] = 1
    out[1::2] = half[: len(out[1::2])]
    return out


_MR = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)


def is_prime_mr(n: int) -> bool:
    if n < 2:
        return False
    for p in _MR:
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for a in _MR:
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _issq(x: np.ndarray) -> np.ndarray:
    r = np.sqrt(x.astype(np.float64)).astype(np.int64)
    return (r * r == x) | ((r + 1) * (r + 1) == x) | ((r - 1) * (r - 1) == x)


_MEMO: dict[tuple, Any] = {}


def _memo(fn: Callable) -> Callable:
    """Keep the most recent range of each range function (several menu items share one range)."""
    def w(N, *a):
        key = (fn.__name__, N, *a)
        if key not in _MEMO:
            for k in [k for k in _MEMO if k[0] == fn.__name__]:
                del _MEMO[k]
            _MEMO[key] = fn(N, *a)
        return _MEMO[key]
    w.__name__ = fn.__name__
    return w


# ----------------------------------------------------------------------------- collatz
COL_STATS = ("steps", "odd", "even", "max", "squares", "stop")


@_memo
def collatz_a(N: int) -> dict[str, np.ndarray]:
    out = {s: np.zeros(N, np.int64) for s in COL_STATS}
    CH = 1 << 19
    for lo in range(1, N + 1, CH):
        hi = min(N, lo + CH - 1)
        k = np.arange(lo, hi + 1, dtype=np.int64)
        x, m = k.copy(), len(k)
        steps, odd = np.zeros(m, np.int64), np.zeros(m, np.int64)
        mx, sq = k.copy(), _issq(k).astype(np.int64)
        stop = np.where(k == 1, 0, -1).astype(np.int64)
        idx = np.nonzero(x > 1)[0]
        while len(idx):
            xa = x[idx]
            o = (xa & 1).astype(bool)
            xa = np.where(o, 3 * xa + 1, xa >> 1)
            x[idx] = xa
            steps[idx] += 1
            odd[idx] += o
            mx[idx] = np.maximum(mx[idx], xa)
            sq[idx] += _issq(xa)
            s_idx = idx[(stop[idx] < 0) & (xa < k[idx])]
            stop[s_idx] = steps[s_idx]
            idx = idx[xa > 1]
        sl = slice(lo - 1, hi)
        out["steps"][sl], out["odd"][sl], out["even"][sl] = steps, odd, steps - odd
        out["max"][sl], out["squares"][sl], out["stop"][sl] = mx, sq, stop
    return out


@_memo
def collatz_b(N: int) -> dict[str, list[int]]:
    """Memoized: walk from k until the first iterate below k, then add the stored statistics."""
    st, od, mx, sq, stop = [0] * (N + 1), [0] * (N + 1), [0] * (N + 1), [0] * (N + 1), [0] * (N + 1)
    if N >= 1:
        mx[1], sq[1] = 1, 1
    for n in range(2, N + 1):
        v, k, o, m = n, 0, 0, n
        s = 1 if math.isqrt(n) ** 2 == n else 0
        while v >= n:
            if v & 1:
                v = 3 * v + 1
                o += 1
            else:
                v >>= 1
            k += 1
            if v > m:
                m = v
            if v >= n and math.isqrt(v) ** 2 == v:
                s += 1
        stop[n] = k
        st[n], od[n], mx[n], sq[n] = k + st[v], o + od[v], max(m, mx[v]), s + sq[v]
    return {"steps": st[1:], "odd": od[1:], "even": [a - b for a, b in zip(st[1:], od[1:])], "max": mx[1:],
            "squares": sq[1:], "stop": stop[1:]}


def collatz_point(k: int) -> dict[str, int]:
    v, steps, odd, m, sq, stop = k, 0, 0, k, (1 if math.isqrt(k) ** 2 == k else 0), (0 if k == 1 else -1)
    while v != 1:
        if v % 2:
            v, odd = 3 * v + 1, odd + 1
        else:
            v //= 2
        steps += 1
        m = max(m, v)
        sq += 1 if math.isqrt(v) ** 2 == v else 0
        if stop < 0 and v < k:
            stop = steps
    return {"steps": steps, "odd": odd, "even": steps - odd, "max": m, "squares": sq, "stop": stop}


# ----------------------------------------------------------------------------- divisors
@_memo
def divisor_a(M: int) -> tuple[np.ndarray, np.ndarray]:
    """d(n), sigma(n) for n = 0..M from divisor pairs i <= sqrt(n)."""
    d, s = np.zeros(M + 1, np.int64), np.zeros(M + 1, np.int64)
    for i in range(1, math.isqrt(M) + 1):
        j = np.arange(i * i, M + 1, i, dtype=np.int64)
        d[i * i::i] += 2
        s[i * i::i] += i + j // i
        d[i * i] -= 1
        s[i * i] -= i
    return d, s


@_memo
def divisor_b(M: int) -> tuple[np.ndarray, np.ndarray]:
    """d(n), sigma(n) for n = 0..M by factorization: divide out every prime p <= sqrt(M)."""
    v = np.arange(M + 1, dtype=np.int64)
    d, s = np.ones(M + 1, np.int64), np.ones(M + 1, np.int64)
    pr = np.nonzero(ba_np(math.isqrt(M)))[0]
    for p in pr.tolist():
        e = np.zeros(len(range(p, M + 1, p)), np.int64)
        pk = p
        while pk <= M:
            e[pk // p - 1::pk // p] += 1
            pk *= p
        d[p::p] *= e + 1
        powp = np.array([p ** i for i in range(int(e.max()) + 2)], dtype=object)
        s[p::p] *= np.array(((powp[e + 1] - 1) // (p - 1)).tolist(), dtype=np.int64)
        v[p::p] //= np.array((powp[e]).tolist(), dtype=np.int64)
    big = v > 1
    d[big] *= 2
    s[big] *= v[big] + 1
    d[0] = s[0] = 0
    return d, s


def ba_np(L: int) -> np.ndarray:
    return np.frombuffer(bytes(ba_sieve(L)), dtype=np.uint8).astype(bool)


def divisor_point(n: int) -> tuple[int, int]:
    d, s, m, p = 1, 1, n, 2
    while p * p <= m:
        if m % p == 0:
            e = 0
            while m % p == 0:
                m //= p
                e += 1
            d *= e + 1
            s *= (p ** (e + 1) - 1) // (p - 1)
        p += 1 if p == 2 else 2
    if m > 1:
        d, s = d * 2, s * (m + 1)
    return d, s


DIV_COMBOS: dict[str, tuple[str, Callable]] = {
    "d": ("number of divisors d(k)", lambda d, s, k: d(k)),
    "sigma": ("sum of divisors sigma(k)", lambda d, s, k: s(k)),
    "dmin1": ("min(d(k), d(k+1))", lambda d, s, k: np.minimum(d(k), d(k + 1))),
    "dmin2": ("min(d(k), d(k+2))", lambda d, s, k: np.minimum(d(k), d(k + 2))),
    "dmin3": ("min(d(k), d(k+1), d(k+2))", lambda d, s, k: np.minimum(np.minimum(d(k), d(k + 1)), d(k + 2))),
    "dsum1": ("d(k) + d(k+1)", lambda d, s, k: d(k) + d(k + 1)),
    "dprod1": ("d(k) * d(k+1) = d(k(k+1))", lambda d, s, k: d(k) * d(k + 1)),
    "dmax1": ("max(d(k), d(k+1))", lambda d, s, k: np.maximum(d(k), d(k + 1))),
}


def _div_items(key: str, fn: Callable) -> tuple[Callable, Callable, Callable]:
    def a(N):
        d, s = divisor_a(N + 3)
        k = np.arange(1, N + 1)
        return fn(lambda i: d[i], lambda i: s[i], k)

    def b(N):
        d, s = divisor_b(N + 3)
        k = np.arange(1, N + 1)
        return fn(lambda i: d[i], lambda i: s[i], k)

    def bp(k):
        cache = {}

        def dd(i):
            i = int(i)
            if i not in cache:
                cache[i] = divisor_point(i)
            return cache[i]
        return int(fn(lambda i: np.int64(dd(i)[0]), lambda i: np.int64(dd(i)[1]), np.int64(k)))
    return a, b, bp


# ----------------------------------------------------------------------------- goldbach
GB_SETS = ("prime", "odd", "twin", "ltwin", "sg", "safe", "m4_1", "m4_3", "m6_1", "m6_5")


def _set_from_primes(pr: Callable[[int], Any], L: int, which: str) -> np.ndarray:
    """Indicator of the restricted prime set on 0..L, from a primality indicator on 0..2L+1."""
    P = pr(2 * L + 3)
    P = np.frombuffer(bytes(P), dtype=np.uint8).astype(bool) if not isinstance(P, np.ndarray) else P
    base = P[: L + 1].copy()
    n = np.arange(L + 1)
    if which == "odd":
        base[2] = False if L >= 2 else base[2]
    elif which == "twin":
        up = np.zeros(L + 1, bool)
        up[: L + 1] = P[2: L + 3]
        dn = np.zeros(L + 1, bool)
        dn[2:] = P[: L - 1]
        base &= up | dn
    elif which == "ltwin":
        base &= P[2: L + 3]
    elif which == "sg":
        base &= P[2 * n + 1]
    elif which == "safe":
        h = np.zeros(L + 1, bool)
        h[1::2] = P[(n[1::2] - 1) // 2]
        base &= h
    elif which.startswith("m"):
        m, r = (int(x) for x in which[1:].split("_"))
        base &= n % m == r
    return base


def _conv_fft(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    n = len(a) + len(b) - 1
    size = 1 << (n - 1).bit_length()
    c = np.fft.irfft(np.fft.rfft(a.astype(np.float64), size) * np.fft.rfft(b.astype(np.float64), size), size)[:n]
    return np.rint(c).astype(np.int64)


_NTT_P, _NTT_G = 998244353, 3


def _ntt(a: np.ndarray, inv: bool = False) -> np.ndarray:
    P = np.uint64(_NTT_P)
    n = len(a)
    bits = n.bit_length() - 1
    j = np.arange(n)
    rev = np.zeros(n, np.int64)
    for b in range(bits):
        rev |= ((j >> b) & 1) << (bits - 1 - b)
    a = a[rev].astype(np.uint64)
    m = 1
    while m < n:
        w = pow(_NTT_G, (_NTT_P - 1) // (2 * m), _NTT_P)
        if inv:
            w = pow(w, _NTT_P - 2, _NTT_P)
        ws = np.empty(m, np.uint64)
        ws[0] = 1
        k = 1
        while k < m:
            ws[k:2 * k] = (ws[:k] * np.uint64(pow(w, k, _NTT_P))) % P
            k *= 2
        a = a.reshape(-1, 2 * m)
        u, v = a[:, :m], (a[:, m:] * ws) % P
        a = np.concatenate(((u + v) % P, (u + P - v) % P), axis=1).reshape(-1)
        m *= 2
    if inv:
        a = (a * np.uint64(pow(n, _NTT_P - 2, _NTT_P))) % P
    return a


def _conv_ntt(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Exact integer convolution (counts stay far below the modulus)."""
    n = len(a) + len(b) - 1
    size = 1 << (n - 1).bit_length()
    A = np.zeros(size, np.uint64)
    B = np.zeros(size, np.uint64)
    A[: len(a)] = a
    B[: len(b)] = b
    return _ntt((_ntt(A) * _ntt(B)) % np.uint64(_NTT_P), True)[:n].astype(np.int64)


def _gb_range(N: int, which: str, kind: str, method: str) -> np.ndarray:
    pr = np_sieve if method == "a" else ba_sieve
    conv = _conv_fft if method == "a" else _conv_ntt
    L = 2 * N + 2
    S = _set_from_primes(pr, L, which if kind != "lem" else "prime").astype(np.int64)
    n = np.arange(1, N + 1)
    if kind == "lem":                                  # 2n+1 = p + 2q
        D = np.zeros(L + 1, np.int64)
        D[0:L + 1:2] = S[: L // 2 + 1]
        c = conv(S, D)
        return c[2 * n + 1]
    c = conv(S, S)
    if kind == "o":
        return c[2 * n]
    if kind == "m":                                    # m = p + q (unordered), every m, not just 2n
        half = np.zeros(N, np.int64)
        half[1::2] = S[n[1::2] // 2]
        return (c[n] + half) // 2
    return (c[2 * n] + S[n]) // 2


def _in_set_point(p: int, which: str) -> bool:
    ip = is_prime_mr
    if not ip(p):
        return False
    if which == "odd":
        return p != 2
    if which == "twin":
        return ip(p - 2) or ip(p + 2)
    if which == "ltwin":
        return ip(p + 2)
    if which == "sg":
        return ip(2 * p + 1)
    if which == "safe":
        return p % 2 == 1 and ip((p - 1) // 2)
    if which.startswith("m"):
        m, r = (int(x) for x in which[1:].split("_"))
        return p % m == r
    return True


def gb_point(n: int, which: str, kind: str) -> int:
    if kind == "lem":
        return sum(1 for q in range(2, n + 1) if is_prime_mr(q) and is_prime_mr(2 * n + 1 - 2 * q))
    m = n if kind == "m" else 2 * n
    P = ba_sieve(max(m, 2))
    cnt = 0
    for p in range(2, m - 1):
        q = m - p
        if P[p] and P[q] and _in_set_point(p, which) and _in_set_point(q, which):
            cnt += 1 if (kind == "o" or p <= q) else 0
    return cnt


# ----------------------------------------------------------------------------- prime patterns
PATTERNS = {"twin": (0, 2), "cousin": (0, 4), "sexy": (0, 6), "trip26": (0, 2, 6), "trip46": (0, 4, 6),
            "quad": (0, 2, 6, 8)}
INTERVALS = ("sq_start", "sq_all", "bert_start", "bert_all")


def _pat_bounds(n: np.ndarray, iv: str, w: int) -> tuple[np.ndarray, np.ndarray]:
    """Inclusive range of admissible starting primes p for interval iv and pattern width w."""
    if iv.startswith("sq"):
        lo, hi = n * n, (n + 1) * (n + 1) - 1
    else:
        lo, hi = n + 1, 2 * n
    return lo, (hi - w if iv.endswith("_all") else hi)


def _pat_range(N: int, pat: str, iv: str, method: str) -> np.ndarray:
    offs = PATTERNS[pat]
    w = offs[-1]
    top = (N + 1) * (N + 1) + w + 2 if iv.startswith("sq") else 2 * N + w + 2
    P = np_sieve(top) if method == "a" else np.frombuffer(bytes(ba_sieve(top)), dtype=np.uint8).astype(bool)
    st = P[: top + 1 - w].copy()
    for o in offs[1:]:
        st &= P[o: top + 1 - w + o]
    cs = np.concatenate(([0], np.cumsum(st.astype(np.int64))))   # cs[x] = #starts < x
    n = np.arange(1, N + 1, dtype=np.int64)
    lo, hi = _pat_bounds(n, iv, w)
    hi = np.maximum(hi, lo - 1)
    return cs[hi + 1] - cs[lo]


def pat_point(n: int, pat: str, iv: str) -> int:
    offs = PATTERNS[pat]
    lo, hi = _pat_bounds(np.int64(n), iv, offs[-1])
    return sum(1 for p in range(int(lo), int(hi) + 1) if all(is_prime_mr(p + o) for o in offs))


# ----------------------------------------------------------------------------- subsets
SUB_SETS = ("ints", "primes", "odds")
SUB_PREDS = ("prime", "square", "prime0", "square0")   # *0: the empty set is included


def _sub_elems(which: str, N: int) -> list[int]:
    if which == "ints":
        return list(range(1, N + 1))
    if which == "odds":
        return list(range(1, 2 * N, 2))
    out, c = [], 2
    while len(out) < N:
        if is_prime_mr(c):
            out.append(c)
        c += 1
    return out


def _pred_mask(S: int, pred: str, method: str) -> list[int]:
    if pred.startswith("prime"):
        P = np_sieve(S) if method == "a" else ba_sieve(S)
        return [x for x in range(S + 1) if P[x]]
    return [i * i for i in range(math.isqrt(S) + 1) if (i > 0 or pred.endswith("0"))]


def subset_a(N: int, which: str, pred: str) -> list[int]:
    el = _sub_elems(which, N)
    S = sum(el)
    good = set(_pred_mask(S, pred, "a"))
    cnt = [0] * (S + 1)
    cnt[0], tot, out = 1, 0, []
    for a in el:
        tot += a
        for s in range(tot, a - 1, -1):
            cnt[s] += cnt[s - a]
        out.append(sum(cnt[s] for s in good if s <= tot))
    return out


def subset_b(N: int, which: str, pred: str) -> list[int]:
    el = _sub_elems(which, N)
    B = N + 2                                   # bits per coefficient (counts <= 2^N)
    g, tot, out = 1, 0, []
    good_all = _pred_mask(sum(el), pred, "b")
    mask = (1 << B) - 1
    for a in el:
        g = g + (g << (a * B))
        tot += a
        out.append(sum((g >> (s * B)) & mask for s in good_all if s <= tot))
    return out


# ----------------------------------------------------------------------------- registry
def _np(x: Any) -> np.ndarray:
    return x if isinstance(x, np.ndarray) else np.array(x, dtype=object if x and max(map(abs, x)) > 2 ** 62 else np.int64)


ITEMS: dict[str, dict[str, Any]] = {}
FAMILY_KW = {
    "collatz": r"collatz|3x\s*\+\s*1|3n\s*\+\s*1|syracuse|hailstone",
    "divisor": r"divisor|\bd\([kn]\)|\btau\b|sigma|A000005|A000203",
    "goldbach": r"goldbach|two primes|p\s*\+\s*q|lemoine|levy|2\s*\*?\s*q|sum of (a|two) .*prime",
    "pattern": r"twin|cousin|sexy|triplet|quadruplet|constellation|tuple|between n\^2|squares",
    "subset": r"subset",
}
CAPS = {"collatz": (1_000_000, 20_000_000), "divisor": (10_000_000, 50_000_000),
        "goldbach": (1_000_000, 8_000_000), "pattern": (5000, 15000), "subset": (100, 250)}

for _s in COL_STATS:
    ITEMS[f"col_{_s}"] = {
        "family": "collatz", "what": f"Collatz 3x+1 {_s} of k",
        "a": (lambda s: lambda N: _np(collatz_b(N)[s]))(_s),
        "b": (lambda s: lambda N: collatz_a(N)[s])(_s),
        "bp": (lambda s: lambda k: collatz_point(int(k))[s])(_s),
        "methods": ["memoized Python walk to the first smaller iterate", "numpy batch iteration of 3x+1 (whole trajectories)"]}
for _key, (_what, _fn) in DIV_COMBOS.items():
    _a, _b, _bp = _div_items(_key, _fn)
    ITEMS[f"div_{_key}"] = {"family": "divisor", "what": _what, "a": _a, "b": _b, "bp": _bp,
                            "methods": ["additive divisor-pair sieve", "multiplicative trial-division factorization"]}
for _w in GB_SETS:
    for _kind in ("u", "o", "m"):
        ITEMS[f"gb_{_w}_{_kind}"] = {
            "family": "goldbach", "what": {"u": "unordered 2n = p + q", "o": "ordered 2n = p + q", "m": "unordered n = p + q"}[_kind] + f", p, q in {_w}",
            "a": (lambda w, k: lambda N: _gb_range(N, w, k, "a"))(_w, _kind),
            "b": (lambda w, k: lambda N: _gb_range(N, w, k, "b"))(_w, _kind),
            "bp": (lambda w, k: lambda n: gb_point(int(n), w, k))(_w, _kind),
            "methods": ["floating-point FFT convolution over a numpy sieve",
                        "exact number-theoretic transform over an independent bytearray sieve"]}
ITEMS["gb_lemoine"] = {
    "family": "goldbach", "what": "2n+1 = p + 2q with p, q prime (Lemoine)",
    "a": lambda N: _gb_range(N, "prime", "lem", "a"), "b": lambda N: _gb_range(N, "prime", "lem", "b"),
    "bp": lambda n: gb_point(int(n), "prime", "lem"),
    "methods": ["floating-point FFT convolution over a numpy sieve", "exact number-theoretic transform over an independent bytearray sieve"]}
for _p in PATTERNS:
    for _iv in INTERVALS:
        ITEMS[f"pat_{_p}_{_iv}"] = {
            "family": "pattern", "what": f"{_p} prime pattern count, {_iv}",
            "a": (lambda p, iv: lambda N: _pat_range(N, p, iv, "a"))(_p, _iv),
            "b": (lambda p, iv: lambda N: _pat_range(N, p, iv, "b"))(_p, _iv),
            "bp": (lambda p, iv: lambda n: pat_point(int(n), p, iv))(_p, _iv),
            "methods": ["numpy sieve with prefix sums", "independent bytearray odd sieve (Miller-Rabin for single values)"]}
for _w in SUB_SETS:
    for _pr in SUB_PREDS:
        ITEMS[f"sub_{_w}_{_pr}"] = {
            "family": "subset", "what": f"subsets of the first n {_w} with {_pr} sum",
            "a": (lambda w, p: lambda N: _np(subset_a(N, w, p)))(_w, _pr),
            "b": (lambda w, p: lambda N: _np(subset_b(N, w, p)))(_w, _pr),
            "bp": (lambda w, p: lambda n: int(subset_b(int(n), w, p)[-1]))(_w, _pr),
            "methods": ["subset-sum list dynamic programming", "big-integer generating function (Kronecker substitution)"]}


def families_for(text: str) -> list[str]:
    t = text.lower()
    return [f for f, rx in FAMILY_KW.items() if re.search(rx, t, re.I)]


def items_for(text: str) -> list[str]:
    fams = set(families_for(text))
    return [k for k, v in ITEMS.items() if v["family"] in fams]


def cap(item: str, deep: bool = False) -> int:
    return CAPS[ITEMS[item]["family"]][1 if deep else 0]


# ----------------------------------------------------------------------------- operations on f(1..N)
OPS = ("terms", "recpos", "recval", "first", "zeros", "eq1", "fgtk", "fgek")
LIST_OPS = {"zeros": "k with f(k) = 0", "fgtk": "k with f(k) > k", "fgek": "k with f(k) >= k"}
LIST_OPS.update({f"eq{c}": f"k with f(k) = {c}" for c in range(1, 13)})
OPS = OPS[:4] + tuple(LIST_OPS)


def listing(op: str, v: np.ndarray) -> list[int]:
    v = np.asarray(v)
    k = np.arange(1, len(v) + 1)
    if v.dtype == object:
        vv = v.tolist()
        if op.startswith("eq"):
            c = int(op[2:])
            return [i for i, x in zip(k.tolist(), vv) if x == c]
        cond = {"zeros": lambda x, i: x == 0, "fgtk": lambda x, i: x > i, "fgek": lambda x, i: x >= i}[op]
        return [i for i, x in zip(k.tolist(), vv) if cond(x, i)]
    if op.startswith("eq"):
        return k[v == int(op[2:])].tolist()
    m = {"zeros": v == 0, "fgtk": v > k, "fgek": v >= k}[op]
    return k[m].tolist()


def records(v: np.ndarray) -> tuple[list[int], list[int]]:
    """Strict records of v (v[0] is f(1)): positions k (1-based) and values."""
    v = np.asarray(v)
    if v.dtype == object:
        pos, val, best = [], [], None
        for i, x in enumerate(v.tolist()):
            if best is None or x > best:
                best = x
                pos.append(i + 1)
                val.append(x)
        return pos, val
    cm = np.maximum.accumulate(v)
    new = np.ones(len(v), bool)
    new[1:] = cm[1:] > cm[:-1]
    pos = np.nonzero(new)[0] + 1
    return pos.tolist(), v[pos - 1].tolist()


def firsts(v: np.ndarray, n_max: int) -> dict[int, int]:
    """Smallest k (1-based) with f(k) = n, for every n <= n_max that occurs."""
    v = np.asarray(v)
    out: dict[int, int] = {}
    if v.dtype != object and len(v):
        vv = v.astype(np.int64)
        ok = (vv >= 0) & (vv <= n_max)
        idx = np.nonzero(ok)[0]
        vals = vv[idx]
        u, first_i = np.unique(vals, return_index=True)
        for a, i in zip(u.tolist(), first_i.tolist()):
            out[int(a)] = int(idx[i]) + 1
        return out
    for i, x in enumerate(v.tolist()):
        if 0 <= x <= n_max and x not in out:
            out[x] = i + 1
    return out
