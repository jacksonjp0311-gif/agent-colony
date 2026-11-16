"""Item 95 (2026-11-16): the novelty gate's own held-out test for ``stem_enable`` candidates.

Before this, every ``stem_enable`` was judged by the lemma hard-tier held-out test, whose
survive condition includes ``kind == "hard_enable"``, so a STEM enable could never survive
(``held_out:hard_tier_green_and_hard_enable``). This module is the STEM-pack equivalent.
It is never looser than the old test: every condition of the old test except the kind
still applies, and several STEM conditions are added on top.

``held_out(name)`` survives only if ALL hold (fail closed on any error):
  1. the lemma hard tier is green with n_hard_pass > 0 (the old test's own condition);
  2. the STEM bench is green with n_pass > 0 (the current pack, as on disk);
  3. ``name`` is a catalog entry in the STEM pack and its coded window passes;
  4. a HARDER held-out instance from the same pack passes: the same check function on
     a wider/extreme parameter grid DISJOINT from the coded window. The grids live HERE
     (outside the desk's mutable impl), so a candidate cannot pick its own held-out set;
     a candidate with no registered grid fails closed;
  5. the held-out instance is falsifiable: at least one single-point mutant of the check
     function (one numeric constant or one arithmetic operator changed) fails the grid.

``triviality(name)`` is the triviality filter for STEM checks, the analogue of the lemma
filter's ``ring_tautology``: if every equality the check asserts is symbolically zero after
substituting the function's own definitions (sympy), the check is true by the algebra of
its own definitions — it verifies nothing independent — and is killed for THAT reason
(``trivial:stem_symbolic_tautology``). Checks that reach their claim by an independent
numerical route (quadrature, search, finite differences, linear solves) are not tautologies.

Read-only: nothing here writes a file or a log, and the Oracle is untouched.
"""
from __future__ import annotations

import ast
import itertools
import math
import types
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STEM_IMPL = ROOT / "society" / "benchmarks" / "artifacts" / "kinematics_impl.py"

# name -> (check function, harder held-out grid). Every grid point is disjoint from the
# entry's coded window in kinematics_impl.STEM_CHECKS (see tests/test_item95_stem_held_out.py)
# and spans wider magnitudes / more extreme cases.
HELD_OUT_GRIDS: dict[str, tuple[str, list[tuple]]] = {
    "suvat_identity": ("check_suvat_displacement", list(itertools.product(
        (-11, 0.25, 9.5), (-7.5, 0.125, 6), (0.25, 4.5, 6)))),
    "projectile_range": ("check_projectile_range", list(itertools.product(
        (2.5, 33, 61), (5, 22.5, 52, 83, 89)))),
    "circular_centripetal": ("check_circular_centripetal", list(itertools.product(
        (0.3, 3.5, 17, -8), (0.125, 3, 9)))),
    "energy_work": ("check_energy_work", list(itertools.product(
        (0.5, 3.5, 11), (-6, 0.5, 8), (-2.5, 0.75, 3), (0.5, 2.5, 9)))),
    "stem_elastic_collision": ("check_elastic_collision_conservation", list(itertools.product(
        (0.25, 2, 11), (0.75, 5, 19), (-9, 1.5, 6), (-7, 2.5, 8)))),
    "stem_kepler_third_law": ("check_kepler_third_circular", list(itertools.product(
        (2.5, 4.9e12, 3.8e16), (0.3, 2.0e8, 4.5e12)))),
    "stem_shm_energy": ("check_shm_energy", list(itertools.product(
        (0.5, 9, 200), (0.05, 2, 7.5), (0.02, 1.7, 6)))),
    "stem_resistor_power_balance": ("check_resistor_power_balance", list(itertools.product(
        (0.5, 24, 400), (0.5, 33), (1.5, 220), (8, 1000)))),
    "stem_isothermal_work": ("check_isothermal_work", [
        (nrt, v1, v2) for nrt in (0.5, 8.314 * 450) for v1, v2 in ((1, 5), (0.25, 1.5), (3, 0.75))]),
    "stem_snell_least_time": ("check_snell_least_time", [
        (n1, n2, a, b, d) for n1, n2 in ((1.2, 1.0), (1.0, 1.7), (2.0, 1.45))
        for a, b, d in ((0.5, 2, 1), (3, 3, 4))]),
    "stem_rc_discharge": ("check_rc_discharge", list(itertools.product(
        (0.5, 9, 30), (0.01, 3, 220)))),
    "stem_thin_lens_matrix": ("check_thin_lens_ray_matrix", list(itertools.product(
        (0.02, 0.25, 1.5), (0.4, 2.2, 7)))),
    "stem_velocity_addition": ("check_velocity_addition_rapidity", list(itertools.product(
        (-0.95, -0.2, 0.45, 0.8), (-0.9, 0.05, 0.75, 0.99)))),
    "stem_wheatstone_balance": ("check_wheatstone_balance", [
        (r1, r2, r3, r4, rg) for r1, r2, r3, r4 in ((2, 4, 5, 10), (3, 3, 8, 8), (2, 4, 5, 11), (7, 2, 3, 1))
        for rg in (0.5, 120)]),
}


