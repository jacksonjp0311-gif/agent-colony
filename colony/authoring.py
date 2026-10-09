"""Desk authoring: compose NEW disabled hard checks from proven (passing) lemmas.

human_guide les_become_author_new_hard_checks_from_proven_lemmas: when no disabled
variants remain, the desk may write a new stress check that conjoins two proven
lemmas on larger, disjoint parameter windows (numeric machine check), add it to
HARD_TIER_LEMMAS **disabled**, and leave enabling to a later cycle so a proposal
can target it and the Oracle judges it (stripped / held-out / CAS). Nothing is
enabled here and nothing bypasses the Oracle.

Guards (mechanism, not a fixed list):
- components: enabled + passing in society/benchmarks/latest.json, not easy_pad /
  adversarial / authored, not cooled or guide-avoided (blocked_themes);
- non-trivial component: its check fn compares computed values, uses its parameters,
  and has no self-identical comparison (x == x);
- extendable: the component's catalog lambda is all(check_f(...) for v in range(A, B) ...)
  with literal bounds; windows are shifted past B (disjoint from the base window);
- duplicate guard: name and normalized AST of the body must be new to the catalog;
- verification in a subprocess on a temp copy: returns True, every component is
  actually evaluated (>= MIN_EVALS calls), forcing any component False makes the
  authored check False (falsifiable), and it finishes inside RUNTIME_BUDGET_S;
- bounds: MAX_AUTHORED_PER_CYCLE new checks per cycle, MAX_AUTHORED_TOTAL overall.

Feed-driven candidates (colony.feeds, OEIS) are tried first: the colony's own sequence
generator must reproduce OEIS held-out terms AND a proven lemma must hold on a new window.
Same guards, same verification, same disabled-until-Oracle path.
"""
from __future__ import annotations

import ast
import copy
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

MAX_AUTHORED_PER_CYCLE = 1
MAX_AUTHORED_TOTAL = 100  # James 2026-10-09 3:52 AM ET: raised from 24 (per-cycle limit unchanged)
MAX_CANDIDATES_TRIED = 8
MIN_EVALS = 3
RUNTIME_BUDGET_S = 0.5
SUBPROCESS_TIMEOUT_S = 10
AUTHORED_PREFIX = "authored_"
INSERT_MARKER = "# Adversarial aliases used by Oracle theme held-out windows"
FALLBACK_MARKER = "# Mutable catalog the conjecture desk may extend / mutate."
AUTHOR_GUIDE_TAGS = {"author_checks", "author_new_checks", "become_author"}


def guide_authoring_active() -> bool:
    try:
        from colony.lessons import load_human_guides
    except Exception:
        return False
    for e in load_human_guides():
        tags = {str(x).lower() for x in (e.get("tags") or [])}
        prefer = {str(x).lower() for x in ((e.get("catalog_hint") or {}).get("prefer") or [])}
        if tags & AUTHOR_GUIDE_TAGS or prefer & AUTHOR_GUIDE_TAGS:
            return True
    return False


def _lemma_impl() -> Path:
    from colony.lessons import BENCH_ARTIFACTS_DIR
    return BENCH_ARTIFACTS_DIR / "lemma_impl.py"


def _catalog_lists(tree: ast.Module) -> dict[str, ast.List]:
    out: dict[str, ast.List] = {}
    for node in tree.body:
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
        if target and isinstance(node.value, ast.List):
            out[target] = node.value
    return out


def _entries(tree: ast.Module) -> list[tuple[str, ast.AST, bool | None]]:
    rows: list[tuple[str, ast.AST, bool | None]] = []
    for lst in _catalog_lists(tree).values():
        for elt in lst.elts:
            if (
                isinstance(elt, ast.Tuple) and len(elt.elts) >= 3
                and isinstance(elt.elts[0], ast.Constant) and isinstance(elt.elts[0].value, str)
            ):
                flag = elt.elts[2].value if isinstance(elt.elts[2], ast.Constant) else None
                rows.append((elt.elts[0].value, elt.elts[1], flag if isinstance(flag, bool) else None))
    return rows


