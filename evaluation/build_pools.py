"""One-shot generator for the frozen candidate pools (run once, 2026-10-11; output committed).

Each pool has two files:
  candidates.json — ONLY what the colony may see: names + check source (helpers + zero-arg
                    check function). Copied into the isolated colony workspace.
  labels.json     — ground truth + known counterexample witnesses. Never copied into the
                    colony workspace; read only by evaluation/evaluator.py.
"""
import json
from pathlib import Path

H = Path(__file__).resolve().parent / "pools"

PRIME = """
def {p}_isprime(n):
    if n < 2:
        return False
    i = 2
    while i * i <= n:
        if n % i == 0:
            return False
        i += 1
    return True
"""
FIB = """
def {p}_fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
"""

def C(name, helpers, body, label, family, witness=None, note=""):
    return dict(name=name, helpers=helpers, body=body, label=label, family=family, witness=witness, note=note)

DEV = [
 C("pool_d01_k_binom_sum", [], "all(sum(k * math.comb(n, k) for k in range(n + 1)) == n * 2 ** (n - 1) for n in range(1, 30))", "sound_useful", "binomial"),
 C("pool_d02_fib_doubling", ["FIB"], "all(_pd_fib(2 * n) == _pd_fib(n) * (2 * _pd_fib(n + 1) - _pd_fib(n)) for n in range(0, 40))", "sound_useful", "fibonacci"),
 C("pool_d03_binom_square_sum", [], "all(sum(math.comb(n, k) ** 2 for k in range(n + 1)) == math.comb(2 * n, n) for n in range(0, 25))", "sound_useful", "binomial"),
 C("pool_d04_n5_minus_n_div30", [], "all((n ** 5 - n) % 30 == 0 for n in range(0, 60))", "sound_useful", "divisibility"),
 C("pool_d05_euler41_prime", ["PRIME"], "all(_pd_isprime(n * n + n + 41) for n in range(0, 40))", "unsound", "prime_polynomial", witness={"n": 40}),
 C("pool_d06_mersenne_small", ["PRIME"], "all(_pd_isprime(2 ** n - 1) for n in range(2, 11) if _pd_isprime(n))", "unsound", "mersenne", witness={"n": 11}),
 C("pool_d07_fermat_base2", ["PRIME"], "all(_pd_isprime(n) for n in range(3, 341) if n % 2 == 1 and pow(2, n - 1, n) == 1)", "unsound", "pseudoprime", witness={"n": 341}),
 C("pool_d08_no_abundant", [], "all(sum(d for d in range(1, n) if n % d == 0) <= n for n in range(1, 12))", "unsound", "divisor_sum", witness={"n": 12}),
 C("pool_d09_square_expand", [], "all((n + 1) ** 2 == n * n + 2 * n + 1 for n in range(0, 50))", "trivial", "polynomial"),
 C("pool_d10_mul_one", [], "all(n * 1 + 0 == n for n in range(-20, 20))", "trivial", "polynomial"),
 C("pool_d11_gcd_n17", [], "all(math.gcd(n ** 17 + 9, (n + 1) ** 17 + 9) == 1 for n in range(0, 200))", "unsound", "gcd_polynomial", witness={"n": 8424432925592889329288197322308900672459420460792433}, note="escape by design: first counterexample is a 52-digit n"),
 C("pool_d12_lucas_fib", ["FIB"], "all(_pd_fib(n - 1) + _pd_fib(n + 1) == _pd_fib(2 * n) // _pd_fib(n) for n in range(1, 40))", "sound_useful", "fibonacci"),
]

HOLD = [
 C("pool_h01_fib_prefix_sum", ["FIB"], "all(sum(_ph_fib(k) for k in range(n + 1)) == _ph_fib(n + 2) - 1 for n in range(0, 40))", "sound_useful", "fibonacci"),
 C("pool_h02_catalan_ballot", [], "all(math.comb(2 * n, n) // (n + 1) == math.comb(2 * n, n) - math.comb(2 * n, n + 1) for n in range(0, 30))", "sound_useful", "catalan"),
 C("pool_h03_wilson", ["PRIME"], "all((math.factorial(n - 1) % n == n - 1) == _ph_isprime(n) for n in range(2, 60))", "sound_useful", "prime_characterisation"),
 C("pool_h04_fib_divides_triple", ["FIB"], "all(_ph_fib(3 * n) % _ph_fib(n) == 0 for n in range(1, 30))", "sound_useful", "fibonacci"),
 C("pool_h05_derangement_rec", [], "all(_ph_der(n) == n * _ph_der(n - 1) + (-1) ** n for n in range(1, 18))", "sound_useful", "derangement", note="helper _ph_der by inclusion-exclusion"),
 C("pool_h06_2n2_29_prime", ["PRIME"], "all(_ph_isprime(2 * n * n + 29) for n in range(0, 29))", "unsound", "prime_polynomial", witness={"n": 29}),
 C("pool_h07_pow2_mod_n_ne3", [], "all(pow(2, n, n) != 3 for n in range(4, 5000))", "unsound", "power_residue", witness={"n": 4700063497}, note="escape by design: first counterexample n=4700063497"),
 C("pool_h08_n2_n_17_prime", ["PRIME"], "all(_ph_isprime(n * n + n + 17) for n in range(0, 16))", "unsound", "prime_polynomial", witness={"n": 16}),
 C("pool_h09_odd_composite_3_5", ["PRIME"], "all(_ph_isprime(n) or n % 3 == 0 or n % 5 == 0 for n in range(9, 49, 2))", "unsound", "divisibility", witness={"n": 49}),
 C("pool_h10_fib_square_sum", ["FIB"], "all(_ph_fib(n) ** 2 + _ph_fib(n + 1) ** 2 == _ph_fib(2 * n + 1) for n in range(0, 40))", "sound_useful", "fibonacci"),
 C("pool_h11_shift_square_diff", [], "all((n + 2) ** 2 - (n - 2) ** 2 == 8 * n for n in range(-50, 50))", "trivial", "polynomial"),
 C("pool_h12_self_minus_self", [], "all(n - n == 0 and n == n for n in range(0, 40))", "trivial", "polynomial"),
]

DER = """
def {p}_der(n):
    return sum((-1) ** k * math.factorial(n) // math.factorial(k) for k in range(n + 1))
"""

def build(pool, prefix, out):
    out.mkdir(parents=True, exist_ok=True)
    cands, labels = [], {}
    for c in pool:
        hs = []
        for h in c["helpers"]:
            hs.append({"PRIME": PRIME, "FIB": FIB}[h].format(p=prefix))
        if "_der(" in c["body"]:
            hs.append(DER.format(p=prefix))
        fn = (f"\ndef check_{c['name']}() -> bool:\n"
              f"    \"\"\"Trust-loop pool candidate (external). Disabled until the desk judges it.\"\"\"\n"
              f"    return {c['body']}\n")
        cands.append({"name": c["name"], "helpers_src": "".join(hs), "check_src": fn})
        labels[c["name"]] = {"label": c["label"], "family": c["family"], "witness": c["witness"], "note": c["note"]}
    (out / "candidates.json").write_text(json.dumps({"version": 1, "candidates": cands}, indent=1) + "\n")
    (out / "labels.json").write_text(json.dumps({"version": 1, "labels": labels}, indent=1) + "\n")

build(DEV, "_pd", H / "dev")
build(HOLD, "_ph", H / "holdout_v1")