def _load(src: str | None = None) -> tuple[dict[str, Any], ast.Module]:
    text = src if src is not None else STEM_IMPL.read_text(encoding="utf-8")
    tree = ast.parse(text)
    mod = types.ModuleType("_stem_held_out_impl")
    exec(compile(tree, str(STEM_IMPL), "exec"), mod.__dict__)  # the repo's own impl file
    return mod.__dict__, tree


def _run_grid(fn: Any, grid: list[tuple]) -> bool:
    try:
        return bool(grid) and all(bool(fn(*args)) for args in grid)
    except Exception:  # noqa: BLE001
        return False


# ----------------------------------------------------------------------------- mutants

def _mutants(fn_node: ast.FunctionDef):
    """Single-point mutants: one numeric constant (x1.1, or 0 -> 1) or one +,-,*,/ swapped."""
    swap = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult}
    targets = []
    for node in ast.walk(fn_node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
                and not isinstance(node.value, bool):
            targets.append(("const", node))
        elif isinstance(node, ast.BinOp) and type(node.op) in swap:
            targets.append(("op", node))
    for i in range(len(targets)):
        mutant = ast.parse(ast.unparse(fn_node)).body[0]
        nodes = []
        for node in ast.walk(mutant):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
                    and not isinstance(node.value, bool):
                nodes.append(("const", node))
            elif isinstance(node, ast.BinOp) and type(node.op) in swap:
                nodes.append(("op", node))
        kind, node = nodes[i]
        if kind == "const":
            node.value = (node.value * 1.1) if node.value else 1
        else:
            node.op = swap[type(node.op)]()
        yield mutant


def falsifiable(fn_name: str, grid: list[tuple], ns: dict[str, Any], tree: ast.Module) -> dict[str, Any]:
    fn_node = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == fn_name), None)
    if fn_node is None:
        return {"falsifiable": False, "mutants": 0, "killed": 0}
    n = killed = 0
    for mutant in _mutants(fn_node):
        n += 1
        local = dict(ns)
        try:
            exec(compile(ast.Module(body=[mutant], type_ignores=[]), "<mutant>", "exec"), local)
        except Exception:  # noqa: BLE001
            killed += 1
            continue
        if not _run_grid(local[fn_name], grid):
            killed += 1
    return {"falsifiable": killed > 0, "mutants": n, "killed": killed}


# ----------------------------------------------------------------------------- held-out

def held_out(name: str, src: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"survives": False, "test": "stem_held_out_v1"}
    try:
        from society.benchmarks.lemma_microbench import run as run_lemma

        lemma = run_lemma()
        out["hard_pass"] = lemma.get("n_hard_pass")
        if not (bool(lemma.get("ok")) and int(lemma.get("n_hard_pass") or 0) > 0):
            out["reason"] = "hard_tier_not_green"
            return out
        ns, tree = _load(src)
        catalog = {e[0]: e for e in ns.get("STEM_CHECKS", [])}
        bench = {}
        for nm, fn, enabled in ns.get("STEM_CHECKS", []):
            if enabled:
                try:
                    bench[nm] = bool(fn())
                except Exception:  # noqa: BLE001
                    bench[nm] = False
        out["stem_n_pass"] = sum(bench.values())
        if not bench or not all(bench.values()):
            out["reason"] = "stem_bench_not_green"
            return out
        if name not in catalog:
            out["reason"] = "not_in_stem_catalog"
            return out
        try:
            window_ok = bool(catalog[name][1]())
        except Exception:  # noqa: BLE001
            window_ok = False
        if not window_ok:
            out["reason"] = "coded_window_fails"
            return out
        if name not in HELD_OUT_GRIDS:
            out["reason"] = "no_registered_harder_instance_fail_closed"
            return out
        fn_name, grid = HELD_OUT_GRIDS[name]
        fn = ns.get(fn_name)
        out["n_held_out"] = len(grid)
        if fn is None or not _run_grid(fn, grid):
            out["reason"] = "harder_instance_fails"
            return out
        fz = falsifiable(fn_name, grid, ns, tree)
        out["mutants"], out["mutants_killed"] = fz["mutants"], fz["killed"]
        if not fz["falsifiable"]:
            out["reason"] = "harder_instance_not_falsifiable"
            return out
        out["survives"] = True
        out["reason"] = "stem_harder_instance_green"
        return out
    except Exception as exc:  # noqa: BLE001
        out["reason"] = f"error:{exc}"
        return out


