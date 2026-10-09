"""Challenger — the colony's internal self-challenge step (adversarial, block-only).

Before a colony-authored check / lemma mutation, a hard-checked claim, or a frontier result is
submitted to the Oracle (or the frontier's independent recheck), the Challenger role tries to
break it with its own probes:

* boundary inputs — the domain edge established by the catalog (0, 1, small n; negatives only
  where an enabled catalog entry already exercises them), plus the cells just outside the tested
  window;
* far ranges well beyond the tested window;
* random sampling with a fixed per-cycle seed (reproducible from ``cycle_id`` + target);
* type / overflow edges — non-bool results, arithmetic/recursion/overflow errors on in-domain
  inputs;
* triviality for identities — empty ranges, both sides constant, sides that are the same
  polynomial (a ring tautology: true for every input by algebra, so a finite check adds
  nothing), or a component that only ever returns through a ``return True`` guard.

The Challenger can only BLOCK: it withholds the submission and writes a ``self_challenge``
lesson naming the counterexample / edge. It never approves, enables, scores or authorizes
anything — passing the Challenger just means "not withheld"; the Oracle (unchanged) still
decides. Every submission carries a short machine-generated ``why_believe`` note (component
lemmas + ranges tested + Challenger summary) built only from the colony's own AST / results —
never from feed text.

The name follows the Challenger teammate concept (naming only; no messaging).
"""
from __future__ import annotations

import ast
import hashlib
import json
import random
import re
import signal
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "commons" / "self_challenge.jsonl"
SYSTEM = ROOT / "society" / "systems" / "self_challenger.json"

ROLE = "challenger"
CAN_APPROVE = False  # structural: the Challenger has no approve path anywhere
DESK_BUDGET_S = 3.0
CLAIM_BUDGET_S = 1.5
FRONTIER_BUDGET_S = 2.0
PROBE_TIMEOUT_S = 0.5  # one element evaluation; a slow probe is inconclusive, never a block
FAR_WIDTH = 3
FAR_CAP = 20_000
SAMPLES = 10
EDGE_ERRORS = (ArithmeticError, RecursionError, ValueError, TypeError, IndexError, KeyError)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cycle_seed(cycle_id: str, target: str) -> int:
    return int(hashlib.sha256(f"{cycle_id}|{target}".encode()).hexdigest()[:12], 16)


# ----------------------------------------------------------------------------- report

@dataclass
class ChallengeReport:
    target: str
    kind: str  # lemma_mutation | claim | frontier
    source: str = ""
    cycle_id: str = ""
    blocked: bool = False
    reason: str = ""
    counterexample: dict[str, Any] | None = None
    probes: dict[str, int] = field(default_factory=lambda: {"boundary": 0, "far": 0, "sample": 0, "edge": 0})
    trivial: dict[str, Any] = field(default_factory=dict)
    components: list[str] = field(default_factory=list)
    ranges_tested: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    seed: int = 0
    seconds: float = 0.0
    budget_s: float = 0.0
    budget_hit: bool = False
    inconclusive: int = 0

    @property
    def approved(self) -> bool:  # never: the Challenger cannot approve
        return False

    def block(self, reason: str, counterexample: dict[str, Any] | None = None) -> None:
        if not self.blocked:  # first concrete break wins
            self.blocked = True
            self.reason = reason
            self.counterexample = counterexample

    def n_probes(self) -> int:
        return sum(self.probes.values())

    def summary(self) -> str:
        p = self.probes
        head = (f"BLOCKED ({self.reason})" if self.blocked else "not broken")
        return (f"Challenger {head}: {self.n_probes()} probes (boundary {p['boundary']}, far {p['far']}, "
                f"sample {p['sample']}, edge {p['edge']}; seed {self.seed}) in {self.seconds:.2f}s"
                + (" [budget hit]" if self.budget_hit else "")
                + (f" [{self.inconclusive} inconclusive]" if self.inconclusive else ""))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.update({"approved": False, "can_approve": CAN_APPROVE, "summary": self.summary()})
        return d


