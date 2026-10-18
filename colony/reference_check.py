"""Stage 2: a surviving conjecture is a surprise only if no reference explains it.

COLONY_REFCHECK = off | shadow (default: label only) | live (an explained claim is not a surprise).

The existing hand-written filters (colony.frontier_conjectures.trivial_reason, known_result, ...)
stay as a PREFILTER. For every claim that passes them, this module looks for a reference:

1. References. Facts about every involved sequence: each primitive and each side / subexpression
   that has an OEIS entry (local OEIS index). Facts come from
   - the OEIS entry itself: its FORMULA and COMMENT fields, fetched politely (cached a month,
     <= NET_MAX requests per cycle), parsed by a few fixed patterns (parity / residue facts,
     "a(n) <= n", "a(n) divides n", relations "a(n) <= A......(n)" / "a(n) divides A......(n)");
   - a catalog of classical results (Euler: phi(n) even for n >= 3; sigma(n) odd iff n is a square
     or twice a square; tau(n) odd iff n is a square; casting out nines; Pisano periodicity of
     Fibonacci / Lucas / Pell residues; Ramanujan's partition congruences; ...).
   Every fact is VALIDATED on the colony's own tables before use; a fact that does not hold on the
   tables (misparse, other offset) is dropped.
2. Explanation test (fact-constrained null). Replace every involved atom by a random sequence that
   keeps ONLY what the facts say (its residues where a fact fixes them, its zero pattern, its bound
   by n, its being a divisor of n; values for n <= SMALL are kept: a finite check). If the claim
   still holds on n = 1..N_EVAL for every one of K random draws, the cited facts explain it. The set
   of facts is then shrunk greedily to a minimal explaining set, and the label is
   "explained by <refs>". Otherwise: "no reference found (checked: <A-numbers>, classical catalog)".
   A direct relation stated in an involved entry ("a(n) <= A000010(n)") explains a matching
   divides / <= claim outright.

This is a heuristic judge: "explained" means "follows from these stated facts by a randomized
test", not a proof; "no reference found" means only that none of the checked texts explains it.
"""
from __future__ import annotations

import json
import math
import os
import random
import re
from typing import Any, Callable

PRIM_ANUM = {"phi": "A000010", "sigma": "A000203", "tau": "A000005", "omega": "A001221", "bigomega": "A001222",
             "mu": "A008683", "rad": "A007947", "lpf": "A020639", "gpf": "A006530", "sopfr": "A001414",
             "sqfree": "A008966", "digsum": "A007953", "popcount": "A000120", "pi": "A000720", "prime": "A000040",
             "csteps": "A006577", "cmax": "A025586", "ds3": "A053735", "rev": "A004086", "pow2": "A000079",
             "fib": "A000045", "lucas": "A000032", "pell": "A000129", "part": "A000041", "gold": "A045917"}
FIXED = ("n", "one")            # the index itself and the constant are never randomized
SMALL = 6
N_EVAL = 240
K_DRAWS = 6
NET_MAX = 4
MODS_ALL = (2, 3, 4, 5, 7, 8, 9, 11)


def mode() -> str:
    v = (os.environ.get("COLONY_REFCHECK") or "shadow").strip().lower()
    return v if v in ("live", "shadow", "off") else "shadow"


# ----------------------------------------------------------------------------- facts
# A fact: {"kind": residue|zero|bound_n|div_n|valueset|rel, ...params, "dom": n0 (holds for n >= n0)
#          or {"q": q, "s": s} (class), "ref": text}
def _sq(n: int) -> bool:
    return math.isqrt(n) ** 2 == n


