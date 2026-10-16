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
PY_WINDOW = 200_000         # span per window for the pure-Python counter
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


def candidates(existing_names: set[str], limit: int = 12) -> list[dict[str, Any]]:
    """Least-used template first, then shortest tuples; window index advances past used ones."""
    try:
        tuples = gap_tuples()
    except Exception:
        return []
    used = {t: sum(1 for n in existing_names if n.startswith(f"{PREFIX}{t}_")) for t in TEMPLATES}
    out = []
    for t in sorted(TEMPLATES, key=lambda t: (used[t], TEMPLATES.index(t))):
        for gaps in tuples:
            w = 1 + sum(1 for n in existing_names if n.startswith(f"{PREFIX}{t}_{_sig(gaps)}_w"))
            c = build(t, gaps, w)
            if c:
                out.append(c)
            if len(out) >= limit:
                return out
    return out