def why_believe(report: ChallengeReport, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Short machine-generated 'why I believe this' note (no free text from feeds)."""
    comps = report.components[:8]
    rng = report.ranges_tested
    text = (f"Believe `{report.target}`: components {', '.join(comps) or '(none)'}; "
            f"ranges tested {json.dumps(rng, sort_keys=True)[:240]}; {report.summary()}.")
    note = {"components": comps, "ranges_tested": rng, "challenger": report.summary(),
            "challenger_blocked": report.blocked, "seed": report.seed, "text": text,
            "generated_by": "colony.challenger", "free_text_from_feeds": False}
    if extra:
        note.update({k: v for k, v in extra.items() if isinstance(v, (int, float, str, bool, list, dict))})
    return note


# ----------------------------------------------------------------------------- budget / timer

class _ProbeTimeout(Exception):
    pass


class Budget:
    def __init__(self, seconds: float) -> None:
        self.seconds = float(seconds)
        self.t0 = time.monotonic()

    def left(self) -> float:
        return self.seconds - (time.monotonic() - self.t0)

    def out(self) -> bool:
        return self.left() <= 0

    def elapsed(self) -> float:
        return time.monotonic() - self.t0


@contextmanager
def _timer(seconds: float) -> Iterator[None]:
    """Per-evaluation alarm (main thread only); elsewhere rely on the budget checks."""
    use = threading.current_thread() is threading.main_thread() and hasattr(signal, "setitimer")
    if not use or seconds <= 0:
        yield
        return

    def _raise(_sig: int, _frm: Any) -> None:
        raise _ProbeTimeout()

    old = signal.signal(signal.SIGALRM, _raise)
    signal.setitimer(signal.ITIMER_REAL, max(0.01, seconds))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


# ----------------------------------------------------------------------------- polynomial normal form

def _poly(node: ast.AST, vars_: set[str]) -> dict[tuple, int] | None:
    """Exact normal form of an integer polynomial expression in ``vars_`` (None if not one)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return {(): node.value} if node.value else {}
    if isinstance(node, ast.Name) and node.id in vars_:
        return {((node.id, 1),): 1}
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        p = _poly(node.operand, vars_)
        if p is None:
            return None
        return {k: -v for k, v in p.items()} if isinstance(node.op, ast.USub) else p
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Pow):
            if not (isinstance(node.right, ast.Constant) and isinstance(node.right.value, int)
                    and 0 <= node.right.value <= 12):
                return None
            base = _poly(node.left, vars_)
            if base is None:
                return None
            out: dict[tuple, int] = {(): 1}
            for _ in range(node.right.value):
                out = _pmul(out, base)
            return out
        a, b = _poly(node.left, vars_), _poly(node.right, vars_)
        if a is None or b is None:
            return None
        if isinstance(node.op, ast.Add):
            return _padd(a, b, 1)
        if isinstance(node.op, ast.Sub):
            return _padd(a, b, -1)
        if isinstance(node.op, ast.Mult):
            return _pmul(a, b)
    return None


def _padd(a: dict, b: dict, s: int) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, 0) + s * v
    return {k: v for k, v in out.items() if v}


def _pmul(a: dict, b: dict) -> dict:
    out: dict[tuple, int] = {}
    for ka, va in a.items():
        for kb, vb in b.items():
            pw: dict[str, int] = {}
            for name, e in ka + kb:
                pw[name] = pw.get(name, 0) + e
            k = tuple(sorted(pw.items()))
            out[k] = out.get(k, 0) + va * vb
    return {k: v for k, v in out.items() if v}


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _conjuncts(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        out: list[ast.AST] = []
        for v in node.values:
            out += _conjuncts(v)
        return out
    return [node]


def _eq_sides(node: ast.AST) -> tuple[ast.AST, ast.AST] | None:
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
        return node.left, node.comparators[0]
    return None


def identity_trivial(node: ast.AST, vars_: set[str]) -> str:
    """Why an identity expression is trivially true ('' if it is not)."""
    if isinstance(node, ast.Constant):
        return "constant_expression" if node.value is True else ""
    sides = _eq_sides(node)
    if sides is None:
        return ""
    a, b = sides
    if ast.dump(a) == ast.dump(b):
        return "identical_sides"
    if not (_names(a) & vars_) and not (_names(b) & vars_):
        return "both_sides_constant"
    pa, pb = _poly(a, vars_), _poly(b, vars_)
    if pa is not None and pb is not None and pa == pb:
        return "ring_tautology"
    return ""


# ----------------------------------------------------------------------------- lemma entries

def _catalog_entries(tree: ast.Module) -> list[tuple[str, ast.AST, bool | None]]:
    from colony.authoring import _entries
    return _entries(tree)


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def _return_expr(fn: ast.FunctionDef) -> ast.AST | None:
    body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(getattr(s, "value", None), ast.Constant))]
    if len(body) == 1 and isinstance(body[0], ast.Return) and body[0].value is not None:
        return body[0].value
    return None


def _entry_expr(node: ast.AST, fns: dict[str, ast.FunctionDef]) -> ast.AST | None:
    if isinstance(node, ast.Lambda):
        return node.body
    if isinstance(node, ast.Name) and node.id in fns and not fns[node.id].args.args:
        return _return_expr(fns[node.id])
    return None


def _lit_range(node: ast.AST) -> tuple[int, int] | None:
    """range(a, b) / range(b) with int literals → (a, b-1)."""
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
        return 0, vals[0] - 1
    if len(vals) == 2:
        return vals[0], vals[1] - 1
    return None


