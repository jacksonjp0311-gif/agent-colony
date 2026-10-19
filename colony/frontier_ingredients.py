"""New generator ingredients for the frontier conjecture generator (COLONY_FRONTIER_INGREDIENTS).

Three families of integer sequences a(n), n >= 1, added as primitives:

graph invariants (counts on small graph families, transfer matrices / closed forms)
  stree_ladder  spanning trees of the ladder P2 x Pn               (A001353)
  stree_grid3   spanning trees of the grid P3 x Pn                 (A006238)
  match_ladder  matchings (all sizes, incl. empty) of P2 x Pn      (A030186)
  indep_grid3   independent vertex sets of P3 x Pn                 (A051736)
  chrom_cycle3  chromatic polynomial of the cycle C_n at k = 3     (2^n + 2(-1)^n)
  chrom_wheel5  chromatic polynomial of the wheel W_n at k = 5     (5(3^n + 3(-1)^n))
  chrom_grid3   proper 3-colourings of P3 x Pn (chromatic polynomial of the grid at k = 3)
restricted partitions (generating-function DP)
  pdist         partitions into distinct parts q(n) (= odd parts, Euler; one table)   (A000009)
  ple3          partitions into parts <= 3                         (A001399)
  prr           partitions into parts = +-1 (mod 5)                (A003114)
  pnot3         partitions into parts not divisible by 3           (A000726)
matrix sequences
  perm_derange  permanent of J - I (n x n), the derangement numbers (A000166)
  tr_petersen   trace of A^n, A the Petersen graph adjacency matrix (3^n + 5 + 4(-2)^n)
  tr_tribo      trace of C^n, C the tribonacci companion matrix     (A001644)
  hankel_part   Hankel determinant det[p(i+j)]_{0<=i,j<n}, p = partition numbers (short table)

Every table is built by a mechanism (transfer matrix, recurrence, DP, Bareiss), not typed in; the
tests check each one against brute force on small n. Modes: off (default; the tables exist but
the generator never samples them), shadow (a dry generator pass that samples them each cycle and
reports per-ingredient counts; nothing is written to the registry, so nothing is authored), live
(the real generator samples them; same triviality filter, reference check, Oracle and caps).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "society" / "systems" / "frontier_ingredients.json"

GROUPS = {
    "graph": ("stree_ladder", "stree_grid3", "match_ladder", "indep_grid3", "chrom_cycle3", "chrom_wheel5",
              "chrom_grid3"),
    "partition": ("pdist", "ple3", "prr", "pnot3"),
    "matrix": ("perm_derange", "tr_petersen", "tr_tribo", "hankel_part"),
}
NEW = tuple(p for g in GROUPS.values() for p in g)
CHEAP = ("ple3",)                     # polynomial growth: tabulated as far as the arithmetic primitives
EXPO_NEW = tuple(p for p in NEW if p not in CHEAP)
EXP_CAP = 2004                        # exponential tables: as far as the held-out range (HELD_EXP 2000)
FACT_CAP = 1200                       # factorial growth
HANKEL_N = 52                         # Hankel determinants: one O(N^3) Bareiss pass
# upper bounds on the linear-recurrence order (transfer-matrix size / closed form), so the
# closure filter labels recurrences and periodic residues of these as expected, never surprises
CF_ORDER_NEW = {"stree_ladder": 2, "stree_grid3": 4, "match_ladder": 4, "indep_grid3": 5, "chrom_cycle3": 2,
                "chrom_wheel5": 2, "chrom_grid3": 12, "ple3": 6, "tr_petersen": 3, "tr_tribo": 3}
POSITIVE_NEW = ("stree_ladder", "stree_grid3", "match_ladder", "indep_grid3", "chrom_grid3", "pdist", "ple3",
                "prr", "pnot3", "tr_tribo")

_FORCE = False


def mode() -> str:
    m = os.environ.get("COLONY_FRONTIER_INGREDIENTS", "off").strip().lower()
    return m if m in ("off", "shadow", "live") else "off"


def active() -> bool:
    """Does the generator sample the new ingredients right now?"""
    return _FORCE or mode() == "live"


def group_of(p: str) -> str:
    return next((g for g, ps in GROUPS.items() if p in ps), "")


# ----------------------------------------------------------------------------- mechanisms

def _linrec(init: list[int], coef: list[int], N: int) -> list[int]:
    a = list(init)
    while len(a) <= N:
        a.append(sum(c * a[-1 - i] for i, c in enumerate(coef)))
    return a[:N + 1]


def _transfer(states: list, compat, N: int, weight=None) -> list[int]:
    """a(n) = number of length-n state sequences with consecutive states compatible; a(0) = 1."""
    w = weight or (lambda s: 1)
    vec = [w(s) for s in states]
    out = [1, sum(vec)]
    adj = [[j for j, t in enumerate(states) if compat(s, t)] for s in states]
    for _ in range(2, N + 1):
        new = [0] * len(states)
        for i, v in enumerate(vec):
            if v:
                for j in adj[i]:
                    new[j] += v
        vec = new
        out.append(sum(vec))
    return out


def bareiss_minors(M: list[list[int]]) -> list[int]:
    """Leading principal minors det(M[:k,:k]), k = 1..n, by fraction-free elimination (no pivoting);
    stops at the first zero pivot."""
    A = [row[:] for row in M]
    n, prev, out = len(A), 1, []
    for k in range(n):
        if A[k][k] == 0:
            break
        out.append(A[k][k])
        for i in range(k + 1, n):
            for j in range(k + 1, n):
                A[i][j] = (A[i][j] * A[k][k] - A[i][k] * A[k][j]) // prev
        prev = A[k][k]
    return out


def det(M: list[list[int]]) -> int:
    n = len(M)
    if n == 0:
        return 1
    m = bareiss_minors(M)
    if len(m) == n:
        return m[-1]
    from fractions import Fraction   # zero pivot: fall back to exact elimination with pivoting
    A = [[Fraction(x) for x in r] for r in M]
    d = Fraction(1)
    for k in range(n):
        p = next((i for i in range(k, n) if A[i][k] != 0), None)
        if p is None:
            return 0
        if p != k:
            A[k], A[p] = A[p], A[k]
            d = -d
        d *= A[k][k]
        for i in range(k + 1, n):
            f = A[i][k] / A[k][k]
            for j in range(k, n):
                A[i][j] -= f * A[k][j]
    return int(d)


def grid_edges(h: int, w: int) -> tuple[int, list[tuple[int, int]]]:
    idx = lambda r, c: r * w + c  # noqa: E731
    E = [(idx(r, c), idx(r, c + 1)) for r in range(h) for c in range(w - 1)]
    E += [(idx(r, c), idx(r + 1, c)) for r in range(h - 1) for c in range(w)]
    return h * w, E


def spanning_trees(nv: int, E: list[tuple[int, int]]) -> int:
    """Kirchhoff's matrix-tree theorem."""
    if nv == 1:
        return 1
    L = [[0] * nv for _ in range(nv)]
    for u, v in E:
        L[u][u] += 1
        L[v][v] += 1
        L[u][v] -= 1
        L[v][u] -= 1
    return det([r[1:] for r in L[1:]])


