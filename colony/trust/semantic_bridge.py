"""Semantic bridge (REPORT-ONLY): does a check's code test the claim its name/docstring states?

Pattern adapted from Governed-Computational-Discovery-Theory ``phase4/semantic_bridge.py``
(spec -> canonical form -> equality check, plus weakened/mutated variants that the bridge must
reject). No SAT code is reused; this is a static AST bridge over the colony's own check sources.

For every Oracle verdict on a check, the bridge:

1. derives the *stated claim* from the check name and docstring
   (sieve instrument checks: template, gap pattern, windows, modulus/classes, sigma;
   composed checks ``authored_A__B_wN``: the two component lemmas);
2. extracts the *parameters actually used* from the function's AST;
3. compares them (``bridge_ok``);
4. builds mutated mismatched variants (other gaps, shifted window, wrong class, swapped
   component) and confirms the bridge rejects every one (``mutants_rejected``).

A mismatch, or a mutant the bridge fails to reject, is logged as ``would_reject``.
It NEVER kills, edits, or changes an Oracle verdict. Disable logging with COLONY_SEMANTIC_BRIDGE=0.
State: society/systems/semantic_bridge.json (totals + last rows).
"""
from __future__ import annotations

import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
STATE = ROOT / "society" / "systems" / "semantic_bridge.json"
KEEP_ROWS = 60
SIEVE_PREFIX = "authored_sieve_"
SIEVE_RE = re.compile(r"^authored_sieve_(hl_within|residue_bal|two_counter)_g([0-9_]+)_w(\d+)$")
COMPOSE_RE = re.compile(r"^authored_([a-z0-9_]+?)__([a-z0-9_]+)_w(\d+)$")


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- claim (from name + docstring)
def stated_claim(name: str, doc: str) -> dict[str, Any] | None:
    m = SIEVE_RE.match(name)
    if m:
        template, sig, w = m.group(1), m.group(2), int(m.group(3))
        gaps = tuple(int(x) for x in sig.split("_"))
        claim: dict[str, Any] = {"kind": "sieve", "template": template, "gaps": gaps, "w": w}
        pm = re.search(r"pattern \(([0-9, ]+)\)", doc or "")
        claim["doc_gaps"] = tuple(int(x) for x in pm.group(1).replace(" ", "").strip(",").split(",")) if pm else None
        wm = re.search(r"Windows (\[[^\]]*\])", doc or "")
        try:
            claim["doc_windows"] = [tuple(x) for x in ast.literal_eval(wm.group(1))] if wm else None
        except (ValueError, SyntaxError):
            claim["doc_windows"] = None
        mm = re.search(r"p mod (\d+) classes ([0-9/]+)", doc or "")
        claim["doc_mod"] = (int(mm.group(1)), tuple(int(x) for x in mm.group(2).split("/"))) if mm else None
        sm = re.search(r"within ([0-9.]+)\*sqrt", doc or "")
        claim["doc_sigma"] = float(sm.group(1)) if sm else None
        return claim
    m = COMPOSE_RE.match(name)
    if m:
        return {"kind": "compose", "components": (m.group(1), m.group(2)), "w": int(m.group(3))}
    return None


# ---------------------------------------------------------------- parameters (from the AST)
def _const(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except Exception:  # noqa: BLE001
        return None


def used_params(fn: ast.FunctionDef) -> dict[str, Any]:
    calls: list[dict[str, Any]] = []
    check_calls: set[str] = set()
    windows = None
    sigmas: set[float] = set()
    for sub in ast.walk(fn):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
            nm = sub.func.id
            if nm in ("sieve_count", "sieve_hl"):
                args = [_const(a) for a in sub.args]
                kw = {k.arg: _const(k.value) for k in sub.keywords if k.arg}
                calls.append({"fn": nm, "gaps": tuple(args[0]) if args and isinstance(args[0], (tuple, list)) else None,
                              "mod": args[3] if len(args) > 3 else kw.get("mod"),
                              "residue": args[4] if len(args) > 4 else kw.get("residue"),
                              "backend": kw.get("backend")})
            elif nm.startswith("check_"):
                check_calls.add(nm[len("check_"):])
        if isinstance(sub, ast.comprehension):
            v = _const(sub.iter)
            if isinstance(v, list) and v and all(isinstance(x, tuple) and len(x) == 2 for x in v):
                windows = [tuple(x) for x in v]
        if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.Mult) and isinstance(sub.left, ast.Constant) \
                and isinstance(sub.left.value, float):
            sigmas.add(float(sub.left.value))
    return {"calls": calls, "check_calls": check_calls, "windows": windows, "sigmas": sigmas}