def _gens(expr: ast.AST) -> list[ast.GeneratorExp]:
    return [n for n in ast.walk(expr) if isinstance(n, ast.GeneratorExp)
            and all(isinstance(c.target, ast.Name) for c in n.generators)]


def _called_checks(expr: ast.AST) -> list[str]:
    out = []
    for n in ast.walk(expr):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id.startswith("check_"):
            out.append(n.func.id)
    return list(dict.fromkeys(out))


def _domain_map(tree: ast.Module, include: str) -> dict[tuple[str, int], int]:
    """(component, arg position) → smallest literal start any enabled entry (or ``include``) uses."""
    fns = _functions(tree)
    dom: dict[tuple[str, int], int] = {}
    for name, node, enabled in _catalog_entries(tree):
        if not enabled and name != include:
            continue
        expr = _entry_expr(node, fns)
        if expr is None:
            continue
        for g in _gens(expr):
            lo_of = {c.target.id: r[0] for c in g.generators if (r := _lit_range(c.iter))}
            for call in ast.walk(g.elt):
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
                    for i, a in enumerate(call.args):
                        if isinstance(a, ast.Name) and a.id in lo_of:
                            k = (call.func.id, i)
                            dom[k] = min(dom.get(k, lo_of[a.id]), lo_of[a.id])
    return dom


def _var_domain(g: ast.GeneratorExp, var: str, own_lo: int, dom: dict[tuple[str, int], int]) -> int:
    lows = []
    for call in ast.walk(g.elt):
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
            for i, a in enumerate(call.args):
                if isinstance(a, ast.Name) and a.id == var and (call.func.id, i) in dom:
                    lows.append(dom[(call.func.id, i)])
    # every place var feeds must stay inside the domain an enabled entry already established
    return min(max(lows), own_lo) if lows else own_lo


def _boundary_values(L: int, lo: int, hi: int) -> list[int]:
    vals = {L, L + 1, L + 2, lo - 1, lo, hi, hi + 1}
    vals |= {x for x in (-2, -1, 0, 1, 2)}
    return sorted(v for v in vals if v >= L)


def _far_values(L: int, hi: int) -> list[int]:
    base = max(abs(hi), 4)
    starts = sorted({min(FAR_CAP, 2 * base + 1), min(FAR_CAP, 4 * base + 3), min(FAR_CAP, 10 * base + 7)})
    vals = [s + i for s in starts for i in range(FAR_WIDTH)]
    if L < 0:  # domain extends to negatives: probe far negatives too
        vals += [-v for v in vals]
    return vals


def _probe_gen(g: ast.GeneratorExp, overrides: dict[int, list[int]]) -> ast.Expression:
    comps = []
    for i, c in enumerate(g.generators):
        it = c.iter
        if i in overrides:
            it = ast.Tuple(elts=[ast.Constant(v) for v in overrides[i]], ctx=ast.Load())
        comps.append(ast.comprehension(target=c.target, iter=it, ifs=c.ifs, is_async=0))
    vars_ = [c.target.id for c in g.generators]
    elt = ast.Tuple(elts=[ast.Tuple(elts=[ast.Name(v, ast.Load()) for v in vars_], ctx=ast.Load()), g.elt],
                    ctx=ast.Load())
    expr = ast.Expression(body=ast.GeneratorExp(elt=elt, generators=comps))
    return ast.fix_missing_locations(expr)


def _run_probe(rep: ChallengeReport, family: str, g: ast.GeneratorExp, overrides: dict[int, list[int]],
               ns: dict[str, Any], budget: Budget, vars_: list[str]) -> None:
    if rep.blocked or budget.out():
        rep.budget_hit = rep.budget_hit or budget.out()
        return
    code = compile(_probe_gen(g, overrides), "<challenger>", "eval")
    it = eval(code, ns)  # noqa: S307 — the colony's own artifact AST, never feed text
    while True:
        if budget.out():
            rep.budget_hit = True
            return
        try:
            with _timer(min(PROBE_TIMEOUT_S, max(0.01, budget.left()))):
                binding, val = next(it)
        except StopIteration:
            return
        except _ProbeTimeout:
            rep.inconclusive += 1
            return
        except EDGE_ERRORS as exc:
            rep.probes["edge"] += 1
            rep.block("edge_error", {"probe": family, "error": f"{type(exc).__name__}: {str(exc)[:80]}",
                                     "range_override": {vars_[i]: v[:6] for i, v in overrides.items()}})
            return
        rep.probes[family] += 1
        b = dict(zip(vars_, binding))
        if not isinstance(val, bool):
            rep.probes["edge"] += 1
            rep.block("type_edge_non_bool", {"probe": family, "inputs": b, "value": repr(val)[:60]})
            return
        if val is False:
            rep.block(f"counterexample_{family}", {"probe": family, "inputs": b})
            return


