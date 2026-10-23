"""Spark S1 (2026-10-11): a real held-out window for the Oracle on hard_enable.

Observed failure (dev ablation dev_v0): with the Challenger off, the Oracle passed every
window-only false claim (Euler n^2+n+41, small Mersenne, base-2 Fermat, 'no abundant < 12')
because its "held-out" for hard_enable was just "the same enabled checks are green".

Re-run supported entries on a disjoint shifted window, preserving literal range steps,
with a process time budget. Unsupported or unexecuted checks and timeouts are not tested
and cannot support survival. A pass is finite-window evidence, never universal proof.
Separate from the Challenger's probes (it does not import colony.challenger).

2026-10-23 (James-approved): authored checks iterate literal window tuples
(``for a, b in [(41, 2026), ...]``) passed as bounds to a bridge call, not range().
Those loops are now shifted onto the next disjoint stretch, capped at the data the
bridge can evaluate (frontier tables). If there is no room, the check stays
``not_tested`` (no_data_headroom) and cannot survive. A shifted frontier window
that falls off the tables or checks nothing is ``not_tested``, never a pass.
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
MIN_WINDOW = 30  # narrowest shifted tuple window (3 windows -> 90, the authoring minimum)


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


def _window_list(node: ast.AST) -> list[tuple[int, int]] | None:
    """A literal, ascending, disjoint list of (lo, hi) int pairs, else None."""
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    try:
        v = ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return None
    if not v or not all(isinstance(w, tuple) and len(w) == 2 and all(type(x) is int for x in w)
                        and w[0] <= w[1] for w in v):
        return None
    if any(v[i][1] > v[i + 1][0] for i in range(len(v) - 1)):
        return None
    return [tuple(w) for w in v]


def _bound_calls(elt: ast.AST, a: str, b: str) -> list[ast.Call]:
    """Calls that take the loop names a, b as consecutive positional arguments (window bounds)."""
    out = []
    for node in ast.walk(elt):
        if isinstance(node, ast.Call):
            args = node.args
            if any(isinstance(x, ast.Name) and x.id == a and isinstance(y, ast.Name) and y.id == b
                   for x, y in zip(args, args[1:])):
                out.append(node)
    return out


def _data_limit(call: ast.Call, want: int) -> int | None:
    """Largest bound the call's data source supports (<= want); None = computed on demand, no table."""
    fn = call.func.id if isinstance(call.func, ast.Name) else None
    if fn == "frontier_holds" and call.args:
        try:
            claim = ast.literal_eval(call.args[0])
            from colony.frontier_checks import evaluable_hi
            return int(evaluable_hi(claim, want))
        except Exception:  # noqa: BLE001
            return 0  # cannot tell what data exists: treat as none (fail closed to not_tested)
    return None


class _ShiftWindows(ast.NodeTransformer):
    """Shift ``for a, b in [(lo, hi), ...]`` loops onto [hi+1, hi+span] within available data."""

    def __init__(self) -> None:
        self.n = 0
        self.no_headroom: list[dict[str, Any]] = []
        self.shifted: list[dict[str, Any]] = []

    def _comp(self, node: ast.AST) -> ast.AST:
        self.generic_visit(node)
        if len(node.generators) != 1:
            return node
        gen = node.generators[0]
        t = gen.target
        if not (isinstance(t, ast.Tuple) and len(t.elts) == 2
                and all(isinstance(e, ast.Name) for e in t.elts)):
            return node
        wins = _window_list(gen.iter)
        if wins is None:
            return node
        a, b = t.elts[0].id, t.elts[1].id
        calls = _bound_calls(node.elt, a, b)
        if not calls:
            return node  # tuples are (point, value) pairs or similar, not window bounds
        lo, hi, k = wins[0][0], wins[-1][1], len(wins)
        span = hi - lo + 1
        end = hi + span
        limits = [lim for lim in (_data_limit(c, end) for c in calls) if lim is not None]
        if limits:
            end = min([end] + limits)
        room = end - hi
        if room < k * MIN_WINDOW:
            self.no_headroom.append({"windows": wins, "data_end": end, "headroom": max(0, room)})
            return node
        step = room // k
        new = [(hi + 1 + i * step, hi + (i + 1) * step if i < k - 1 else end) for i in range(k)]
        self.n += 1
        self.shifted.append({"from": wins, "to": new})
        gen.iter = ast.Call(func=ast.Name("_oracle_shifted_windows", ast.Load()),
                            args=[ast.parse(repr(new), mode="eval").body], keywords=[])
        return node

    visit_GeneratorExp = visit_ListComp = visit_SetComp = _comp


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
    sw = _ShiftWindows()
    new = sw.visit(new)
    if sw.no_headroom:
        return {"ok": False, "status": "not_tested", "reason": "shift_not_applicable(no_data_headroom)",
                "applied": False, "no_headroom": sw.no_headroom}
    if sh.n == 0 and sw.n == 0:
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
def shifted_windows(ws):
    global probes
    for w in ws:
        probes += 1
        yield w
ns['_oracle_shifted_range'] = shifted_range
ns['_oracle_shifted_windows'] = shifted_windows
zeros = []
if callable(ns.get('frontier_holds')):
    _fh = ns['frontier_holds']
    def _frontier_holds(claim, a, b):
        c = _fh(claim, a, b)
        if not c:
            from colony import frontier_conjectures as _f
            zeros.append(_f.holds_on_detail(claim, int(a), int(b)))
        return c
    ns['frontier_holds'] = _frontier_holds
ok = bool(eval(p['expr'], ns))
print(json.dumps({'ok': ok, 'probes': probes, 'zeros': zeros}))
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
        if sw.n:
            res.update(windows_shifted=sw.n, shifted=sw.shifted)
        zeros = observed.get("zeros") or []
        if not val and zeros:
            # A frontier bridge returned 0: only a real counterexample is a failure.
            bad = [z for z in zeros if z.get("reason") == "counterexample"]
            if bad:
                res.update(counterexample=bad[0])
            else:
                res.update(ok=False, status="not_tested", applied=False,
                           reason=f"shift_window_untestable({zeros[0].get('reason')})", zeros=zeros[:3])
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