# ----------------------------------------------------------------------------- triviality

class _Unanalyzable(Exception):
    pass


def _sym():
    import sympy
    return sympy


def _rat(v: Any):
    sp = _sym()
    if isinstance(v, bool):
        raise _Unanalyzable("bool")
    if isinstance(v, int):
        return sp.Integer(v)
    if isinstance(v, float):
        return sp.Rational(repr(v))
    raise _Unanalyzable("const")


_MATH = {"sqrt": "sqrt", "sin": "sin", "cos": "cos", "tan": "tan", "exp": "exp", "log": "log",
         "tanh": "tanh", "atanh": "atanh", "hypot": None, "radians": None}


def _ev(node: ast.AST, env: dict[str, Any]):
    sp = _sym()
    if isinstance(node, ast.Constant):
        return _rat(node.value)
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        raise _Unanalyzable(node.id)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _ev(node.operand, env)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp):
        a, b = _ev(node.left, env), _ev(node.right, env)
        ops = {ast.Add: lambda: a + b, ast.Sub: lambda: a - b, ast.Mult: lambda: a * b,
               ast.Div: lambda: a / b, ast.Pow: lambda: a ** b}
        if type(node.op) not in ops:
            raise _Unanalyzable("op")
        return ops[type(node.op)]()
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "math":
        if node.attr == "pi":
            return sp.pi
        raise _Unanalyzable(node.attr)
    if isinstance(node, ast.IfExp):
        # ``expr if guard else degenerate``: the generic case is the body branch.
        return _ev(node.body, env)
    if isinstance(node, ast.Call) and not node.keywords:
        args = [_ev(a, env) for a in node.args]
        f = node.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "math":
            if f.attr == "radians":
                return args[0] * sp.pi / 180
            if f.attr == "hypot":
                return sp.sqrt(sum(a * a for a in args))
            if _MATH.get(f.attr):
                return getattr(sp, _MATH[f.attr])(*args)
            raise _Unanalyzable(f.attr)
        if isinstance(f, ast.Name) and f.id == "abs" and len(args) == 1:
            return sp.Abs(args[0])
        if isinstance(f, ast.Name) and isinstance(env.get(f.id), tuple) and env[f.id][0] == "lambda":
            _, lam, closure = env[f.id]
            inner = dict(closure)
            for p, a in zip(lam.args.args, args):
                inner[p.arg] = a
            return _ev(lam.body, inner)
        raise _Unanalyzable("call")
    raise _Unanalyzable(type(node).__name__)


def _has_tolerance(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Constant) and isinstance(n.value, float) and 0 < n.value < 1e-3
               for n in ast.walk(node))


def _abs_arg(node: ast.AST) -> ast.AST | None:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "abs" \
            and len(node.args) == 1:
        return node.args[0]
    return None


def _claims(node: ast.AST, op: type) -> list[ast.AST] | None:
    """Equality claims ``abs(X) <op> tol`` in a (conjunctive) condition; None if unanalyzable.
    Inequality bounds (``abs(w) < 1``) assert no equality and are skipped."""
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And) and op is ast.Lt:
        out: list[ast.AST] = []
        for v in node.values:
            c = _claims(v, op)
            if c is None:
                return None
            out += c
        return out
    if isinstance(node, ast.Name):
        return [("name", node.id)]
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], op):
        arg = _abs_arg(node.left)
        if arg is not None:
            return [arg] if _has_tolerance(node.comparators[0]) else []
    return None