def _instrumented_ns(tree: ast.Module, ns: dict[str, Any], comps: list[str]) -> tuple[dict[str, Any], list[int]]:
    """Copy of ``ns`` whose component functions count hits on literal ``return True`` guards."""
    hits = [0]
    ns2 = dict(ns)
    ns2["__challenger_guard__"] = lambda: (hits.__setitem__(0, hits[0] + 1), True)[1]
    fns = _functions(tree)
    body = []
    for name in comps:
        fn = fns.get(name)
        if fn is None:
            continue
        fn2 = ast.parse(ast.unparse(fn)).body[0]

        # A guard is a top-level `if cond: return True` that precedes the real computation; the
        # final `return True` of a loop that survived every test is the success path, not a guard.
        for stmt in fn2.body[:-1]:
            if isinstance(stmt, ast.If):
                for j, inner in enumerate(stmt.body):
                    if (isinstance(inner, ast.Return) and isinstance(inner.value, ast.Constant)
                            and inner.value.value is True):
                        stmt.body[j] = ast.copy_location(ast.Return(value=ast.Call(
                            func=ast.Name("__challenger_guard__", ast.Load()), args=[], keywords=[])), inner)
        body.append(fn2)
    if body:
        mod = ast.fix_missing_locations(ast.Module(body=body, type_ignores=[]))
        exec(compile(mod, "<challenger-guard>", "exec"), ns2)  # noqa: S102 — own artifact AST
    return ns2, hits


def _vacuous_guard(tree: ast.Module, ns: dict[str, Any], g: ast.GeneratorExp, budget: Budget) -> tuple[int, int]:
    """(elements evaluated on the tested window, elements that only passed via a return-True guard)."""
    comps = [c for c in _called_checks(g.elt)]
    ns2, hits = _instrumented_ns(tree, ns, comps)
    code = compile(_probe_gen(g, {}), "<challenger-vac>", "eval")
    n = vac = 0
    try:
        it = eval(code, ns2)  # noqa: S307
        while not budget.out():
            before = hits[0]
            try:
                with _timer(min(PROBE_TIMEOUT_S, max(0.01, budget.left()))):
                    next(it)
            except StopIteration:
                break
            n += 1
            if hits[0] > before:
                vac += 1
    except Exception:  # noqa: BLE001 — informational only
        return n, 0
    return n, vac


def challenge_entry(src: str, name: str, *, cycle_id: str = "", before_src: str | None = None,
                    budget_s: float = DESK_BUDGET_S, source: str = "conjecture_desk",
                    kind: str = "lemma_mutation") -> ChallengeReport:
    """Try to break catalog entry ``name`` of artifact source ``src`` (the post-mutation source)."""
    rep = ChallengeReport(target=name, kind=kind, source=source, cycle_id=cycle_id,
                          seed=cycle_seed(cycle_id, name), budget_s=budget_s)
    budget = Budget(budget_s)
    try:
        _challenge_entry(rep, src, name, before_src, budget)
    except Exception as exc:  # noqa: BLE001 — a Challenger crash is noted, it is not a block
        rep.notes.append(f"challenger_error:{type(exc).__name__}:{str(exc)[:80]}")
    rep.seconds = round(budget.elapsed(), 4)
    return rep


