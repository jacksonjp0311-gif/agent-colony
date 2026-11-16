"""One-shot generator for the frozen holdout_v3 pool (item 93, 2026-11-16; output committed).

Item 93 (James, 2026-11-16 12:47 AM ET): raise held-out n for a clearer capability signal.
holdout_v3 has 24 candidates (v1 / v2 had 12): 12 sound, 8 unsound (1 escape-by-design),
4 trivial, and the preregistered exposure uses 10 paired seeds (v1 / v2: 5). A larger n only
adds evidence; no gate, threshold or scoring rule is changed, and every arm (including the
learning-off twin arm and any --baseline-ref code) sees exactly this pool in one exposure.

Same layout as build_pools.py / build_pools_v2.py: candidates.json (colony-visible source only)
and labels.json (ground truth + witnesses, read only by evaluation/evaluator_v3.py). Families
were chosen so none appears in dev, holdout_v1, holdout_v2, the lemma catalog or the authored
checks at commit time (tests/test_item93_holdout_v3.py re-checks this).
"""
import json
from pathlib import Path

H = Path(__file__).resolve().parent / "pools"

HELP = {
 "PRIME": """
def _pv3_isprime(n):
    if n < 2:
        return False
    i = 2
    while i * i <= n:
        if n % i == 0:
            return False
        i += 1
    return True
""",
 "NDIV": """
def _pv3_ndiv(n):
    return sum(1 for d in range(1, n + 1) if n % d == 0)
""",
 "FIB": """
def _pv3_fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
""",
 "STERN": """
def _pv3_stern(n, _memo={0: 0, 1: 1}):
    if n not in _memo:
        h = n // 2
        _memo[n] = _pv3_stern(h) if n % 2 == 0 else _pv3_stern(h) + _pv3_stern(h + 1)
    return _memo[n]
""",
 "JOS": """
def _pv3_josephus(n):
    people = list(range(1, n + 1))
    i = 0
    while len(people) > 1:
        i = (i + 1) % len(people)
        people.pop(i)
    return people[0]
""",
 "KAP": """
def _pv3_kaprekar_ok(n):
    ds = f"{n:04d}"
    if len(set(ds)) == 1:
        return True
    for _ in range(7):
        if n == 6174:
            return True
        ds = f"{n:04d}"
        n = int("".join(sorted(ds, reverse=True))) - int("".join(sorted(ds)))
    return n == 6174
""",
 "RAMSEY": """
def _pv3_k6_mono_triangle():
    import itertools
    edges = list(itertools.combinations(range(6), 2))
    idx = {e: i for i, e in enumerate(edges)}
    tris = [(idx[(a, b)], idx[(a, c)], idx[(b, c)]) for a, b, c in itertools.combinations(range(6), 3)]
    for mask in range(1 << 15):
        if not any(((mask >> x) & 1) == ((mask >> y) & 1) == ((mask >> z) & 1) for x, y, z in tris):
            return False
    return True
""",
 "SYL": """
def _pv3_sylvester(k):
    s = [2]
    while len(s) < k:
        s.append(s[-1] * s[-1] - s[-1] + 1)
    return s
""",
 "CUBE33": """
def _pv3_cube33(N):
    for x in range(-N, N + 1):
        for y in range(-N, N + 1):
            r = 33 - x ** 3 - y ** 3
            z = round(abs(r) ** (1.0 / 3)) * (1 if r >= 0 else -1)
            for zz in (z - 1, z, z + 1):
                if zz ** 3 == r and max(abs(x), abs(y), abs(zz)) == N:
                    return True
    return False
""",
 "FIFTH": """
def _pv3_four_fifths(e):
    t = e ** 5
    fifth = {i ** 5: i for i in range(1, e)}
    for a in range(1, e):
        for b in range(a, e):
            for c in range(b, e):
                r = t - a ** 5 - b ** 5 - c ** 5
                if r < c ** 5:
                    break
                if r in fifth:
                    return True
    return False
""",
}


def C(name, helpers, body, label, family, witness=None, note=""):
    return dict(name=name, helpers=helpers, body=body, label=label, family=family, witness=witness, note=note)


