"""Stage 4 — proof path for surviving frontier conjectures (James 2026-10-18 11:06 AM ET).

COLONY_PROOF=live|shadow|off (code default shadow). For each surviving conjecture the prover tries:
 (i)  periodic residues / finite case split: split n into classes mod Q; on each class derive the
      value of every sub-expression mod m from classical lemmas (colony.proof_check: phi even,
      casting out nines, sigma and tau parity, sigma(x) = 0 mod k for x = -1 mod k, lpf / rad / mu
      on divisibility classes, Ramanujan, C-finite sequences periodic mod m by their recurrence,
      f(2x) rewrites, Collatz maxima = 1 mod 3, ...), running sums S via one full period (k >= N0)
      plus a direct anchor value; n < N0 checked directly. Congruences and divisibility.
 (ii) closed forms with sympy: after exact rewrites (e.g. lpf(2n) = 2) each side is a combination
      of 2^x, Fibonacci, Lucas, Pell and n; identities / recurrences are checked symbolically.
 (iii) basic-inequality reduction: A <= B is reduced, class by class, to a non-negative integer
      combination of the basic-inequality library (tau >= Omega + 1, phi >= gpf - 1, f(2x) >= f(x),
      ...) with the derivation recorded.
Every certificate is re-verified by the separate checker (colony.proof_check.check) before it is
counted. Labels: "machine-proved (certificate)" or "conjecture surviving N checks".
shadow: report only (society/systems/proof_path.json); live: the frontier registry label and
certificate are updated too. Never touches P, the Oracle, the 0.70 bar, fitness or desk decisions.
"""
from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from colony import proof_check as K

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "society" / "systems" / "proof_path.json"
MODES = ("live", "shadow", "off")
QBASE = (1, 2, 3, 4, 6, 8, 9, 10, 12, 18, 20, 24, 30, 36, 60)
QMAX = 360
ARG_M = 2520 * 11 * 13
BUDGET_S = 20.0
PER_CLAIM_S = 3.0
LABEL = "machine-proved (certificate)"


def mode() -> str:
    m = os.environ.get("COLONY_PROOF", "shadow").strip().lower()
    return m if m in MODES else "shadow"


class _Timeout(Exception):
    pass


