"""Strong known-results check (COLONY_REFCHECK_STRONG = off | shadow | live; default off).

Runs on a claim that survived testing and the Stage 2 reference check, BEFORE it can earn surprise
credit. Any one of these explains it (label 'known/derived: ...'; live: not a surprise, credit 0):

(c) follows from known lemmas: the Stage 4 proof kernel (colony.proof_path) finds a certificate
    built only from its table of classical lemmas, re-verified by colony.proof_check.
(b) derivation library (each fact is either a theorem applied to a checked hypothesis, or a
    finite computation that is a proof):
    - C-finite identity: for g | f with both sides C-finite (orders bounded by construction,
      frontier_conjectures.cf_order), the quotient h = f / g is matched by an integer monic linear
      recurrence; g*h - f is C-finite of order <= ord(f) + ord(g) ord(h), so agreement on that
      many terms proves f = g*h for all n. This covers strong divisibility of Lucas sequences
      (a(n) | a(kn)) and product / closed formulas such as the grid spanning-tree counts.
    - periodic residues: every C-finite sequence with an integer monic recurrence, and every
      P-recursive one with unit leading coefficient (derangements), is periodic mod m; a
      congruence that holds under a null keeping exactly those residues follows from them.
    - (multiplicativity and the classical parity rules come in through the kernel and the
      Stage 2 catalog.)
(d) the claim's derived sequence (the quotient f/g of a divisibility, the gap B - A of an
    inequality) is itself an OEIS entry (local OEIS terms index).
(a) OEIS entries of the involved sequences, fetched politely and cached on disk: FORMULA /
    COMMENT text stating a divisibility-sequence property, or a relation that names another
    involved sequence; one level of cross-referenced entries (A-numbers cited in those formulas).

'explained' is conservative in the direction of FEWER surprises: (b)(c) are proofs, (d) and the
text matches of (a) are heuristics (a match removes credit; it never adds any).
"""
from __future__ import annotations

import json
import os
import re
from fractions import Fraction
from typing import Any, Callable

ING_ANUM = {"stree_ladder": "A001353", "stree_grid3": "A006238", "match_ladder": "A030186", "pdist": "A000009",
            "ple3": "A001399", "prr": "A003114", "pnot3": "A000726", "perm_derange": "A000166", "tr_tribo": "A001644"}
NET_MAX = 12
MAX_ORD = 16
# parity facts of non-periodic sequences (classical; each is checked against the table in the tests)
PARITY_FACTS = {"pdist": "Euler: q(n) is odd iff n is a generalized pentagonal number k(3k-1)/2 (pentagonal theorem mod 2)",
}
P_RECURSIVE_UNIT = {"perm_derange": "D(n) = n D(n-1) + (-1)^n (P-recursive, unit leading coefficient)"}
_DIVSEQ = re.compile(r"divisibility sequence|a\(m\)\s*(?:divides|\|)\s*a\(n\)|a\(n\)\s*(?:divides|\|)\s*a\((?:k\s*\*?\s*)?[mk]\s*\*?\s*n\)"
                     r"|gcd\(\s*a\(m\)\s*,\s*a\(n\)\s*\)\s*=\s*a\(\s*gcd", re.I)
_ANUM = re.compile(r"A\d{6}")
_REL_OP = {"divides": re.compile(r"divid|\|"), "le": re.compile(r"<=|>=|<|>|\\le|\\ge"),
           "identity": re.compile(r"=")}


def mode() -> str:
    v = (os.environ.get("COLONY_REFCHECK_STRONG") or "off").strip().lower()
    return v if v in ("live", "shadow", "off") else "off"


# ----------------------------------------------------------------------------- recurrences

def find_recurrence(x: list[int], max_ord: int = MAX_ORD) -> list[Fraction] | None:
    """Shortest c with x[i] = sum_j c[j] x[i-1-j] on every available term (needs >= 3d + 20 terms)."""
    for d in range(1, max_ord + 1):
        if len(x) < 3 * d + 20:
            break
        A = [[Fraction(x[i - 1 - j]) for j in range(d)] + [Fraction(x[i])] for i in range(d, 2 * d)]
        sol = _solve(A, d)
        if sol is None:
            continue
        if all(sum(c * x[i - 1 - j] for j, c in enumerate(sol)) == x[i] for i in range(d, len(x))):
            return sol
    return None


