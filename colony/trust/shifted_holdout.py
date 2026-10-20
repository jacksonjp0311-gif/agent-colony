"""Spark S1 (2026-10-11): a real held-out window for the Oracle on hard_enable.

Observed failure (dev ablation dev_v0): with the Challenger off, the Oracle passed every
window-only false claim (Euler n^2+n+41, small Mersenne, base-2 Fermat, 'no abundant < 12')
because its "held-out" for hard_enable was just "the same enabled checks are green".

Re-run supported entries on a disjoint shifted window, preserving literal range steps,
with a process time budget. Unsupported or unexecuted checks and timeouts are not tested
and cannot support survival. A pass is finite-window evidence, never universal proof.
Separate from the Challenger's probes (it does not import colony.challenger).
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

BUDGET_S = 2.0


def _lit(node: ast.AST) -> tuple[int, int, int] | None:
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "range" and not node.keywords):
        return None
    vals = []
    for arg in node.args:
        try:
            value = ast.literal_eval(arg)
        except (ValueError, TypeError):
            return None
        if type(value) is not int:
            return None
        vals.append(value)
    if len(vals) == 1:
        return 0, vals[0], 1
    if len(vals) == 2:
        return vals[0], vals[1], 1
    if len(vals) == 3 and vals[2] != 0:
        return tuple(vals)
    return None


class _Shift(ast.NodeTransformer):
    def __init__(self) -> None:
        self.n = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        r = _lit(node)
        if r:
            a, b, step = r
            count = max(0, (b - a + step - (1 if step > 0 else -1)) // step)
            if count:
                start = a + count * step
                self.n += 1
                return ast.Call(func=ast.Name("_oracle_shifted_range", ast.Load()), args=[
                    ast.Constant(start), ast.Constant(start + count * step), ast.Constant(step)], keywords=[])
        return node


def _entry_expr(tree: ast.Module, name: str) -> ast.AST | None:
    fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Tuple) and len(node.elts) >= 3 and isinstance(node.elts[0], ast.Constant) \
                and node.elts[0].value == name:
            ref = node.elts[1]
            if isinstance(ref, ast.Lambda):
                return ref.body
            if isinstance(ref, ast.Name) and ref.id in fns and not fns[ref.id].args.args:
                body = [s for s in fns[ref.id].body
                        if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                                and isinstance(s.value.value, str))]
                if len(body) != 1:
                    return None
                rets = [s for s in body if isinstance(s, ast.Return)]
                if len(rets) == 1 and rets[0].value is not None:
                    return rets[0].value
    return None


def shifted_window_check(src_path: Path, name: str, *, budget_s: float = BUDGET_S) -> dict[str, Any]:
    try:
        src = src_path.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": "not_tested", "applied": False, "reason": f"shift_parse_error:{type(exc).__name__}"}
    expr = _entry_expr(tree, name)
    if expr is None:
        return {"ok": False, "status": "not_tested", "reason": "shift_not_applicable(entry_shape)", "applied": False}
    if any(isinstance(node, ast.comprehension) and node.ifs for node in ast.walk(expr)):
        # A shifted range can execute while every value is filtered out, making
        # all(...) vacuously true without evaluating its predicate.
        return {"ok": False, "status": "not_tested",
                "reason": "shift_not_applicable(filtered_comprehension)", "applied": False}
    sh = _Shift()
    new = sh.visit(ast.parse(ast.unparse(expr), mode="eval"))
    if sh.n == 0:
        return {"ok": False, "status": "not_tested", "reason": "shift_not_applicable(no_literal_range)", "applied": False}
    ast.fix_missing_locations(new)
    t0 = time.monotonic()
    # A child process bounds both module initialization and the check on Windows too.
    worker = """
import json, sys
p = json.load(sys.stdin)
ns = {'__name__': 'colony_oracle_shift'}
exec(p['source'], ns)
probes = 0
def shifted_range(*args):
    global probes
    for value in range(*args):
        probes += 1
        yield value
ns['_oracle_shifted_range'] = shifted_range
ok = bool(eval(p['expr'], ns))
print(json.dumps({'ok': ok, 'probes': probes}))
"""
    try:
        run = subprocess.run([sys.executable, "-c", worker], input=json.dumps({
            "source": src, "expr": ast.unparse(new)}), capture_output=True, text=True,
            timeout=budget_s, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if run.returncode:
            raise ValueError("shift worker failed")
        observed = json.loads(run.stdout.splitlines()[-1])
        probes = observed["probes"]
        val = observed["ok"] is True and probes > 0
        res = {"ok": val, "status": "pass" if val else "fail",
               "reason": "shift_window_pass" if val else "shift_window_counterexample",
               "applied": probes > 0, "ranges_shifted": sh.n, "probes": probes}
        if probes == 0:
            res.update(status="not_tested", reason="shift_not_executed")
    except subprocess.TimeoutExpired:
        res = {"ok": False, "status": "not_tested", "reason": "shift_window_inconclusive_timeout(fail_closed)", "applied": False}
    except Exception as exc:  # noqa: BLE001
        res = {"ok": False, "status": "fail", "reason": f"shift_window_error:{type(exc).__name__}", "applied": True}
    res["seconds"] = round(time.monotonic() - t0, 3)
    res["window_expr"] = ast.unparse(new)[:240]
    res["scope"] = "finite_shifted_window_only_not_universal_proof"
    return res