class Prover:
    def __init__(self, T: Any, deadline: float):
        self.T, self.deadline = T, deadline

    def node(self, e: tuple, a: int, b: int, cls: tuple[int, int], big: bool, M: int) -> dict[str, Any]:
        from colony.frontier_conjectures import canon
        if time.time() > self.deadline:
            raise _Timeout()
        nd: dict[str, Any] = {"e": canon(e), "pt": [a, b]}
        op = e[0]
        r, d = K._class_of(cls, a, b)
        nd = self._node(e, a, b, cls, big, M, nd, r, d)
        if M and nd["rule"] != "atom":
            w = K.reduce_mod(nd["val"], M)
            if w != nd["val"]:
                nd["mod"], nd["val"] = M, w
        return nd

    def _node(self, e, a, b, cls, big, M, nd, r, d):
        from colony.frontier_conjectures import canon
        op = e[0]

        def atom():
            for k in ("kids", "lemma", "inner", "Qe", "de"):
                nd.pop(k, None)
            nd.update(rule="atom", val=K.V(0, {f"{canon(e)}@{a},{b}": 1}))
            return nd

        if op == "p":
            name = e[1]
            if name == "n":
                if M and d > 1 and math.gcd(d, M) > 1:
                    nd.update(rule="nclass", val=K.V(r, {}, d))
                else:
                    nd.update(rule="n", val=K.V(b, {"n@1,0": a}))
                return nd
            bv = K.branch_value(name, cls, a, b)
            if bv:
                nd.update(rule="branch", lemma=bv[0], val=bv[1])
                return nd
            lv = K.value_lemma(name, r, d, big)
            if lv and (lv[1]["d"] == 0 or (M and math.gcd(lv[1]["d"], M) > 1)):
                nd.update(rule="lemma", lemma=lv[0], val=lv[1])
                return nd
            if big and a % 2 == 0 and b % 2 == 0:
                r2, d2 = K._class_of(cls, a // 2, b // 2)
                lm = K.dbl_lemma(name, r2 % 2 if d2 % 2 == 0 else None)
                if lm:
                    nd.update(rule="dbl_rw", lemma=lm[0],
                              val=K.V(lm[2], {K.atom(k, a // 2, b // 2): v for k, v in lm[1].items()}))
                    return nd
            if b >= 1:
                sl = K.step_lemma(name, r, d, big)
                if sl:
                    nd.update(rule="step_rw", lemma=sl[0], val=K.V(sl[1], {K.atom(name, a, b - 1): 1}))
                    return nd
            return atom()
        if op in ("+", "-", "*"):
            u = self.node(e[1], a, b, cls, big, M)
            v = self.node(e[2], a, b, cls, big, M)
            w = K.add(u["val"], v["val"], 1 if op == "+" else -1) if op != "*" else K.mul(u["val"], v["val"])
            if w is None:
                return atom()
            nd.update(rule="arith", kids=[u, v], val=w)
            return nd
        if op == "gcd":
            u = self.node(e[1], a, b, cls, big, M or ARG_M)
            v = self.node(e[2], a, b, cls, big, M or ARG_M)
            if K.gcd_tau_applies(e, a, b, cls, u["val"], v["val"]):
                nd.update(rule="gcd_tau", kids=[u, v], val=K.V(1))
                return nd
            w = K.gcd_val(u["val"], v["val"], K.nonneg(e[1]), K.nonneg(e[2]))
            if w is None or (M == 0 and w["d"]):
                return atom()
            nd.update(rule="gcd", kids=[u, v], val=w)
            return nd
        if op == "sh":
            u = self.node(e[1], a, b + 1, cls, big, M)
            nd.update(rule="sh", kids=[u], val=u["val"])
            return nd
        if op == "dbl":
            u = self.node(e[1], 2 * a, 2 * b, cls, big, M)
            nd.update(rule="dbl", kids=[u], val=u["val"])
            return nd
        if op == "D":
            x = e[1]
            if x[0] == "p":
                lv = K.d_lemma(x[1], r, d, big)
                if lv:
                    nd.update(rule="Dlemma", lemma=lv[0], val=lv[1])
                    return nd
            if x[0] in ("+", "-"):
                u = self.node(("D", x[1]), a, b, cls, big, M)
                v = self.node(("D", x[2]), a, b, cls, big, M)
                nd.update(rule="Dsum", kids=[u, v], val=K.add(u["val"], v["val"], 1 if x[0] == "+" else -1))
                return nd
            if x[0] == "*":
                da = self.node(("D", x[1]), a, b, cls, big, M)
                db = self.node(("D", x[2]), a, b, cls, big, M)
                va = self.node(x[1], a, b, cls, big, M)
                vb = self.node(x[2], a, b, cls, big, M)
                ps = [K.mul(da["val"], db["val"]), K.mul(da["val"], vb["val"]), K.mul(va["val"], db["val"])]
                if None not in ps:
                    w = K.add(K.add(ps[0], ps[1]), ps[2])
                    if K.pure(K.reduce_mod(w, M)) or M == 0:
                        nd.update(rule="Dprod", kids=[da, db, va, vb], val=w)
                        return nd
            u = self.node(x, a, b + 1, cls, big, M)
            v = self.node(x, a, b, cls, big, M)
            nd.update(rule="Ddiff", kids=[u, v], val=K.add(u["val"], v["val"], -1))
            return nd
        if op == "o" and e[1] == "pi" and e[2] == ("p", "prime"):
            g = self.node(("p", "n"), a, b, cls, big, M)       # pi(prime(x)) = x
            nd.update(rule="pi_prime", kids=[g], val=g["val"])
            return nd
        if op == "o" and e[2][0] == "p":
            lm = K.compose_prime_lemma(e[1], e[2][1], big)
            if lm:
                nd.update(rule="o_prime", lemma=lm[0],
                          val=K.V(lm[2], {K.atom(e[2][1], a, b): k for k in lm[1].values()}))
                return nd
        if op == "o":
            g = self.node(e[2], a, b, cls, big, ARG_M)
            gv = g["val"]
            if K.pure(gv):
                if gv["d"] == 0:
                    arr = self.T.t[e[1]]
                    if 1 <= gv["c"] < len(arr):
                        nd.update(rule="o", kids=[g], val=K.V(arr[gv["c"]]))
                        return nd
                else:
                    lv = K.value_lemma(e[1], gv["c"], gv["d"], False)
                    if lv and (lv[1]["d"] == 0 or (M and math.gcd(lv[1]["d"], M) > 1)):
                        nd.update(rule="o", lemma=lv[0], kids=[g], val=lv[1])
                        return nd
            return atom()
        if op == "S":
            if M == 0:
                return atom()
            got = self._S1(e, a, b, cls, M, nd)
            if got is None:
                got = self._S2(e, a, b, cls, M, nd)
            return got if got is not None else atom()
        return atom()

    def _S2(self, e, a, b, cls, M, nd):
        """Running sum over pairs (2j, 2j+1): S(N) for odd N from block sums e(2j) + e(2j+1)."""
        r0, d0 = K._class_of(cls, a, b)
        if d0 % 2 or r0 % 2 == 0 or d0 > 120:
            return None
        Qj = d0
        blocks, de = [], 0
        for u in range(Qj):
            w0 = self.node(e[1], 2, 0, (u, Qj), True, M)
            w1 = self.node(e[1], 2, 1, (u, Qj), True, M)
            w = K.reduce_mod(K.add(w0["val"], w1["val"]), M)
            if not K.pure(w):
                return None
            blocks.append([w0, w1])
            de = math.gcd(de, w["d"])
        de = math.gcd(de, M) if de else M
        if de < 2:
            return None
        P = 2 * Qj * de
        L = d0 * P // math.gcd(d0, P)
        if L > 20000:
            return None
        try:
            x = K.evaluate_prefix(e[1], self.T, K.N0 + L + 3)
        except ValueError:
            return None
        vals = []
        for j in range(L // d0):
            Ns = (r0 + j * d0) % L
            while Ns < K.N0 + 2:
                Ns += L
            vals.append(K.V(x[Ns - 1], {}, de))
        nd.update(rule="S2", Qj=Qj, de=de, blocks=blocks, val=K.join(vals))
        return nd

    def _S1(self, e, a, b, cls, M, nd):
        if True:
            Qe = a * cls[1]
            if Qe > 240:
                return None
            inner, de = [], 0
            for j in range(Qe):
                w = self.node(e[1], 1, 0, (j, Qe), True, M)
                if not K.pure(w["val"]):
                    return None
                inner.append(w)
                de = math.gcd(de, w["val"]["d"])
            de = math.gcd(de, M) if de else M
            if de < 2:
                return None
            P = Qe * de
            r0, d0 = K._class_of(cls, a, b)
            L = d0 * P // math.gcd(d0, P)
            if L > 20000:
                return None
            try:
                x = K.evaluate_prefix(e[1], self.T, K.N0 + L + 1)
            except ValueError:
                return None
            vals = []
            for j in range(L // d0):
                Ns = (r0 + j * d0) % L
                while Ns < K.N0:
                    Ns += L
                vals.append(K.V(x[Ns - 1], {}, de))
            nd.update(rule="S", Qe=Qe, de=de, inner=inner, val=K.join(vals))
            return nd


def _qs(q: int) -> list[int]:
    out = sorted({q * k // math.gcd(q, k) for k in QBASE})
    return [Q for Q in out if Q <= QMAX]


def _ineq_search(form: dict[str, Any]) -> list | None:
    from colony.frontier_conjectures import DBL_MONO, SH_MONO
    rem = dict(form["a"])
    rem["_k"] = form["c"]
    if any("*" in k for k in rem):
        return None
    atoms = [K.split_atom(k) for k in rem if k not in ("_k", "n@1,0")]
    pts = sorted({(a, b) for _n, a, b in atoms}) or [(1, 0)]
    present = {(nm, a, b) for nm, a, b in atoms}
    inst = []
    for (a, b) in pts:
        names = {nm for nm, x, y in present if (x, y) == (a, b)} | {"n", "one"}
        for i, f in enumerate(K.INEQ):
            if set(f) - {"_k"} <= names:
                inst.append(("basic", i, a, b))
    for nm, a, b in present:
        if a % 2 == 0 and b % 2 == 0 and (nm, a // 2, b // 2) in present and nm in DBL_MONO:
            inst.append(("dbl_mono", nm, a // 2, b // 2))
        if (nm, a, b - 1) in present and nm in SH_MONO:
            inst.append(("sh_mono", nm, a, b - 1))
    forms = [(x, K.ineq_instance(*x)) for x in inst]

    def done(r):
        return all(v == 0 for k, v in r.items() if k != "_k") and r.get("_k", 0) >= 0

    def dfs(r, depth, start, path):
        if done(r):
            return path
        if depth == 0:
            return None
        for i in range(start, len(forms)):
            x, f = forms[i]
            for lam in (1, 2):
                nr = dict(r)
                for k, v in f.items():
                    nr[k] = nr.get(k, 0) - lam * v
                got = dfs(nr, depth - 1, i + 1, path + [list(x) + [lam]])
                if got is not None:
                    return got
        return None
    return dfs(rem, 4, 0, [])


def prove(claim: dict[str, Any], T: Any, budget_s: float = PER_CLAIM_S) -> dict[str, Any] | None:
    """Certificate for a registry claim (kind, lhs, rhs, params), re-verified by the checker; else None."""
    from colony import frontier_conjectures as FC
    kind = claim["kind"]
    try:
        le = FC.parse(claim["lhs"])
        re_ = FC.parse(claim["rhs"]) if claim.get("rhs") else None
    except Exception:  # noqa: BLE001
        return None
    p = claim.get("params") or {}
    if kind == "modpat":
        return _recurrence_cert(claim, le, re_, T)
    P = Prover(T, time.time() + budget_s)
    qs = _qs(p["q"]) if kind == "cong" else [1, 2, 4, 6, 12, 24, 36, 60]
    for Q in qs:
        classes = [t for t in range(Q) if kind != "cong" or t % p["q"] == p["s"]]
        out: dict[str, Any] = {}
        method = None
        try:
            for t in classes:
                cls = (t, Q)
                if kind in ("cong", "divides"):
                    method = "periodic residues"
                    one = _residue_class(P, kind, le, re_, p, cls)
                    if one is None:   # squarefree case split: sqfree(n) = 0 / sqfree(n) = 1
                        b0 = _residue_class(P, kind, le, re_, p, (t, Q, 0))
                        b1 = _residue_class(P, kind, le, re_, p, (t, Q, 1)) if b0 is not None else None
                        if b1 is None:
                            raise ValueError("class")
                        one = {"split": "sqfree", "b0": b0, "b1": b1}
                    out[str(t)] = one
                elif kind == "le":
                    method = "basic-inequality derivation"
                    u = P.node(le, 1, 0, cls, True, 0)
                    v = P.node(re_, 1, 0, cls, True, 0)
                    if u["val"]["d"] or v["val"]["d"]:
                        raise ValueError("class")
                    steps = _ineq_search(K.add(v["val"], u["val"], -1))
                    if steps is None:
                        raise ValueError("class")
                    out[str(t)] = {"lhs": u, "rhs": v, "steps": steps}
                elif kind == "identity":
                    method = "closed form (sympy)"
                    out[str(t)] = {"lhs": P.node(le, 1, 0, cls, True, 0), "rhs": P.node(re_, 1, 0, cls, True, 0)}
                elif kind == "rec":
                    method = "closed form (sympy)"
                    k = len(p["c"])
                    out[str(t)] = {"shifts": [P.node(le, 1, i, cls, True, 0) for i in range(k + 1)]}
                else:
                    return None
        except _Timeout:
            return None
        except ValueError:
            continue
        cert = {"method": method, "Q": Q, "N0": K.N0, "classes": out,
                "finite_check": [1, K.N0 - 1], "lemmas": sorted(_lemmas(out))}
        ok, _why = K.check(cert, claim, T)
        if ok:
            cert["checker"] = "colony.proof_check.check: ok"
            return cert
    return _recurrence_cert(claim, le, re_, T) if kind == "cong" else None


def _recurrence_cert(claim: dict[str, Any], le: tuple, re_: tuple | None, T: Any) -> dict[str, Any] | None:
    """'recurrence residues': parts with a citable linear recurrence (OEIS-listed signature from the
    local cache, or a defining recurrence), residue period computed and re-checked by the checker."""
    try:
        from colony import known_check as KC
        c = {"kind": claim["kind"], "lhs": claim["lhs"], "rhs": claim.get("rhs") or "",
             "params": claim.get("params") or {}, "_le": le, "_re": re_}
        if re_ is not None:
            return None
        from colony import frontier_conjectures as FC
        recs = KC.recurrence_recs(c, T, KC.Net(budget=0), FC.default_lookup())
        return KC.recurrence_certificate(c, T, recs) if recs else None
    except Exception:  # noqa: BLE001
        return None


def _residue_class(P: "Prover", kind: str, le: tuple, re_: tuple | None, p: dict[str, Any], cls: tuple):
    if kind == "cong":
        nd = P.node(le, 1, 0, cls, True, p["m"])
        v = K.reduce_mod(nd["val"], p["m"])
        if not K.pure(v) or (v["d"] and v["d"] % p["m"]) or (v["c"] - p["r"]) % p["m"]:
            return None
        return {"lhs": nd}
    for Mv in (ARG_M, 0):
        u = P.node(le, 1, 0, cls, True, 0)
        v = P.node(re_, 1, 0, cls, True, Mv)
        if K.divides_ok(u["val"], v["val"], K.positive(le)):
            return {"lhs": u, "rhs": v}
    return None


def _lemmas(x: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(x, dict):
        if x.get("lemma"):
            out.add(x["lemma"])
        for v in x.values():
            out |= _lemmas(v)
    elif isinstance(x, list):
        for v in x:
            out |= _lemmas(v)
    return out


def summary_of(cert: dict[str, Any]) -> str:
    ls = cert.get("lemmas") or []
    if cert.get("method") == "recurrence residues":
        src = "; ".join(f"{k}: {v['source']}" for k, v in sorted((cert.get("recurrences") or {}).items()))
        return (f"recurrence residues: residues periodic with period {cert.get('period')} from n = "
                f"{cert.get('preperiod_from')} ({src[:200]}); every n <= {cert['finite_check'][1]} checked")
    return (f"{cert['method']}: n split mod {cert['Q']}, every class derived from "
            f"{len(ls)} lemma(s){': ' + '; '.join(ls)[:240] if ls else ''}; n < {cert['N0']} checked directly")


def run(T: Any = None, *, state_path: Path | None = None, write: bool = True,
        budget_s: float = BUDGET_S) -> dict[str, Any]:
    """Attempt proofs for the frontier registry and the authored frontier checks."""
    from colony import frontier_conjectures as FC
    from colony.frontier_checks import check_name
    t0 = time.time()
    st = FC.load_state(state_path or FC.STATE)
    if T is None:
        if FC._BRIDGE_T is None:
            FC._BRIDGE_T = FC.Tables(lim=FC.BRIDGE_LIM, exp_n=FC.BRIDGE_EXP)
        T = FC._BRIDGE_T
    reg = st.get("registry") or {}
    prev = {}
    try:
        prev = json.loads(REPORT.read_text(encoding="utf-8")).get("results") or {}
    except Exception:  # noqa: BLE001
        pass
    claims: dict[str, dict[str, Any]] = {}
    for r in reg.values():
        if r.get("falsified_later") or not r.get("sig"):
            continue
        claims[r["statement"]] = dict(r, check=check_name(r))
    try:  # authored frontier checks (lemma_impl literals), including ones no longer in the registry
        import ast
        from colony.authoring import _lemma_impl
        src = _lemma_impl().read_text(encoding="utf-8")
        for fn in ast.parse(src).body:
            if isinstance(fn, ast.FunctionDef) and fn.name.startswith("check_authored_frontier_"):
                lit = next((x for x in ast.walk(fn) if isinstance(x, ast.Dict)), None)
                if lit is None:
                    continue
                c = ast.literal_eval(lit)
                s = FC.statement({"kind": c["kind"], "params": c.get("params") or {}, "lhs": c["lhs"],
                                  "rhs": c.get("rhs") or ""})
                claims.setdefault(s, dict(c, statement=s))
                claims[s]["check"] = fn.name[len("check_"):]
                claims[s]["authored"] = True
    except Exception:  # noqa: BLE001
        pass
    results: dict[str, Any] = {}
    n_new = 0
    for s, c in sorted(claims.items(), key=lambda kv: (kv[1].get("kind") == "rec", kv[0])):
        old = prev.get(s)
        # v4 (2026-10-23) adds 'recurrence residues': earlier 'not proved' results are retried once
        if old and ((old.get("status") == "proved" and old.get("v") in (3, 4)) or
                    (old.get("status") == "not proved" and old.get("v") == 4)):
            results[s] = dict(old, authored=bool(c.get("authored")), unknown=bool(c.get("unknown")))
            continue
        if time.time() - t0 > budget_s:
            results[s] = {"status": "not attempted (budget)", "kind": c["kind"], "check": c.get("check")}
            continue
        cert = prove(c, T)
        n_new += 1
        results[s] = {"v": 4, "status": "proved" if cert else "not proved", "kind": c["kind"],
                      "check": c.get("check"), "authored": bool(c.get("authored")),
                      "prior_certificate": bool(c.get("certificate")),
                      "unknown": bool(c.get("unknown")), "checks": c.get("checks"),
                      "summary": summary_of(cert) if cert else None, "certificate": cert}
    proved = [s for s, r in results.items() if r["status"] == "proved"]
    if mode() == "live":
        changed = False
        for r in reg.values():
            res = results.get(r.get("statement"))
            if res and res["status"] == "proved" and not r.get("certificate"):
                r["certificate"] = {"method": res["certificate"]["method"], "summary": res["summary"],
                                    "checker": "colony.proof_check.check: ok"}
                r["label"] = LABEL
                changed = True
        if changed and write:
            p = state_path or FC.STATE
            p.write_text(json.dumps(st, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    by_kind: dict[str, list[int]] = {}
    for r in results.values():
        k = by_kind.setdefault(r["kind"], [0, 0])
        k[0] += 1
        k[1] += r["status"] == "proved"
    out = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "mode": mode(),
           "n_claims": len(results), "n_proved": len(proved),
           "n_proved_new": sum(1 for s in proved if not results[s].get("prior_certificate")),
           "n_surprises_proved": sum(1 for s in proved if results[s].get("unknown")),
           "n_authored_proved": sum(1 for s in proved if results[s].get("authored")),
           "n_authored": sum(1 for r in results.values() if r.get("authored")),
           "by_kind": by_kind, "attempted_now": n_new, "seconds": round(time.time() - t0, 2),
           "results": results,
           "note": ("'machine-proved (certificate)' = every residue class derived from named classical lemmas "
                    "and re-verified by colony.proof_check, n < N0 checked directly; anything else stays "
                    "'conjecture surviving N checks'.")}
    if write:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    import sys
    res = run(budget_s=float(sys.argv[1]) if len(sys.argv) > 1 else 600.0)
    print(json.dumps({k: v for k, v in res.items() if k != "results"}, indent=1))
    for s, r in sorted(res["results"].items(), key=lambda kv: kv[1]["status"]):
        if r["kind"] != "rec" or not r.get("prior_certificate"):
            print(f"{r['status']:13} {'S' if r.get('unknown') else ' '}{'A' if r.get('authored') else ' '}"
                  f"{'c' if r.get('prior_certificate') else ' '} {s[:90]}")
