"""Independent evaluator for holdout_v2 (out of loop; never imported by colony/).

Shares no code with the candidates: primes by deterministic Miller-Rabin, Fibonacci by fast
doubling, sigma by factorisation, partitions by Euler's pentagonal recurrence / generating
products, sums of squares by Legendre/Jacobi characterisations, Pell witness checked directly.
Each claim is judged on an extended range well past the coded window plus any known witness.
"""
from __future__ import annotations

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


def sigma(n: int) -> int:
    r = 1
    for p, e in factor(n).items():
        r *= (p ** (e + 1) - 1) // (p - 1)
    return r


def ndiv(n: int) -> int:
    r = 1
    for e in factor(n).values():
        r *= e + 1
    return r


@lru_cache(maxsize=None)
def p_all(n: int) -> int:  # Euler pentagonal recurrence
    if n < 0:
        return 0
    if n == 0:
        return 1
    s, k = 0, 1
    while True:
        g1, g2 = k * (3 * k - 1) // 2, k * (3 * k + 1) // 2
        if g1 > n:
            break
        sg = 1 if k % 2 else -1
        s += sg * (p_all(n - g1) + p_all(n - g2))
        k += 1
    return s


def q_distinct(n: int) -> int:  # product (1+x^k)
    w = [1] + [0] * n
    for k in range(1, n + 1):
        for s in range(n, k - 1, -1):
            w[s] += w[s - k]
    return w[n]


def q_odd(n: int) -> int:  # product 1/(1-x^k), k odd
    w = [1] + [0] * n
    for k in range(1, n + 1, 2):
        for s in range(k, n + 1):
            w[s] += w[s - k]
    return w[n]


def is_three_squares(n: int) -> bool:  # Legendre: n != 4^a(8b+7)
    if n == 0:
        return True
    while n % 4 == 0:
        n //= 4
    return n % 8 != 7


def is_four_squares(n: int) -> bool:  # n - a^2 a sum of three squares (Legendre) for some a
    return any(is_three_squares(n - a * a) for a in range(math.isqrt(n) + 1))


REF: dict[str, tuple[Callable[[int], bool], Any]] = {
    "pool_v01_euler_odd_distinct": (lambda n: q_odd(n) == q_distinct(n), range(0, 300)),
    "pool_v02_binom_fib_double": (lambda n: sum(math.comb(n, k) * fib(k) for k in range(n + 1)) == fib(2 * n), range(0, 300)),
    "pool_v03_divcount_odd_iff_square": (lambda n: (ndiv(n) % 2 == 1) == (math.isqrt(n) ** 2 == n), range(1, 20000)),
    "pool_v04_sigma_multiplicative": (lambda n: all(sigma(m * n) == sigma(m) * sigma(n) for m in range(1, 80) if math.gcd(m, n) == 1), range(1, 400)),
    "pool_v05_lagrange_four_squares": (is_four_squares, range(0, 3000)),
    "pool_v06_fermat_little": (lambda p: (not is_prime(p)) or all(pow(a, p, p) == a % p for a in range(0, 200)), range(2, 3000)),
    "pool_v07_fermat_numbers_prime": (lambda k: is_prime(2 ** (2 ** k) + 1), range(0, 7)),
    "pool_v08_three_squares": (is_three_squares, range(0, 5000)),
    "pool_v09_sigma_below_3n": (lambda n: sigma(n) < 3 * n, range(1, 50000)),
    "pool_v10_pell991_no_solution": (lambda y: math.isqrt(991 * y * y + 1) ** 2 != 991 * y * y + 1, range(1, 200000)),
    "pool_v11_diff_sq_expand": (lambda n: (n + 3) * (n - 3) == n * n - 9, range(-5000, 5000)),
    "pool_v12_abs_symmetric": (lambda n: abs(n) == abs(-n), range(-5000, 5000)),
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


score_run = None  # set below (same scoring rule as v1, with this module's judge)


def _score_run(pool: str, kept: list[str], picked_counts: dict[str, int] | None = None) -> dict[str, Any]:
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


score_run = _score_run

if __name__ == "__main__":
    j = judge_pool("holdout_v2")
    print({n: (v["truth"], v["agree"], v["counterexample"]) for n, v in j.items()})