CATALOG: dict[str, list[dict[str, Any]]] = {
    "phi": [{"kind": "residue", "m": 2, "dom": 3, "ref": "Euler: phi(n) is even for n >= 3 (classical)"},
            {"kind": "bound_n", "dom": 1, "ref": "phi(n) <= n (classical)"}],
    "sigma": [{"kind": "residue", "m": 2, "dom": 1, "ref": "sigma(n) is odd iff n is a square or twice a square (classical)"}],
    "tau": [{"kind": "residue", "m": 2, "dom": 1, "ref": "tau(n) is odd iff n is a square (classical)"}],
    "mu": [{"kind": "zero", "dom": 1, "ref": "mu(n) = 0 iff n is not squarefree (definition)"},
           {"kind": "valueset", "vals": [-1, 1], "dom": 1, "ref": "mu(n) in {-1, 0, 1} (definition)"}],
    "sqfree": [{"kind": "zero", "dom": 1, "ref": "squarefree indicator (definition)"},
               {"kind": "valueset", "vals": [1], "dom": 1, "ref": "squarefree indicator in {0, 1} (definition)"}],
    "rad": [{"kind": "div_n", "dom": 1, "ref": "rad(n) divides n (definition)"},
            {"kind": "residue", "m": 2, "dom": 1, "ref": "rad(n) is even iff n is even (definition)"}]
           + [{"kind": "divby", "m": p, "dom": 1, "ref": f"{p} divides rad(n) iff {p} divides n (definition)"}
              for p in (3, 5, 7)],
    "lpf": [{"kind": "div_n", "dom": 1, "ref": "lpf(n) divides n (definition)"},
            {"kind": "residue", "m": 2, "dom": 1, "ref": "lpf(n) = 2 iff n is even, else odd (definition)"}],
    "gpf": [{"kind": "div_n", "dom": 1, "ref": "gpf(n) divides n (definition)"},
            {"kind": "residue", "m": 2, "dom": 3, "ref": "gpf(n) is odd unless n is a power of 2 (definition)"}],
    "sopfr": [{"kind": "bound_n", "dom": 1, "ref": "sopfr(n) <= n (classical)"}],
    "prime": [{"kind": "residue", "m": 2, "dom": 2, "ref": "every prime > 2 is odd"},
              {"kind": "residue", "m": 3, "dom": 3, "ref": "every prime > 3 is 1 or 2 mod 3"}],
    "digsum": [{"kind": "residue", "m": 9, "dom": 1, "ref": "casting out nines: digsum(n) = n (mod 9) (classical)"}],
    "rev": [{"kind": "residue", "m": 9, "dom": 1, "ref": "casting out nines: reversal keeps n mod 9 (classical)"}],
    "ds3": [{"kind": "residue", "m": 2, "dom": 1, "ref": "base-3 digit sum = n (mod 2) (casting out (b-1))"}],
    "pow2": [{"kind": "residue", "m": 2, "dom": 1, "ref": "2^n is even for n >= 1"}],
    "fib": [{"kind": "residue_all", "dom": 1, "ref": "Pisano periodicity: Fibonacci numbers mod m are periodic (classical)"}],
    "lucas": [{"kind": "residue_all", "dom": 1, "ref": "Lucas numbers mod m are periodic (classical)"}],
    "pell": [{"kind": "residue_all", "dom": 1, "ref": "Pell numbers mod m are periodic (classical)"}],
    "part": [{"kind": "residue", "m": 5, "dom": {"q": 5, "s": 4}, "ref": "Ramanujan: p(5k+4) = 0 (mod 5)"},
             {"kind": "residue", "m": 7, "dom": {"q": 7, "s": 5}, "ref": "Ramanujan: p(7k+5) = 0 (mod 7)"},
             {"kind": "residue", "m": 11, "dom": {"q": 11, "s": 6}, "ref": "Ramanujan: p(11k+6) = 0 (mod 11)"}],
    "cmax": [{"kind": "residue", "m": 2, "dom": 2, "ref": "Collatz: the maximum of a trajectory from n >= 2 is even"}],
}

_PAT = [
    (re.compile(r"a\(n\)\s+(?:is|are)\s+(even|odd)(?:\s+(?:for|if|when)\s+(?:all\s+)?n\s*(>=|>)\s*(\d+))?", re.I), "parity"),
    (re.compile(r"a\(n\)\s+is\s+(?:even|odd)\s+(?:iff|if and only if)\s+n\s+is", re.I), "parity_iff"),
    (re.compile(r"a\(n\)\s*==\s*(-?\d+)\s*\(mod\s*(\d+)\)(?:\s*(?:for|if)\s+(?:all\s+)?n\s*(>=|>)\s*(\d+))?", re.I), "mod"),
    (re.compile(r"a\(n\)\s*==\s*n\s*\(mod\s*(\d+)\)", re.I), "mod_n"),
    (re.compile(r"a\(n\)\s*<=\s*n\b(?!\s*[\^*/+-])", re.I), "le_n"),
    (re.compile(r"a\(n\)\s*(?:divides|\|)\s*n\b(?!\s*[\^*/+!-])", re.I), "div_n"),
    (re.compile(r"a\(n\)\s*(<=|>=|divides|\|)\s*(A\d{6})\(n\)", re.I), "rel"),
]


