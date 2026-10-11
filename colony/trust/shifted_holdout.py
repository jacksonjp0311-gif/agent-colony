"""Spark S1 (2026-10-11): a real held-out window for the Oracle on hard_enable.

Observed failure (dev ablation dev_v0): with the Challenger off, the Oracle passed every
window-only false claim (Euler n^2+n+41, small Mersenne, base-2 Fermat, 'no abundant < 12')
because its "held-out" for hard_enable was just "the same enabled checks are green".

Fix: re-run the enabled entry on a DISJOINT shifted window — every literal ``range(a, b)``
in the check becomes ``range(b, b + (b - a))`` — with a time budget. A failure or exception
kills; a timeout is fail-closed (kill, labelled inconclusive). Pure in-loop check, separate
from the Challenger's probes (it does not import colony.challenger).
"""
from __future__ import annotations

import ast
import signal
import threading
import time
from pathlib import Path
from typing import Any

BUDGET_S = 2.0


class _Timeout(Exception):
    pass


def _lit(node: ast.AST) -> tuple[int, int] | None:
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "range"):
        return None
    vals = []
    for a in node.args:
        if isinstance(a, ast.Constant) and isinstance(a.value, int):
            vals.append(a.value)
        elif isinstance(a, ast.UnaryOp) and isinstance(a.op, ast.USub) and isinstance(a.operand, ast.Constant):
            vals.append(-a.operand.value)
        else:
            return None
    if len(vals) == 1:
        return (0, vals[0])
    if len(vals) == 2:
        return (vals[0], vals[1])
    return None  # stepped ranges: leave alone


class _Shift(ast.NodeTransformer):
    def __init__(self) -> None:
        self.n = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        r = _lit(node)
        if r and r[1] > r[0]:
            a, b = r
            self.n += 1
            return ast.Call(func=ast.Name("range", ast.Load()),
                            args=[ast.Constant(b), ast.Constant(b + (b - a))], keywords=[])
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
                body = fns[ref.id].body
                rets = [s for s in body if isinstance(s, ast.Return)]
                if len(rets) == 1 and rets[0].value is not None:
                    return rets[0].value
    return None


def shifted_window_check(src_path: Path, name: str, *, budget_s: float = BUDGET_S) -> dict[str, Any]:
    try:
        src = src_path.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"shift_parse_error:{type(exc).__name__}"}
    expr = _entry_expr(tree, name)
    if expr is None:
        return {"ok": True, "reason": "shift_not_applicable(entry_shape)", "applied": False}
    sh = _Shift()
    new = sh.visit(ast.parse(ast.unparse(expr), mode="eval"))
    if sh.n == 0:
        return {"ok": True, "reason": "shift_not_applicable(no_literal_range)", "applied": False}
    ast.fix_missing_locations(new)
    ns: dict[str, Any] = {"__name__": "colony_oracle_shift"}
    use_alarm = threading.current_thread() is threading.main_thread() and hasattr(signal, "setitimer")
    t0 = time.monotonic()

    def _raise(_s: int, _f: Any) -> None:
        raise _Timeout()

    old = signal.signal(signal.SIGALRM, _raise) if use_alarm else None
    try:
        exec(compile(tree, "<oracle-shift-artifact>", "exec"), ns)  # noqa: S102 — the colony's own artifact
        if use_alarm:
            signal.setitimer(signal.ITIMER_REAL, budget_s)
        val = bool(eval(compile(new, "<oracle-shift>", "eval"), ns))  # noqa: S307
        res = {"ok": val, "reason": "shift_window_pass" if val else "shift_window_counterexample",
               "applied": True, "ranges_shifted": sh.n}
    except _Timeout:
        res = {"ok": False, "reason": "shift_window_inconclusive_timeout(fail_closed)", "applied": True}
    except Exception as exc:  # noqa: BLE001
        res = {"ok": False, "reason": f"shift_window_error:{type(exc).__name__}", "applied": True}
    finally:
        if use_alarm:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old)
    res["seconds"] = round(time.monotonic() - t0, 3)
    res["window_expr"] = ast.unparse(new)[:240]
    return res