def _fn_nontrivial(fn: ast.FunctionDef) -> bool:
    """Compares computed values, uses its params, no self-identical comparison."""
    params = {a.arg for a in fn.args.args}
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    if params and not (params & names):
        return False
    compares = [n for n in ast.walk(fn) if isinstance(n, ast.Compare)]
    if not compares:
        return False
    for c in compares:
        left = ast.dump(c.left)
        if any(ast.dump(r) == left for r in c.comparators):
            return False
    return True


def _extendable(lam: ast.AST) -> tuple[str, ast.GeneratorExp] | None:
    """lambda: all(check_f(...) for v in range(A, B) ...) with >=1 literal range → (fn, genexp)."""
    if not isinstance(lam, ast.Lambda):
        return None
    call = lam.body
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "all"
            and len(call.args) == 1 and isinstance(call.args[0], ast.GeneratorExp)):
        return None
    gen = call.args[0]
    if not (isinstance(gen.elt, ast.Call) and isinstance(gen.elt.func, ast.Name)
            and gen.elt.func.id.startswith("check_")):
        return None
    if not any(_literal_range(c.iter) for c in gen.generators):
        return None
    return gen.elt.func.id, gen


def _literal_range(node: ast.AST) -> tuple[int, int] | None:
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "range"):
        return None
    vals = [a.value if isinstance(a, ast.Constant) and isinstance(a.value, int) else None for a in node.args]
    if any(v is None for v in vals):
        return None
    if len(vals) == 1:
        return 0, int(vals[0])
    if len(vals) == 2:
        return int(vals[0]), int(vals[1])
    return None


def _shift_windows(gen: ast.GeneratorExp, k: int) -> ast.GeneratorExp:
    """Copy of gen with every literal range(A, B) moved to a disjoint, larger window."""
    new = copy.deepcopy(gen)
    for comp in new.generators:
        rng = _literal_range(comp.iter)
        if not rng:
            continue
        a, b = rng
        span = max(2, (b - a) // 2)
        lo = b + (k - 1) * span
        comp.iter = ast.Call(
            func=ast.Name(id="range", ctx=ast.Load()),
            args=[ast.Constant(lo), ast.Constant(lo + span)],
            keywords=[],
        )
    return ast.fix_missing_locations(new)


def eligible_components(src: str) -> list[dict[str, Any]]:
    from colony.lessons import _bench_check_status, blocked_themes, guide_avoid_themes
    tree = ast.parse(src)
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    status = _bench_check_status()
    blocked = set(blocked_themes())
    avoided = {t for t in guide_avoid_themes() if t and len(t) >= 6}
    out: list[dict[str, Any]] = []
    seen_fn: set[str] = set()
    for name, callable_node, flag in _entries(tree):
        if flag is not True or status.get(name) is not True:
            continue
        if name.startswith(("easy_pad", "adversarial_", AUTHORED_PREFIX, "stem_")):
            continue
        if name in blocked or any(t in name for t in avoided):
            continue
        ext = _extendable(callable_node)
        if not ext:
            continue
        fn_name, gen = ext
        fn = funcs.get(fn_name)
        if fn is None or fn_name in seen_fn or not _fn_nontrivial(fn):
            continue
        seen_fn.add(fn_name)
        out.append({"lemma": name, "function": fn_name, "gen": gen})
    return out


def _existing_bodies(tree: ast.Module) -> set[str]:
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    bodies: set[str] = set()
    for _name, node, _flag in _entries(tree):
        if isinstance(node, ast.Lambda):
            bodies.add(ast.dump(node.body))
        elif isinstance(node, ast.Name) and node.id in funcs:
            ret = funcs[node.id].body[-1]
            if isinstance(ret, ast.Return) and ret.value is not None:
                bodies.add(ast.dump(ret.value))
    return bodies


def _build_candidate(a: dict[str, Any], b: dict[str, Any], k: int) -> tuple[str, str, ast.AST, str]:
    name = f"{AUTHORED_PREFIX}{a['lemma']}__{b['lemma']}_w{k}"
    body = ast.BoolOp(
        op=ast.And(),
        values=[
            ast.Call(func=ast.Name(id="all", ctx=ast.Load()), args=[_shift_windows(c["gen"], k)], keywords=[])
            for c in (a, b)
        ],
    )
    body = ast.fix_missing_locations(body)
    expr = ast.unparse(body)
    fn_src = (
        f"def check_{name}() -> bool:\n"
        f'    """Authored stress check (desk): proven lemmas {a["lemma"]} + {b["lemma"]} on\n'
        f"    larger windows disjoint from their base windows (generation {k}).\n\n"
        f"    Components: society/benchmarks/artifacts/lemma_impl.py::{a['function']},\n"
        f"    ::{b['function']}; checked by society/benchmarks/lemma_microbench.py.\n"
        f'    Machine check only — not a novel theorem. Disabled until the Oracle passes it.\n'
        f'    """\n'
        f"    return {expr}\n"
    )
    return name, fn_src, body, expr


def _defined_functions(src: str) -> set[str]:
    try:
        return {n.name for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)}
    except SyntaxError:
        return set()