def _challenge_entry(rep: ChallengeReport, src: str, name: str, before_src: str | None, budget: Budget) -> None:
    if before_src is not None and before_src == src:
        rep.block("no_op_submission", {"detail": "artifact unchanged by the mutation"})
        return
    tree = ast.parse(src)
    fns = _functions(tree)
    entry = next(((n, node, en) for n, node, en in _catalog_entries(tree) if n == name), None)
    if entry is None:
        rep.block("entry_missing", {"detail": f"{name} not in any catalog list"})
        return
    _n, node, enabled = entry
    if enabled is not True:
        rep.block("not_enabled", {"detail": f"{name} is not enabled in the submitted artifact"})
        return
    expr = _entry_expr(node, fns)
    ns: dict[str, Any] = {"__name__": "colony_challenger_probe"}
    exec(compile(tree, "<challenger-artifact>", "exec"), ns)  # noqa: S102 — the colony's own artifact
    if expr is None:
        if isinstance(node, ast.Name) and node.id in fns and not fns[node.id].args.args:
            _challenge_function(rep, fns[node.id], ns, budget)
        else:
            rep.notes.append("entry_shape_unparsed")
        return
    rep.components = _called_checks(expr)
    gens = _gens(expr)
    if not gens:
        if not _names(expr) - {"True", "False"} and identity_trivial(expr, set()):
            rep.trivial["entry"] = "constant_expression"
            rep.block("trivial:constant_expression", {"detail": ast.unparse(expr)[:80]})
            return
        rep.notes.append("no_free_variables_to_probe")
        return
    dom = _domain_map(tree, name)
    rng = random.Random(rep.seed)
    trivial_flags: list[str] = []
    for gi, g in enumerate(gens):
        vars_ = [c.target.id for c in g.generators]
        lits = {i: r for i, c in enumerate(g.generators) if (r := _lit_range(c.iter))}
        rep.ranges_tested[f"g{gi}"] = {vars_[i]: list(r) for i, r in lits.items()} | {
            vars_[i]: "dependent" for i in range(len(vars_)) if i not in lits}
        # --- triviality (identity level, then component level, then vacuity)
        why = ""
        conj = _conjuncts(g.elt)
        flags = [identity_trivial(c, set(vars_)) for c in conj]
        if conj and all(flags):
            why = flags[0]
        else:
            comp_flags = []
            for c in conj:
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id in fns:
                    fn = fns[c.func.id]
                    ret = _return_expr(fn)
                    params = {a.arg for a in fn.args.args}
                    comp_flags.append(identity_trivial(ret, params) if ret is not None else "")
                else:
                    comp_flags.append(identity_trivial(c, set(vars_)))
            if comp_flags and all(comp_flags):
                why = "component:" + comp_flags[0]
        n_el, vac = _vacuous_guard(tree, ns, g, budget)
        if n_el == 0 and not budget.out():
            why = why or "vacuous_empty_range"
        elif n_el and vac == n_el:
            why = why or "vacuous_guard_return_true"
        rep.trivial[f"g{gi}"] = why or "nontrivial"
        trivial_flags.append(why)
        # --- probes: boundary / far / sample per literal-range variable
        for i, (lo, hi) in lits.items():
            L = _var_domain(g, vars_[i], lo, dom)
            _run_probe(rep, "boundary", g, {i: _boundary_values(L, lo, hi)}, ns, budget, vars_)
            _run_probe(rep, "far", g, {i: _far_values(L, hi)}, ns, budget, vars_)
            span_hi = max(_far_values(L, hi)[-1], hi + 1)
            pts = sorted({rng.randint(L, span_hi) for _ in range(SAMPLES)})
            _run_probe(rep, "sample", g, {i: pts}, ns, budget, vars_)
            if rep.blocked:
                return
    if trivial_flags and all(trivial_flags):
        rep.block(f"trivial:{trivial_flags[0]}", {"detail": "every part of the check is trivially true; "
                                                            "a finite check adds nothing"})


def _range_sites(fn: ast.FunctionDef) -> list[ast.Call]:
    """Literal range(...) calls that drive a loop or comprehension inside ``fn``."""
    sites = []
    for n in ast.walk(fn):
        it = n.iter if isinstance(n, (ast.For, ast.comprehension)) else None
        if it is not None and _lit_range(it):
            sites.append(it)
    return sites


def _challenge_function(rep: ChallengeReport, fn: ast.FunctionDef, ns: dict[str, Any], budget: Budget) -> None:
    """Zero-arg check with a multi-statement body: substitute probe values into one literal loop
    range at a time, re-run the whole function, and require it to stay True."""
    rep.components = [fn.name] + [c for c in _called_checks(fn) if c != fn.name]
    sites = _range_sites(fn)
    if not sites:
        rep.notes.append("no_free_variables_to_probe")
        return
    rng = random.Random(rep.seed)
    for si in range(len(sites)):
        lo, hi = _lit_range(sites[si])
        rep.ranges_tested[f"loop{si}"] = [lo, hi]
        L = lo  # no catalog evidence below the check's own window
        span_hi = max(_far_values(L, hi)[-1], hi + 1)
        for family, vals in (("boundary", _boundary_values(L, lo, hi)), ("far", _far_values(L, hi)),
                             ("sample", sorted({rng.randint(L, span_hi) for _ in range(SAMPLES)}))):
            if rep.blocked:
                return
            if budget.out():
                rep.budget_hit = True
                return
            fn2 = ast.parse(ast.unparse(fn)).body[0]
            target = _range_sites(fn2)[si]
            tup = ast.Tuple(elts=[ast.Constant(v) for v in vals], ctx=ast.Load())

            class _Sub(ast.NodeTransformer):
                def visit_Call(self, node: ast.Call) -> ast.AST:
                    return tup if node is target else self.generic_visit(node)

            fn2 = ast.fix_missing_locations(_Sub().visit(fn2))
            fn2.name = "__challenger_probe__"
            ns2 = dict(ns)
            exec(compile(ast.Module(body=[fn2], type_ignores=[]), "<challenger-fn>", "exec"), ns2)  # noqa: S102
            try:
                with _timer(min(PROBE_TIMEOUT_S * 2, max(0.01, budget.left()))):
                    val = ns2["__challenger_probe__"]()
            except _ProbeTimeout:
                rep.inconclusive += 1
                continue
            except EDGE_ERRORS as exc:
                rep.probes["edge"] += 1
                rep.block("edge_error", {"probe": family, "loop": si, "values": vals[:8],
                                         "error": f"{type(exc).__name__}: {str(exc)[:80]}"})
                return
            rep.probes[family] += len(vals)
            if not isinstance(val, bool):
                rep.probes["edge"] += 1
                rep.block("type_edge_non_bool", {"probe": family, "loop": si, "value": repr(val)[:60]})
            elif val is False:
                rep.block(f"counterexample_{family}", {"probe": family, "loop": si, "values": vals[:12]})


