"""Independent evaluator for holdout_v3 (item 93; out of loop; never imported by colony/).

Shares no code with the candidates: primes by deterministic Miller-Rabin, Fibonacci by fast
doubling (both from evaluator.py), divisor counts by factorisation and the Dirichlet
hyperbola method, Stern's sequence by the iterative fusc algorithm, Legendre symbols by the
Jacobi-symbol algorithm, Josephus by a deque simulation, Gray codes by the trailing-zero rule,
sums of fifth powers by a pair-sum table, and the sums-of-three-cubes witness by its published
solution (verified by arithmetic). Each claim is judged on an extended range well past the
coded window plus any known witness. Same scoring rule as v1 / v2.
"""
from __future__ import annotations

import collections
import itertools
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import evaluator as _v1  # same directory; reuse only is_prime / fib (independent of candidates)

HERE = Path(__file__).resolve().parent
is_prime, fib = _v1.is_prime, _v1.fib


def factor(n: int) -> dict[int, int]:
    f: dict[int, int] = {}
    d = 2
    while d * d <= n:
        while n % d == 0:
            f[d] = f.get(d, 0) + 1
            n //= d
        d += 1
    if n > 1:
        f[n] = f.get(n, 0) + 1
    return f


def ndiv(n: int) -> int:
    r = 1
    for e in factor(n).values():
        r *= e + 1
    return r


@lru_cache(maxsize=None)
def ndiv_prefix(n: int) -> int:
    return 0 if n == 0 else ndiv_prefix(n - 1) + ndiv(n)


