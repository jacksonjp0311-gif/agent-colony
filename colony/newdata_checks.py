"""COLONY_NEWDATA=live: verified beyond-frontier terms become authored checks the Oracle judges.

A claim in society/frontier/claims.json (computed past the OEIS frontier by method A and recomputed
by an independent method B) becomes a DISABLED hard check ``term = value`` on three consecutive new
terms. The check recomputes each term through the bridge ``newdata_term`` (method B, from scratch,
no stored data), so the Oracle judges it by recomputation. Same desk path as every authored check;
nothing here enables, scores or authorizes anything; the Oracle is unchanged. One in flight at a time.
"""
from __future__ import annotations

import json
from typing import Any

PREFIX = "authored_newdata_"
BRIDGE_MARKER = "# --- new-data bridge (colony.new_data) ---"
BRIDGE_SRC = f'''{BRIDGE_MARKER}
def newdata_term(key, n):
    """Bridge to colony.new_data: term n (colony indexing) of menu sequence ``key``, recomputed from
    scratch by the independent method B. Bounded recomputation, not proof of novelty."""
    from colony import new_data as _nd
    return int(_nd.MENU[str(key)]["b"]([int(n)])[0])
'''
BRIDGE_FNS = ("newdata_term",)
N_TERMS = 3


def ensure_bridges(src: str, marker: str) -> str:
    if BRIDGE_MARKER in src or marker not in src:
        return src
    return src.replace(marker, BRIDGE_SRC + "\n\n" + marker, 1)


def check_name(c: dict[str, Any]) -> str:
    return f"{PREFIX}{c['anum'].lower()}_k{c['k_range'][0]}_w1"


def build(c: dict[str, Any]) -> dict[str, Any] | None:
    import ast
    from colony.new_data import ROOT
    if c.get("op") != "terms" or c.get("label") != "computed beyond published frontier (verified 2 ways)":
        return None
    key = c["item"].split(":")[0]
    data = ROOT / c["data_file"]
    try:
        rows = [tuple(int(x) for x in ln.split()) for ln in data.read_text(encoding="utf-8").splitlines()
                if ln and not ln.startswith("#")]
    except Exception:  # noqa: BLE001
        return None
    d = int(c.get("d") or 0)
    pick = [(k - d, v) for k, v in rows if c["k_range"][0] <= k <= c["k_range"][1]][:N_TERMS]
    if len(pick) < N_TERMS:
        return None
    name = check_name(c)
    expr = f"all(type(x := newdata_term({key!r}, n)) is int and x == v for n, v in {pick!r})"
    try:
        body = ast.parse(expr, mode="eval").body
    except SyntaxError:
        return None
    ks = [k + d for k, _ in pick]
    fn_src = (
        f"def check_{name}() -> bool:\n"
        f'    """Authored new-data check (desk): {c["anum"]} terms a({ks[0]})..a({ks[-1]}) computed past the\n'
        f"    OEIS frontier ({c['frontier_source']}, checked {c['checked']}) by {c['methods'][0]};\n"
        f"    recomputed here by {c['methods'][1]}. New data, not a theorem; papers may go further.\n"
        f'    Disabled until the Oracle passes it.\n'
        f'    """\n'
        f"    return {expr}\n"
    )
    return {"name": name, "fn_src": fn_src, "body": body, "expr": expr, "components": [],
            "verify_fns": list(BRIDGE_FNS), "evidence": ["colony/new_data.py", f"oeis:{c['anum']}", c["data_file"]],
            "source": "newdata",
            "what": f"authored disabled new-data check `{name}`: {c['anum']} a({ks[0]}..{ks[-1]}) past the OEIS b-file"}


def candidates(existing_names: set[str], limit: int = 3) -> list[dict[str, Any]]:
    from colony.new_data import CLAIMS, _load
    out = []
    for c in sorted((_load(CLAIMS, {}).get("claims") or []), key=lambda c: c.get("ts") or ""):
        if check_name(c) in existing_names:
            continue
        b = build(c)
        if b:
            out.append(b)
        if len(out) >= limit:
            break
    return out


def pending(src: str) -> list[str]:
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


_SELF: dict[str, Any] = {}


def self_test(force: bool = False) -> dict[str, Any]:
    """Method A and method B agree on small ranges for every menu item, and the first published terms
    of A002375 / A006577 / A047160 are reproduced (hard-coded from the OEIS). Fail closed."""
    if _SELF and not force:
        return dict(_SELF)
    try:
        from colony import new_data as N
        checks = {}
        for k, m in N.MENU.items():
            a = m["a"](80)
            checks[k] = a == m["b"](list(range(1, 81)))
        checks["A002375"] = N.MENU["gb_u_odd"]["a"](12) == [0, 0, 1, 1, 2, 1, 2, 2, 2, 2, 3, 3]
        checks["A006577"] = N.MENU["col_steps"]["a"](10) == [0, 1, 7, 2, 5, 8, 16, 3, 19, 6]
        checks["A047160"] = N.MENU["gb_close"]["a"](12)[1:] == [0, 0, 1, 0, 1, 0, 3, 2, 3, 0, 1]
        res = {"ok": all(checks.values()), "checks": checks}
    except Exception as exc:  # noqa: BLE001
        res = {"ok": False, "checks": {}, "error": str(exc)[:200]}
    _SELF.clear()
    _SELF.update(res)
    return dict(res)


def newdata_links(fn_node: Any, artifact_src: str) -> list[dict[str, Any]]:
    import ast
    called = [f for f in BRIDGE_FNS if any(isinstance(s, ast.Call) and isinstance(s.func, ast.Name)
                                           and s.func.id == f for s in ast.walk(fn_node))]
    if not called:
        return []
    bridged = BRIDGE_MARKER in artifact_src and all(f"def {f}(" in artifact_src for f in called)
    ok = bridged and bool(self_test().get("ok"))
    return [{"lemma": f"newdata:{f}", "function": f, "proven": ok, "source": "colony/new_data.py"} for f in called]
