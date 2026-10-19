"""New frontier ingredients: every table agrees with brute force on small n; gating; report-only shadow."""
import itertools

import pytest

from colony import frontier_conjectures as FC
from colony import frontier_ingredients as I


@pytest.fixture(scope="module")
def T():
    return FC.Tables(lim=3000, exp_n=300)


def _adj(nv, E):
    A = [[0] * nv for _ in range(nv)]
    for u, v in E:
        A[u][v] = A[v][u] = 1
    return A


def _proper_colourings(nv, E, k):
    return sum(all(c[u] != c[v] for u, v in E) for c in itertools.product(range(k), repeat=nv))


def _partitions(n, ok, distinct=False, m=None):
    m = n if m is None else m
    if n == 0:
        return 1
    tot = 0
    for k in range(min(n, m), 0, -1):
        if ok(k):
            tot += _partitions(n - k, ok, distinct, k - 1 if distinct else k)
    return tot


def _matpow_trace(A, n):
    k = len(A)
    P = [[int(i == j) for j in range(k)] for i in range(k)]
    for _ in range(n):
        P = [[sum(P[i][t] * A[t][j] for t in range(k)) for j in range(k)] for i in range(k)]
    return sum(P[i][i] for i in range(k))


def test_graph_tables_match_brute_force(T):
    t = T.t
    for w in range(1, 8):
        assert t["stree_ladder"][w] == I.spanning_trees(*I.grid_edges(2, w))
        assert t["stree_grid3"][w] == I.spanning_trees(*I.grid_edges(3, w))
    for w in range(1, 5):
        nv, E = I.grid_edges(2, w)
        assert t["match_ladder"][w] == sum(
            1 for r in range(len(E) + 1) for S in itertools.combinations(E, r)
            if len({x for e in S for x in e}) == 2 * len(S))
        nv, E = I.grid_edges(3, w)
        assert t["indep_grid3"][w] == sum(
            1 for m in range(1 << nv) if not any((m >> u) & 1 and (m >> v) & 1 for u, v in E))
    for w in range(1, 4):
        assert t["chrom_grid3"][w] == _proper_colourings(*I.grid_edges(3, w), 3)
    for n in range(3, 8):
        assert t["chrom_cycle3"][n] == _proper_colourings(n, [(i, (i + 1) % n) for i in range(n)], 3)
    for n in range(3, 6):
        E = [(i, (i + 1) % n) for i in range(n)] + [(i, n) for i in range(n)]
        assert t["chrom_wheel5"][n] == _proper_colourings(n + 1, E, 5)


def test_partition_tables_match_brute_force(T):
    t = T.t
    for n in range(0, 22):
        assert t["pdist"][n] == _partitions(n, lambda k: True, distinct=True) == _partitions(n, lambda k: k % 2)
        assert t["ple3"][n] == _partitions(n, lambda k: k <= 3)
        assert t["prr"][n] == _partitions(n, lambda k: k % 5 in (1, 4))
        assert t["pnot3"][n] == _partitions(n, lambda k: k % 3)


def test_matrix_tables_match_brute_force(T):
    t = T.t
    for n in range(1, 7):
        perm = sum(all(p[i] != i for i in range(n)) for p in itertools.permutations(range(n)))
        assert t["perm_derange"][n] == perm
    outer = [(i, (i + 1) % 5) for i in range(5)]
    inner = [(5 + i, 5 + (i + 2) % 5) for i in range(5)]
    spokes = [(i, 5 + i) for i in range(5)]
    P = _adj(10, outer + inner + spokes)
    C = [[1, 1, 1], [1, 0, 0], [0, 1, 0]]
    for n in range(1, 8):
        assert t["tr_petersen"][n] == _matpow_trace(P, n)
        assert t["tr_tribo"][n] == _matpow_trace(C, n)
    sympy = pytest.importorskip("sympy")
    p = I._part_numbers(30)
    for n in range(1, 12):
        assert t["hankel_part"][n] == sympy.Matrix(n, n, lambda i, j: p[i + j]).det()


def test_gating(monkeypatch):
    monkeypatch.delenv("COLONY_FRONTIER_INGREDIENTS", raising=False)
    assert I.mode() == "off" and not set(FC.menu_prims()) & set(I.NEW)
    monkeypatch.setenv("COLONY_FRONTIER_INGREDIENTS", "shadow")
    assert not set(FC.menu_prims()) & set(I.NEW)
    monkeypatch.setenv("COLONY_FRONTIER_INGREDIENTS", "live")
    assert set(I.NEW) <= set(FC.menu_prims())
    assert FC.cf_order(("p", "chrom_grid3")) and FC.cf_order(("p", "pdist")) is None


def test_shadow_pass_registers_nothing(T, tmp_path, monkeypatch):
    monkeypatch.setenv("COLONY_FRONTIER", "live")
    monkeypatch.setenv("COLONY_FRONTIER_INGREDIENTS", "shadow")
    monkeypatch.setattr(I, "REPORT", tmp_path / "ing.json")
    before = FC.STATE.read_bytes() if FC.STATE.exists() else b""
    out = I.shadow_cycle("t1", T=T)
    assert (FC.STATE.read_bytes() if FC.STATE.exists() else b"") == before
    assert out["mode"] == "shadow" and sum(r["produced"] for r in out["totals"].values()) > 0
    assert not I._FORCE


def test_short_table_gets_no_window():
    from colony import frontier_checks as F
    r = {"kind": "cong", "lhs": "hankel_part", "rhs": "", "params": {"m": 2, "r": 0, "q": 1, "s": 0}}
    assert F.windows(r, 1) == [] and F.build(r) is None


def test_outer_self_tautology_is_trivial():
    for kind, lhs in (("divides", "gpf[pnot3]"), ("le", "gpf[pnot3]"), ("divides", "rad[part]")):
        c = {"kind": kind, "_le": FC.parse(lhs), "_re": FC.parse(lhs.split("[")[1].rstrip("]")), "params": {}}
        assert FC._outer_self(c)
    c = {"kind": "divides", "_le": FC.parse("tau[pnot3]"), "_re": FC.parse("pnot3"), "params": {}}
    assert not FC._outer_self(c)