# ---------------------------------------------------------------- bridge
def bridge(claim: dict[str, Any], used: dict[str, Any]) -> list[str]:
    """Mismatches between the stated claim and the parameters actually used ([] = bridge ok)."""
    bad: list[str] = []
    if claim["kind"] == "compose":
        alias = claim.get("alias") or {}
        want = {alias.get(c, c) for c in claim["components"]}
        if used["check_calls"] != want:
            bad.append(f"components_used={sorted(used['check_calls'])}!=claimed={sorted(want)}")
        return bad
    from colony import instrument_checks as ic
    gaps, t = claim["gaps"], claim["template"]
    calls = used["calls"]
    if not calls:
        return ["no_instrument_call"]
    if any(c["gaps"] != gaps for c in calls):
        bad.append(f"gaps_used={sorted({c['gaps'] for c in calls if c['gaps']})}!=claimed={gaps}")
    if claim.get("doc_gaps") is not None and claim["doc_gaps"] != gaps:
        bad.append(f"doc_gaps={claim['doc_gaps']}!=name_gaps={gaps}")
    wins = used["windows"]
    if not wins:
        bad.append("no_windows")
    else:
        if claim.get("doc_windows") is not None and wins != claim["doc_windows"]:
            bad.append("windows!=docstring")
        if wins[0][0] != 10_000_000 * claim["w"]:
            bad.append(f"window_base={wins[0][0]}!=w{claim['w']}")
        if any(b <= a for a, b in wins) or any(wins[i][1] > wins[i + 1][0] for i in range(len(wins) - 1)):
            bad.append("windows_not_disjoint_increasing")
    fns = {c["fn"] for c in calls}
    if t == "hl_within":
        if fns != {"sieve_count", "sieve_hl"}:
            bad.append(f"hl_within_calls={sorted(fns)}")
        if claim.get("doc_sigma") is not None and used["sigmas"] and claim["doc_sigma"] not in used["sigmas"]:
            bad.append(f"sigma_used={sorted(used['sigmas'])}!=claimed={claim['doc_sigma']}")
    elif t == "residue_bal":
        mods = {c["mod"] for c in calls}
        res = tuple(sorted(c["residue"] for c in calls if c["residue"] is not None))
        if len(mods) != 1 or None in mods:
            bad.append(f"mods_used={sorted(m for m in mods if m is not None)}")
        else:
            m = mods.pop()
            if tuple(sorted(ic._residues(gaps, m))) != res:
                bad.append(f"classes_used={res}!=admissible={tuple(ic._residues(gaps, m))} mod {m}")
            if claim.get("doc_mod") is not None and (claim["doc_mod"][0] != m or tuple(sorted(claim["doc_mod"][1])) != res):
                bad.append("mod/classes!=docstring")
    elif t == "two_counter":
        backends = [c["backend"] for c in calls]
        if len(calls) < 2 or "python" not in backends or all(b == "python" for b in backends):
            bad.append(f"two_counter_backends={backends}")
    return bad


