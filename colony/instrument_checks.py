"""Instrument-backed authored checks: let the desk write hard checks that CALL colony instruments.

Mechanism (no hardcoded targets): admissible gap tuples are enumerated from small even gaps,
and three claim templates are instantiated on disjoint, capped windows:

- hl_within   : count of consecutive-prime pattern T on each window is within K_SIGMA*sqrt(HL)
                of the Hardy-Littlewood forecast (conjectural heuristic; a failure is informative)
- residue_bal : the residue classes of p mod M (M in {4, 3}) that the pattern can occupy are
                balanced to within K_SIGMA*sqrt(total) on each window
- two_counter : the C/primesieve counter and the independent pure-Python counter agree exactly

Each candidate goes through the SAME desk path as every authored check (colony.authoring):
inserted DISABLED, verified in a subprocess (must hold, every bridge evaluated >= MIN_EVALS
times, falsifiable when a bridge is forced False, inside RUNTIME_BUDGET_S), and only the Oracle
can later pass it via a proposal. Nothing here enables, scores or authorizes anything.
"""
from __future__ import annotations

import ast
import itertools
from typing import Any

PREFIX = "authored_sieve_"
K_SIGMA = 4.0
WINDOW = 2_000_000          # span per window (C backend: milliseconds)
PY_WINDOW = 50_000          # span per window for the pure-Python counter (kept small: bench time)
N_WINDOWS = 3
MAX_TUPLE_LEN = 3
GAP_CHOICES = (2, 4, 6)
TEMPLATES = ("hl_within", "residue_bal", "two_counter")

BRIDGE_MARKER = "# --- instrument bridges (colony.instruments.sieve) ---"
BRIDGE_SRC = f'''{BRIDGE_MARKER}
def sieve_count(gaps, a, b, mod=1, residue=None, backend="auto"):
    """Bridge to colony.instruments.sieve.count_pattern (capped). Returns an int count."""
    from colony.instruments import sieve as _s
    r = _s.count_pattern(list(gaps), int(a), int(b), mod=int(mod), backend=backend)
    return int(r["total"] if residue is None else r["by_residue"].get(int(residue), 0))


def sieve_hl(gaps, a, b):
    """Bridge to the Hardy-Littlewood consecutive forecast (conjectural heuristic). Returns a float."""
    from colony.instruments import sieve as _s
    return float(_s.hl_predict(list(gaps), int(a), int(b), prime_limit=200_000, steps=400)["prediction"])
'''
BRIDGE_FNS = ("sieve_count", "sieve_hl")


def ensure_bridges(src: str, marker: str) -> str:
    if BRIDGE_MARKER in src or marker not in src:
        return src
    return src.replace(marker, BRIDGE_SRC + "\n\n" + marker, 1)


def gap_tuples() -> list[tuple[int, ...]]:
    from colony.instruments.sieve import _offsets, is_admissible
    out = []
    for n in range(1, MAX_TUPLE_LEN + 1):
        for g in itertools.product(GAP_CHOICES, repeat=n):
            if is_admissible(_offsets(g)):
                out.append(g)
    return out


def _residues(gaps: tuple[int, ...], m: int) -> list[int]:
    """Classes r (mod m) a large pattern prime can occupy: every member coprime to m."""
    from math import gcd
    offs = [0] + list(itertools.accumulate(gaps))
    return [r for r in range(m) if all(gcd(r + h, m) == 1 for h in offs)]


def _sig(gaps: tuple[int, ...]) -> str:
    return "g" + "_".join(str(g) for g in gaps)


def _windows(w: int, span: int) -> list[tuple[int, int]]:
    base = 10_000_000 * w
    return [(base + i * span, base + (i + 1) * span) for i in range(N_WINDOWS)]