def oeis_candidates(src: str, comps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Feed-driven: an OEIS sequence that matched one of the colony's OWN sequences becomes a
    cross-check — the generator must reproduce OEIS's held-out terms (indices never used in
    the query) AND a proven lemma about that sequence must hold on a new window.

    Only integers (digits-only parsed) and a validated A-number reach the generated code;
    no fetched text does. The expression template comes from colony.feeds.SEQ_GENERATORS.
    """
    try:
        from colony.feeds import generator_by_name, sequence_items
        seqs = sequence_items()
    except Exception:
        return []
    defined = _defined_functions(src)
    by_fn = {c["function"]: c for c in comps}
    out: list[dict[str, Any]] = []
    for it in seqs:
        gen = generator_by_name(str(it.get("generator") or ""))
        if not gen or not all(f in defined for f in gen["base_fns"]):
            continue
        comp = next((by_fn[f] for f in gen["lemma_fns"] if f in by_fn), None)
        if comp is None:
            continue
        anum = str(it["oeis_id"]).lower()
        feed_id = f"oeis:{it['oeis_id']}:{gen['name']}"  # rebuilt from validated parts only
        fetched = str(it.get("fetched_at") or "")
        fetched = fetched if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", fetched) else "unknown"
        terms = [int(t) for t in it["terms"]]
        h0 = int(it["heldout_start"])
        name = f"{AUTHORED_PREFIX}oeis_{anum}__{comp['lemma']}"
        oeis_expr = (f"all(({gen['expr']}) == t for n, t in zip(range({h0}, {h0 + len(terms)}), "
                     f"({', '.join(str(t) for t in terms)},)))")
        oeis_node = ast.parse(oeis_expr, mode="eval").body
        lemma_node = ast.Call(func=ast.Name(id="all", ctx=ast.Load()), args=[_shift_windows(comp["gen"], 1)], keywords=[])
        body = ast.fix_missing_locations(ast.BoolOp(op=ast.And(), values=[lemma_node, oeis_node]))
        expr = ast.unparse(body)
        fn_src = (
            f"def check_{name}() -> bool:\n"
            f'    """Authored feed cross-check (desk): OEIS {it["oeis_id"]} held-out terms\n'
            f"    n={h0}..{h0 + len(terms) - 1} must equal the colony's `{gen['name']}` ({gen['expr']}), and the\n"
            f"    proven lemma {comp['lemma']} must hold on a window past its base window.\n\n"
            f"    Components: society/benchmarks/artifacts/lemma_impl.py::{comp['function']},\n"
            f"    ::{', ::'.join(gen['base_fns'])}; checked by society/benchmarks/lemma_microbench.py.\n"
            f"    Source: https://oeis.org/{it['oeis_id']} (feed {feed_id}, fetched {fetched}).\n"
            f'    Machine check only — not a novel theorem. Disabled until the Oracle passes it.\n'
            f'    """\n'
            f"    return {expr}\n"
        )
        out.append({
            "name": name, "fn_src": fn_src, "body": body, "expr": expr,
            "components": [comp], "verify_fns": [comp["function"], *gen["base_fns"]],
            "evidence": [f"oeis:{it['oeis_id']}", f"https://oeis.org/{it['oeis_id']}", f"feed:{feed_id}"],
            "what": (f"authored disabled feed cross-check `{name}`: OEIS {it['oeis_id']} held-out terms vs "
                     f"`{gen['name']}` + proven lemma {comp['lemma']} on a new window; awaits Oracle via proposal"),
            "source": "oeis",
        })
    return out


