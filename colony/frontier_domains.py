"""Two new verifiable domains for the frontier generator (COLONY_DOMAINS = off | shadow | live).

automatic sequences / combinatorics on words (0/1 sequences, tabulated as far as the arithmetic
primitives; each built from its digit rule and checked against its morphism in the tests)
  tm     Thue-Morse                 popcount(n) mod 2              | morphism 0->01, 1->10   (A010060)
  rs     Rudin-Shapiro (0/1)        #('11' blocks in binary) mod 2 | 4-letter morphism       (A020987)
  pfold  regular paperfolding       n = 2^k m, m = 1 (mod 4)       | a(2n+1)=a(n) toeplitz   (A014577 shifted)
  pdbl   period-doubling            v2(n) mod 2                    | morphism 0->01, 1->00   (A096268 shifted)
  baum   Baum-Sweet                 no odd block of 0s in binary   | b(4n)=b(n), b(2n+1)=b(n), b(4n+2)=0 (A086747)
  fibw   Fibonacci word             Beatty floor((n+2)/phi)-...    | morphism 0->01, 1->0    (A003849)
partition / q-series products (Euler transform of the exponents c_k in prod (1-q^k)^(-c_k);
checked against brute-force enumeration of the objects in the tests)
  overpart  overpartitions          prod (1+q^k)/(1-q^k)            (A015128)
  podd      odd parts distinct      prod (1+q^(2k-1))/(1-q^(2k))    (A006950)
  cubic     cubic partitions        prod 1/((1-q^k)(1-q^(2k)))      (A002513)
  pplane    plane partitions        prod (1-q^k)^(-k), MacMahon     (A000219)

Honest labelling: a claim built only from the words (with n, one and the generator's operators) is
a first-order statement about automatic sequences, decidable in principle (e.g. Walnut); the
known-results check labels it so and it earns no surprise credit. Modes as for the other ingredients:
off (tables exist, never sampled), shadow (dry pass, report only, nothing registered or authored),
live (sampled by the real generator; same filters, reference check, Oracle and caps).
"""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "society" / "systems" / "frontier_domains.json"
GROUPS = {"words": ("tm", "rs", "pfold", "pdbl", "baum", "fibw"),
          "qseries": ("overpart", "podd", "cubic", "pplane")}
WORDS = GROUPS["words"]
PRIMS = tuple(p for g in GROUPS.values() for p in g)
POSITIVE = GROUPS["qseries"]
ANUM = {"tm": "A010060", "rs": "A020987", "pfold": "A014577", "pdbl": "A096268", "baum": "A086747",
        "fibw": "A003849", "overpart": "A015128", "podd": "A006950", "cubic": "A002513", "pplane": "A000219"}
QS_CAP = 2004
_FORCE = False


def mode() -> str:
    m = os.environ.get("COLONY_DOMAINS", "off").strip().lower()
    return m if m in ("off", "shadow", "live") else "off"


def active() -> bool:
    return _FORCE or mode() == "live"


# ----------------------------------------------------------------------------- words (digit rules)
def word(name: str, N: int) -> list[int]:
    """[a(0), a(1), ..., a(N)] from the digit / arithmetic rule."""
    if name == "tm":
        return [bin(n).count("1") & 1 for n in range(N + 1)]
    if name == "rs":
        return [bin(n & (n >> 1)).count("1") & 1 for n in range(N + 1)]
    if name == "pfold":
        out = [0]
        for n in range(1, N + 1):
            m = n // (n & -n)
            out.append(1 if m % 4 == 1 else 0)
        return out
    if name == "pdbl":
        return [0] + [((n & -n).bit_length() - 1) & 1 for n in range(1, N + 1)]
    if name == "baum":
        out = [1]
        for n in range(1, N + 1):
            blocks = bin(n)[2:].split("1")
            out.append(0 if any(len(b) % 2 for b in blocks) else 1)
        return out
    if name == "fibw":   # A003849(n) = 2 - (floor((n+2) phi) - floor((n+1) phi)); floor(k phi) = (k + isqrt(5k^2)) // 2
        fl = lambda k: (k + math.isqrt(5 * k * k)) // 2  # noqa: E731
        return [2 - (fl(n + 2) - fl(n + 1)) for n in range(N + 1)]
    raise KeyError(name)


