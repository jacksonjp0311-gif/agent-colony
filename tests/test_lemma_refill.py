"""Building-block lemma refill: 30 classical lemmas, disabled, each passes, survives the Oracle's
shifted held-out window, is falsifiable, and is reachable by the desk via MUTATION_SNIPPETS."""
import ast
from pathlib import Path

import pytest

from colony.authoring import _extendable, _fn_nontrivial
from colony.conjecture_mutations import MUTATION_SNIPPETS
from colony.trust.shifted_holdout import shifted_window_check
from society.benchmarks.artifacts import lemma_impl as L

IMPL = Path(L.__file__)
SRC = IMPL.read_text(encoding="utf-8")
REFILL = [
    "fermat_little", "euler_theorem", "wilson_theorem", "quadratic_reciprocity", "mobius_divisor_sum",
    "gauss_phi_divisor_sum", "sigma_multiplicative", "mobius_inversion_sigma", "bezout_identity",
    "crt_coprime_pair", "lucas_theorem_binomial", "stirling_first_row_sum", "bell_stirling_sum",
    "alternating_binomial_row", "multinomial_three", "euler_pentagonal", "odd_distinct_partitions",
    "partition_conjugate_parts", "cayley_tree_count", "cycle_spanning_trees", "complete_bipartite_trees",
    "cayley_hamilton_2x2", "cayley_hamilton_3x3", "newton_identities", "polynomial_remainder",
    "telescoping_sum", "abel_summation", "faulhaber_power_sums", "lagrange_cyclic_orders",
    "burnside_necklaces",
]
BY = {n: (f, e) for n, f, e in L.HARD_TIER_LEMMAS}
TREE = ast.parse(SRC)
FUNCS = {n.name: n for n in TREE.body if isinstance(n, ast.FunctionDef)}
LAMBDAS = {n.elts[0].value: n.elts[1] for n in ast.walk(TREE) if isinstance(n, ast.Tuple) and len(n.elts) == 3
           and isinstance(n.elts[0], ast.Constant) and isinstance(n.elts[0].value, str)}


def test_refill_present_disabled_and_reachable():
    snip = {n for n, k, _ in MUTATION_SNIPPETS if k == "hard_enable"}
    for n in REFILL:
        assert n in BY, n  # born disabled (68954ec); the desk may enable one only via the Oracle
        assert n in snip, n
    assert len(set(REFILL)) == 30


@pytest.mark.parametrize("name", REFILL)
def test_lemma_passes_and_survives_shifted_window(name):
    assert BY[name][0]() is True
    sh = shifted_window_check(IMPL, name)
    assert sh["applied"] and sh["ok"], sh


@pytest.mark.parametrize("name", REFILL)
def test_lemma_is_composable_and_falsifiable(name):
    ext = _extendable(LAMBDAS[name])
    assert ext, name
    fn = FUNCS[ext[0]]
    assert _fn_nontrivial(fn)
    # Falsifiable: flip the == / != of the claim in the function's final return (not the domain
    # filters inside comprehension `if`s); the catalog entry must then fail.
    bad = ast.parse(ast.unparse(fn))
    ret = bad.body[0].body[-1]  # the final top-level statement is the claim's return
    assert isinstance(ret, ast.Return), name
    skip = {id(x) for c in ast.walk(ret) if isinstance(c, ast.comprehension) for i in c.ifs for x in ast.walk(i)}
    for outer in ast.walk(ret):  # only outermost claims: not nested in another Compare / IfExp
        if isinstance(outer, (ast.Compare, ast.IfExp)):
            skip |= {id(x) for x in ast.walk(outer) if x is not outer}
    flipped = 0
    for node in ast.walk(ret):
        if isinstance(node, ast.Compare) and id(node) not in skip:
            node.ops = [ast.NotEq() if isinstance(o, ast.Eq) else ast.Eq() if isinstance(o, ast.NotEq) else o
                        for o in node.ops]
            flipped += 1
    assert flipped, name
    ast.fix_missing_locations(bad)
    ns = dict(vars(L))
    exec(compile(bad, "<flipped>", "exec"), ns)  # noqa: S102
    expr = ast.Expression(LAMBDAS[name].body)
    ast.fix_missing_locations(expr)
    assert eval(compile(expr, "<entry>", "eval"), ns) is False, name  # noqa: S307


def test_no_textbook_list_or_human_guide_touched():
    from colony import novelty_gate as NG
    assert all(NG.textbook_reuse_score(n) < 0.34 for n in REFILL)  # building blocks; not pre-killed
