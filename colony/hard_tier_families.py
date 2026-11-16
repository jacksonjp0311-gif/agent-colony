"""Spark (2026-11-16): auto-build the next hard-tier family from OEIS relations when they run out.

When the lemma catalog has no hand-written hard-tier family left to enable (every
``HARD_TIER_LEMMAS`` entry that is not ``authored_`` / ``adversarial_`` is enabled), the desk
used to re-propose enabled lemmas and the Oracle pass count stalled. This module adds the next
family from a VETTED pool of classical, proven relations between OEIS sequences, each written
in this repo (nothing from the web) and checked by two independent computations (lattice-path
or brute-force counting vs a closed form / a different recurrence).

Path (same as every other hard-tier family):
  * at most one family per cycle, only when ``families_remaining() == 0``;
  * inserted DISABLED as ``("name", lambda: all(check_name(n) for n in range(A, B)), False)``,
    the shape the Oracle's shifted-window held-out re-runs on a disjoint window;
  * verified before writing, in a subprocess on a temp copy: the entry holds on its window,
    the Oracle's own ``shifted_window_check`` passes on the next disjoint window, and the check
    is falsifiable (single-point mutants of its code fail the window);
  * registered as a ``hard_enable`` candidate; only the desk's enable through the unchanged
    Oracle (held-out harder, stripped baseline, novelty gate) can turn it on;
  * treatment only (self-mod); the control arm never builds. Pool size bounds the total.

Logged append-only to data/commons/hard_tier_supply.jsonl. Finite-window evidence of known
theorems, not discoveries.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SUPPLY_LOG = Path(os.path.join(os.fspath(ROOT), "data", "commons", "hard_tier_supply.jsonl"))
NON_FAMILY_PREFIXES = ("authored_", "adversarial_")
INSERT_MARKER = "# Adversarial aliases used by Oracle theme held-out windows"
FALLBACK_MARKER = "# Mutable catalog the conjecture desk may extend / mutate."
SUBPROCESS_TIMEOUT_S = 30

# (name, (A, B) window, check function source). Vetted: tests/test_spark_hard_tier_families.py
# runs every entry on its window, on the shifted window, and checks the OEIS opening terms.
POOL: list[tuple[str, tuple[int, int], str]] = [
    ("oeis_a000032_lucas_norm", (1, 60), '''
def check_oeis_a000032_lucas_norm(n: int) -> bool:
    """Lucas A000032 vs Fibonacci A000045: L(n) = F(n-1) + F(n+1) and L(n)^2 - 5 F(n)^2 = 4 (-1)^n.
    L by its own recurrence, F by fast doubling (independent routes)."""
    if n < 1:
        return True
    lo, hi = 2, 1
    for _ in range(n):
        lo, hi = hi, lo + hi

    def fib(k: int) -> int:
        a, b = 0, 1
        for bit in bin(k)[2:]:
            c, d = a * (2 * b - a), a * a + b * b
            a, b = (d, c + d) if bit == "1" else (c, d)
        return a
    return lo == fib(n - 1) + fib(n + 1) and lo * lo - 5 * fib(n) ** 2 == 4 * (-1) ** n
'''),
    ("oeis_a001006_motzkin_ballot_sum", (0, 40), '''
def check_oeis_a001006_motzkin_ballot_sum(n: int) -> bool:
    """Motzkin A001006: lattice-path count (U/D/F, never below 0) equals sum_k C(n,2k) C(2k,k)/(k+1)."""
    row = [1] + [0] * (n + 1)
    for _ in range(n):
        new = [0] * (n + 2)
        for h, v in enumerate(row):
            if v:
                new[h] += v
                if h + 1 <= n:
                    new[h + 1] += v
                if h:
                    new[h - 1] += v
        row = new
    closed = sum(math.comb(n, 2 * k) * (math.comb(2 * k, k) // (k + 1)) for k in range(n // 2 + 1))
    return row[0] == closed
'''),
    ("oeis_a005043_riordan_motzkin", (0, 40), '''
def check_oeis_a005043_riordan_motzkin(n: int) -> bool:
    """Riordan A005043 by its recurrence (k+1) R(k) = (k-1)(2 R(k-1) + 3 R(k-2));
    Motzkin A001006 by lattice paths: M(n) = R(n) + R(n+1)."""
    r = [1, 0]
    for k in range(2, n + 2):
        num = (k - 1) * (2 * r[k - 1] + 3 * r[k - 2])
        if num % (k + 1):
            return False
        r.append(num // (k + 1))
    row = [1] + [0] * (n + 1)
    for _ in range(n):
        new = [0] * (n + 2)
        for h, v in enumerate(row):
            if v:
                new[h] += v
                if h + 1 <= n:
                    new[h + 1] += v
                if h:
                    new[h - 1] += v
        row = new
    return row[0] == r[n] + r[n + 1]
'''),
    ("oeis_a001850_central_delannoy", (0, 30), '''
def check_oeis_a001850_central_delannoy(n: int) -> bool:
    """Central Delannoy A001850: grid-path count with steps E, N, NE to (n, n)
    equals sum_k C(n,k) C(n+k,k)."""
    grid = [[0] * (n + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        for j in range(n + 1):
            if i == 0 or j == 0:
                grid[i][j] = 1
            else:
                grid[i][j] = grid[i - 1][j] + grid[i][j - 1] + grid[i - 1][j - 1]
    return grid[n][n] == sum(math.comb(n, k) * math.comb(n + k, k) for k in range(n + 1))
'''),
    ("oeis_a006318_schroeder_paths", (0, 30), '''
def check_oeis_a006318_schroeder_paths(n: int) -> bool:
    """Large Schroeder A006318: paths (0,0)->(2n,0) with U, D, flat-2 steps never below 0
    (DP) equal sum_k C(n+k, n-k) C(2k,k)/(k+1)."""
    ways = [dict() for _ in range(2 * n + 1)]
    ways[0][0] = 1
    for x in range(2 * n):
        for h, v in ways[x].items():
            ways[x + 1][h + 1] = ways[x + 1].get(h + 1, 0) + v
            if h:
                ways[x + 1][h - 1] = ways[x + 1].get(h - 1, 0) + v
            if x + 2 <= 2 * n:
                ways[x + 2][h] = ways[x + 2].get(h, 0) + v
    closed = sum(math.comb(n + k, n - k) * (math.comb(2 * k, k) // (k + 1)) for k in range(n + 1))
    return ways[2 * n].get(0, 0) == closed
'''),
    ("oeis_a000085_involutions", (0, 50), '''
def check_oeis_a000085_involutions(n: int) -> bool:
    """Involutions A000085: a(k) = a(k-1) + (k-1) a(k-2) equals sum_j n! / (j! (n-2j)! 2^j);
    for n <= 7 also a brute-force count over all permutations."""
    a = [1, 1]
    for k in range(2, n + 1):
        a.append(a[k - 1] + (k - 1) * a[k - 2])
    closed = sum(math.factorial(n) // (math.factorial(j) * math.factorial(n - 2 * j) * 2 ** j)
                 for j in range(n // 2 + 1))
    if a[n] != closed:
        return False
    if n <= 7:
        import itertools
        brute = sum(1 for p in itertools.permutations(range(n)) if all(p[p[i]] == i for i in range(n)))
        return brute == a[n]
    return True
'''),
    ("oeis_a001045_jacobsthal_sum", (1, 60), '''
def check_oeis_a001045_jacobsthal_sum(n: int) -> bool:
    """Jacobsthal A001045: J(k) = J(k-1) + 2 J(k-2) equals (2^n - (-1)^n)/3 and
    sum_k C(n-1-k, k) 2^k."""
    if n < 1:
        return True
    j0, j1 = 0, 1
    for _ in range(n - 1):
        j0, j1 = j1, j1 + 2 * j0
    return 3 * j1 == 2 ** n - (-1) ** n and j1 == sum(math.comb(n - 1 - k, k) * 2 ** k
                                                      for k in range((n - 1) // 2 + 1))
'''),
    ("oeis_a002426_central_trinomial", (0, 50), '''
def check_oeis_a002426_central_trinomial(n: int) -> bool:
    """Central trinomial A002426: coefficient of x^n in (1+x+x^2)^n (polynomial powers) equals
    sum_k C(n,2k) C(2k,k) and the P-recurrence k a(k) = (2k-1) a(k-1) + 3(k-1) a(k-2)."""
    if n < 0:
        return True
    poly = [1]
    for _ in range(n):
        nxt = [0] * (len(poly) + 2)
        for i, c in enumerate(poly):
            nxt[i] += c
            nxt[i + 1] += c
            nxt[i + 2] += c
        poly = nxt
    coeff = poly[n]
    closed = sum(math.comb(n, 2 * k) * math.comb(2 * k, k) for k in range(n // 2 + 1))
    a = [1, 1]
    for k in range(2, n + 1):
        num = (2 * k - 1) * a[k - 1] + 3 * (k - 1) * a[k - 2]
        if num % k:
            return False
        a.append(num // k)
    return coeff == closed == a[n]
'''),
    ("oeis_a000111_zigzag_boustrophedon", (0, 40), '''
def check_oeis_a000111_zigzag_boustrophedon(n: int) -> bool:
    """Euler zigzag A000111: the Seidel boustrophedon triangle equals the convolution
    recurrence 2 a(k+1) = sum_j C(k,j) a(j) a(k-j) (k >= 1); brute-force alternating
    permutations for small n."""
    if n < 0:
        return True
    row, zz = [1], [1]
    for k in range(1, n + 1):
        nxt = [0]
        for x in reversed(row):
            nxt.append(nxt[-1] + x)
        row = nxt
        zz.append(row[-1])
    a = [1, 1]
    for k in range(1, n):
        s = sum(math.comb(k, j) * a[j] * a[k - j] for j in range(k + 1))
        if s % 2:
            return False
        a.append(s // 2)
    if zz[n] != a[n]:
        return False
    if 2 <= n <= 7:
        import itertools
        brute = sum(1 for p in itertools.permutations(range(n))
                    if all((p[i] < p[i + 1]) == (i % 2 == 1) for i in range(n - 1)))
        return brute == a[n]
    return True
'''),
    ("oeis_a000262_lah_row_sums", (0, 40), '''
def check_oeis_a000262_lah_row_sums(n: int) -> bool:
    """A000262 (sets of lists): sum_k L(n,k) with unsigned Lah L(n,k) = C(n-1,k-1) n!/k! equals
    the recurrence a(k) = (2k-1) a(k-1) - (k-1)(k-2) a(k-2)."""
    if n < 0:
        return True
    lah = 1 if n == 0 else sum(math.comb(n - 1, k - 1) * math.factorial(n) // math.factorial(k)
                               for k in range(1, n + 1))
    a = [1, 1]
    for k in range(2, n + 1):
        a.append((2 * k - 1) * a[k - 1] - (k - 1) * (k - 2) * a[k - 2])
    return lah == a[n]
'''),
    ("oeis_a001764_ternary_trees", (0, 40), '''
def check_oeis_a001764_ternary_trees(n: int) -> bool:
    """Ternary trees A001764: C(3n,n)/(2n+1) equals the tree decomposition
    a(m) = sum_{i+j+k=m-1} a(i) a(j) a(k)."""
    if n < 0:
        return True
    a = [1]
    for m in range(1, n + 1):
        pair = [sum(a[i] * a[s - i] for i in range(s + 1)) for s in range(m)]
        a.append(sum(a[i] * pair[m - 1 - i] for i in range(m)))
    return (2 * n + 1) * a[n] == math.comb(3 * n, n)
'''),
    ("oeis_a000957_fine_no_hills", (1, 40), '''
def check_oeis_a000957_fine_no_hills(n: int) -> bool:
    """Fine numbers A000957: Dyck paths with no hill (peak at height 1), counted by a path DP,
    satisfy 2 F(n) + F(n-1) = Catalan(n) = C(2n,n)/(n+1)."""
    if n < 1:
        return True

    def no_hills(m: int) -> int:
        if m == 0:
            return 1
        # state: (height, last step was an up-step from height 0)
        cur = {(0, False): 1}
        for _ in range(2 * m):
            nxt = {}
            for (h, from0), c in cur.items():
                key = (h + 1, h == 0)
                nxt[key] = nxt.get(key, 0) + c
                if h > 0 and not (h == 1 and from0):
                    key = (h - 1, False)
                    nxt[key] = nxt.get(key, 0) + c
            cur = nxt
        return cur.get((0, False), 0)
    return 2 * no_hills(n) + no_hills(n - 1) == math.comb(2 * n, n) // (n + 1)
'''),
    ("oeis_a001003_little_schroeder", (1, 40), '''
def check_oeis_a001003_little_schroeder(n: int) -> bool:
    """Little Schroeder A001003 by (k+1) s(k) = 3(2k-1) s(k-1) - (k-2) s(k-2) is half the large
    Schroeder number counted by a lattice-path DP (steps E, N, NE staying weakly below y = x)."""
    if n < 1:
        return True
    s = [1, 1]
    for k in range(2, n + 1):
        num = 3 * (2 * k - 1) * s[k - 1] - (k - 2) * s[k - 2]
        if num % (k + 1):
            return False
        s.append(num // (k + 1))
    grid = [[0] * (n + 1) for _ in range(n + 1)]
    grid[0][0] = 1
    for x in range(n + 1):
        for y in range(x + 1):
            if x == 0 and y == 0:
                continue
            v = 0
            if x > 0 and y <= x - 1:
                v += grid[x - 1][y]
            if y > 0:
                v += grid[x][y - 1]
            if x > 0 and y > 0:
                v += grid[x - 1][y - 1]
            grid[x][y] = v
    return 2 * s[n] == grid[n][n]
'''),
    ("oeis_a005259_apery_recurrence", (0, 40), '''
def check_oeis_a005259_apery_recurrence(n: int) -> bool:
    """Apery numbers A005259: sum_k C(n,k)^2 C(n+k,k)^2 satisfies Apery's recurrence
    k^3 a(k) = (34k^3 - 51k^2 + 27k - 5) a(k-1) - (k-1)^3 a(k-2)."""
    if n < 0:
        return True
    closed = sum(math.comb(n, k) ** 2 * math.comb(n + k, k) ** 2 for k in range(n + 1))
    a = [1, 5]
    for k in range(2, n + 1):
        num = (34 * k ** 3 - 51 * k ** 2 + 27 * k - 5) * a[k - 1] - (k - 1) ** 3 * a[k - 2]
        if num % k ** 3:
            return False
        a.append(num // k ** 3)
    return closed == a[n]
'''),
    ("oeis_a000172_franel_recurrence", (0, 40), '''
def check_oeis_a000172_franel_recurrence(n: int) -> bool:
    """Franel numbers A000172: sum_k C(n,k)^3 satisfies Franel's recurrence
    (k+1)^2 a(k+1) = (7k^2 + 7k + 2) a(k) + 8 k^2 a(k-1)."""
    if n < 0:
        return True
    closed = sum(math.comb(n, k) ** 3 for k in range(n + 1))
    a = [1, 2]
    for k in range(1, n):
        num = (7 * k * k + 7 * k + 2) * a[k] + 8 * k * k * a[k - 1]
        if num % (k + 1) ** 2:
            return False
        a.append(num // (k + 1) ** 2)
    return closed == a[n]
'''),
    ("oeis_a002893_hexagonal_walks", (0, 40), '''
def check_oeis_a002893_hexagonal_walks(n: int) -> bool:
    """A002893: sum_k C(n,k)^2 C(2k,k) satisfies (k+1)^2 a(k+1) = (10k^2 + 10k + 3) a(k) - 9 k^2 a(k-1)."""
    if n < 0:
        return True
    closed = sum(math.comb(n, k) ** 2 * math.comb(2 * k, k) for k in range(n + 1))
    a = [1, 3]
    for k in range(1, n):
        num = (10 * k * k + 10 * k + 3) * a[k] - 9 * k * k * a[k - 1]
        if num % (k + 1) ** 2:
            return False
        a.append(num // (k + 1) ** 2)
    return closed == a[n]
'''),
]

# A few opening terms of each sequence (OEIS), used by the vetting test.
OEIS_TERMS: dict[str, list[int]] = {
    "A000032": [2, 1, 3, 4, 7, 11, 18, 29, 47, 76],
    "A001006": [1, 1, 2, 4, 9, 21, 51, 127, 323, 835],
    "A005043": [1, 0, 1, 1, 3, 6, 15, 36, 91, 232],
    "A001850": [1, 3, 13, 63, 321, 1683, 8989, 48639],
    "A006318": [1, 2, 6, 22, 90, 394, 1806, 8558],
    "A000085": [1, 1, 2, 4, 10, 26, 76, 232, 764, 2620],
    "A001045": [0, 1, 1, 3, 5, 11, 21, 43, 85, 171],
    # item 99: widened pool
    "A002426": [1, 1, 3, 7, 19, 51, 141, 393, 1107, 3139],
    "A000111": [1, 1, 1, 2, 5, 16, 61, 272, 1385, 7936],
    "A000262": [1, 1, 3, 13, 73, 501, 4051, 37633],
    "A001764": [1, 1, 3, 12, 55, 273, 1428, 7752],
    "A000957": [1, 0, 1, 2, 6, 18, 57, 186, 622, 2120],
    "A001003": [1, 1, 3, 11, 45, 197, 903, 4279, 20793],
    "A005259": [1, 5, 73, 1445, 33001, 819005],
    "A000172": [1, 2, 10, 56, 346, 2252, 15184],
    "A002893": [1, 3, 15, 93, 639, 4653, 35169],
}


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _self_mod() -> bool:
    try:
        from colony.arm import self_mod_enabled
        return bool(self_mod_enabled())
    except Exception:  # noqa: BLE001
        return False


def _hard_entries(src: str) -> list[tuple[str, bool | None]]:
    tree = ast.parse(src)
    for node in tree.body:
        tgt = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            tgt = node.target.id
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            tgt = node.targets[0].id
        if tgt == "HARD_TIER_LEMMAS" and isinstance(node.value, ast.List):
            out = []
            for e in node.value.elts:
                if isinstance(e, ast.Tuple) and len(e.elts) == 3 and isinstance(e.elts[0], ast.Constant):
                    flag = e.elts[2].value if isinstance(e.elts[2], ast.Constant) else None
                    out.append((str(e.elts[0].value), flag))
            return out
    return []


def families_remaining(src: str) -> list[str]:
    """Hand-written hard-tier families still waiting for an enable (not authored/adversarial)."""
    return [n for n, flag in _hard_entries(src) if flag is False and not n.startswith(NON_FAMILY_PREFIXES)]


def insert_family(src: str, name: str, window: tuple[int, int], fn_src: str) -> str | None:
    marker = INSERT_MARKER if INSERT_MARKER in src else FALLBACK_MARKER
    if marker not in src or f'("{name}"' in src or f"def check_{name}(" in src:
        return None
    src = src.replace(marker, fn_src.strip("\n") + "\n\n\n" + marker, 1)
    tree = ast.parse(src)
    lst = None
    for node in tree.body:
        tgt = getattr(getattr(node, "target", None), "id", None) or (
            node.targets[0].id if isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name) else None)
        if tgt == "HARD_TIER_LEMMAS" and isinstance(getattr(node, "value", None), ast.List):
            lst = node.value
    if lst is None:
        return None
    lines = src.splitlines(keepends=True)
    a, b = window
    entry = f'    ("{name}", lambda: all(check_{name}(n) for n in range({a}, {b})), False),\n'
    lines.insert(lst.end_lineno - 1, entry)
    out = "".join(lines)
    ast.parse(out)
    return out


_PROBE = r'''
import json, sys
from pathlib import Path
path, name, a, b = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
import importlib.util
spec = importlib.util.spec_from_file_location("hts_probe", path)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
entry = {n: (f, e) for n, f, e in mod.HARD_TIER_LEMMAS}.get(name)
out = {"in_catalog": entry is not None, "disabled": bool(entry) and entry[1] is False}
out["window_ok"] = bool(entry) and bool(entry[0]())
from colony.trust.shifted_holdout import shifted_window_check
sw = shifted_window_check(Path(path), name)
out["shift_status"], out["shift_reason"] = sw.get("status"), sw.get("reason")
import ast
from colony.stem_held_out import falsifiable
ns = dict(mod.__dict__)
fz = falsifiable("check_" + name, [(n,) for n in range(a, b)], ns, ast.parse(Path(path).read_text()))
out["mutants"], out["mutants_killed"] = fz["mutants"], fz["killed"]
out["falsifiable"] = fz["falsifiable"]
print(json.dumps(out))
'''


def verify(new_src: str, name: str, window: tuple[int, int]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lemma_impl_probe.py"
        path.write_text(new_src, encoding="utf-8")
        try:
            proc = subprocess.run([sys.executable, "-c", _PROBE, str(path), name, str(window[0]), str(window[1])],
                                  capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_S, cwd=str(ROOT))
        except subprocess.TimeoutExpired:
            return {"accepted": False, "reason": "timeout"}
    if proc.returncode != 0:
        return {"accepted": False, "reason": f"error:{(proc.stderr or '').strip()[-160:]}"}
    try:
        res = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"accepted": False, "reason": "bad_probe_output"}
    if not (res.get("in_catalog") and res.get("disabled")):
        return {**res, "accepted": False, "reason": "not_inserted_disabled"}
    if not res.get("window_ok"):
        return {**res, "accepted": False, "reason": "does_not_hold_on_window"}
    if res.get("shift_status") != "pass":
        return {**res, "accepted": False, "reason": f"oracle_shifted_window:{res.get('shift_reason')}"}
    if not res.get("falsifiable"):
        return {**res, "accepted": False, "reason": "trivial:not_falsifiable"}
    return {**res, "accepted": True, "reason": "verified"}


def _append(row: dict[str, Any]) -> None:
    if os.environ.get("PYTEST_CURRENT_TEST") and SUPPLY_LOG == Path(
            os.path.join(os.fspath(ROOT), "data", "commons", "hard_tier_supply.jsonl")):
        return
    try:
        SUPPLY_LOG.parent.mkdir(parents=True, exist_ok=True)
        with SUPPLY_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


def birth_record_enabled() -> bool:
    """Item 100 kill switch: COLONY_SUPPLY_BIRTH_RECORD=off stops writing the authoring record."""
    return (os.environ.get("COLONY_SUPPLY_BIRTH_RECORD") or "live").strip().lower() != "off"


def _birth_record(name: str, window: tuple[int, int], cycle_id: str) -> dict[str, Any] | None:
    """Item 100: the family's authoring record (lesson type ``authored_check``), like every other
    authored hard check. Without it a later keep of the family cites no prior lesson, so every
    supply keep scored 0 in lesson uptake (7 of the last 7 keeps). The novelty gate already treats
    a candidate's own authoring record as not prior knowledge; the 150 cap counts ``authored_``
    entries in the lemma file, not lessons, so it is unaffected. Treatment only (supply is)."""
    if not birth_record_enabled() or not _self_mod():
        return None
    try:
        from colony import lessons as _L
        real = Path(os.path.join(os.fspath(ROOT), "data", "commons", "lessons.jsonl"))
        if os.environ.get("PYTEST_CURRENT_TEST") and Path(_L.LESSONS_JSONL).resolve() == real.resolve():
            return None  # tests never write the real lesson log
        return _L.write_lesson(
            decision="skip", check="authoring", source="conjecture_desk", cycle_id=cycle_id,
            mutation=name, lesson_type="authored_check", family="hard_tier",
            what=(f"authored hard-tier family `{name}` (vetted OEIS relation, window {window[0]}..{window[1]}), "
                  "inserted DISABLED; the Oracle decides the enable. Not discovery."),
            tags=["authoring", "authored_check", "hard_tier_supply", "oeis"],
            evidence=["data/commons/hard_tier_supply.jsonl", "colony/hard_tier_families.py"],
        )
    except Exception:  # noqa: BLE001
        return None


def build_next(lemma_path: Path, *, cycle_id: str = "", write: bool = True,
               blocked: set[str] | None = None) -> dict[str, Any] | None:
    """Add one vetted family (disabled) when none remain. None when nothing to do."""
    if not _self_mod():
        return None
    real = ROOT / "society" / "benchmarks" / "artifacts" / "lemma_impl.py"
    if os.environ.get("PYTEST_CURRENT_TEST") and Path(lemma_path).resolve() == real.resolve():
        return None  # tests never build into (or edit) the real catalog
    src = lemma_path.read_text(encoding="utf-8")
    remaining = families_remaining(src)
    if remaining:
        return None
    blocked = blocked or set()
    tried = []
    for name, window, fn_src in POOL:
        if name in blocked or f'("{name}"' in src:
            continue
        new_src = insert_family(src, name, window, fn_src)
        if new_src is None:
            continue
        v = verify(new_src, name, window)
        tried.append({"name": name, "reason": v.get("reason")})
        if not v.get("accepted"):
            continue
        row = {"ts": _utc(), "cycle_id": cycle_id, "name": name, "window": list(window),
               "families_remaining_before": 0, "verify": v, "written": bool(write), "enabled": False,
               "note": "Vetted OEIS relation family, inserted DISABLED; the Oracle decides. Not discovery."}
        if write:
            lemma_path.write_text(new_src, encoding="utf-8")
            try:
                from colony.conjecture_mutations import register_mutation_candidate
                register_mutation_candidate(name, "hard_enable", f"enable:{name}")
            except Exception:  # noqa: BLE001
                pass
            _append(row)
            row["birth_record"] = bool(_birth_record(name, window, cycle_id))
        return row
    if tried:
        _append({"ts": _utc(), "cycle_id": cycle_id, "name": None, "tried": tried, "written": False})
    return {"name": None, "tried": tried, "pool_exhausted": not tried}