def parse_facts(anum: str, texts: list[tuple[str, str]]) -> list[dict[str, Any]]:
    out = []
    for field, t in texts:
        t1 = re.sub(r"<[^>]+>|_[A-Z][^_]*_", "", t)
        for rx, kind in _PAT:
            for m in rx.finditer(t1):
                snip = t1[max(0, m.start() - 30): m.end() + 30].strip()
                ref = f"{anum} ({field}): ...{snip}..."
                if kind == "parity":
                    n0 = int(m.group(3)) + (1 if m.group(2) == ">" else 0) if m.group(3) else 1
                    out.append({"kind": "residue", "m": 2, "dom": n0, "ref": ref})
                elif kind == "parity_iff":
                    out.append({"kind": "residue", "m": 2, "dom": 1, "ref": ref})
                elif kind == "mod":
                    n0 = int(m.group(4)) + (1 if m.group(3) == ">" else 0) if m.group(4) else 1
                    out.append({"kind": "residue", "m": int(m.group(2)), "dom": n0, "ref": ref})
                elif kind == "mod_n":
                    out.append({"kind": "residue", "m": int(m.group(1)), "dom": 1, "ref": ref})
                elif kind == "le_n":
                    out.append({"kind": "bound_n", "dom": 1, "ref": ref})
                elif kind == "div_n":
                    out.append({"kind": "div_n", "dom": 1, "ref": ref})
                elif kind == "rel":
                    out.append({"kind": "rel", "op": m.group(1).lower().replace("|", "divides"), "other": m.group(2),
                                "dom": 1, "ref": ref})
    return out


def _in_dom(n: int, dom: Any) -> bool:
    if isinstance(dom, dict):
        return n % dom["q"] == dom["s"]
    return n >= int(dom)


