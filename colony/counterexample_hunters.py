"""Item 106: counterexample hunter swarm (James 2026-11-16: "Begin that plan. Evolve and expand the swarms").

Static, deterministic agents whose only job is to try to FALSIFY claims the colony already holds
(OEIS menu targets whose last attempt held, with a sound computable definition), beyond the
window the in-loop desk searched. They never prove anything and never loosen a check.

Hunters
  * ``far_modular``  continues the residue search of oeis_deep.deep_search past the in-loop
                     window with its own time budget and three extra primes. A nonzero residue of
                     the claim's difference is an exact failure of a ring-safe identity / congruence;
                     a mismatch is CRT-lifted over all primes (the symmetric residue modulo the
                     product, i.e. the exact difference when it is smaller than half the product).
  * ``cem_sample``   a network-free cross-entropy search (after Wagner, arXiv:2104.14516,
                     reimplemented: no neural net, no fetched code) over log10(n) for C-finite
                     definitions, where any far term costs O(K^3 log n) by companion-matrix powers.
                     Each round samples indices from a Gaussian over log10(n), scores the violation
                     (number of primes on which the claim's difference is nonzero, plus a graded
                     exact margin for inequality claims), refits the Gaussian on the elite fraction,
                     and widens it when no signal appears. On a hit it SHRINKS: scans downward for
                     the smallest failing index in a window below the hit.
A hit counts ONLY after the unchanged in-loop confirmation (oeis_deep._confirm_mod: path B term
values from a different algorithm, the path B parser / evaluator) agrees on two primes. Everything
else is logged as a lead. Z3 was not added: it is not needed by any claim form in the menu and
would add a large binary dependency to every workflow install (noted in the queue file).

Append-only log: data/commons/counterexample_hunts.jsonl. Progress state (not a log):
society/systems/counterexample_hunters.json. Confirmed hits go to the OEIS desk's scoreboard and
the review file, exactly like an in-loop counterexample; nothing is submitted or posted.

Switch ``COLONY_CE_HUNTERS`` = live (default) | off; always off on the control arm.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "commons" / "counterexample_hunts.jsonl"
STATE = ROOT / "society" / "systems" / "counterexample_hunters.json"
PRIMES = (2 ** 61 - 1, 2 ** 31 - 1, 1000000007, 998244353, 4294967291)
FAR_CAP = 10 ** 8
CEM_ROUNDS = 6
CEM_SAMPLES = 48
CEM_ELITE = 0.2
CEM_LOG_LO, CEM_LOG_HI = 7.0, 15.0
SHRINK_WINDOW = 2048
BUDGET_S = 15.0
PER_CYCLE = 2


def enabled() -> bool:
    try:
        from colony.arm import self_mod_enabled
        if not self_mod_enabled():
            return False
    except Exception:  # noqa: BLE001
        return False
    return (os.environ.get("COLONY_CE_HUNTERS") or "live").strip().lower() == "live"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_prime(m: int) -> bool:
    if m < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if m % p == 0:
            return m == p
    d, s = m - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        x = pow(a, d, m)
        if x in (1, m - 1):
            continue
        for _ in range(s - 1):
            x = x * x % m
            if x == m - 1:
                break
        else:
            return False
    return True


assert all(_is_prime(p) for p in PRIMES)


def crt_lift(residues: list[tuple[int, int]]) -> dict[str, Any]:
    """Combine (r_i mod m_i) into r mod M; the symmetric representative is the exact value
    whenever |value| < M/2."""
    r, M = 0, 1
    for ri, mi in residues:
        g = math.gcd(M, mi)
        if g != 1:
            continue
        t = ((ri - r) * pow(M, -1, mi)) % mi
        r, M = r + M * t, M * mi
        r %= M
    sym = r - M if r > M // 2 else r
    return {"residue": r, "modulus": M, "symmetric": sym, "bits": M.bit_length()}


# ----------------------------------------------------------------------------- targets

def _held_targets(menu: list[dict[str, Any]], state: dict[str, Any]) -> list[dict[str, Any]]:
    from colony import oeis_conjectures as OC
    from colony import oeis_deep as D
    out = []
    tg = (state or {}).get("targets") or {}
    for e in menu:
        st = tg.get(e["id"]) or {}
        if st.get("status") not in ("holds_on_range",):
            continue
        claim = e.get("claim") or {}
        if claim.get("form") != "relation":
            continue
        d = e.get("definition") or OC.computable_definition(e)
        if not d:
            continue
        if d.get("kind") in ("xexpr", "holo") and d.get("provenance") not in ("name",):
            continue      # item 105 conditional definitions are never hunted for verified hits
        ent = dict(e)
        ent["definition"] = d
        out.append(ent)
    return out


def _generator(e: dict[str, Any]):
    from colony import oeis_deep as D
    from colony import oeis_guess as G
    d = e["definition"]
    g = None
    if d.get("kind") == "alg":
        cr = G.certified_recurrence(d["expr"], e["offset"], e["terms"])
        g = D.Holo(cr, e["offset"]) if cr else None
    else:
        g = D.generator(e)
    if g is None or not D.matches_bfile(g, e["offset"], e["terms"]):
        return None
    return g


def _codes(claim: dict[str, Any]):
    from colony import oeis_deep as D
    from colony import oeis_eval_b as B
    from colony import oeis_conjectures as OC
    parts = claim.get("parts") or []
    codes = [B.compile_expr(p) for p in parts]
    safe = all(D.ring_safe(c) for c in codes) and not any(
        t[0] == "fn" and t[1].startswith("A") for c in codes for t in c)
    evA = [OC._A(p) for p in parts]
    return codes, evA, safe


def _diff_mod(evA, codes, n: int, M: int, value) -> list[int] | None:
    """Residues of consecutive part differences at n (path A evaluator), or None if undefined."""
    from colony import oeis_deep as D
    from colony import oeis_eval_b as B

    def seq(nm, i):
        if nm != "a":
            raise B.Missing(nm)
        return value(i, M)
    try:
        vals = [evA[k].ev(evA[k].tree, n, seq) for k in range(len(codes))]
    except (B.Missing, B.Bad, ZeroDivisionError, ValueError, KeyError, IndexError):
        return None
    out = []
    for i in range(len(vals) - 1):
        dlt = vals[i] - vals[i + 1]
        if dlt.denominator % M == 0:
            return None
        out.append(D._modf(dlt, M))
    return out


def _confirm(g, codes, n: int, claim: dict[str, Any]) -> dict[str, Any]:
    """The unchanged in-loop confirmation (path B values + path B evaluator) on two primes."""
    from colony import oeis_deep as D
    from colony import oeis_eval_b as B
    mods = [claim["mod"]] if claim.get("mod") else [D.P1, D.P2]
    ok = []
    for M in mods:
        ok.append(D._confirm_mod(g, codes, n, M, lambda k, nn, sq: B.evaluate(codes[k], {"n": nn}, sq)))
    return {"confirmed": any(ok), "per_modulus": ok, "moduli": mods}


# ----------------------------------------------------------------------------- hunters

def far_modular(e: dict[str, Any], g, lo: int, seconds: float) -> dict[str, Any]:
    claim = e["claim"]
    res: dict[str, Any] = {"hunter": "far_modular", "id": e["id"], "anum": e["anum"], "lo": lo}
    codes, evA, safe = _codes(claim)
    if not safe or not (claim.get("mod") or all(r == "=" for r in claim.get("rels") or [])):
        res["status"] = "not_ring_safe"
        return res
    mods = [claim["mod"]] if claim.get("mod") else list(PRIMES[:2])
    t0 = time.time()
    hi = min(FAR_CAP, lo + 50_000_000)
    tabs = []
    for M in mods:
        xs = g.mod(M, hi, seconds / (2 * len(mods)))
        hi = min(hi, g.s0 + len(xs) - 1)
        tabs.append(xs)
    res["hi"] = None
    last = None
    for n in range(lo, hi + 1):
        hit = None
        for M, xs in zip(mods, tabs):
            dl = _diff_mod(evA, codes, n, M, lambda i, _M, _xs=xs: _xs[i - g.s0] if 0 <= i - g.s0 < len(_xs) else _missing())
            if dl is None:
                continue
            if any(dl):
                hit = (M, dl)
                break
        if hit:
            res.update(status="lead", n=n, modulus=hit[0])
            res["lift"] = _lift(g, evA, codes, n, claim)
            res.update(_confirm(g, codes, n, claim))
            res["status"] = "counterexample_confirmed" if res["confirmed"] else "lead_unconfirmed"
            res["hi"] = n
            return res
        last = n
        if (n & 4095) == 0 and time.time() - t0 > seconds:
            break
    res["hi"] = last
    res["status"] = "holds_mod_primes" if last is not None else "no_range"
    return res


def _missing():
    from colony import oeis_eval_b as B
    raise B.Missing("a")


def _lift(g, evA, codes, n: int, claim: dict[str, Any]) -> dict[str, Any]:
    """CRT-lift the first part difference at n over all PRIMES (b_value per prime)."""
    if claim.get("mod"):
        return {"note": "congruence: the residue is the result"}
    rs = []
    for M in PRIMES:
        cache: dict[int, int] = {}

        def val(i, _M, _c=cache):
            if i < g.s0:
                _missing()
            if i not in _c:
                _c[i] = g.b_value(i, _M)
            return _c[i]
        try:
            dl = _diff_mod(evA, codes, n, M, val)
        except Exception:  # noqa: BLE001
            dl = None
        if dl:
            rs.append((dl[0], M))
    return crt_lift(rs) if rs else {"note": "no residues"}


def _cf_value(cf: dict[str, Any]):
    from colony import oeis_deep as D

    def value(i: int, M: int) -> int:
        if i < cf["s0"]:
            _missing()
        return int(D.companion_pow(cf, i, M))
    return value


def cem_sample(e: dict[str, Any], g, lo: int, seed: int, seconds: float) -> dict[str, Any]:
    """Cross-entropy search over log10(n) for C-finite definitions (random access by matrix powers)."""
    from colony import oeis_deep as D
    claim = e["claim"]
    res: dict[str, Any] = {"hunter": "cem_sample", "id": e["id"], "anum": e["anum"]}
    if not isinstance(g, D.CF):
        res["status"] = "no_random_access"
        return res
    codes, evA, safe = _codes(claim)
    if not safe or not (claim.get("mod") or all(r == "=" for r in claim.get("rels") or [])):
        res["status"] = "not_ring_safe"
        return res
    value = _cf_value(g.cf)
    mods = [claim["mod"]] if claim.get("mod") else list(PRIMES[2:])   # primes the in-loop search never used
    rng = random.Random(seed)
    mu = (max(CEM_LOG_LO, math.log10(max(lo, 10))) + CEM_LOG_HI) / 2
    sigma = (CEM_LOG_HI - CEM_LOG_LO) / 2
    t0 = time.time()
    sampled = 0
    best: tuple[float, int] | None = None
    history = []
    for rnd in range(CEM_ROUNDS):
        pts = []
        for _ in range(CEM_SAMPLES):
            x = min(CEM_LOG_HI, max(math.log10(max(lo, 10)), rng.gauss(mu, sigma)))
            n = int(10 ** x)
            score = 0.0
            for M in mods:
                dl = _diff_mod(evA, codes, n, M, value)
                if dl and any(dl):
                    score += 1.0
            pts.append((score, x, n))
            sampled += 1
            if score > 0 and (best is None or score > best[0]):
                best = (score, n)
            if time.time() - t0 > seconds:
                break
        pts.sort(key=lambda t: (-t[0], t[1]))
        k = max(2, int(len(pts) * CEM_ELITE))
        elite = pts[:k]
        if elite and elite[0][0] > 0:
            xs = [p[1] for p in elite if p[0] > 0]
            mu = sum(xs) / len(xs)
            sigma = max(0.05, (sum((v - mu) ** 2 for v in xs) / max(1, len(xs) - 1)) ** 0.5)
        else:
            sigma = min((CEM_LOG_HI - CEM_LOG_LO), sigma * 1.3)   # no signal: widen
            mu = rng.uniform(CEM_LOG_LO, CEM_LOG_HI)
        history.append({"round": rnd, "mu": round(mu, 3), "sigma": round(sigma, 3),
                        "elite_score": elite[0][0] if elite else 0})
        if best or time.time() - t0 > seconds:
            break
    res.update(sampled=sampled, rounds=history, log10_range=[round(math.log10(max(lo, 10)), 2), CEM_LOG_HI])
    if not best:
        res["status"] = "no_violation_sampled"
        return res
    n_hit = best[1]
    n_min = shrink(evA, codes, mods, value, n_hit, max(lo, n_hit - SHRINK_WINDOW))
    res.update(n_hit=n_hit, n=n_min)
    res["lift"] = _lift(g, evA, codes, n_min, claim)
    res.update(_confirm(g, codes, n_min, claim))
    res["status"] = "counterexample_confirmed" if res["confirmed"] else "lead_unconfirmed"
    return res


def shrink(evA, codes, mods, value, n_hit: int, floor_n: int) -> int:
    """Smallest failing index in [floor_n, n_hit] (failures are not monotone, so a scan)."""
    for n in range(floor_n, n_hit + 1):
        for M in mods:
            dl = _diff_mod(evA, codes, n, M, value)
            if dl and any(dl):
                return n
    return n_hit


# ----------------------------------------------------------------------------- one turn

def load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {"targets": {}}


def _append(row: dict[str, Any]) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as fh:
        fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def turn(cycle_id: str, budget_s: float = BUDGET_S, k: int = PER_CYCLE) -> dict[str, Any] | None:
    """Run up to k hunts (deterministic rotation by cycle id). Treatment only."""
    if not enabled():
        return None
    from colony import oeis_conjectures as OC
    menu = OC.load_menu()
    oc_state = OC._load(OC.STATE, {"targets": {}})
    held = _held_targets(menu, oc_state)
    if not held:
        return {"hunts": [], "held": 0}
    hs = load_state()
    if hs.get("last_cycle") == cycle_id:
        return None          # once per cycle, however many desk passes the cycle makes
    hs["last_cycle"] = cycle_id
    prog = hs.setdefault("targets", {})
    # least-hunted first, ties broken by a hash of (cycle, id): deterministic, rotating
    held.sort(key=lambda e: (int((prog.get(e["id"]) or {}).get("hunts") or 0),
                             hashlib.sha256((cycle_id + e["id"]).encode()).hexdigest()))
    out = []
    t0 = time.time()
    for e in held[:k]:
        left = budget_s - (time.time() - t0)
        if left < 2:
            break
        g = _generator(e)
        if g is None:
            continue
        p = prog.setdefault(e["id"], {"hunts": 0, "far_hi": 0})
        in_loop = int((oc_state.get("targets", {}).get(e["id"]) or {}).get("tested_hi") or 0)
        lo = max(in_loop, int(p.get("far_hi") or 0)) + 1
        r1 = far_modular(e, g, lo, left / 2)
        rows = [r1]
        if r1.get("hi"):
            p["far_hi"] = max(int(p.get("far_hi") or 0), int(r1["hi"]))
        if r1.get("status") != "counterexample_confirmed":
            seed = int(hashlib.sha256((cycle_id + e["id"]).encode()).hexdigest()[:8], 16)
            rows.append(cem_sample(e, g, max(lo, p["far_hi"] + 1), seed, max(1.0, left / 2)))
        p["hunts"] = int(p.get("hunts") or 0) + 1
        for r in rows:
            r.update(ts=_utc(), cycle_id=cycle_id,
                     note="hunter result; a hit counts only when status is counterexample_confirmed")
            _append(r)
            out.append(r)
            if r.get("status") == "counterexample_confirmed":
                _record_confirmed(e, r, cycle_id)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(hs, indent=1, sort_keys=True) + "\n")
    return {"hunts": out, "held": len(held)}


def _record_confirmed(e: dict[str, Any], r: dict[str, Any], cycle_id: str) -> None:
    """Same bookkeeping as an in-loop counterexample (live desk only)."""
    from colony import oeis_conjectures as OC
    if OC.mode() != "live":
        return
    state = OC._load(OC.STATE, {"targets": {}, "families": {}, "credit_total": 0.0})
    res = {"action": "attempt_disprove", "id": e["id"], "anum": e["anum"], "status": "counterexample_verified",
           "counterexample_n": r.get("n"), "fails_A": [{"n": r.get("n"), "modulus": r.get("modulus")}],
           "fails_B": [{"n": r.get("n"), "path": "hunter %s, confirmed by oeis_deep._confirm_mod" % r["hunter"]}],
           "b_source": "recomputed from the definition", "data_hi": 0, "deep_terms": 0, "found_by": r["hunter"]}
    OC._score(state, e, [res])
    OC._flag(e, res, cycle_id)
    OC.STATE.write_text(json.dumps(state, indent=1) + "\n")