def hyperbola(n: int) -> int:  # sum_{k<=n} floor(n/k) by the Dirichlet hyperbola method
    r = math.isqrt(n)
    return 2 * sum(n // k for k in range(1, r + 1)) - r * r


def jacobi(a: int, n: int) -> int:
    a %= n
    t = 1
    while a:
        while a % 2 == 0:
            a //= 2
            if n % 8 in (3, 5):
                t = -t
        a, n = n, a
        if a % 4 == 3 and n % 4 == 3:
            t = -t
        a %= n
    return t if n == 1 else 0


def fusc(n: int) -> int:  # iterative Stern diatomic
    a, b = 1, 0
    while n:
        if n & 1:
            b += a
        else:
            a += b
        n >>= 1
    return b


def josephus_sim(n: int) -> int:
    q = collections.deque(range(1, n + 1))
    while len(q) > 1:
        q.rotate(-1)
        q.popleft()
    return q[0]


def gray_ok(n: int) -> bool:  # g(n) ^ g(n+1) is the single bit at the trailing-zero position of n+1
    g = lambda k: k ^ (k >> 1)  # noqa: E731
    m = n + 1
    return g(n) ^ g(m) == (m & -m)


def kaprekar(n: int) -> bool:
    s = str(n).zfill(4)
    if len(set(s)) == 1:
        return True
    for _ in range(8):
        if n == 6174:
            return True
        s = str(n).zfill(4)
        hi = int("".join(sorted(s))[::-1])
        lo = int("".join(sorted(s)))
        n = hi - lo
    return n == 6174


def k6_every_coloring_mono() -> bool:
    edges = list(itertools.combinations(range(6), 2))
    for mask in range(1 << len(edges)):
        col = {e: (mask >> i) & 1 for i, e in enumerate(edges)}
        if not any(col[(a, b)] == col[(a, c)] == col[(b, c)] for a, b, c in itertools.combinations(range(6), 3)):
            return False
    return True


_PRIMES = [p for p in range(2, 40000) if is_prime(p)]


def sylvester_by_product(k: int) -> list[int]:
    s: list[int] = []
    for _ in range(k):
        s.append(math.prod(s) + 1)
    return s


KNOWN_33 = {8866128975287528: (8866128975287528, -8778405442862239, -2736111468807040)}


def no_cube33_at(N: int) -> bool:
    if N in KNOWN_33:
        x, y, z = KNOWN_33[N]
        return not (x ** 3 + y ** 3 + z ** 3 == 33 and max(abs(x), abs(y), abs(z)) == N)
    cubes = {i ** 3: i for i in range(-N, N + 1)}
    for x in range(-N, N + 1):
        for y in range(-N, N + 1):
            z = cubes.get(33 - x ** 3 - y ** 3)
            if z is not None and max(abs(x), abs(y), abs(z)) == N:
                return False
    return True


@lru_cache(maxsize=1)
def _pair_fifths(limit: int = 200) -> dict[int, tuple[int, int]]:
    return {a ** 5 + b ** 5: (a, b) for a in range(1, limit) for b in range(a, limit)}


def no_four_fifths(e: int) -> bool:
    t = e ** 5
    pairs = _pair_fifths()
    return not any((t - s) in pairs and max(pairs[t - s] + ab) < e for s, ab in pairs.items() if s < t)


REF: dict[str, tuple[Callable[[int], bool], Any]] = {
    "pool_w01_bertrand_postulate": (lambda n: any(is_prime(p) for p in range(n + 1, 2 * n + 1)), range(1, 20000)),
    "pool_w02_wolstenholme": (lambda p: (not is_prime(p)) or p < 5 or math.comb(2 * p - 1, p - 1) % p ** 3 == 1, range(2, 400)),
    "pool_w03_divisor_count_hyperbola": (lambda n: ndiv_prefix(n) == hyperbola(n), range(1, 5000)),
    "pool_w04_factorial_succ_coprime": (lambda n: math.gcd(math.factorial(n) + 1, math.factorial(n + 1) + 1) == 1, range(1, 300)),
    "pool_w05_sylvester_coprime": (lambda k: all(math.gcd(sylvester_by_product(k + 1)[k], s) == 1 for s in sylvester_by_product(k)), range(1, 12)),
    "pool_w06_euler_criterion_multiplicative": (lambda p: (not is_prime(p)) or p == 2 or all(jacobi(a * b, p) == jacobi(a, p) * jacobi(b, p) for a in range(1, p) for b in range(1, p)), range(2, 120)),
    "pool_w07_josephus_k2_closed_form": (lambda n: josephus_sim(n) == 2 * (n - 2 ** (len(bin(n)) - 3)) + 1, range(1, 1500)),
    "pool_w08_gray_code_adjacent": (gray_ok, range(0, 200000)),
    "pool_w09_stern_diatomic_coprime": (lambda n: math.gcd(fusc(n), fusc(n + 1)) == 1, range(1, 100000)),
    "pool_w10_kaprekar_6174": (kaprekar, range(1000, 10000)),
    "pool_w11_prime_square_mod24": (lambda p: (not is_prime(p)) or p < 5 or p * p % 24 == 1, range(2, 200000)),
    "pool_w12_ramsey_r33_k6": (lambda n: k6_every_coloring_mono(), range(6, 7)),
    "pool_w13_prime_prefix_sum_nonsquare": (lambda n: math.isqrt(sum(_PRIMES[:n])) ** 2 != sum(_PRIMES[:n]), range(1, 3000)),
    "pool_w14_fermat_base3_implies_prime": (lambda n: pow(3, n - 1, n) != 1 or is_prime(n), range(2, 20000)),
    "pool_w15_odd_composite_prime_twice_square": (lambda n: n % 2 == 0 or is_prime(n) or any(is_prime(n - 2 * k * k) for k in range(1, math.isqrt(n // 2) + 1)), range(9, 20000)),
    "pool_w16_n2_plus_1_squarefree": (lambda n: all(e == 1 for e in factor(n * n + 1).values()), range(1, 2000)),
    "pool_w17_euclid_primorial_prime": (lambda k: is_prime(math.prod(_PRIMES[:k]) + 1), range(1, 12)),
    "pool_w18_fibonacci_prime_index": (lambda p: (not is_prime(p)) or p < 3 or is_prime(fib(p)), range(2, 200)),
    "pool_w19_three_cubes_33_none": (no_cube33_at, range(0, 60)),
    "pool_w20_euler_sum_of_fifth_powers": (no_four_fifths, range(2, 180)),
    "pool_w21_consecutive_square_gap": (lambda n: (n + 1) ** 2 - n * n == 2 * n + 1, range(-5000, 5000)),
    "pool_w22_consecutive_product_even": (lambda n: n * (n + 1) % 2 == 0, range(-5000, 5000)),
    "pool_w23_max_ge_min": (lambda n: all(max(n, b) >= min(n, b) for b in range(-200, 200)), range(-200, 200)),
    "pool_w24_mod7_bound": (lambda n: 0 <= n % 7 < 7, range(-5000, 5000)),
}


def load_labels(pool: str) -> dict[str, Any]:
    return json.loads((HERE / "pools" / pool / "labels.json").read_text())["labels"]


def judge(name: str, label: dict[str, Any]) -> dict[str, Any]:
    pred, rng = REF[name]
    cex = None
    for n in rng:
        try:
            ok = pred(n)
        except Exception:  # noqa: BLE001
            ok = False
        if not ok:
            cex = n
            break
    wit = (label.get("witness") or {}).get("n")
    witness_breaks = False
    if cex is None and wit is not None:
        witness_breaks = not pred(int(wit))
        if witness_breaks:
            cex = int(wit)
    truth = "unsound" if cex is not None else ("trivial" if label["label"] == "trivial" else "sound_useful")
    return {"name": name, "truth": truth, "label": label["label"], "agree": truth == label["label"],
            "counterexample": cex, "found_by": ("witness" if witness_breaks else ("extended_range" if cex is not None else None))}


@lru_cache(maxsize=4)
def _judge_cached(pool: str) -> str:
    labels = load_labels(pool)
    return json.dumps({n: judge(n, lab) for n, lab in labels.items()})


def judge_pool(pool: str) -> dict[str, dict[str, Any]]:
    return json.loads(_judge_cached(pool))


def score_run(pool: str, kept: list[str], picked_counts: dict[str, int] | None = None) -> dict[str, Any]:
    truth = judge_pool(pool)
    kept_pool = [k for k in kept if k in truth]
    verified = [k for k in kept_pool if truth[k]["truth"] == "sound_useful"]
    harmful = [k for k in kept_pool if truth[k]["truth"] == "unsound"]
    coverage_only = [k for k in kept_pool if truth[k]["truth"] == "trivial"]
    sound = [n for n, t in truth.items() if t["truth"] == "sound_useful"]
    return {"pool": pool, "n_candidates": len(truth), "n_sound_useful": len(sound),
            "verified": sorted(verified), "harmful_kept": sorted(harmful),
            "coverage_only_kept": sorted(coverage_only),
            "sound_not_kept": sorted(set(sound) - set(verified))}


if __name__ == "__main__":
    j = judge_pool("holdout_v3")
    print({n: (v["truth"], v["agree"], v["counterexample"], v["found_by"]) for n, v in j.items()})