def _partitions(N: int, allowed, distinct: bool = False) -> list[int]:
    a = [1] + [0] * N
    for k in range(1, N + 1):
        if not allowed(k):
            continue
        if distinct:
            for n in range(N, k - 1, -1):
                a[n] += a[n - k]
        else:
            for n in range(k, N + 1):
                a[n] += a[n - k]
    return a


def _part_numbers(N: int) -> list[int]:
    return _partitions(N, lambda k: True)


def _derangements(N: int) -> list[int]:
    d = [1, 0]
    for n in range(2, N + 1):
        d.append((n - 1) * (d[-1] + d[-2]))
    return d[:N + 1]


def _stree_grid3(N: int) -> list[int]:
    # A006238 recurrence a(n) = 15a(n-1) - 32a(n-2) + 15a(n-3) - a(n-4), checked against
    # Kirchhoff on P3 x Pn for n = 1..9 every time the table is built
    kir = [0] + [spanning_trees(*grid_edges(3, w)) for w in range(1, 10)]
    a = _linrec(kir[1:5], [15, -32, 15, -1], N + 8)
    a = [0] + a
    if a[1:10] != kir[1:10]:
        raise ValueError("stree_grid3: recurrence disagrees with Kirchhoff")
    return a[:N + 1]


def _match_ladder(N: int) -> list[int]:
    # state per column: (top/bottom vertex already matched by a horizontal edge from the left)
    # count by a transfer over columns: choose horizontal edges to the next column + a rung
    def col_ways(left: tuple[int, int]):
        """yield (ways, right-state) for one column given which vertices are taken from the left."""
        for rung in (0, 1):
            if rung and (left[0] or left[1]):
                continue
            used = (left[0] or rung, left[1] or rung)
            for ht in (0, 1):
                for hb in (0, 1):
                    if (ht and used[0]) or (hb and used[1]):
                        continue
                    yield (ht, hb)
    out = [1]
    vec = {(0, 0): 1}
    for n in range(1, N + 1):
        new: dict[tuple[int, int], int] = {}
        tot = 0
        for st, v in vec.items():
            for right in col_ways(st):
                if right == (0, 0):
                    tot += v
                new[right] = new.get(right, 0) + v
        out.append(tot)        # a(n): no horizontal edge leaves the last column
        vec = new
    return out


def _indep_grid3(N: int) -> list[int]:
    cols = [s for s in range(8) if not (s & (s >> 1))]
    return _transfer(cols, lambda s, t: not (s & t), N)


def _chrom_grid3(N: int) -> list[int]:
    cols = [(a, b, c) for a in range(3) for b in range(3) for c in range(3) if a != b and b != c]
    return _transfer(cols, lambda s, t: all(x != y for x, y in zip(s, t)), N)