# ----------------------------------------------------------------------------- claims

def challenge_claim(theme_id: str, bench_hint: str, *, cycle_id: str = "", lemma_src: str | None = None,
                    budget_s: float = CLAIM_BUDGET_S, cache: dict[str, ChallengeReport] | None = None) -> ChallengeReport:
    """A claim theme is backed by the catalog entries it names (token overlap). Break those."""
    rep = ChallengeReport(target=theme_id, kind="claim", source="claim_pipeline", cycle_id=cycle_id,
                          seed=cycle_seed(cycle_id, theme_id), budget_s=budget_s)
    t0 = time.monotonic()
    try:
        if "lemma" not in (bench_hint or "").lower():
            rep.notes.append("no_lemma_identity_to_break (bench-level claim)")
            return rep
        if lemma_src is None:
            from colony.authoring import _lemma_impl
            lemma_src = _lemma_impl().read_text(encoding="utf-8")
        tree = ast.parse(lemma_src)
        toks = {t for t in theme_id.lower().replace("-", "_").split("_") if len(t) >= 4}
        for pat in re.findall(r"hard:(\S+)", bench_hint or ""):  # the colony's own fixed hint table
            toks |= {x.strip("*").lower() for x in pat.split("|") if len(x.strip("*")) >= 4}
        related = [n for n, _node, en in _catalog_entries(tree) if en and toks & set(n.lower().split("_"))][:3]
        rep.components = related
        if not related:
            rep.notes.append("no_related_catalog_entry")
            return rep
        per = max(0.2, budget_s / len(related))
        for name in related:
            key = f"{cycle_id}|{name}"
            sub = (cache or {}).get(key)
            if sub is None:
                sub = challenge_entry(lemma_src, name, cycle_id=cycle_id, budget_s=per, source="claim_pipeline",
                                      kind="claim_component")
                if cache is not None:
                    cache[key] = sub
            for k, v in sub.probes.items():
                rep.probes[k] += v
            rep.ranges_tested[name] = sub.ranges_tested
            rep.budget_hit = rep.budget_hit or sub.budget_hit
            rep.inconclusive += sub.inconclusive
            if sub.blocked and not sub.reason.startswith("trivial"):
                rep.block(f"component_broken:{name}:{sub.reason}", sub.counterexample)
                break
            if sub.blocked:
                rep.notes.append(f"component_trivial:{name}")
    except Exception as exc:  # noqa: BLE001
        rep.notes.append(f"challenger_error:{type(exc).__name__}")
    rep.seconds = round(time.monotonic() - t0, 4)
    return rep


# ----------------------------------------------------------------------------- frontier

def challenge_frontier(task: dict[str, Any], primary: dict[str, Any], t: dict[str, Any], impl: Any, *,
                       cycle_id: str = "", budget_s: float = FRONTIER_BUDGET_S) -> ChallengeReport:
    """Try to break a frontier primary result before the independent recheck sees it."""
    rep = ChallengeReport(target=str(task.get("target")), kind="frontier", source="frontier", cycle_id=cycle_id,
                          seed=cycle_seed(cycle_id, f"{task.get('target')}:{task.get('lo')}"), budget_s=budget_s)
    budget = Budget(budget_s)
    try:
        if task.get("family") == "oeis_recurrence":
            _challenge_recurrence(rep, task, primary, t)
        else:
            _challenge_range(rep, task, primary, t, impl, budget)
    except Exception as exc:  # noqa: BLE001
        rep.notes.append(f"challenger_error:{type(exc).__name__}:{str(exc)[:80]}")
    rep.seconds = round(budget.elapsed(), 4)
    return rep


def _challenge_recurrence(rep: ChallengeReport, task: dict[str, Any], r: dict[str, Any], t: dict[str, Any]) -> None:
    terms = [int(x) for x in t.get("terms") or []]
    rep.components = ["fit_recurrence"]
    rep.ranges_tested = {"terms": [0, len(terms) - 1]}
    if not r.get("holds"):
        rep.notes.append("nothing_claimed")
        return
    d = int(r.get("order") or 0)
    coeffs = [Fraction(str(c)) for c in r.get("coeffs") or []]
    rep.probes["edge"] += 1
    if d <= 0 or len(coeffs) != d + 1:
        rep.block("type_edge_bad_recurrence_shape", {"order": d, "n_coeffs": len(coeffs)})
        return
    if all(c == 0 for c in coeffs[:d]):
        rep.block("trivial:both_sides_constant", {"detail": "recurrence has no dependence on earlier terms"})
        return
    if len(set(terms)) < 4:
        rep.block("trivial:near_constant_sequence", {"distinct": len(set(terms))})
        return
    for n in range(d, len(terms)):  # every listed index from the first one the recurrence defines
        fam = "boundary" if n < d + 3 else "sample"
        rep.probes[fam] += 1
        pred = sum(coeffs[i] * terms[n - 1 - i] for i in range(d)) + coeffs[d]
        if pred != terms[n]:
            rep.block(f"counterexample_{fam}", {"index": n, "predicted": str(pred), "listed": terms[n]})
            return
    rep.trivial["fit"] = "nontrivial"