def insert_disabled(src: str, name: str, fn_src: str) -> str | None:
    """Add the function and a disabled HARD_TIER_LEMMAS entry; None if markers are missing."""
    marker = INSERT_MARKER if INSERT_MARKER in src else FALLBACK_MARKER
    if marker not in src:
        return None
    src = src.replace(marker, fn_src + "\n\n" + marker, 1)
    tree = ast.parse(src)
    lst = _catalog_lists(tree).get("HARD_TIER_LEMMAS")
    if lst is None:
        return None
    lines = src.splitlines(keepends=True)
    close_idx = lst.end_lineno - 1  # line holding the closing bracket
    entry = f'    ("{name}", check_{name}, False),\n'
    lines.insert(close_idx, entry)
    out = "".join(lines)
    ast.parse(out)  # must stay valid Python
    return out


_VERIFY = r'''
import importlib.util, json, sys, time
path, name, comps = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
spec = importlib.util.spec_from_file_location("authored_probe", path)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
fn = getattr(mod, "check_" + name)
counts = {c: 0 for c in comps}
orig = {c: getattr(mod, c) for c in comps}
def wrap(c):
    def w(*a, **k):
        counts[c] += 1
        return orig[c](*a, **k)
    return w
for c in comps:
    setattr(mod, c, wrap(c))
t0 = time.perf_counter(); ok = bool(fn()); secs = time.perf_counter() - t0
falsifiable = {}
for c in comps:
    for d in comps:
        setattr(mod, d, orig[d])
    setattr(mod, c, lambda *a, **k: False)
    falsifiable[c] = (fn() is False)
print(json.dumps({"ok": ok, "seconds": secs, "counts": counts, "falsifiable": falsifiable}))
'''


def verify_candidate(new_src: str, name: str, components: list[str]) -> dict[str, Any]:
    """Run the authored check in a subprocess on a temp copy; enforce the guards."""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lemma_impl_probe.py"
        path.write_text(new_src, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, "-c", _VERIFY, str(path), name, json.dumps(components)],
                capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return {"accepted": False, "reason": "timeout"}
    if proc.returncode != 0:
        return {"accepted": False, "reason": f"error:{(proc.stderr or '').strip()[-160:]}"}
    try:
        res = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"accepted": False, "reason": "bad_probe_output"}
    if not res.get("ok"):
        return {**res, "accepted": False, "reason": "does_not_hold_on_new_window"}
    if any(int(res["counts"].get(c, 0)) < MIN_EVALS for c in components):
        return {**res, "accepted": False, "reason": "trivial:too_few_evaluations"}
    if not all(res["falsifiable"].get(c) for c in components):
        return {**res, "accepted": False, "reason": "trivial:not_falsifiable"}
    if float(res.get("seconds") or 0) > RUNTIME_BUDGET_S:
        return {**res, "accepted": False, "reason": "too_slow"}
    return {**res, "accepted": True, "reason": "verified"}


