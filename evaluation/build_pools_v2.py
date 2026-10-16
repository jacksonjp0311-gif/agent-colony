"""One-shot generator for the frozen holdout_v2 pool (run once, 2026-10-16; output committed).

Same layout as build_pools.py: candidates.json (colony-visible source only) and labels.json
(ground truth + witnesses, read only by evaluation/evaluator_v2.py). Families were chosen so
that none appears in dev, holdout_v1, the lemma catalog or the colony's authored checks at
commit time (grep audit recorded in evidence/2026-10-16-holdout-v2/NOVELTY_AUDIT.txt).
Design mirrors v1: 6 sound, 4 unsound (1 escape-by-design), 2 trivial.
"""
import json
from pathlib import Path

H = Path(__file__).resolve().parent / "pools"
P = "_pv"

HELP = {
 "PRIME": """
def _pv_isprime(n):
    if n < 2:
        return False
    i = 2
    while i * i <= n:
        if n % i == 0:
            return False
        i += 1
    return True
""",
 "FIB": """
def _pv_fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
""",
 "SIGMA": """
def _pv_sigma(n):
    return sum(d for d in range(1, n + 1) if n % d == 0)
""",
 "PART": """
def _pv_parts(n, allowed, distinct):
    ways = [1] + [0] * n
    for p in allowed:
        if distinct:
            for s in range(n, p - 1, -1):
                ways[s] += ways[s - p]
        else:
            for s in range(p, n + 1):
                ways[s] += ways[s - p]
    return ways[n]
""",
 "SQ": """
def _pv_sumsq(n, k):
    if k == 0:
        return n == 0
    a = 0
    while a * a <= n:
        if _pv_sumsq(n - a * a, k - 1):
            return True
        a += 1
    return False
""",
}

def C(name, helpers, body, label, family, witness=None, note=""):
    return dict(name=name, helpers=helpers, body=body, label=label, family=family, witness=witness, note=note)

HOLD2 = [
 C("pool_v01_euler_odd_distinct", ["PART"], "all(_pv_parts(n, range(1, n + 1, 2), False) == _pv_parts(n, range(1, n + 1), True) for n in range(0, 26))", "sound_useful", "partition"),
 C("pool_v02_binom_fib_double", ["FIB"], "all(sum(math.comb(n, k) * _pv_fib(k) for k in range(n + 1)) == _pv_fib(2 * n) for n in range(0, 30))", "sound_useful", "fibonacci_binomial"),
 C("pool_v03_divcount_odd_iff_square", [], "all((sum(1 for d in range(1, n + 1) if n % d == 0) % 2 == 1) == (math.isqrt(n) ** 2 == n) for n in range(1, 200))", "sound_useful", "divisor_count"),
 C("pool_v04_sigma_multiplicative", ["SIGMA"], "all(_pv_sigma(m * n) == _pv_sigma(m) * _pv_sigma(n) for m in range(1, 30) for n in range(1, 30) if math.gcd(m, n) == 1)", "sound_useful", "divisor_sum"),
 C("pool_v05_lagrange_four_squares", ["SQ"], "all(_pv_sumsq(n, 4) for n in range(0, 150))", "sound_useful", "sums_of_squares"),
 C("pool_v06_fermat_little", ["PRIME"], "all(pow(a, p, p) == a % p for p in range(2, 60) if _pv_isprime(p) for a in range(0, 20))", "sound_useful", "modular"),
 C("pool_v07_fermat_numbers_prime", ["PRIME"], "all(_pv_isprime(2 ** (2 ** k) + 1) for k in range(0, 5))", "unsound", "fermat_number", witness={"n": 5}),
 C("pool_v08_three_squares", ["SQ"], "all(_pv_sumsq(n, 3) for n in range(0, 7))", "unsound", "sums_of_squares", witness={"n": 7}),
 C("pool_v09_sigma_below_3n", ["SIGMA"], "all(_pv_sigma(n) < 3 * n for n in range(1, 120))", "unsound", "divisor_sum", witness={"n": 120}),
 C("pool_v10_pell991_no_solution", [], "all(math.isqrt(991 * y * y + 1) ** 2 != 991 * y * y + 1 for y in range(1, 3000))", "unsound", "pell", witness={"n": 12055735790331359447442538767}, note="escape by design: smallest y solving x^2-991y^2=1 has 29 digits"),
 C("pool_v11_diff_sq_expand", [], "all((n + 3) * (n - 3) == n * n - 9 for n in range(-40, 40))", "trivial", "polynomial"),
 C("pool_v12_abs_symmetric", [], "all(abs(n) >= 0 and abs(n) == abs(-n) for n in range(-40, 40))", "trivial", "polynomial"),
]

def build(pool, out):
    out.mkdir(parents=True, exist_ok=True)
    cands, labels = [], {}
    for c in pool:
        hs = "".join(HELP[h] for h in c["helpers"])
        fn = (f"\ndef check_{c['name']}() -> bool:\n"
              f"    \"\"\"Trust-loop pool candidate (external). Disabled until the desk judges it.\"\"\"\n"
              f"    return {c['body']}\n")
        cands.append({"name": c["name"], "helpers_src": hs, "check_src": fn})
        labels[c["name"]] = {"label": c["label"], "family": c["family"], "witness": c["witness"], "note": c["note"]}
    (out / "candidates.json").write_text(json.dumps({"version": 1, "candidates": cands}, indent=1) + "\n")
    (out / "labels.json").write_text(json.dumps({"version": 1, "labels": labels}, indent=1) + "\n")

if __name__ == "__main__":
    build(HOLD2, H / "holdout_v2")