HOLD3 = [
 # 12 sound
 C("pool_w01_bertrand_postulate", ["PRIME"], "all(any(_pv3_isprime(p) for p in range(n + 1, 2 * n + 1)) for n in range(1, 300))", "sound_useful", "prime_gaps"),
 C("pool_w02_wolstenholme", ["PRIME"], "all(math.comb(2 * p - 1, p - 1) % p ** 3 == 1 for p in range(5, 60) if _pv3_isprime(p))", "sound_useful", "binomial_congruence"),
 C("pool_w03_divisor_count_hyperbola", ["NDIV"], "all(sum(_pv3_ndiv(k) for k in range(1, n + 1)) == sum(n // k for k in range(1, n + 1)) for n in range(1, 120))", "sound_useful", "divisor_summatory"),
 C("pool_w04_factorial_succ_coprime", [], "all(math.gcd(math.factorial(n) + 1, math.factorial(n + 1) + 1) == 1 for n in range(1, 60))", "sound_useful", "factorial_gcd"),
 C("pool_w05_sylvester_coprime", ["SYL"], "all(math.gcd(a, b) == 1 for i, a in enumerate(_pv3_sylvester(8)) for b in _pv3_sylvester(8)[:i])", "sound_useful", "sylvester_sequence"),
 C("pool_w06_euler_criterion_multiplicative", ["PRIME"], "all(pow(a * b, (p - 1) // 2, p) == (pow(a, (p - 1) // 2, p) * pow(b, (p - 1) // 2, p)) % p for p in range(3, 40) if _pv3_isprime(p) for a in range(1, p) for b in range(1, p))", "sound_useful", "quadratic_character"),
 C("pool_w07_josephus_k2_closed_form", ["JOS"], "all(_pv3_josephus(n) == 2 * (n - (1 << (n.bit_length() - 1))) + 1 for n in range(1, 150))", "sound_useful", "josephus"),
 C("pool_w08_gray_code_adjacent", [], "all(bin((n ^ (n >> 1)) ^ ((n + 1) ^ ((n + 1) >> 1))).count('1') == 1 for n in range(0, 2000))", "sound_useful", "gray_code"),
 C("pool_w09_stern_diatomic_coprime", ["STERN"], "all(math.gcd(_pv3_stern(n), _pv3_stern(n + 1)) == 1 for n in range(1, 1500))", "sound_useful", "stern_diatomic"),
 C("pool_w10_kaprekar_6174", ["KAP"], "all(_pv3_kaprekar_ok(n) for n in range(1000, 10000))", "sound_useful", "kaprekar"),
 C("pool_w11_prime_square_mod24", ["PRIME"], "all(p * p % 24 == 1 for p in range(5, 3000) if _pv3_isprime(p))", "sound_useful", "prime_residues"),
 C("pool_w12_ramsey_r33_k6", ["RAMSEY"], "_pv3_k6_mono_triangle()", "sound_useful", "ramsey"),
 # 8 unsound (coded windows stop before the counterexample)
 C("pool_w13_prime_prefix_sum_nonsquare", ["PRIME"], "all(math.isqrt(s) ** 2 != s for s in [sum([p for p in range(2, 200) if _pv3_isprime(p)][:n]) for n in range(1, 9)])", "unsound", "prime_prefix_sum", witness={"n": 9}),
 C("pool_w14_fermat_base3_implies_prime", ["PRIME"], "all(_pv3_isprime(n) for n in range(2, 91) if pow(3, n - 1, n) == 1)", "unsound", "pseudoprime_base3", witness={"n": 91}),
 C("pool_w15_odd_composite_prime_twice_square", ["PRIME"], "all(_pv3_isprime(n) or any(_pv3_isprime(n - 2 * k * k) for k in range(1, math.isqrt(n // 2) + 1)) for n in range(9, 5777, 2))", "unsound", "goldbach_odd_composite", witness={"n": 5777}),
 C("pool_w16_n2_plus_1_squarefree", [], "all(all((n * n + 1) % (d * d) for d in range(2, math.isqrt(n * n + 1) + 1)) for n in range(1, 7))", "unsound", "squarefree_values", witness={"n": 7}),
 C("pool_w17_euclid_primorial_prime", ["PRIME"], "all(_pv3_isprime(math.prod([p for p in range(2, 30) if _pv3_isprime(p)][:k]) + 1) for k in range(1, 6))", "unsound", "euclid_numbers", witness={"n": 6}),
 C("pool_w18_fibonacci_prime_index", ["PRIME", "FIB"], "all(_pv3_isprime(_pv3_fib(p)) for p in range(3, 19) if _pv3_isprime(p))", "unsound", "fibonacci_primality", witness={"n": 19}),
 C("pool_w19_three_cubes_33_none", ["CUBE33"], "all(not _pv3_cube33(N) for N in range(0, 40))", "unsound", "sums_of_three_cubes", witness={"n": 8866128975287528}, note="escape by design: smallest known solution (Booker 2019) has 16-digit coordinates"),
 C("pool_w20_euler_sum_of_fifth_powers", ["FIFTH"], "all(not _pv3_four_fifths(e) for e in range(2, 60))", "unsound", "euler_sum_of_powers", witness={"n": 144}, note="Lander-Parkin 1966: 27^5+84^5+110^5+133^5 = 144^5"),
 # 4 trivial
 C("pool_w21_consecutive_square_gap", [], "all((n + 1) ** 2 - n * n == 2 * n + 1 for n in range(-50, 50))", "trivial", "square_gap_trivial"),
 C("pool_w22_consecutive_product_even", [], "all(n * (n + 1) % 2 == 0 for n in range(-50, 50))", "trivial", "parity"),
 C("pool_w23_max_ge_min", [], "all(max(a, b) >= min(a, b) for a in range(-10, 10) for b in range(-10, 10))", "trivial", "order"),
 C("pool_w24_mod7_bound", [], "all(0 <= n % 7 < 7 for n in range(-100, 100))", "trivial", "modular_trivial"),
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
    build(HOLD3, H / "holdout_v3")
