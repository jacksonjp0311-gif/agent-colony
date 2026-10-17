"""COLONY_FRONTIER=live: the colony's own surviving frontier conjectures become authored checks.

Each candidate is a SURPRISE from colony.frontier_conjectures (survived held-out falsification,
not a trivial rewrite, not a duplicate, involved derived sequence not in the OEIS index), turned
into a disabled hard check that re-tests the claim on three disjoint windows of n through the
bridge ``frontier_holds``. It goes through the SAME desk path as every authored check
(colony.authoring): inserted DISABLED, verified in a subprocess (must hold, bridge evaluated on
every window, falsifiable when the bridge is forced False, inside the runtime budget) and only
the Oracle can later pass it via a proposal. Nothing here enables, scores or authorizes anything,
and the Oracle is unchanged. One frontier check in flight at a time (no slot burn).
"""
from __future__ import annotations

import json
from typing import Any

PREFIX = "authored_frontier_"
BRIDGE_MARKER = "# --- frontier bridge (colony.frontier_conjectures) ---"
BRIDGE_SRC = f'''{BRIDGE_MARKER}
def frontier_holds(claim, a, b):
    """Bridge to colony.frontier_conjectures.holds_on: checks done when the self-chosen
    conjecture holds for every n in [a, b], else 0. Bounded evidence, not proof."""
    from colony import frontier_conjectures as _f
    return int(_f.holds_on(claim, int(a), int(b)))
'''
BRIDGE_FNS = ("frontier_holds",)
CHEAP_HI = 6000
EXP_HI = 900


def ensure_bridges(src: str, marker: str) -> str:
    if BRIDGE_MARKER in src or marker not in src:
        return src
    return src.replace(marker, BRIDGE_SRC + "\n\n" + marker, 1)


def check_name(r: dict[str, Any]) -> str:
    return f"{PREFIX}{r['kind']}_x{(r.get('sig') or '0' * 8)[:8]}_w1"


def windows(r: dict[str, Any]) -> list[tuple[int, int]]:
    from colony.frontier_conjectures import EXPO, parse, prims_of
    ps = prims_of(parse(r["lhs"])) | (prims_of(parse(r["rhs"])) if r.get("rhs") else set())
    hi = EXP_HI if ps & set(EXPO) else CHEAP_HI
    lo = 40
    step = (hi - lo) // 3
    return [(lo + i * step + 1, lo + (i + 1) * step) for i in range(3)]


def build(r: dict[str, Any]) -> dict[str, Any] | None:
    import ast
    name = check_name(r)
    claim = {"kind": r["kind"], "lhs": r["lhs"], "rhs": r.get("rhs") or "", "params": r.get("params") or {}}
    wins = windows(r)
    lit = repr(dict(sorted(claim.items())))
    expr = f"all(type(c := frontier_holds({lit}, a, b)) is int and c > 0 for a, b in {wins!r})"
    try:
        body = ast.parse(expr, mode="eval").body
    except SyntaxError:
        return None
    stmt = str(r.get("statement") or "").replace('"""', "'")
    fn_src = (
        f"def check_{name}() -> bool:\n"
        f'    """Authored frontier check (desk): the colony\'s own conjecture\n'
        f"    {stmt}\n"
        f"    re-tested on windows {wins}. {r.get('label')}. Bounded evidence, not proof.\n"
        f'    Disabled until the Oracle passes it.\n'
        f'    """\n'
        f"    return {expr}\n"
    )
    return {"name": name, "fn_src": fn_src, "body": body, "expr": expr, "components": [],
            "verify_fns": list(BRIDGE_FNS), "evidence": ["colony/frontier_conjectures.py", f"claim:{r['statement']}"],
            "source": "frontier",
            "what": f"authored disabled frontier check `{name}`: {r['statement']}; awaits Oracle via proposal"}


def still_new(r: dict[str, Any]) -> bool:
    """Re-screen a registry surprise with the CURRENT rewrite filters (they get stricter over time)."""
    import random
    from colony import frontier_conjectures as FC
    try:
        if FC._BRIDGE_T is None:
            FC._BRIDGE_T = FC.Tables(lim=FC.BRIDGE_LIM, exp_n=FC.BRIDGE_EXP)
        c = {"kind": r["kind"], "params": r.get("params") or {}, "_le": FC.parse(r["lhs"]),
             "_re": FC.parse(r["rhs"]) if r.get("rhs") else None}
        if r.get("loose"):
            return False
        return FC.trivial_reason(c, FC._BRIDGE_T, random.Random(r.get("sig") or "x"), FC.fit_n()) == ""
    except Exception:  # noqa: BLE001
        return False