def author_checks(*, max_new: int = MAX_AUTHORED_PER_CYCLE, cycle_id: str = "", write: bool = True) -> list[dict[str, Any]]:
    """Compose up to ``max_new`` new disabled hard checks from proven lemmas. Returns rows."""
    path = _lemma_impl()
    if not path.exists() or max_new <= 0:
        return []
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = {n for n, _c, _f in _entries(tree)}
    n_authored = sum(1 for n in names if n.startswith(AUTHORED_PREFIX))
    if n_authored >= MAX_AUTHORED_TOTAL:
        return []
    try:
        from colony.lessons import blocked_themes
        blocked = set(blocked_themes())
    except Exception:
        blocked = set()
    try:  # never retry a candidate the desk already rejected (no reject spam)
        from colony.lessons import load_lessons
        rejected = {
            str(e.get("mutation") or "") for e in load_lessons(limit=400, include_expired=True)
            if e.get("type") == "authoring_reject"
        }
    except Exception:
        rejected = set()
    comps = eligible_components(src)
    bodies = _existing_bodies(tree)
    authored_names = [n for n in names if n.startswith(AUTHORED_PREFIX)]
    comp_use = {c["lemma"]: sum(1 for n in authored_names if f"_{c['lemma']}_" in f"_{n}_") for c in comps}
    pairs = []
    for i, a in enumerate(comps):
        for b in comps[i + 1:]:
            prefix = f"{AUTHORED_PREFIX}{a['lemma']}__{b['lemma']}_w"
            used = sum(1 for n in authored_names if n.startswith(prefix))
            spread = comp_use[a["lemma"]] + comp_use[b["lemma"]]
            pairs.append(((used, spread, a["lemma"], b["lemma"]), a, b, used + 1))
    # least-used pair, then least-used components (diversity), then stable name order
    pairs.sort(key=lambda t: t[0])
    candidates: list[dict[str, Any]] = list(oeis_candidates(src, comps))  # feeds first
    for _key, a, b, k in pairs:
        name, fn_src, body, expr = _build_candidate(a, b, k)
        candidates.append({
            "name": name, "fn_src": fn_src, "body": body, "expr": expr, "components": [a, b],
            "verify_fns": [a["function"], b["function"]], "evidence": [], "source": "compose",
            "what": (f"authored disabled hard check `{name}` from proven lemmas "
                     f"{a['lemma']} + {b['lemma']} on new windows; awaits Oracle via proposal"),
        })
    out: list[dict[str, Any]] = []
    tried = 0
    for cand in candidates:
        if len(out) >= max_new or tried >= MAX_CANDIDATES_TRIED:
            break
        name, body = cand["name"], cand["body"]
        if name in names or name in blocked or name in rejected or ast.dump(body) in bodies:
            continue  # duplicate / cooled
        new_src = insert_disabled(src, name, cand["fn_src"])
        if new_src is None:
            break
        tried += 1
        res = verify_candidate(new_src, name, cand["verify_fns"])
        if not res.get("accepted"):
            out_row = {"name": name, "accepted": False, "reason": res.get("reason")}
            if write:
                _lesson_for(out_row, cand, cycle_id)
            rejected.add(name)
            continue
        if write:
            path.write_text(new_src, encoding="utf-8")
            _invalidate(path)
        src, tree = new_src, ast.parse(new_src)
        names.add(name)
        bodies.add(ast.dump(body))
        row = {
            "name": name,
            "accepted": True,
            "source": cand["source"],
            "components": [c["lemma"] for c in cand["components"]],
            "functions": list(cand["verify_fns"]),
            "assertion": cand["expr"],
            "evidence": list(cand["evidence"]),
            "seconds": res.get("seconds"),
            "evaluations": res.get("counts"),
        }
        if write:
            _lesson_for(row, cand, cycle_id)
        out.append(row)
    return out


def _invalidate(path: Path) -> None:
    cache = path.parent / "__pycache__"
    if cache.is_dir():
        for pyc in cache.glob(f"{path.stem}*.pyc"):
            try:
                pyc.unlink()
            except OSError:
                pass


def _lesson_for(row: dict[str, Any], cand: dict[str, Any], cycle_id: str) -> None:
    try:
        from colony.lessons import write_lesson
        ok = row.get("accepted")
        comps = cand["components"]
        evidence = [f"society/benchmarks/artifacts/lemma_impl.py::{f}" for f in cand["verify_fns"]]
        evidence += ["society/benchmarks/lemma_microbench.py"] + [f"lemma:{c['lemma']}" for c in comps]
        evidence += list(cand.get("evidence") or [])
        write_lesson(
            decision="skip",
            check="authoring",
            what=(cand["what"] if ok else f"rejected authored candidate `{row['name']}`: {row.get('reason')}")[:400],
            source="conjecture_desk",
            cycle_id=cycle_id,
            mutation=row["name"],
            lesson_type="authored_check" if ok else "authoring_reject",
            family="hard_tier",
            tags=["authoring", "authored_check" if ok else "authoring_reject",
                  *[c["lemma"] for c in comps], *(["feed", cand["source"]] if cand.get("source") == "oeis" else [])],
            evidence=evidence,
        )
    except Exception:
        pass
