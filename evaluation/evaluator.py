"""Independent out-of-loop evaluator for the trust-loop candidate pools.

Isolation: lives under evaluation/, which is NOT copied into the colony workspace during
experiments and is never imported by colony/ (tests/test_trust_isolation.py). It shares no
code with the candidates or with society/benchmarks: primality is deterministic Miller-Rabin,
Fibonacci is fast doubling, sums are recomputed from definitions, and every claim is checked
on an extended range far past the candidate's coded window plus any known witness.

Ground truth per candidate:
  sound_useful — reference holds on the extended range (and label agrees)
  unsound      — reference finds a counterexample (extended range or known witness)
  trivial      — true but adds no information (polynomial/tautology); keeping it is coverage only
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent


def is_prime(n: int) -> bool:
    if n < 2:
        return False
    small = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
    for p in small:
        if n % p == 0:
            return n == p
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for a in small:
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


def fib(n: int) -> int:
    def fd(k: int) -> tuple[int, int]:
        if k == 0:
            return (0, 1)
        a, b = fd(k >> 1)
        c = a * (2 * b - a)
        d = a * a + b * b
        return (d, c + d) if k & 1 else (c, d)
    return fd(n)[0]


def sigma_proper(n: int) -> int:
    s, i = 0, 1
    while i * i <= n:
        if n % i == 0:
            s += i
            j = n // i
            if j != i:
                s += j
        i += 1
    return s - n


def derange(n: int) -> int:
    a, b = 1, 0  # D0, D1
    if n == 0:
        return 1
    for k in range(2, n + 1):
        a, b = b, (k - 1) * (a + b)
    return b


# name -> (predicate(n) -> bool, iterable of n to check)
REF: dict[str, tuple[Callable[[int], bool], Any]] = {
    # dev
    "pool_d01_k_binom_sum": (lambda n: sum(k * math.comb(n, k) for k in range(n + 1)) == n * 2 ** (n - 1), range(1, 120)),
    "pool_d02_fib_doubling": (lambda n: fib(2 * n) == fib(n) * (2 * fib(n + 1) - fib(n)), range(0, 400)),
    "pool_d03_binom_square_sum": (lambda n: sum(math.comb(n, k) ** 2 for k in range(n + 1)) == math.comb(2 * n, n), range(0, 150)),
    "pool_d04_n5_minus_n_div30": (lambda n: pow(n, 5, 30) == n % 30, range(0, 5000)),
    "pool_d05_euler41_prime": (lambda n: is_prime(n * n + n + 41), range(0, 400)),
    "pool_d06_mersenne_small": (lambda n: (not is_prime(n)) or is_prime(2 ** n - 1), range(2, 64)),
    "pool_d07_fermat_base2": (lambda n: n % 2 == 0 or pow(2, n - 1, n) != 1 or is_prime(n), range(3, 20000)),
    "pool_d08_no_abundant": (lambda n: sigma_proper(n) <= n, range(1, 500)),
    "pool_d09_square_expand": (lambda n: (n + 1) ** 2 == n * n + 2 * n + 1, range(-1000, 1000)),
    "pool_d10_mul_one": (lambda n: n * 1 == n, range(-1000, 1000)),
    "pool_d11_gcd_n17": (lambda n: math.gcd(n ** 17 + 9, (n + 1) ** 17 + 9) == 1, range(0, 3000)),
    "pool_d12_lucas_fib": (lambda n: fib(n - 1) + fib(n + 1) == fib(2 * n) // fib(n), range(1, 400)),
    # holdout v1
    "pool_h01_fib_prefix_sum": (lambda n: fib(n + 2) - 1 == sum(fib(k) for k in range(n + 1)), range(0, 300)),
    "pool_h02_catalan_ballot": (lambda n: math.comb(2 * n, n) // (n + 1) == math.comb(2 * n, n) - math.comb(2 * n, n + 1), range(0, 300)),
    "pool_h03_wilson": (lambda n: ((math.factorial(n - 1) + 1) % n == 0) == is_prime(n), range(2, 700)),
    "pool_h04_fib_divides_triple": (lambda n: fib(3 * n) % fib(n) == 0, range(1, 400)),
    "pool_h05_derangement_rec": (lambda n: derange(n) == n * derange(n - 1) + (-1) ** n, range(1, 200)),
    "pool_h06_2n2_29_prime": (lambda n: is_prime(2 * n * n + 29), range(0, 400)),
    "pool_h07_pow2_mod_n_ne3": (lambda n: pow(2, n, n) != 3, range(4, 20000)),
    "pool_h08_n2_n_17_prime": (lambda n: is_prime(n * n + n + 17), range(0, 400)),
    "pool_h09_odd_composite_3_5": (lambda n: is_prime(n) or n % 3 == 0 or n % 5 == 0, range(9, 5001, 2)),
    "pool_h10_fib_square_sum": (lambda n: fib(n) ** 2 + fib(n + 1) ** 2 == fib(2 * n + 1), range(0, 400)),
    "pool_h11_shift_square_diff": (lambda n: (n + 2) ** 2 - (n - 2) ** 2 == 8 * n, range(-1000, 1000)),
    "pool_h12_self_minus_self": (lambda n: n - n == 0, range(-1000, 1000)),
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


def judge_pool(pool: str) -> dict[str, dict[str, Any]]:
    labels = load_labels(pool)
    return {n: judge(n, lab) for n, lab in labels.items()}


def score_run(pool: str, kept: list[str], picked_counts: dict[str, int] | None = None) -> dict[str, Any]:
    """Score one colony run: which pool candidates it kept, judged by ground truth."""
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
    for pool in ("dev", "holdout_v1"):
        j = judge_pool(pool)
        print(pool, {n: (v["truth"], v["agree"], v["counterexample"]) for n, v in j.items()})