def _resolve(found: list, env: dict[str, Any]) -> list:
    """Evaluate claim nodes in the environment where they are asserted."""
    out = []
    for c in found:
        if isinstance(c, tuple) and c[0] == "name":
            v = env.get(c[1])
            if not (isinstance(v, tuple) and v[0] == "claims"):
                raise _Unanalyzable("claim_name")
            out += v[1]
        else:
            out.append(_ev(c, env))
    return out


def _exec_block(stmts: list[ast.stmt], env: dict[str, Any], claims: list) -> bool:
    """Symbolically run a block; append each asserted ``X == 0`` to ``claims``. True on return."""
    sp = _sym()
    for st in stmts:
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant):
            continue
        if isinstance(st, ast.Assign) and len(st.targets) == 1:
            tgt, val = st.targets[0], st.value
            if isinstance(tgt, ast.Name) and isinstance(val, ast.Lambda):
                env[tgt.id] = ("lambda", val, dict(env))
            elif isinstance(tgt, ast.Name):
                v = _claims(val, ast.Lt) if isinstance(val, (ast.Compare, ast.BoolOp)) else None
                if v is not None:
                    env[tgt.id] = ("claims", _resolve(v, env))
                else:
                    env[tgt.id] = _ev(val, env)
            elif isinstance(tgt, ast.Tuple) and isinstance(val, ast.Tuple) and len(tgt.elts) == len(val.elts):
                vals = [_ev(v, env) for v in val.elts]
                for t, v in zip(tgt.elts, vals):
                    if not isinstance(t, ast.Name):
                        raise _Unanalyzable("target")
                    env[t.id] = v
            else:
                raise _Unanalyzable("assign")
            continue
        if isinstance(st, ast.If) and not st.orelse and len(st.body) == 1 and isinstance(st.body[0], ast.Return) \
                and isinstance(st.body[0].value, ast.Constant) and isinstance(st.body[0].value.value, bool):
            if st.body[0].value.value is True:
                continue  # domain guard
            c = _claims(st.test, ast.Gt)
            if c is None:
                raise _Unanalyzable("if")
            claims.extend(_resolve(c, env))
            continue
        if isinstance(st, ast.For) and isinstance(st.target, ast.Name) and not st.orelse:
            inner = dict(env)
            inner[st.target.id] = sp.Symbol(st.target.id, integer=True, nonnegative=True)
            if _exec_block(st.body, inner, claims):
                raise _Unanalyzable("return_in_loop")
            continue
        if isinstance(st, ast.Return) and st.value is not None:
            if isinstance(st.value, ast.Constant) and st.value.value is True:
                return True
            c = _claims(st.value, ast.Lt)
            if c is None:
                raise _Unanalyzable("return")
            claims.extend(_resolve(c, env))
            return True
        raise _Unanalyzable(type(st).__name__)
    return False


def _is_zero(expr) -> bool:
    sp = _sym()
    for f in (lambda e: e, sp.expand_trig, lambda e: e.rewrite(sp.exp)):
        try:
            if sp.simplify(f(expr)) == 0:
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def triviality(name: str, src: str | None = None) -> dict[str, Any]:
    """{'trivial': bool, 'reason': str, ...}. Unanalyzable → not trivial (other gates still apply)."""
    out: dict[str, Any] = {"trivial": False, "reason": "", "test": "stem_triviality_v1"}
    try:
        if name not in HELD_OUT_GRIDS:
            out["reason"] = "no_registered_check"
            return out
        fn_name = HELD_OUT_GRIDS[name][0]
        _, tree = _load(src)
        fn_node = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == fn_name), None)
        if fn_node is None:
            out["reason"] = "no_check_function"
            return out
        sp = _sym()
        for assumptions in ({"real": True}, {"positive": True}):
            env = {a.arg: sp.Symbol(a.arg, **assumptions) for a in fn_node.args.args}
            claims: list = []
            try:
                _exec_block(fn_node.body, env, claims)
            except _Unanalyzable as exc:
                out["reason"] = f"independent_route_or_unanalyzable:{exc}"
                return out
            exprs = claims
            if not exprs:
                out["reason"] = "no_equality_claim"
                return out
            out["n_claims"] = len(exprs)
            if all(_is_zero(e) for e in exprs):
                out["trivial"] = True
                out["reason"] = "stem_symbolic_tautology"
                out["domain"] = next(iter(assumptions))
                return out
        out["reason"] = "not_a_tautology"
        return out
    except Exception as exc:  # noqa: BLE001
        out["reason"] = f"independent_route_or_unanalyzable:{exc}"
        return out