def word_by_morphism(name: str, N: int) -> list[int]:
    """The same words from their morphisms / recursions (the second, independent construction)."""
    def iterate(rules: dict[str, str], start: str, coding: dict[str, int]) -> list[int]:
        w = start
        while len(w) <= N:
            w = "".join(rules[c] for c in w)
        return [coding[c] for c in w[:N + 1]]
    if name == "tm":
        return iterate({"0": "01", "1": "10"}, "0", {"0": 0, "1": 1})
    if name == "rs":
        return iterate({"a": "ab", "b": "ac", "c": "db", "d": "dc"}, "a", {"a": 0, "b": 0, "c": 1, "d": 1})
    if name == "pdbl":   # A096268 (offset 0) is v2(n+1) mod 2: our a(n) = A096268(n-1)
        w = iterate({"0": "01", "1": "00"}, "0", {"0": 0, "1": 1})
        return [0] + w[:N]
    if name == "fibw":
        return iterate({"0": "01", "1": "0"}, "0", {"0": 0, "1": 1})
    if name == "pfold":
        a = [0] * (N + 1)
        for n in range(1, N + 1):
            a[n] = a[n // 2] if n % 2 == 0 else (1 if n % 4 == 1 else 0)
        return a
    if name == "baum":
        b = [1] * (N + 1)
        for n in range(1, N + 1):
            if n % 2 == 1:
                b[n] = b[n // 2]
            elif n % 4 == 2:
                b[n] = 0
            else:
                b[n] = b[n // 4]
        b[0] = 1
        return b
    raise KeyError(name)


# ----------------------------------------------------------------------------- q-series products
EXPONENTS = {
    "overpart": lambda k: 2 if k % 2 else 1,
    "podd": lambda k: 1 if k % 2 else (0 if k % 4 == 2 else 1),
    "cubic": lambda k: 2 if k % 2 == 0 else 1,
    "pplane": lambda k: k,
}


def euler_transform(c: Any, N: int) -> list[int]:
    """Coefficients a(0..N) of prod_k (1-q^k)^(-c(k)) by a(n) = (1/n) sum_k b(k) a(n-k), b(k) = sum_{d|k} d c(d)."""
    b = [0] * (N + 1)
    for d in range(1, N + 1):
        cd = c(d) * d
        if cd:
            for k in range(d, N + 1, d):
                b[k] += cd
    a = [1] + [0] * N
    for n in range(1, N + 1):
        s = 0
        for k in range(1, n + 1):
            s += b[k] * a[n - k]
        a[n] = s // n
    return a


def qseries(name: str, N: int) -> list[int]:
    return euler_transform(EXPONENTS[name], N)


def table(name: str, T: Any = None) -> list[int]:
    if name in WORDS:
        n = int(getattr(T, "lim", 0) or 0) or 20000
        return word(name, n)
    e = max(4, min(int(getattr(T, "exp_n", QS_CAP) or QS_CAP), QS_CAP))
    return qseries(name, e)


def automatic_only(prims: set[str]) -> bool:
    """True when every primitive is a word (or n / one): a decidable automatic-sequence statement."""
    return bool(prims & set(WORDS)) and prims <= set(WORDS) | {"n", "one"}


# ----------------------------------------------------------------------------- report-only tally
STAGES = ("produced", "fresh", "passed_filter", "tested", "survived", "surprise", "explained_by_reference",
          "no_reference_found", "machine_checked", "explained_by_known_check")


def new_tally() -> dict[str, dict[str, int]]:
    return {p: {s: 0 for s in STAGES} for p in PRIMS}


def shadow_cycle(cycle_id: str, T: Any = None) -> dict[str, Any] | None:
    global _FORCE
    from colony import frontier_conjectures as fc
    tally = new_tally()
    _FORCE = True
    try:
        summ = fc.run_cycle(f"{cycle_id}:domains", T=T, write=False, tally=tally)
    finally:
        _FORCE = False
    return record(cycle_id, "shadow", tally, summ)


def record(cycle_id: str, mode_: str, tally: dict, summ: dict | None) -> dict[str, Any]:
    try:
        st = json.loads(REPORT.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        st = {}
    tot = st.get("totals") or {}
    for p, row in tally.items():
        for k, v in row.items():
            tot.setdefault(p, {}).setdefault(k, 0)
            tot[p][k] += v
    surv = [{"statement": s["statement"], "unknown": s.get("unknown"), "why": s.get("unknown_reason"),
             "deep": s.get("deep")} for s in ((summ or {}).get("new_survivors") or [])
            if any(re.search(rf"(?<![A-Za-z0-9_]){p}(?![A-Za-z0-9_])", s["statement"]) for p in PRIMS)]
    groups = {g: {k: sum(tally[p][k] for p in ps) for k in STAGES} for g, ps in GROUPS.items()}
    hist = (st.get("history") or []) + [{"cycle_id": cycle_id, "mode": mode_, "groups": groups, "survivors": surv[:8]}]
    out = {"note": "Per-primitive counts for the new domains (colony/frontier_domains.py). shadow = dry pass, "
                   "nothing registered or authored; live = the real pass.", "mode": mode_, "anums": ANUM,
           "totals": tot, "history": hist[-30:]}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return out