def validate(f: dict[str, Any], v: list[int]) -> bool:
    """v[i] = value at n = i + 1. A residue fact only says 'the residue mod m is determined' (by n or a
    simple property of n), so it is validated by a determinism test against n's own residues /
    squareness; bounds and divisibility literally."""
    k = f["kind"]
    ns = [n for n in range(1, len(v) + 1) if _in_dom(n, f["dom"])]
    if not ns:
        return False
    if k == "bound_n":
        return all(v[n - 1] <= n for n in ns)
    if k == "div_n":
        return all(v[n - 1] != 0 and n % v[n - 1] == 0 for n in ns)
    if k == "zero":
        return any(v[n - 1] == 0 for n in ns)
    if k == "valueset":
        return all(v[n - 1] == 0 or v[n - 1] in f["vals"] for n in ns)
    if k == "residue":
        m = f["m"]
        # determined by (n mod m*m*4, squareness): a residue that is a function of simple data of n
        seen: dict[tuple, int] = {}
        for n in ns:
            key = (n % (4 * m * m), _sq(n), n % 2 == 0 and _sq(n // 2), n < 30 and n)
            r = v[n - 1] % m
            if seen.setdefault(key, r) != r:
                return False
        return True
    if k == "residue_all":
        return True
    if k == "divby":
        return all((v[n - 1] % f["m"] == 0) == (n % f["m"] == 0) for n in ns)
    return k == "rel"


# ----------------------------------------------------------------------------- the null model
def _null_values(true: list[int], facts: list[dict[str, Any]], rng: random.Random, L: int) -> list[int]:
    """Random sequence keeping only what the facts say (index 0 unused, kept as 0)."""
    out = [0] * (L + 1)
    for n in range(1, L + 1):
        t = true[n]
        if n <= SMALL:
            out[n] = t
            continue
        fs = [f for f in facts if _in_dom(n, f["dom"])]
        mods = [f["m"] for f in fs if f["kind"] == "residue"]
        if any(f["kind"] == "residue_all" for f in fs):
            mods += list(MODS_ALL)
        M = 1
        for m in mods:
            M = M * m // math.gcd(M, m)
        zero = any(f["kind"] == "zero" for f in fs)
        if zero and t == 0:
            out[n] = 0
            continue
        dv = [f["m"] for f in fs if f["kind"] == "divby"]

        def ok(x: int) -> bool:
            return (x - t) % M == 0 and all((x % m == 0) == (t % m == 0) for m in dv)
        vs = next((f["vals"] for f in fs if f["kind"] == "valueset"), None)
        if vs is not None:
            cand = [x for x in vs if ok(x)] or [t]
            out[n] = rng.choice(cand)
            continue
        if any(f["kind"] == "div_n" for f in fs):
            divs = [d for d in range(1, math.isqrt(n) + 1) if n % d == 0]
            divs = sorted(set(divs + [n // d for d in divs]))
            cand = [d for d in divs if ok(d)] or [t]
            out[n] = rng.choice(cand)
            continue
        hi = n if any(f["kind"] == "bound_n" for f in fs) else max(1000, 2 * abs(t) + 10)
        base = t % M
        k_max = max(0, (hi - base) // M)
        x = t
        for _ in range(40):             # keep the stated divisibility pattern (rejection sampling)
            x = base + M * rng.randint(0, k_max)
            if x != 0 and all((x % m == 0) == (t % m == 0) for m in dv):
                break
        else:
            x = t
        out[n] = x if (x != 0 or zero) else t
    return out


def _holds_with(c: dict[str, Any], T: Any, tab: dict[str, list[int]], N: int) -> bool | None:
    from colony import frontier_conjectures as FC
    a = FC.evaluate(c["_le"], N, T, tab)
    b = FC.evaluate(c["_re"], N, T, tab) if c.get("_re") is not None else None
    if a is None or (c.get("_re") is not None and b is None):
        return None
    return FC.holds(c["kind"], c["params"], a, b)[0]


def explained_by(c: dict[str, Any], T: Any, facts: dict[str, list[dict[str, Any]]], seed: int = 0) -> bool | None:
    """True if the claim holds for every K_DRAWS fact-constrained null draw of its primitives."""
    from colony import frontier_conjectures as FC
    prims = FC.prims_of(c["_le"]) | (FC.prims_of(c["_re"]) if c.get("_re") is not None else set())
    L = 2 * N_EVAL + 4
    rng = random.Random(seed)
    for _ in range(K_DRAWS):
        tab = dict(T.t)
        for p in prims:
            if p in FIXED or p.startswith("_c") or p not in T.t or len(T.t[p]) <= L:
                continue
            tab[p] = _null_values(T.t[p], facts.get(p) or [], rng, L)
        r = _holds_with(c, T, tab, N_EVAL)
        if r is None:
            return None
        if not r:
            return False
    return True


def _side_null_holds(c: dict[str, Any], lv: list[int], facts: list[dict[str, Any]]) -> bool:
    from colony import frontier_conjectures as FC
    rng = random.Random(3)
    for _ in range(K_DRAWS):
        nv = _null_values([0] + lv, facts, rng, len(lv))[1:N_EVAL + 1]
        if not FC.holds(c["kind"], c["params"], nv, None)[0]:
            return False
    return True


# ----------------------------------------------------------------------------- OEIS texts
def fetch_texts(anum: str, net: Any) -> list[tuple[str, str]] | None:
    txt = net.get(f"https://oeis.org/search?q=id:{anum}&fmt=json", f"{anum}.json")
    if txt is None:
        return None
    try:
        js = json.loads(txt or "null")
        rec = js[0] if isinstance(js, list) and js else ((js or {}).get("results") or [None])[0]
    except (ValueError, TypeError, IndexError):
        return []
    if not isinstance(rec, dict):
        return []
    return [("formula", str(x)) for x in rec.get("formula") or []] + [("comment", str(x)) for x in rec.get("comment") or []]


def involved(c: dict[str, Any], T: Any, lookup: Callable | None) -> dict[str, str]:
    """primitive / side name -> A-number (primitives by table; sides via the local OEIS index)."""
    from colony import frontier_conjectures as FC
    out = {}
    prims = FC.prims_of(c["_le"]) | (FC.prims_of(c["_re"]) if c.get("_re") is not None else set())
    for p in prims:
        if p in PRIM_ANUM:
            out[p] = PRIM_ANUM[p]
    for a in c.get("oeis_anums") or []:
        out.setdefault(f"side:{a}", a)
    return out


def check(c: dict[str, Any], T: Any, net: Any, lookup: Callable | None = None) -> dict[str, Any]:
    """{'explained': bool, 'label': str, 'refs': [...], 'checked': [...], 'unfetched': [...]}"""
    from colony import frontier_conjectures as FC
    inv = involved(c, T, lookup)
    facts: dict[str, list[dict[str, Any]]] = {}
    checked, unfetched, rel_refs = ["classical catalog"], [], []
    L = 2 * N_EVAL + 4
    side_anums = {k[5:]: k for k in inv if k.startswith("side:")}
    for name, anum in sorted(inv.items()):
        texts = fetch_texts(anum, net)
        if texts is None:
            unfetched.append(anum)
            texts = []
        else:
            checked.append(anum)
        parsed = parse_facts(anum, texts)
        if name.startswith("side:"):
            # a fact stated by a side's own entry ("a(n) is odd", "a(n) == 0 (mod 3)") explains a
            # congruence on that side when the claim survives a null of the side keeping that fact
            if c["kind"] in ("cong", "modpat"):
                lv = FC.evaluate(c["_le"], L, T)
                if lv is not None and anum in (c.get("lhs_anums") or [anum]):
                    good = [f for f in parsed if f["kind"] == "residue" and validate(f, lv)]
                    if good and _side_null_holds(c, lv, good):
                        return {"explained": True, "label": f"explained by {good[0]['ref'][:160]}",
                                "refs": [good[0]["ref"]], "checked": checked + [anum], "unfetched": unfetched}
            # a relation stated by an involved side's own entry ("a(n) <= A000010(n)")
            for f in parsed:
                if f["kind"] == "rel" and c["kind"] in ("le", "divides") and f["other"] in side_anums \
                        and f["other"] != anum and ((c["kind"] == "le" and f["op"] in ("<=", ">="))
                                                    or (c["kind"] == "divides" and f["op"] == "divides")):
                    rel_refs.append(f["ref"])
            continue
        tv = T.t.get(name)
        if tv is None or len(tv) <= L:
            continue
        good = [f for f in CATALOG.get(name, []) + parsed if f["kind"] != "rel" and validate(f, tv[1:L + 1])]
        facts[name] = good
    if rel_refs:
        return {"explained": True, "label": f"explained by {rel_refs[0][:160]}", "refs": rel_refs[:2],
                "checked": checked, "unfetched": unfetched}
    ex = explained_by(c, T, facts)
    if ex:
        # shrink to a minimal explaining set of facts (greedy), then cite
        flat = [(p, i) for p, fs in facts.items() for i in range(len(fs))]
        keep = set(flat)
        for x in flat:
            trial = keep - {x}
            sub = {p: [f for i, f in enumerate(fs) if (p, i) in trial] for p, fs in facts.items()}
            if explained_by(c, T, sub, seed=1):
                keep = trial
        refs = sorted({facts[p][i]["ref"] for p, i in keep})
        lab = ("explained by " + "; ".join(r[:120] for r in refs)) if refs else \
            "explained by its small cases alone (n <= 6) plus structure that random values keep"
        if refs:
            lab += f" (+ direct check n <= {SMALL})"
        return {"explained": True, "label": lab, "refs": refs, "checked": checked, "unfetched": unfetched}
    lab = "no reference found (checked: " + ", ".join(checked) + (f"; not fetched: {', '.join(unfetched)}" if unfetched else "") + ")"
    return {"explained": False, "label": lab, "refs": [], "checked": checked, "unfetched": unfetched,
            "null_test": "inconclusive" if ex is None else "claim fails under fact-constrained nulls"}


class Net:
    """Same polite cache as colony.new_data (shared cache directory), with its own small budget."""

    def __init__(self) -> None:
        from colony.new_data import Net as _N
        self._n = _N()
        self._max = NET_MAX

    @property
    def n(self) -> int:
        return self._n.n

    def get(self, url: str, name: str) -> str | None:
        from colony import new_data as N
        p = N._cache_dir() / name
        if not p.exists() and self._n.n >= self._max:
            return None
        return self._n.get(url, name)


# ----------------------------------------------------------------------------- calibration
CALIB_OUT = "society/frontier/refcheck_calibration.json"


def calibrate(surprises: list[dict[str, Any]], net: Any = None, T: Any = None) -> dict[str, Any]:
    """Run the reference check on past surprises and compare with how each was settled by hand
    (the hand-written prefilter rules that now catch it: colony.frontier_conjectures.trivial_reason /
    known_result)."""
    from colony import frontier_conjectures as FC
    T = T or FC.tables()
    rng = random.Random(7)
    rows = []
    for s in surprises:
        try:
            c = {"kind": s["kind"], "params": s["params"], "lhs": s["lhs"], "rhs": s.get("rhs") or "",
                 "_le": FC.parse(s["lhs"]), "_re": FC.parse(s["rhs"]) if s.get("rhs") else None,
                 "oeis_anums": s.get("oeis_anums") or []}
        except Exception:  # noqa: BLE001
            continue
        hand = FC.trivial_reason(c, T, rng, FC.fit_n()) or ("known: " + FC.known_result(c) if FC.known_result(c) else "")
        r = check(c, T, net or Net())
        rows.append({"statement": s.get("statement") or FC.statement(c), "found_at": s.get("found_at"),
                     "hand_rule_now": hand or "(none: still a surprise under the hand rules)",
                     "reference_label": r["label"], "explained": r["explained"], "refs": r["refs"]})
    n = len(rows)
    by_hand = [x for x in rows if not x["hand_rule_now"].startswith("(none")]
    agree = sum(1 for x in by_hand if x["explained"])
    return {"n": n, "settled_by_hand": len(by_hand), "explained_by_reference": sum(x["explained"] for x in rows),
            "agreement_on_hand_settled": f"{agree}/{len(by_hand)}", "rows": rows}