def _challenge_range(rep: ChallengeReport, task: dict[str, Any], r: dict[str, Any], t: dict[str, Any],
                     impl: Any, budget: Budget) -> None:
    fam = task["family"]
    lo, hi = int(task["lo"]), int(task["hi"])
    start = int(t.get("start") or 1)
    rep.components = [f"{fam}:primary", f"{fam}:independent"]
    # integrity / type edges of the claimed result
    rep.probes["edge"] += 1
    top = r.get("checked_hi")
    if not isinstance(top, int) or isinstance(top, bool) or not (lo - 1 <= top <= hi):
        rep.block("type_edge_checked_hi", {"checked_hi": repr(top)[:40], "lo": lo, "hi": hi})
        return
    if r.get("complete") and top != hi:
        rep.block("integrity_complete_but_short", {"checked_hi": top, "hi": hi})
        return
    if r.get("proof") is not False or r.get("label") != "bounded evidence, not proof":
        rep.block("integrity_label", {"proof": r.get("proof")})
        return
    ce = r.get("counterexample")
    if ce is not None and not (lo <= int(ce) <= hi):
        rep.block("integrity_counterexample_outside_window", {"n": ce})
        return
    rep.ranges_tested = {"window": [lo, top]}
    if top < lo:
        return
    check, holds = impl.FAMILIES[fam]
    rng = random.Random(rep.seed)
    B = 12

    def compare(a: int, b: int, family: str) -> None:
        """Primary on a narrow window vs the independent method on every n in it."""
        if rep.blocked or budget.out():
            rep.budget_hit = rep.budget_hit or budget.out()
            return
        a, b = max(a, start), max(b, start)
        if b < a:
            return
        try:
            with _timer(min(PROBE_TIMEOUT_S * 2, max(0.01, budget.left()))):
                if fam == "twin_hl":
                    same = impl.twin_pairs_in(a, b) == impl.twin_pairs_in_mr(a, b)
                    rep.probes[family] += 1
                    if not same:
                        rep.block(f"counterexample_{family}", {"window": [a, b], "detail": "sieve vs MR twin count differ"})
                    return
                sub = check(a, b, impl.Deadline(max(0.05, budget.left())))
                bad_primary = sub.get("counterexample")
                for n in range(a, b + 1):
                    rep.probes[family] += 1
                    if not holds(n) and (bad_primary is None or int(bad_primary) > n):
                        # independent finds a failure the primary passed → loud, withheld for review
                        rep.block(f"primary_missed_{family}", {"n": n, "window": [a, b],
                                                               "independent_fails": True})
                        return
                if bad_primary is not None and holds(int(bad_primary)):
                    rep.block(f"primary_false_alarm_{family}", {"n": int(bad_primary), "window": [a, b]})
        except _ProbeTimeout:
            rep.inconclusive += 1
        except EDGE_ERRORS as exc:
            rep.probes["edge"] += 1
            rep.block("edge_error", {"probe": family, "window": [a, b], "error": f"{type(exc).__name__}"})

    if ce is not None:  # a counterexample claim: is it reproducible on a narrow window around it?
        n = int(ce)
        compare(n - B, n, "boundary")
        return
    compare(start, start + B, "boundary")       # statement's domain edge
    compare(lo - 2, lo + B, "boundary")          # window start (segment seams)
    compare(top - B, top + 2, "boundary")        # window end and just beyond
    for f in (2 * top + 1, 4 * top + 3):         # far beyond the tested window
        compare(f, f + B, "far")
    for _ in range(3):
        p = rng.randint(lo, top)
        compare(p, p + 4, "sample")


# ----------------------------------------------------------------------------- record / lesson / metrics