def _solve(A: list[list[Fraction]], d: int) -> list[Fraction] | None:
    A = [r[:] for r in A]
    for k in range(d):
        p = next((i for i in range(k, d) if A[i][k] != 0), None)
        if p is None:
            return None
        A[k], A[p] = A[p], A[k]
        for i in range(d):
            if i != k and A[i][k] != 0:
                f = A[i][k] / A[k][k]
                A[i] = [a - f * b for a, b in zip(A[i], A[k])]
    return [A[i][d] / A[i][i] for i in range(d)]


def cfinite_identity(c: dict[str, Any], T: Any) -> str | None:
    """(b) g | f proved by f = g*h with h an integer monic recurrence (C-finite closure)."""
    from colony import frontier_conjectures as FC
    if c["kind"] != "divides" or c.get("_re") is None:
        return None
    og, of = FC.cf_order(c["_le"]), FC.cf_order(c["_re"])
    if og is None or of is None:
        return None
    N = min(FC.max_n(c["_le"], T, 400), FC.max_n(c["_re"], T, 400))
    if N < 60:
        return None
    g, f = FC.evaluate(c["_le"], N, T), FC.evaluate(c["_re"], N, T)
    if g is None or f is None or any(v == 0 for v in g) or any(b % a for a, b in zip(g, f)):
        return None
    h = [b // a for a, b in zip(g, f)]
    rec = find_recurrence(h)
    if rec is None or any(r.denominator != 1 for r in rec):
        return None
    oh = len(rec)
    need = of + og * oh
    if N < need + 5:
        return None
    return (f"derived (proof): {FC.canon(c['_re'])} = {FC.canon(c['_le'])} * h(n) with h an integer linear recurrence of "
            f"order {oh} (c = {[int(r) for r in rec]}); both sides C-finite, so agreement on {N} >= {need} terms "
            f"proves the identity (C-finite closure; strong divisibility / product formula)")


def periodic_facts(c: dict[str, Any], T: Any) -> dict[str, list[dict[str, Any]]]:
    from colony import frontier_conjectures as FC
    from colony import reference_check as RC
    out: dict[str, list[dict[str, Any]]] = {}
    for p in FC.prims_of(c["_le"]) | (FC.prims_of(c["_re"]) if c.get("_re") is not None else set()):
        fs = list(RC.CATALOG.get(p, []))
        if p in FC.CF_ORDER and p not in ("n", "one"):
            fs.append({"kind": "residue_all", "dom": 1,
                       "ref": f"{p} is C-finite with an integer monic recurrence, so periodic mod m (classical)"})
        if PARITY_FACTS.get(p):
            fs.append({"kind": "residue", "m": 2, "dom": 1, "ref": PARITY_FACTS[p]})
        if p in P_RECURSIVE_UNIT:
            fs.append({"kind": "residue_all", "dom": 1, "ref": f"{P_RECURSIVE_UNIT[p]}: periodic mod m"})
        out[p] = fs
    return out


def FC_canon(e: Any) -> str:
    from colony import frontier_conjectures as FC
    return FC.canon(e)


def periodic_null(c: dict[str, Any], T: Any) -> str | None:
    """(b) a congruence that survives nulls keeping the provable periodic residues of its parts."""
    from colony import reference_check as RC
    if c["kind"] not in ("cong", "modpat"):
        return None
    le = c["_le"]
    if c["kind"] == "cong" and c.get("_re") is None and le[0] == "o":
        # f[g] with "f(x) = 0 mod m iff x = 0 mod m" (definition of f): reduce to the same claim on g
        m, r = int(c["params"].get("m", 0)), int(c["params"].get("r", -1))
        if r == 0 and any(f["kind"] in ("residue", "divby") and f.get("m") == m and "iff" in f["ref"]
                          for f in RC.CATALOG.get(le[1], [])):
            inner = dict(c, _le=le[2], lhs=FC_canon(le[2]))
            got = periodic_null(inner, T)
            if got:
                return got.replace("derived: ", f"derived: {le[1]}(x) = 0 mod {m} iff x = 0 mod {m}, and ", 1)
    facts = periodic_facts(c, T)
    new = [f for fs in facts.values() for f in fs if f["kind"] == "residue_all" or f["ref"] in PARITY_FACTS.values()]
    if not new:
        return None
    if RC.explained_by(c, T, facts) and RC.explained_by(c, T, facts, seed=5):
        refs = sorted({f["ref"] for f in new})
        return "derived: follows from periodic residues of its parts (" + "; ".join(refs)[:220] + ")"
    return None


def kernel(c: dict[str, Any], T: Any) -> str | None:
    """(c) a proof-kernel certificate from the table of classical lemmas."""
    try:
        from colony import proof_path
        cert = proof_path.prove({"kind": c["kind"], "lhs": c["lhs"], "rhs": c.get("rhs") or "",
                                 "params": c["params"]}, T)
    except Exception:  # noqa: BLE001
        return None
    if cert:
        return f"derived from classical lemmas (proof-kernel certificate, {cert.get('method')})"
    return None


def derived_in_oeis(c: dict[str, Any], T: Any, lookup: Callable | None) -> str | None:
    """(d) the quotient of a divisibility / the gap of an inequality is an OEIS entry."""
    from colony import frontier_conjectures as FC
    if lookup is None or c.get("_re") is None or c["kind"] not in ("divides", "le"):
        return None
    a, b = FC.evaluate(c["_le"], 40, T), FC.evaluate(c["_re"], 40, T)
    if a is None or b is None:
        return None
    if c["kind"] == "divides":
        if any(x == 0 for x in a) or any(y % x for x, y in zip(a, b)):
            return None
        d, what = [y // x for x, y in zip(a, b)], "quotient"
    else:
        d, what = [y - x for x, y in zip(a, b)], "gap"
    r1, r2 = lookup(d[:30]), lookup(d[10:40])   # two windows must name the same entry
    both = sorted(set(r1.get("anums") or []) & set(r2.get("anums") or []))
    if r1.get("status") == "found" and both:
        return f"known: its {what} sequence is OEIS {', '.join(both[:2])}"
    return None


# ----------------------------------------------------------------------------- OEIS texts

def anums(c: dict[str, Any], T: Any, lookup: Callable | None) -> dict[str, str]:
    from colony import frontier_conjectures as FC
    from colony import reference_check as RC
    out = {}
    for p in FC.prims_of(c["_le"]) | (FC.prims_of(c["_re"]) if c.get("_re") is not None else set()):
        a = RC.PRIM_ANUM.get(p) or ING_ANUM.get(p) or _obs_anum(p)
        if a is None and lookup is not None and p in T.t and len(T.t[p]) > 31:
            r = lookup(T.t[p][1:31])
            a = (r.get("anums") or [None])[0] if r.get("status") == "found" else None
        if a:
            out[p] = a
    for a in c.get("oeis_anums") or []:
        out.setdefault(f"side:{a}", a)
    return out


def entry(anum: str, net: Any) -> dict[str, Any] | None:
    txt = net.get(f"https://oeis.org/search?q=id:{anum}&fmt=json", f"{anum}.json")
    if txt is None:
        return None
    try:
        js = json.loads(txt or "null")
        rec = js[0] if isinstance(js, list) and js else ((js or {}).get("results") or [None])[0]
    except (ValueError, TypeError, IndexError):
        return {}
    return rec if isinstance(rec, dict) else {}


def _lines(rec: dict[str, Any]) -> list[tuple[str, str]]:
    return ([("name", str(rec.get("name") or ""))] + [("formula", str(x)) for x in rec.get("formula") or []]
            + [("comment", str(x)) for x in rec.get("comment") or []])


def _divseq_ok(v: list[int]) -> bool:
    """Numerical validation of a stated divisibility-sequence property: a(m) | a(n) for m | n <= 120."""
    L = min(len(v) - 1, 120)
    return L >= 40 and all(v[m] != 0 and v[n] % v[m] == 0 for m in range(1, L + 1) for n in range(2 * m, L + 1, m))


def _rel_rx(kind: str, b: str) -> re.Pattern | None:
    op = {"divides": r"(?:divides|\|)", "le": r"(?:<=|\\le)", "identity": r"="}.get(kind)
    return re.compile(r"a\(n\)\s*" + op + r"\s*" + b + r"\(n\)\s*(?:[.,;]|for|$)") if op else None


def oeis_texts(c: dict[str, Any], T: Any, net: Any, lookup: Callable | None) -> tuple[str | None, list[str]]:
    """(a) FORMULA / COMMENT text of the involved entries (and of entries their formulas cite):
    a stated divisibility-sequence property (validated on the table) explains f | f(kn); a stated
    relation 'a(n) <op> B(n)' with the claim's own relation and another involved sequence B explains it."""
    from colony import frontier_conjectures as FC
    inv = anums(c, T, lookup)
    others = set(inv.values())
    checked: list[str] = []
    divseq = c["kind"] == "divides" and c.get("_re") is not None and c["_le"][0] == "p" \
        and c["_re"][0] == "dbl" and FC.canon(c["_re"][1]) == FC.canon(c["_le"])
    for name, a in sorted(inv.items()):
        rec = entry(a, net)
        if rec is None:
            continue
        checked.append(a)
        for field, t in _lines(rec):
            if divseq and not name.startswith("side:") and name == c["_le"][1] and _DIVSEQ.search(t) \
                    and name in T.t and _divseq_ok(T.t[name]):
                return f"known: {a} ({field}) states a divisibility property (validated): {t[:140]}", checked
            for b in sorted(others - {a}):
                rx = _rel_rx(c["kind"], b)
                if rx is not None and rx.search(t):
                    return f"known: OEIS {a} ({field}) states a(n) {c['kind']} {b}(n): {t[:140]}", checked
    return None, checked


class Net:
    """colony.new_data's polite cache (shared ~/.cache/colony/bfiles), own per-cycle budget."""

    def __init__(self, budget: int = NET_MAX) -> None:
        from colony.new_data import Net as _N
        self._n = _N()
        self._max = budget

    def get(self, url: str, name: str) -> str | None:
        from colony import new_data as N
        p = N._cache_dir() / name
        if not p.exists() and self._n.n >= self._max:
            return None
        import colony.new_data as _nd
        old = _nd.NET_MAX_PER_CYCLE
        _nd.NET_MAX_PER_CYCLE = max(old, self._max)
        try:
            return self._n.get(url, name)
        finally:
            _nd.NET_MAX_PER_CYCLE = old


def check(c: dict[str, Any], T: Any, net: Any = None, lookup: Callable | None = None) -> dict[str, Any]:
    """{'explained': bool, 'label': str, 'step': 'kernel'|'cfinite'|'periodic'|'oeis_derived'|'oeis_text'|''}"""
    from colony import frontier_conjectures as FC
    taut = lambda: ("known: a property of the outer function alone (g(x) | x or g(x) <= x)"  # noqa: E731
                    if c.get("_re") is not None and FC._outer_self(c) else None)
    steps = (("tautology", taut), ("kernel", lambda: kernel(c, T)), ("cfinite", lambda: cfinite_identity(c, T)),
             ("periodic", lambda: periodic_null(c, T)), ("oeis_derived", lambda: derived_in_oeis(c, T, lookup)))
    for name, fn in steps:
        try:
            lab = fn()
        except Exception:  # noqa: BLE001
            lab = None
        if lab:
            return {"explained": True, "label": lab, "step": name}
    checked: list[str] = []
    if net is not None:
        try:
            lab, checked = oeis_texts(c, T, net, lookup)
        except Exception:  # noqa: BLE001
            lab = None
        if lab:
            return {"explained": True, "label": lab, "step": "oeis_text"}
    return {"explained": False, "step": "",
            "label": "no known result found (kernel, C-finite identity, periodic residues, OEIS derived sequence, "
                     f"OEIS texts: {', '.join(checked) or 'none fetched'})"}


def _obs_anum(p: str) -> str | None:
    try:
        from colony import obscure_pool as OP
        return OP.ANUM.get(p)
    except Exception:  # noqa: BLE001
        return None