def build(template: str, gaps: tuple[int, ...], w: int) -> dict[str, Any] | None:
    g = repr(tuple(gaps))
    name = f"{PREFIX}{template}_{_sig(gaps)}_w{w}"
    if template == "hl_within":
        wins = _windows(w, WINDOW)
        expr = (f"all(type(c := sieve_count({g}, a, b)) is int and type(h := sieve_hl({g}, a, b)) is float "
                f"and h > 0 and abs(c - h) <= {K_SIGMA} * h ** 0.5 for a, b in {wins!r})")
        claim = f"count of consecutive pattern {gaps} on each window is within {K_SIGMA}*sqrt of the HL forecast"
        fns = ["sieve_count", "sieve_hl"]
    elif template == "residue_bal":
        m = next((m for m in (4, 3) if len(_residues(gaps, m)) == 2), None)
        if m is None:
            return None
        r1, r2 = _residues(gaps, m)
        wins = _windows(w, WINDOW)
        expr = (f"all(type(x := sieve_count({g}, a, b, {m}, {r1})) is int and type(y := sieve_count({g}, a, b, {m}, {r2})) is int "
                f"and x + y > 0 and abs(x - y) <= {K_SIGMA} * (x + y) ** 0.5 for a, b in {wins!r})")
        claim = f"p mod {m} classes {r1}/{r2} of pattern {gaps} are balanced within {K_SIGMA}*sqrt(total)"
        fns = ["sieve_count"]
    elif template == "two_counter":
        wins = _windows(w, PY_WINDOW)
        expr = (f"all(type(c := sieve_count({g}, a, b)) is int and c > 0 and "
                f"c == sieve_count({g}, a, b, backend='python') for a, b in {wins!r})")
        claim = f"C/primesieve and pure-Python counters agree exactly on pattern {gaps}"
        fns = ["sieve_count"]
    else:
        return None
    body = ast.parse(expr, mode="eval").body
    fn_src = (
        f"def check_{name}() -> bool:\n"
        f'    """Authored instrument check (desk): {claim}.\n'
        f"    Windows {wins} (disjoint, capped). Uses colony.instruments.sieve via the bridges\n"
        f"    sieve_count / sieve_hl. HL is a conjectural heuristic; counts are bounded evidence, not proof.\n"
        f'    Disabled until the Oracle passes it.\n'
        f'    """\n'
        f"    return {expr}\n"
    )
    return {"name": name, "fn_src": fn_src, "body": body, "expr": expr, "components": [],
            "verify_fns": fns, "evidence": ["colony/instruments/sieve.py", f"pattern:{gaps}", f"template:{template}"],
            "source": "instrument", "template": template, "gaps": list(gaps),
            "what": f"authored disabled instrument check `{name}`: {claim}; awaits Oracle via proposal"}


def _uses(existing_names: set[str], template: str, gaps: tuple[int, ...]) -> int:
    return sum(1 for n in existing_names if n.startswith(f"{PREFIX}{template}_{_sig(gaps)}_w"))


def candidates(existing_names: set[str], limit: int = 12) -> list[dict[str, Any]]:
    """Rotate across gap patterns before re-windowing one.

    Order key per (template, pattern): windows already written for that pair, then how often
    the pattern has been used under ANY template (so a new pattern beats a new window of an
    old one), then least-used template, then enumeration order. Window index advances past
    used ones.
    """
    try:
        tuples = gap_tuples()
    except Exception:
        return []
    names = set(existing_names)
    t_used = {t: sum(1 for n in names if n.startswith(f"{PREFIX}{t}_")) for t in TEMPLATES}
    pairs = []
    for ti, t in enumerate(TEMPLATES):
        for gi, gaps in enumerate(tuples):
            pair_n = _uses(names, t, gaps)
            pat_n = sum(_uses(names, tt, gaps) for tt in TEMPLATES)
            pairs.append(((pair_n, pat_n, t_used[t], gi, ti), t, gaps, pair_n + 1))
    pairs.sort(key=lambda r: r[0])
    out = []
    for _k, t, gaps, w in pairs:
        c = build(t, gaps, w)
        if c:
            out.append(c)
        if len(out) >= limit:
            break
    return out


def _catalog_flags(src: str) -> dict[str, bool | None]:
    """catalog name -> enabled flag, read from source (never executed)."""
    out: dict[str, bool | None] = {}
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.Tuple) and len(node.elts) >= 3 and isinstance(node.elts[0], ast.Constant) \
                and isinstance(node.elts[0].value, str) and isinstance(node.elts[2], ast.Constant):
            v = node.elts[2].value
            out[node.elts[0].value] = v if isinstance(v, bool) else None
    return out