# ---------------------------------------------------------------- mutants (must be rejected)
def _mutants(claim: dict[str, Any], used: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    import copy
    out: list[tuple[str, dict[str, Any]]] = []
    if claim["kind"] == "compose":
        a, b = claim["components"]
        u = copy.deepcopy(used); u["check_calls"] = {a, "other_lemma_x"}
        out.append(("swap_component", u))
        u = copy.deepcopy(used); u["check_calls"] = {a}
        out.append(("drop_component", u))
        return out
    gaps = claim["gaps"]
    other = tuple(g + 2 for g in gaps)
    u = copy.deepcopy(used)
    for c in u["calls"]:
        c["gaps"] = other
    out.append(("other_gaps", u))
    if used["windows"]:
        u = copy.deepcopy(used); u["windows"] = [(a + 1_000_000, b + 1_000_000) for a, b in used["windows"]]
        out.append(("shifted_windows", u))
    if claim["template"] == "residue_bal":
        u = copy.deepcopy(used)
        if u["calls"]:
            u["calls"][-1]["residue"] = (u["calls"][-1]["residue"] or 0) + 1
        out.append(("wrong_class", u))
    if claim["template"] == "two_counter":
        u = copy.deepcopy(used)
        for c in u["calls"]:
            c["backend"] = None
        out.append(("same_backend_twice", u))
    if claim["template"] == "hl_within":
        u = copy.deepcopy(used); u["calls"] = [c for c in u["calls"] if c["fn"] != "sieve_hl"]
        out.append(("no_forecast", u))
    return out


def _catalog_alias(tree: ast.Module) -> dict[str, str]:
    """catalog lemma name -> the check function it runs (minus ``check_``), e.g. cassini -> cassini_identity."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Tuple) and len(node.elts) >= 2 and isinstance(node.elts[0], ast.Constant)
                and isinstance(node.elts[0].value, str)):
            continue
        ref = node.elts[1]
        if isinstance(ref, ast.Name) and ref.id.startswith("check_"):
            out.setdefault(node.elts[0].value, ref.id[len("check_"):])
        elif isinstance(ref, ast.Lambda):  # ("cassini", lambda: all(check_cassini_identity(n) ...), True)
            fns = {c.func.id for c in ast.walk(ref) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                   and c.func.id.startswith("check_")}
            if len(fns) == 1:
                out.setdefault(node.elts[0].value, next(iter(fns))[len("check_"):])
    return out


def _find_fn(name: str) -> tuple[ast.FunctionDef | None, str]:
    try:
        from colony.lessons import BENCH_ARTIFACTS_DIR
    except Exception:  # noqa: BLE001
        return None, ""
    for path in sorted(Path(BENCH_ARTIFACTS_DIR).glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == f"check_{name}":
                node._colony_alias = _catalog_alias(tree)  # type: ignore[attr-defined]
                return node, str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    return None, ""


def assess(name: str, fn: ast.FunctionDef | None = None) -> dict[str, Any]:
    if fn is None:
        fn, art = _find_fn(name)
    else:
        art = ""
    if fn is None:
        return {"mutation": name, "status": "unbridged", "reason": "check source not found"}
    claim = stated_claim(name, ast.get_docstring(fn) or "")
    if claim is None:
        return {"mutation": name, "status": "unbridged", "reason": "no claim parser for this check family"}
    if claim["kind"] == "compose":
        claim["alias"] = getattr(fn, "_colony_alias", {}) or {}
    used = used_params(fn)
    bad = bridge(claim, used)
    leaked = [label for label, u in _mutants(claim, used) if not bridge(claim, u)]
    status = "ok" if not bad and not leaked else "would_reject"
    return {"mutation": name, "status": status, "family": claim["kind"],
            "template": claim.get("template"), "mismatches": bad,
            "mutants_tested": len(_mutants(claim, used)), "mutants_not_rejected": leaked, "artifact": art}


def report(*, mutation: str, kind: str, oracle_passed: bool, cycle_id: str = "") -> dict[str, Any] | None:
    """Log the bridge result for one Oracle verdict. Report-only; never raises; never alters verdicts."""
    try:
        from colony.trust.flags import semantic_bridge_enabled
        if not semantic_bridge_enabled() or not (mutation or "").startswith("authored_"):
            return None
        row = assess(mutation)
        row.update(ts=_utc(), cycle_id=cycle_id, kind=kind, oracle_passed=bool(oracle_passed),
                   mode="report_only")
        try:
            st = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            st = {"version": 1, "totals": {}, "rows": []}
        tot = st.setdefault("totals", {})
        tot[row["status"]] = int(tot.get(row["status"], 0)) + 1
        if row["status"] == "would_reject" and oracle_passed:
            tot["would_reject_on_oracle_pass"] = int(tot.get("would_reject_on_oracle_pass", 0)) + 1
        st["rows"] = (st.get("rows") or [])[-(KEEP_ROWS - 1):] + [row]
        st["updated_at"] = row["ts"]
        st["note"] = ("REPORT-ONLY semantic bridge: claim vs parameters + mutants that must fail. "
                      "Never kills or changes an Oracle verdict.")
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(st, indent=2, default=list) + "\n", encoding="utf-8")
        return row
    except Exception:  # noqa: BLE001
        return None