def candidates(existing_names: set[str], limit: int = 6, state: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Surprises not yet authored, highest hunt value first (the colony's own ranking)."""
    from colony.frontier_conjectures import load_state
    st = state if state is not None else load_state()
    reg = [r for r in (st.get("registry") or {}).values()
           if r.get("unknown") and not r.get("falsified_later") and r.get("sig")]
    reg.sort(key=lambda r: (-(r.get("hunt_value") or 0), r.get("found_at") or ""))
    out = []
    for r in reg:
        if check_name(r) in existing_names or not still_new(r):
            continue
        c = build(r)
        if c:
            out.append(c)
        if len(out) >= limit:
            break
    return out


def pending(src: str) -> list[str]:
    """Frontier checks written but still disabled with no Oracle verdict (one in flight at a time)."""
    from colony.instrument_checks import _catalog_flags
    flags = _catalog_flags(src)
    disabled = {n for n, f in flags.items() if n.startswith(PREFIX) and f is False}
    if not disabled:
        return []
    judged: set[str] = set()
    try:
        from colony.oracle import ORACLE_LOG
        for ln in ORACLE_LOG.read_text(encoding="utf-8").splitlines():
            if PREFIX in ln:
                m = str(json.loads(ln).get("mutation") or "")
                if m in disabled:
                    judged.add(m)
    except Exception:  # noqa: BLE001
        pass
    try:
        from colony.lessons import mutation_cooldown
        cd = mutation_cooldown()
        cooled = {n for n in disabled if not cd.allows(n)}
    except Exception:  # noqa: BLE001
        cooled = set()
    return sorted(disabled - judged - cooled)


_SELF_TEST: dict[str, Any] = {}


def self_test(force: bool = False) -> dict[str, Any]:
    """The frontier engine's own tests against independent brute force on small n (primitive
    tables, the claim checker on a known-true and a known-false claim). Fail closed."""
    if _SELF_TEST and not force:
        return dict(_SELF_TEST)
    import math
    res: dict[str, Any] = {"ok": False, "checks": {}}
    try:
        from colony import frontier_conjectures as FC
        T = FC.Tables(lim=3000, exp_n=60)
        t = T.t
        divs = lambda n: [d for d in range(1, n + 1) if n % d == 0]  # noqa: E731
        isp = lambda n: n > 1 and all(n % d for d in range(2, int(n ** 0.5) + 1))  # noqa: E731

        def mu(n):
            ps = [p for p in range(2, n + 1) if n % p == 0 and isp(p)]
            return 0 if any(n % (p * p) == 0 for p in ps) else (-1) ** len(ps)

        def part(n, k=None):
            k = n if k is None else k
            return 1 if n == 0 else sum(part(n - j, j) for j in range(1, min(n, k) + 1))
        rng = range(1, 400)
        checks = {
            "phi": all(t["phi"][n] == sum(1 for k in range(1, n + 1) if math.gcd(n, k) == 1) for n in rng),
            "sigma_tau": all(t["sigma"][n] == sum(divs(n)) and t["tau"][n] == len(divs(n)) for n in rng),
            "mu": all(t["mu"][n] == mu(n) for n in range(1, 200)),
            "prime_pi": t["prime"][1:30] == [p for p in range(2, 200) if isp(p)][:29]
                        and all(t["pi"][n] == sum(1 for p in range(2, n + 1) if isp(p)) for n in range(1, 300)),
            "fib": all(t["fib"][n + 2] == t["fib"][n + 1] + t["fib"][n] for n in range(1, 50)),
            "partitions": all(t["part"][n] == part(n) for n in range(1, 25)),
            "true_claim_holds": FC.holds_on({"kind": "le", "lhs": "phi", "rhs": "n", "params": {}}, 1, 2000) > 0,
            "false_claim_fails": FC.holds_on({"kind": "le", "lhs": "pi", "rhs": "(one+tau)", "params": {}}, 1, 2000) == 0,
        }
        res = {"ok": all(checks.values()), "checks": checks}
    except Exception as exc:  # noqa: BLE001
        res = {"ok": False, "checks": {}, "error": str(exc)[:200]}
    _SELF_TEST.clear()
    _SELF_TEST.update(res)
    return dict(res)


def frontier_links(fn_node: Any, artifact_src: str) -> list[dict[str, Any]]:
    """Cite links for a disabled frontier check: proven only when the bridge is present in the
    artifact AND the engine's own self_test passes (same rule as instrument checks)."""
    import ast
    called = [f for f in BRIDGE_FNS if any(isinstance(s, ast.Call) and isinstance(s.func, ast.Name)
                                           and s.func.id == f for s in ast.walk(fn_node))]
    if not called:
        return []
    bridged = BRIDGE_MARKER in artifact_src and all(f"def {f}(" in artifact_src for f in called)
    ok = bridged and bool(self_test().get("ok"))
    return [{"lemma": f"frontier:{f}", "function": f, "proven": ok, "source": "colony/frontier_conjectures.py"}
            for f in called]
