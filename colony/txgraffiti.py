"""Item 109: TxGraffiti-style bound / relation generators (James 2026-11-16: "Evolve and expand the swarms").

After the Graffiti / TxGraffiti line of automated conjecturing (reference only:
github.com/RandyRDavila/TxGraffiti2; reimplemented here, nothing fetched or run). Objects are the
indices n of integer sequences; invariants are exact integer sequences:
  * built-in classical tables (n, n^2, 2^n, n!, Fibonacci, Lucas, Catalan, central binomial, Motzkin,
    sigma, tau, phi) evaluated by colony/oeis_definitions.py's own functions, and
  * every OEIS menu entry with a SOUND definition or an Oracle-passed hard-tier family, using its
    stored b-file terms (the colony's OEIS tables / passed checks).
Generators, for every ordered pair (Y, X) on a TRAINING range n0..N_train:
  * ratio:  Y >= c_lo * X  and  Y <= c_hi * X, with c = min / max of Y/X (exact Fractions);
  * hull:   the convex hull of the points (X(n), Y(n)); each upper (lower) hull edge gives
            Y <= m X + q  (Y >= m X + q), exact rational m, q.
Pre-filter (before any check, TxGraffiti's triviality controls):
  * touch number: the bound must be attained (equality) on >= 2 training objects (>= 3 for a hull
    edge, which always touches its own two endpoints);
  * simplicity: numerators and denominators of m and q at most 10^4;
  * identical / affine-trivial: Y == X, or Y - X constant on the training range;
  * Dalmatian: a bound is kept only if it is strictly tighter than every kept bound on the same
    target and direction (including stored lemmas) on at least one object;
  * implied: a bound already implied by a stored lemma on the same pair (same direction, weaker or
    equal constant) is dropped and the lemma is CITED.
Check: the survivors are tested on a held-out range N_train < n <= N_test (exact integers). A pass
is NOT a proof: it is stored as a ``lemma`` row (status ``checked_not_proved``, with its range,
touch number and citations) in the append-only knowledge library (data/commons/knowledge_library.jsonl),
where later generator runs read it for the Dalmatian and implication filters and cite it.

Switch ``COLONY_TXGRAFFITI`` = live (default) | off; always off on the control arm. One run per cycle,
time-budgeted. Nothing here touches the Oracle, P, gates, or the desk's decisions.
"""
from __future__ import annotations

import hashlib
import math
import os
import time
from fractions import Fraction
from typing import Any, Callable

TOUCH_MIN = 2          # ratio bounds: equality on >= 2 objects
TOUCH_MIN_HULL = 3     # a hull edge always touches its 2 endpoints: needs a third collinear object
MAX_HEIGHT = 10 ** 4   # simplicity (Graffiti): numerators / denominators of m and q
N0 = 1
N_TRAIN = 40
N_TEST = 120
BUDGET_S = 8.0
MAX_LEMMAS_PER_RUN = 12


def enabled() -> bool:
    try:
        from colony.arm import self_mod_enabled
        if not self_mod_enabled():
            return False
    except Exception:  # noqa: BLE001
        return False
    return (os.environ.get("COLONY_TXGRAFFITI") or "live").strip().lower() == "live"