def record(rep: ChallengeReport, *, why: dict[str, Any] | None = None) -> dict[str, Any]:
    """Append the challenge receipt; on a block, write the self_challenge lesson. Never raises."""
    row = {"ts": _utc(), **rep.to_dict(), "why_believe": why or why_believe(rep)}
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass
    if rep.blocked:
        try:
            from colony.lessons import write_lesson
            ce = json.dumps(rep.counterexample, sort_keys=True, default=str)[:200] if rep.counterexample else ""
            write_lesson(
                decision="block",
                check="self_challenge",
                what=(f"Challenger self-rejected `{rep.target}` ({rep.kind}) before submission: {rep.reason}"
                      + (f"; edge/counterexample {ce}" if ce else "") + ". Withheld; nothing was scored."),
                source="challenger",
                cycle_id=rep.cycle_id,
                mutation=rep.target if rep.kind in ("lemma_mutation",) else "",
                family="self_challenge",
                lesson_type="self_challenge",
                tags=["self_challenge", rep.kind, rep.reason.split(":")[0]],
                evidence=["data/commons/self_challenge.jsonl"],
            )
        except Exception:
            pass
    return row


def load_log(limit: int = 5000) -> list[dict[str, Any]]:
    if not LOG.exists():
        return []
    out = []
    for ln in LOG.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def blocked_targets(lookback: int = 200) -> dict[str, str]:
    """Lemma mutations the Challenger broke recently (deterministic edges → do not re-pick)."""
    out: dict[str, str] = {}
    for r in load_log(limit=lookback):
        if r.get("blocked") and r.get("kind") == "lemma_mutation" and r.get("target"):
            out[str(r["target"])] = f"self_challenge:{str(r.get('reason') or '')[:40]}"
    return out


def metrics(*, oracle_rows: list[dict[str, Any]] | None = None, rows: list[dict[str, Any]] | None = None,
            frontier_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Observability only — never enters aggregate fitness."""
    rows = rows if rows is not None else load_log()
    top = [r for r in rows if r.get("kind") in ("lemma_mutation", "claim", "frontier")]
    n = len(top)
    nb = sum(1 for r in top if r.get("blocked"))
    if oracle_rows is None:
        try:
            from colony.oracle import ORACLE_LOG as _OJ
        except Exception:
            _OJ = ROOT / "data" / "commons" / "oracle.jsonl"
        oracle_rows = []
        if Path(_OJ).exists():
            for ln in Path(_OJ).read_text(encoding="utf-8").splitlines():
                try:
                    oracle_rows.append(json.loads(ln))
                except json.JSONDecodeError:
                    continue
    src_of = {"lemma_mutation": "conjecture_desk", "claim": "claim_pipeline"}
    passed_keys = {(src_of[r["kind"]], str(r.get("target")), str(r.get("cycle_id")))
                   for r in top if not r.get("blocked") and r.get("kind") in src_of}
    first_ts = min((str(r.get("ts")) for r in top), default=None)
    judged = [o for o in oracle_rows
              if (str(o.get("source")), str(o.get("mutation")), str(o.get("cycle_id"))) in passed_keys]
    pre = [o for o in oracle_rows if o.get("source") in ("conjecture_desk", "claim_pipeline")
           and (first_ts is None or str(o.get("ts") or "") < first_ts)]

    def _rate(xs: list[dict[str, Any]]) -> float | None:
        return round(sum(1 for o in xs if not o.get("passed")) / len(xs), 4) if xs else None

    if frontier_rows is None:
        try:
            from colony.frontier import load_log as _fl
            frontier_rows = _fl()
        except Exception:
            frontier_rows = []
    fr_after = [r for r in frontier_rows if (r.get("challenger") or {}).get("blocked") is False]
    fr_bad = [r for r in fr_after if r.get("outcome") in ("disagreement", "unresolved_anomaly")]
    by_kind: dict[str, dict[str, int]] = {}
    for r in top:
        k = by_kind.setdefault(r["kind"], {"challenged": 0, "blocked": 0})
        k["challenged"] += 1
        k["blocked"] += int(bool(r.get("blocked")))
    catches = [{"ts": r.get("ts"), "target": r.get("target"), "kind": r.get("kind"), "reason": r.get("reason"),
                "counterexample": r.get("counterexample")} for r in top if r.get("blocked")][-5:]
    return {
        "challenged": n,
        "blocked": nb,
        "self_reject_rate": round(nb / n, 4) if n else 0.0,
        "by_kind": by_kind,
        "post_challenger_oracle_judged": len(judged),
        "post_challenger_oracle_kill_rate": _rate(judged),
        "pre_challenger_oracle_judged": len(pre),
        "pre_challenger_oracle_kill_rate": _rate(pre),
        "post_challenger_frontier_recheck_fail_rate": round(len(fr_bad) / len(fr_after), 4) if fr_after else None,
        "challenger_catches": catches,
        "can_approve": CAN_APPROVE,
        "note": "Observability only: the Challenger can block, never approve; not part of aggregate fitness.",
    }


def write_system() -> dict[str, Any]:
    m = metrics()
    m["updated_at"] = _utc()
    try:
        SYSTEM.parent.mkdir(parents=True, exist_ok=True)
        SYSTEM.write_text(json.dumps(m, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    except OSError:
        pass
    return m
