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


def candidates(existing_names: set[str], limit: int = 6, state: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Surprises not yet authored, highest hunt value first (the colony's own ranking)."""
    from colony.frontier_conjectures import load_state
    st = state if state is not None else load_state()
    reg = [r for r in (st.get("registry") or {}).values()
           if r.get("unknown") and not r.get("falsified_later") and r.get("sig")]
    reg.sort(key=lambda r: (-(r.get("hunt_value") or 0), r.get("found_at") or ""))
    out = []
    for r in reg:
        if check_name(r) in existing_names:
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