def oracle_judged(names: set[str] | None = None) -> set[str]:
    """Mutation names that already have an Oracle verdict row (pass or kill)."""
    try:
        from colony.oracle import ORACLE_LOG
    except Exception:
        return set()
    out: set[str] = set()
    if not ORACLE_LOG.exists():
        return out
    import json
    for ln in ORACLE_LOG.read_text(encoding="utf-8").splitlines():
        if PREFIX not in ln:
            continue
        try:
            m = str(json.loads(ln).get("mutation") or "")
        except Exception:
            continue
        if m.startswith(PREFIX) and (names is None or m in names):
            out.add(m)
    return out


def pending(src: str) -> list[str]:
    """Instrument checks written but still DISABLED with no Oracle verdict yet (awaiting judgment).

    While any exist the desk must not author another instrument check (no slot burn). A check
    the Oracle killed is no longer pending; cooled names (kill cooldown / guide avoid) neither.
    """
    flags = _catalog_flags(src)
    disabled = {n for n, f in flags.items() if n.startswith(PREFIX) and f is False}
    if not disabled:
        return []
    judged = oracle_judged(disabled)
    try:
        from colony.lessons import mutation_cooldown
        cd = mutation_cooldown()
        cooled = {n for n in disabled if not cd.allows(n)}
    except Exception:
        cooled = set()
    return sorted(disabled - judged - cooled)


_SELF_TEST: dict[str, Any] = {}


def _brute_pattern(gaps: tuple[int, ...], a: int, b: int) -> int:
    """Independent reference: trial division, consecutive primes p in [a, b) with the given gaps."""
    def isp(n: int) -> bool:
        if n < 2:
            return False
        i = 2
        while i * i <= n:
            if n % i == 0:
                return False
            i += 1
        return True
    span = sum(gaps)
    ps = [n for n in range(max(2, a), b + span + 200) if isp(n)]
    c = 0
    for i, p in enumerate(ps):
        if p >= b:
            break
        if p < a or i + len(gaps) >= len(ps):
            continue
        if all(ps[i + j + 1] - ps[i + j] == g for j, g in enumerate(gaps)):
            c += 1
    return c


def self_test(force: bool = False) -> dict[str, Any]:
    """The instrument's own tests: counts vs an independent trial-division reference on small
    ranges, C/Python backend agreement when C is present, and a finite positive HL forecast.
    Cached per process. Any exception or mismatch => ok False (fail closed).
    """
    if _SELF_TEST and not force:
        return dict(_SELF_TEST)
    res: dict[str, Any] = {"ok": False, "checks": {}}
    try:
        from colony.instruments import sieve as _s
        checks: dict[str, bool] = {}
        for gaps, (a, b) in (((2,), (3, 20000)), ((2, 4), (5, 20000)), ((6,), (1000, 30000))):
            ref = _brute_pattern(gaps, a, b)
            py = int(_s.count_pattern(list(gaps), a, b, backend="python")["total"])
            checks[f"python_vs_reference:{_sig(gaps)}"] = py == ref and ref > 0
            if _s._helper() is not None:
                cc = int(_s.count_pattern(list(gaps), a, b, backend="c")["total"])
                checks[f"c_vs_python:{_sig(gaps)}"] = cc == py
        hl = float(_s.hl_predict([2], 10 ** 6, 2 * 10 ** 6, prime_limit=20_000, steps=200)["prediction"])
        checks["hl_finite_positive"] = hl > 0 and hl == hl and hl != float("inf")
        res = {"ok": all(checks.values()), "checks": checks}
    except Exception as exc:  # noqa: BLE001
        res = {"ok": False, "checks": {}, "error": str(exc)[:200]}
    _SELF_TEST.clear()
    _SELF_TEST.update(res)
    return dict(res)


def instrument_links(fn_node: Any, artifact_src: str) -> list[dict[str, Any]]:
    """Cite links for a disabled instrument check: one link per bridge it calls.

    A link is ``proven`` only when the bridge is present in the artifact AND the instrument's
    own self_test passes. Returns [] when the check calls no bridge (not instrument-sourced).
    """
    called = []
    for sub in ast.walk(fn_node):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id in BRIDGE_FNS:
            if sub.func.id not in called:
                called.append(sub.func.id)
    if not called:
        return []
    bridged = BRIDGE_MARKER in artifact_src and all(f"def {f}(" in artifact_src for f in called)
    ok = bridged and bool(self_test().get("ok"))
    return [{"lemma": f"instrument:sieve.{f}", "function": f, "proven": ok,
             "source": "colony/instruments/sieve.py"} for f in called]
    return out