def _hankel_part(N: int) -> list[int]:
    """det[p(i+j)] for sizes 1..N: one Bareiss pass gives every leading minor up to the first zero
    pivot; from there each size is a separate exact determinant (these Hankel determinants do vanish)."""
    p = _part_numbers(2 * N)
    H = [[p[i + j] for j in range(N)] for i in range(N)]
    m = bareiss_minors(H)
    out = [1] + m
    for k in range(len(m) + 1, N + 1):
        out.append(det([r[:k] for r in H[:k]]))
    return out


def _builders(T: Any) -> dict[str, Any]:
    E = max(4, min(T.exp_n, EXP_CAP))
    return {
        "stree_ladder": lambda: _linrec([0, 1], [4, -1], E),
        "stree_grid3": lambda: _stree_grid3(E),
        "match_ladder": lambda: _match_ladder(E),
        "indep_grid3": lambda: _indep_grid3(E),
        "chrom_cycle3": lambda: [2 ** n + 2 * (-1) ** n for n in range(E + 1)],
        "chrom_wheel5": lambda: [5 * (3 ** n + 3 * (-1) ** n) for n in range(E + 1)],
        "chrom_grid3": lambda: _chrom_grid3(E),
        "pdist": lambda: _partitions(E, lambda k: True, distinct=True),
        "ple3": lambda: [(n + 3) ** 2 // 12 + (1 if ((n + 3) ** 2 % 12) * 2 >= 12 else 0) for n in range(T.lim + 1)],
        "prr": lambda: _partitions(E, lambda k: k % 5 in (1, 4)),
        "pnot3": lambda: _partitions(E, lambda k: k % 3 != 0),
        "perm_derange": lambda: _derangements(min(E, FACT_CAP)),
        "tr_petersen": lambda: [3 ** n + 5 + 4 * (-2) ** n for n in range(E + 1)],
        "tr_tribo": lambda: _linrec([3, 1, 3], [1, 1, 1], E),
        "hankel_part": lambda: _hankel_part(min(HANKEL_N, E)),
    }


class LazyTable(dict):
    """A Tables.t that builds an ingredient table the first time it is looked up, so code that
    never touches the new ingredients (e.g. an authored check's runtime budget) pays nothing."""

    def __init__(self, T: Any, *a: Any, **k: Any) -> None:
        super().__init__(*a, **k)
        self._T = T

    def __missing__(self, key: str) -> list[int]:
        if key not in NEW:
            raise KeyError(key)
        v = _builders(self._T)[key]()
        self[key] = v
        return v

    def __contains__(self, key: object) -> bool:
        return dict.__contains__(self, key) or key in NEW

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def build_all(self) -> None:
        for k in NEW:
            self[k]


def extend(T: Any) -> None:
    """Make the ingredient tables available on a frontier Tables object (built lazily)."""
    if not isinstance(T.t, LazyTable):
        T.t = LazyTable(T, T.t)


# ----------------------------------------------------------------------------- per-ingredient tally

STAGES = ("produced", "fresh", "passed_filter", "tested", "survived", "surprise", "explained_by_reference",
          "no_reference_found", "machine_checked")


def new_tally() -> dict[str, dict[str, int]]:
    return {p: {s: 0 for s in STAGES} for p in NEW}


def mark(tally: dict | None, prims: set[str], stage: str) -> None:
    if tally is None:
        return
    for p in prims & set(NEW):
        tally[p][stage] = tally[p].get(stage, 0) + 1


def shadow_cycle(cycle_id: str, T: Any = None) -> dict[str, Any] | None:
    """Report-only pass: the same generator, filter and reference check, with the ingredients in the
    menu; nothing is written to the frontier state (no registry entries, so nothing is authored)."""
    global _FORCE
    from colony import frontier_conjectures as fc
    tally = new_tally()
    _FORCE = True
    try:
        summ = fc.run_cycle(f"{cycle_id}:ingredients", T=T, write=False, tally=tally)
    finally:
        _FORCE = False
    return record(cycle_id, "shadow", tally, summ)


def record(cycle_id: str, mode_: str, tally: dict, summ: dict | None) -> dict[str, Any]:
    try:
        st = json.loads(REPORT.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        st = {}
    tot = st.get("totals") or new_tally()
    for p, row in tally.items():
        for k, v in row.items():
            tot.setdefault(p, {}).setdefault(k, 0)
            tot[p][k] += v
    surv = [s for s in ((summ or {}).get("new_survivors") or []) if any(p in s["statement"] for p in NEW)]
    hist = (st.get("history") or []) + [{"cycle_id": cycle_id, "mode": mode_,
                                         "by_group": {g: {k: sum(tally[p][k] for p in ps) for k in STAGES}
                                                      for g, ps in GROUPS.items()},
                                         "survivors": surv[:8]}]
    out = {"note": "Per-ingredient counts for the new generator ingredients (colony/frontier_ingredients.py). "
                   "shadow = a dry generator pass, nothing registered or authored; live = the real pass.",
           "mode": mode_, "groups": GROUPS, "totals": tot, "history": hist[-30:]}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return out
