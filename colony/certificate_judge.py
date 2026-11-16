"""Item 107: certificate proof judge (James 2026-11-16: "Begin that plan").

A proof counts as NON-ROUTINE only when it carries a machine certificate that an independent
checker re-verifies (oeis_conjectures._score / twin.collect_arm_metrics read ``certificate_verified``).
Heuristic results (guesses, finite checks, conditional definitions) stay labeled and never count.

First slice: Gosper certificates for indefinite hypergeometric sums (SymPy's concrete module,
reference https://docs.sympy.org/latest/modules/concrete.html; nothing fetched or run from the web).
For S(n) = Sum_{k=lo..n} t(k) with t hypergeometric in k, Gosper's algorithm returns a rational
function R(k) with G(k) = R(k) t(k) and G(k+1) - G(k) = t(k); then S(n) = G(n+1) - G(lo).
The certificate is (t, R, G, lo). The checker (verify_gosper) does NOT call Gosper's algorithm:
  1. symbolic: G(k+1) - G(k) - t(k) simplifies to 0 (combsimp / simplify),
  2. exact numeric, by a second evaluator (colony.oeis_definitions path A on the parsed term):
     G(k+1) - G(k) == t(k) for k = lo .. lo+40, and G finite at every integer used,
  3. no pole of G at an integer >= lo (denominator roots),
  4. the claimed closed form f(n) equals G(n+1) - G(lo): symbolically AND at n = lo .. lo+60.
Gosper's algorithm is a decision procedure, so a Gosper certificate is CERTIFIED but ROUTINE: it
proves the identity soundly and is recorded in the certified-proof table, and the scoreboard keeps
non-routine = certified and not routine-by-type. Definite sums Sum_{k} F(n,k) need creative
telescoping (Zeilberger / WZ pairs); not in this slice, reported as such.

Switch ``COLONY_CERT_JUDGE`` = live (default) | off; always off on the control arm.
Append-only log: data/commons/certificate_proofs.jsonl.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "commons" / "certificate_proofs.jsonl"
ROUTINE_TYPES = frozenset({"gosper_sum"})
NUM_CHECK = 40


def enabled() -> bool:
    try:
        from colony.arm import self_mod_enabled
        if not self_mod_enabled():
            return False
    except Exception:  # noqa: BLE001
        return False
    return (os.environ.get("COLONY_CERT_JUDGE") or "live").strip().lower() == "live"


def _sp():
    import sympy as sp
    return sp


def to_sympy(node, syms: dict[str, Any]):
    """colony.oeis_definitions AST -> SymPy expression (no floor: not hypergeometric)."""
    sp = _sp()
    k = node[0]
    if k == "num":
        return sp.Integer(node[1])
    if k == "var":
        return syms[node[1]]
    if k == "neg":
        return -to_sympy(node[1], syms)
    if k in ("add", "sub", "mul", "div", "pow"):
        x, y = to_sympy(node[1], syms), to_sympy(node[2], syms)
        return {"add": x + y, "sub": x - y, "mul": x * y, "div": x / y if k == "div" else None,
                "pow": x ** y if k == "pow" else None}[k]
    if k == "call":
        args = [to_sympy(a, syms) for a in node[2]]
        fn = node[1]
        if fn == "binomial":
            return sp.binomial(*args)
        if fn == "fact":
            return sp.factorial(args[0])
        if fn == "catalan":
            return sp.binomial(2 * args[0], args[0]) / (args[0] + 1)
        if fn == "cbinom":
            return sp.binomial(2 * args[0], args[0])
        if fn == "pow2":
            return sp.Integer(2) ** args[0]
        raise ValueError("not hypergeometric: %s" % fn)
    raise ValueError("node %s" % k)


def _sum_shape(tree) -> tuple[str, Any, Any] | None:
    """('k', lo_node, term_node) when tree is Sum_{k=lo..n} term(k) with term free of n."""
    if tree[0] != "sum":
        return None
    _, v, lo, hi, body = tree
    if hi != ("var", "n"):
        return None

    def uses_n(nd) -> bool:
        if not isinstance(nd, tuple):
            return False
        if nd == ("var", "n") or nd[0] == "a":
            return True
        if nd[0] == "call":
            return any(uses_n(x) for x in nd[2])
        return any(uses_n(x) for x in nd[1:] if isinstance(x, tuple))
    if uses_n(body) or uses_n(lo):
        return None
    return v, lo, body


def find_gosper(sum_text: str) -> dict[str, Any] | None:
    """Certificate for 'Sum_{k=lo..n} t(k)', or None (not indefinite / not Gosper-summable)."""
    from colony import oeis_definitions as OD
    sp = _sp()
    try:
        tree = OD.parse_expr(sum_text)
    except OD.ParseError:
        return None
    shape = _sum_shape(tree)
    if not shape:
        return None
    v, lo_node, body = shape
    ks = sp.Symbol(v, integer=True)
    try:
        t = to_sympy(body, {v: ks})
        lo = int(OD.eval_a(lo_node, {}, lambda i: 0, 1e18))
        from sympy.concrete.gosper import gosper_term
        R = gosper_term(t, ks)
    except Exception:  # noqa: BLE001
        return None
    if R is None:
        return None
    G = sp.simplify(sp.combsimp(R * t))
    return {"type": "gosper_sum", "var": v, "lo": lo, "term": sp.srepr(t), "R": sp.srepr(R), "G": sp.srepr(G),
            "term_text": str(t), "G_text": str(G), "R_text": str(R), "sum_text": sum_text, "body_ast": json.dumps(body)}


def _tuple(x):
    return tuple(_tuple(y) for y in x) if isinstance(x, list) else x


def verify_gosper(cert: dict[str, Any], closed_text: str | None = None) -> tuple[bool, str]:
    """Independent re-check (see module docstring). closed_text: 'f(n)' the sum is claimed to equal."""
    from colony import oeis_definitions as OD
    sp = _sp()
    try:
        v = cert["var"]
        ks = sp.Symbol(v, integer=True)
        n = sp.Symbol("n", integer=True)
        G = sp.sympify(sp.parse_expr(cert["G_text"], local_dict={v: ks}, evaluate=True))
        t = sp.sympify(sp.parse_expr(cert["term_text"], local_dict={v: ks}, evaluate=True))
        lo = int(cert["lo"])
    except Exception as ex:  # noqa: BLE001
        return False, "certificate does not parse: %s" % ex
    # 1 symbolic telescoping
    try:
        d = sp.simplify(sp.combsimp((G.subs(ks, ks + 1) - G - t).rewrite(sp.factorial)))
    except Exception as ex:  # noqa: BLE001
        return False, "symbolic check failed: %s" % ex
    if d != 0:
        return False, "G(k+1) - G(k) != t(k)"
    # 3 poles
    try:
        den = sp.denom(sp.together(sp.parse_expr(cert["R_text"], local_dict={v: ks})))
        for r in sp.roots(sp.Poly(den, ks)).keys() if den.is_polynomial(ks) and den.has(ks) else []:
            if r.is_integer and int(r) >= lo:
                return False, "G has a pole at k = %s" % r
    except Exception:  # noqa: BLE001
        pass
    # 2 exact numeric: G(k) = R(k) t(k), R evaluated exactly (a pole at an integer used rejects),
    #   t by a second evaluator (colony.oeis_definitions path A on the parsed term)
    body = _tuple(json.loads(cert["body_ast"]))
    try:
        R = sp.parse_expr(cert["R_text"], local_dict={v: ks})
    except Exception as ex:  # noqa: BLE001
        return False, "R does not parse: %s" % ex
    Gv = []
    for kk in range(lo, lo + NUM_CHECK + 2):
        try:
            rv = sp.Rational(sp.together(R).subs(ks, kk))
            if not rv.is_finite:
                raise ValueError
        except Exception:  # noqa: BLE001
            return False, "R has a pole at k = %d" % kk
        tv = OD.eval_a(body, {v: kk}, lambda i: 0, 1e18)
        Gv.append(Fraction(int(rv.p), int(rv.q)) * tv)
    for j, kk in enumerate(range(lo, lo + NUM_CHECK + 1)):
        tv = OD.eval_a(body, {v: kk}, lambda i: 0, 1e18)
        if Gv[j + 1] - Gv[j] != tv:
            return False, "numeric telescoping fails at k = %d" % kk
    try:   # G(lo) by the same exact route, for the closed-form step
        G_lo = Gv[0]
    except IndexError:
        return False, "no values"
    why = "Gosper certificate: G(k) = %s telescopes t(k) = %s (symbolic + exact numeric k=%d..%d)" % (
        cert["G_text"], cert["term_text"], lo, lo + NUM_CHECK)
    if closed_text is None:
        return True, why
    # 4 closed form
    try:
        f = to_sympy(OD.parse_expr(closed_text), {"n": n})
        S = G.subs(ks, n + 1) - sp.Rational(G_lo.numerator, G_lo.denominator)
        if sp.simplify(sp.combsimp((f - S).rewrite(sp.factorial))) != 0:
            return False, "closed form differs from G(n+1) - G(lo) symbolically"
        acc = Fraction(0)
        ftree = OD.parse_expr(closed_text)
        for nn in range(lo, lo + 60):
            acc += OD.eval_a(body, {v: nn}, lambda i: 0, 1e18)
            if OD.eval_a(ftree, {"n": nn}, lambda i: 0, 1e18) != acc:
                return False, "closed form differs from the partial sum at n = %d" % nn
    except Exception as ex:  # noqa: BLE001
        return False, "closed form check failed: %s" % ex
    return True, why + "; equals the closed form %s (symbolic + n=%d..%d)" % (closed_text, lo, lo + 59)


# ----------------------------------------------------------------------------- desk use

def _closed(text: str) -> str | None:
    m = re.search(r"a\(n\)\s*=\s*(.+)$", text or "")
    return m.group(1).strip() if m else None


def judge_entry(e: dict[str, Any]) -> dict[str, Any] | None:
    """Try a Gosper certificate for a sum identity linking the entry's sound definition and its claim
    (or a stated FORMULA line). Returns a proof row or None."""
    from colony import oeis_definitions as OD
    d = e.get("definition") or {}
    claim = e.get("claim") or {}
    pairs: list[tuple[str, str, str]] = []    # (sum_text, closed_text, what)
    parts = claim.get("parts") or []
    if d.get("kind") == "xexpr" and d.get("provenance") == OD.PROV_NAME and str(d.get("expr", "")).startswith("Sum_"):
        if len(parts) == 2 and parts[0].strip() == "a(n)":
            pairs.append((d["expr"], parts[1], "claim"))
    if d.get("kind") == "xexpr" and d.get("provenance") == OD.PROV_NAME and not d.get("recursive") \
            and not str(d.get("expr", "")).startswith("Sum_"):
        cache = OD.load_formula_cache()
        for line in ((cache.get("entries") or {}).get(str(e.get("anum") or "")) or {}).get("formula") or []:
            if OD._COND.search(line):
                continue
            c = _closed(OD._strip_text(line))
            if c and c.startswith("Sum_"):
                pairs.append((c, d["expr"], "stated_formula"))
    for sum_text, closed, what in pairs:
        cert = find_gosper(sum_text)
        if not cert:
            continue
        ok, why = verify_gosper(cert, closed)
        return {"id": e.get("id"), "anum": e.get("anum"), "what": what, "certificate": cert,
                "certificate_verified": ok, "checker": why, "routine": cert["type"] in ROUTINE_TYPES}
    return None


def log(row: dict[str, Any]) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    out = dict(row)
    out["ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with LOG.open("a") as fh:
        fh.write(json.dumps(out, sort_keys=True, default=str) + "\n")


def counts_as_non_routine(proof: dict[str, Any]) -> bool:
    """The rule: non-routine needs a verified machine certificate and a non-routine certificate type."""
    return bool(proof.get("certificate_verified")) and not bool(proof.get("routine"))


def _logged_keys() -> set[str]:
    keys = set()
    try:
        for ln in LOG.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            keys.add("%s|%s|%s" % (r.get("id"), r.get("what"), (r.get("certificate") or {}).get("sum_text")))
    except OSError:
        pass
    return keys


def judge_menu(menu: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Treatment only: try a certificate for every entry with a sound definition; log new results."""
    if not enabled():
        return None
    from colony import oeis_conjectures as OC
    menu = OC.load_menu() if menu is None else menu
    seen = _logged_keys()
    rows = []
    for e in menu:
        try:
            d = e.get("definition") or OC.computable_definition(e)
        except Exception:  # noqa: BLE001
            d = None
        if not d:
            continue
        ent = dict(e)
        ent["definition"] = d
        try:
            r = judge_entry(ent)
        except Exception:  # noqa: BLE001
            r = None
        if not r:
            continue
        key = "%s|%s|%s" % (r.get("id"), r.get("what"), r["certificate"].get("sum_text"))
        if key in seen:
            continue
        log(r)
        rows.append(r)
    return {"new": rows, "certified": sum(1 for r in rows if r.get("certificate_verified"))}