def _sigma(m: int) -> int:
    s, d = 0, 1
    while d * d <= m:
        if m % d == 0:
            s += d + (m // d if d * d != m else 0)
        d += 1
    return s


def _tau(m: int) -> int:
    c, d = 0, 1
    while d * d <= m:
        if m % d == 0:
            c += 2 if d * d != m else 1
        d += 1
    return c


def _phi(m: int) -> int:
    r, x, p = m, m, 2
    while p * p <= x:
        if x % p == 0:
            while x % p == 0:
                x //= p
            r -= r // p
        p += 1
    if x > 1:
        r -= r // x
    return r


def builtin_invariants() -> dict[str, Callable[[int], int]]:
    from colony import oeis_definitions as OD
    return {
        "n": lambda n: n, "n^2": lambda n: n * n, "2^n": lambda n: 2 ** n, "n!": math.factorial,
        "Fibonacci(n)": OD._fib, "Lucas(n)": OD._lucas, "Catalan(n)": OD._catalan,
        "binomial(2n,n)": lambda n: math.comb(2 * n, n), "Motzkin(n)": OD._motzkin,
        "sigma(n)": _sigma, "tau(n)": _tau, "phi(n)": _phi,
    }


def table_invariants(menu: list[dict[str, Any]], max_tables: int = 24) -> dict[str, dict[int, int]]:
    """OEIS tables: stored b-file terms of menu entries with a sound definition (by A-number)."""
    out: dict[str, dict[int, int]] = {}
    for e in menu:
        d = e.get("definition") or {}
        if not d:
            continue
        if d.get("kind") in ("xexpr", "holo") and d.get("provenance") != "name":
            continue
        off = int(e.get("offset") or 0)
        terms = list(e.get("terms") or [])
        if off + len(terms) - 1 < N_TEST:
            continue
        out[str(e.get("anum"))] = {off + i: int(v) for i, v in enumerate(terms[:N_TEST + 2])}
        if len(out) >= max_tables:
            break
    return out


def _values(inv, n: int) -> int | None:
    try:
        return int(inv(n)) if callable(inv) else inv.get(n)
    except Exception:  # noqa: BLE001
        return None


def _hull(points: list[tuple[int, int]]):
    pts = sorted(set(points))
    if len(pts) < 2:
        return [], []

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower, upper


def _edges(chain):
    out = []
    for a, b in zip(chain, chain[1:]):
        if b[0] == a[0]:
            continue
        m = Fraction(b[1] - a[1], b[0] - a[0])
        q = Fraction(a[1]) - m * a[0]
        out.append((m, q))
    return out


def lemma_id(stmt: str) -> str:
    return "lem_" + hashlib.sha256(stmt.encode()).hexdigest()[:12]


def _fmt(c: Fraction) -> str:
    return str(c.numerator) if c.denominator == 1 else "%d/%d" % (c.numerator, c.denominator)


def generate(invs: dict[str, Any], lemmas: list[dict[str, Any]] | None = None, budget_s: float = BUDGET_S,
             n0: int = N0, n_train: int = N_TRAIN, n_test: int = N_TEST) -> dict[str, Any]:
    t0 = time.time()
    lemmas = list(lemmas or [])
    names = sorted(invs)
    vals: dict[str, dict[int, int]] = {}
    for nm in names:
        row = {}
        for n in range(n0, n_test + 1):
            v = _values(invs[nm], n)
            if v is None:
                break
            row[n] = v
        if len(row) == n_test - n0 + 1:
            vals[nm] = row
    names = sorted(vals)
    train = range(n0, n_train + 1)
    test = range(n_train + 1, n_test + 1)
    stats = {"pairs": 0, "candidates": 0, "touch_filtered": 0, "trivial": 0, "dalmatian": 0, "implied": 0,
             "held_out_fail": 0, "passed": 0}
    kept: list[dict[str, Any]] = []
    # Dalmatian baselines: (target, direction) -> list of value tables of kept bounds
    base: dict[tuple[str, str], list[tuple[str, dict[int, Fraction]]]] = {}
    by_pair: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for lem in lemmas:
        if lem.get("generator") in ("ratio", "hull") and lem.get("target") in vals and lem.get("source") in vals:
            m, q = Fraction(lem["m"]), Fraction(lem["q"])
            tb = {n: m * vals[lem["source"]][n] + q for n in train}
            base.setdefault((lem["target"], lem["rel"]), []).append((lem["id"], tb))
            by_pair.setdefault((lem["target"], lem["source"], lem["rel"]), []).append(lem)
    for y in names:
        for x in names:
            if x == y or time.time() - t0 > budget_s:
                continue
            Y, X = vals[y], vals[x]
            stats["pairs"] += 1
            if all(Y[n] == X[n] for n in train) or len({Y[n] - X[n] for n in train}) == 1:
                stats["trivial"] += 1
                continue
            cands = []
            if all(X[n] > 0 for n in train):
                rs = [Fraction(Y[n], X[n]) for n in train]
                cands.append(("ratio", "<=", max(rs), Fraction(0)))
                cands.append(("ratio", ">=", min(rs), Fraction(0)))
            lower, upper = _hull([(X[n], Y[n]) for n in train])
            for m, q in _edges(upper):
                cands.append(("hull", "<=", m, q))
            for m, q in _edges(lower):
                cands.append(("hull", ">=", m, q))
            for gen, rel, m, q in cands:
                stats["candidates"] += 1
                bound = {n: m * X[n] + q for n in train}
                ok_train = all((Y[n] <= bound[n]) if rel == "<=" else (Y[n] >= bound[n]) for n in train)
                if not ok_train:
                    continue
                touch = sum(1 for n in train if Y[n] == bound[n])
                if touch < (TOUCH_MIN_HULL if gen == "hull" else TOUCH_MIN):
                    stats["touch_filtered"] += 1
                    continue
                if max(abs(m.numerator), m.denominator, abs(q.numerator), q.denominator) > MAX_HEIGHT:
                    stats["not_simple"] = stats.get("not_simple", 0) + 1
                    continue
                if m == 0 or (m == 1 and q == 0):
                    stats["trivial"] += 1
                    continue
                cites = []
                implied = None
                for lem in by_pair.get((y, x, rel), []):
                    lm, lq = Fraction(lem["m"]), Fraction(lem["q"])
                    lb = {n: lm * X[n] + lq for n in train}
                    tighter_or_equal = all((lb[n] <= bound[n]) if rel == "<=" else (lb[n] >= bound[n]) for n in train)
                    if tighter_or_equal:
                        implied = lem["id"]
                        break
                if implied:
                    stats["implied"] += 1
                    continue
                if m > 0:   # converse: y rel m*x + q  <=>  x rel' (1/m)*y - q/m  (same inequality)
                    flip = ">=" if rel == "<=" else "<="
                    if any(Fraction(lem["m"]) == 1 / m and Fraction(lem["q"]) == -q / m
                           for lem in by_pair.get((x, y, flip), [])):
                        stats["converse"] = stats.get("converse", 0) + 1
                        continue
                prev = base.get((y, rel), [])
                if prev:
                    if not any((bound[n] < min(pb[n] for _i, pb in prev)) if rel == "<=" else
                               (bound[n] > max(pb[n] for _i, pb in prev)) for n in train):
                        stats["dalmatian"] += 1
                        continue
                    cites = [i for i, _pb in prev][:6]
                if not all((Y[n] <= m * X[n] + q) if rel == "<=" else (Y[n] >= m * X[n] + q) for n in test):
                    stats["held_out_fail"] += 1
                    continue
                stmt = "%s %s %s%s%s" % (y, rel, "" if m == 1 else _fmt(m) + "*", x, ("" if q == 0 else (" + " + _fmt(q) if q > 0 else " - " + _fmt(-q))))
                row = {"event": "lemma", "id": lemma_id(stmt), "statement": stmt, "target": y, "source": x,
                       "rel": rel, "m": _fmt(m), "q": _fmt(q), "generator": gen, "touch": touch,
                       "range": [n0, n_test], "train_hi": n_train, "status": "checked_not_proved",
                       "cites": cites, "note": "TxGraffiti-style bound; checked on a held-out range, not a proof"}
                kept.append(row)
                stats["passed"] += 1
                base.setdefault((y, rel), []).append((row["id"], bound))
                by_pair.setdefault((y, x, rel), []).append(row)
    return {"lemmas": kept, "stats": stats, "elapsed_s": round(time.time() - t0, 2)}


def stored_lemmas() -> list[dict[str, Any]]:
    from colony import knowledge_library as KL
    return [r for r in KL.load_library() if r.get("event") == "lemma"]


def turn(cycle_id: str, menu: list[dict[str, Any]] | None = None, budget_s: float = BUDGET_S) -> dict[str, Any] | None:
    """One generator run per cycle (treatment only); appends new lemma rows to the knowledge library."""
    if not enabled():
        return None
    from colony import knowledge_library as KL
    from colony import oeis_conjectures as OC
    have = stored_lemmas()
    if any(r.get("cycle_id") == cycle_id for r in have):
        return None
    menu = OC.load_menu() if menu is None else menu
    invs: dict[str, Any] = dict(builtin_invariants())
    invs.update(table_invariants(menu))
    res = generate(invs, have, budget_s)
    known = {r.get("id") for r in have}
    new = sorted((r for r in res["lemmas"] if r["id"] not in known),
                 key=lambda r: (-int(r["touch"]), r["generator"] != "ratio", r["statement"]))[:MAX_LEMMAS_PER_RUN]
    for r in new:
        r["cycle_id"] = cycle_id
        KL._append(KL.library_path(), r)
    res["stored"] = len(new)
    return res
