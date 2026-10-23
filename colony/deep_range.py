"""Deep falsification range for arithmetic claims (COLONY_DEEP = off | shadow | live; default off).

Sieve-backed tables to DEEP_N = 10^6 for the arithmetic primitives (numpy smallest-prime-factor
sieve, built once per process, ~1-2 s), used only for claims that already survived the held-out
range and every filter. live: a claim built only from these primitives is a surprise (earns
credit) only if it also holds for every n <= DEEP_N; a failure there is recorded as 'falsified at
deep range'. Claims with exponential-growth or short-table parts cannot be taken that far: they are
labelled 'deep range n/a (tested to N)' and earn no credit in live mode (honest: shallow evidence).
"""
from __future__ import annotations

import os
from typing import Any

DEEP_N = 10 ** 6
DEEP_PRIMS = ("n", "one", "phi", "sigma", "tau", "omega", "bigomega", "mu", "rad", "lpf", "gpf", "sopfr", "sqfree",
              "digsum", "popcount", "pi", "tm", "rs", "pfold", "pdbl", "baum", "fibw")
_T: dict[str, list[int]] = {}


def mode() -> str:
    m = os.environ.get("COLONY_DEEP", "off").strip().lower()
    return m if m in ("off", "shadow", "live") else "off"


def tables(N: int = DEEP_N) -> dict[str, list[int]]:
    """Arithmetic functions on 0..N (index 0 = 0) from one numpy spf sieve."""
    if _T.get("_N") == [N]:
        return _T
    import numpy as np
    spf = np.zeros(N + 1, dtype=np.int64)
    for p in range(2, int(N ** 0.5) + 1):
        if spf[p] == 0:
            blk = spf[p * p::p]
            blk[blk == 0] = p
    idx = np.arange(N + 1, dtype=np.int64)
    isp = (spf == 0) & (idx >= 2)
    spf[isp] = idx[isp]
    spf[0] = spf[1] = 0
    # multiplicative data by iterating n -> n / p^e (vectorised over all n at once)
    phi = idx.copy(); sigma = np.ones(N + 1, dtype=np.int64); tau = np.ones(N + 1, dtype=np.int64)
    omega = np.zeros(N + 1, dtype=np.int64); bigo = np.zeros(N + 1, dtype=np.int64)
    rad = np.ones(N + 1, dtype=np.int64); sopfr = np.zeros(N + 1, dtype=np.int64)
    sqf = np.ones(N + 1, dtype=np.int64); gpf = np.ones(N + 1, dtype=np.int64)
    m = idx.copy(); m[0] = 1
    np.seterr(divide="ignore", invalid="ignore")
    while True:
        act = m > 1
        if not act.any():
            break
        p = np.where(act, spf[m], 1)
        e = np.zeros(N + 1, dtype=np.int64); pk = np.ones(N + 1, dtype=np.int64)
        while True:
            dv = act & (m % p == 0)
            if not dv.any():
                break
            m = np.where(dv, m // p, m); e += dv; pk = np.where(dv, pk * p, pk)
        phi = np.where(act, phi // p * (p - 1), phi)
        sigma = np.where(act, sigma * ((pk * p - 1) // (p - 1)), sigma)
        tau = np.where(act, tau * (e + 1), tau)
        omega += act; bigo += e; rad = np.where(act, rad * p, rad); sopfr += e * p
        sqf = np.where(act & (e > 1), 0, sqf); gpf = np.where(act, np.maximum(gpf, p), gpf)
    mu = np.where(sqf == 1, np.where(omega % 2 == 0, 1, -1), 0)
    lpf = np.where(idx >= 2, spf, 1)
    pi = np.cumsum(isp.astype(np.int64))
    ds = np.zeros(N + 1, dtype=np.int64); x = idx.copy()
    while x.any():
        ds += x % 10; x //= 10
    pc = np.zeros(N + 1, dtype=np.int64); x = idx.copy()
    while x.any():
        pc += x & 1; x >>= 1
    out = {"n": idx, "one": np.ones(N + 1, dtype=np.int64), "phi": phi, "sigma": sigma, "tau": tau, "omega": omega,
           "bigomega": bigo, "mu": mu, "rad": rad, "lpf": lpf, "gpf": gpf, "sopfr": sopfr, "sqfree": sqf,
           "digsum": ds, "popcount": pc, "pi": pi}
    _T.clear()
    for k, v in out.items():
        v = v.copy()
        v[0] = 0 if k not in ("one",) else 0
        _T[k] = v.tolist()
    from colony import frontier_domains as DM
    for w in DM.WORDS:
        _T[w] = DM.word(w, N)
    _T["_N"] = [N]
    return _T


def applicable(c: dict[str, Any]) -> bool:
    from colony import frontier_conjectures as FC
    ps = FC.prims_of(c["_le"]) | (FC.prims_of(c["_re"]) if c.get("_re") is not None else set())
    return ps <= set(DEEP_PRIMS)


def test(c: dict[str, Any], T: Any, N: int = DEEP_N) -> dict[str, Any]:
    """{'status': 'survived'|'falsified'|'n/a', 'N': int, 'label': str}"""
    from colony import frontier_conjectures as FC
    if not applicable(c):
        return {"status": "n/a", "N": int((c.get("range") or [0, 0])[1] or 0),
                "label": f"deep range n/a (non-arithmetic parts; tested to {(c.get('range') or [0, 0])[1]})"}
    tab = tables(N)
    M = N // 2 if (FC.canon(c["_le"]) + (FC.canon(c["_re"]) if c.get("_re") is not None else "")).count("dbl") else N
    M -= 2
    if c["kind"] == "rec":
        return {"status": "n/a", "N": 0, "label": "deep range n/a (recurrence claim)"}
    a = FC.evaluate(c["_le"], M, T, tab)
    b = FC.evaluate(c["_re"], M, T, tab) if c.get("_re") is not None else None
    if a is None or (c.get("_re") is not None and b is None):
        return {"status": "n/a", "N": 0, "label": "deep range n/a (does not evaluate to 10^6)"}
    ok, n = FC.holds(c["kind"], c["params"], a, b)
    if ok:
        return {"status": "survived", "N": M, "label": f"survived the deep range n <= {M} ({n} checks)"}
    return {"status": "falsified", "N": M, "label": f"falsified at deep range (n <= {M})"}
