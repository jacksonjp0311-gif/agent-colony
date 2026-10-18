"""COLONY_NEWDATA: the colony picks computational frontier targets and computes past the published frontier.

Menu (we widen it; the colony chooses): integer sequences the colony can compute two independent ways
(Goldbach representation counts / least and closest Goldbach primes, incl. residue-class variants;
Collatz steps, odd/even step counts, excursions, stopping times) and their record sequences (record
positions / values). The colony identifies which OEIS entry a menu item is by its own terms (local
OEIS stripped index), learns the published frontier from the OEIS b-file (fetched politely, cached),
and spends its CPU budget where the expected number of terms past that frontier per CPU-second is
highest (it learns this from its own measured costs).

Honesty rules:
- every term past the frontier is computed by method A and recomputed by an independent method B
  (different algorithm / arithmetic); both must agree, else "unverified";
- all published terms that method A reaches must match the b-file first (else the identification is
  wrong and nothing is claimed);
- no b-file / no OEIS index -> "frontier unknown", never "new";
- "beyond published frontier" means beyond the OEIS b-file on the date checked. Papers or external
  tables may go further; this is new DATA, not a theorem and not a discovery claim.

Modes: off | shadow (default: compute and report; nothing authored) | live (verified terms become
disabled authored checks the Oracle judges by recomputation through the bridge).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "society" / "systems" / "new_data.json"
FRONTIER_DIR = ROOT / "society" / "frontier"
INDEX = FRONTIER_DIR / "frontier_index.json"
CLAIMS = FRONTIER_DIR / "claims.json"
LEDGER = FRONTIER_DIR / "NEW_DATA.md"
DATA_DIR = FRONTIER_DIR / "data"
MODES = ("live", "shadow", "off")
UA = "agent-colony new-data (free; cached; <= 1 request / 2 s)"
NET_GAP_S = 2.0
NET_MAX_PER_CYCLE = 6
INDEX_MAX_AGE_DAYS = 30
CYCLE_BUDGET_S = 40.0        # CPU seconds per cycle for the whole stage
TARGET_BUDGET_S = 20.0       # CPU seconds for one target
DISCOVER_PER_CYCLE = 3
MAX_BEYOND = 1000            # at most this many new terms per target per claim
PROBE_N = 60
LABEL_NEW = "computed beyond published frontier (verified 2 ways)"
LABEL_MATCH = "matches published"
LABEL_UNVERIFIED = "unverified"
LABEL_UNKNOWN = "frontier unknown"


def mode() -> str:
    v = os.environ.get("COLONY_NEWDATA", "shadow").strip().lower()
    return v if v in MODES else "shadow"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ----------------------------------------------------------------------------- arithmetic, method A
def sieve_a(L: int) -> bytearray:
    s = bytearray([1]) * (L + 1)
    s[0:2] = b"\x00\x00"[: min(2, L + 1)]
    for i in range(2, math.isqrt(L) + 1):
        if s[i]:
            s[i * i::i] = bytearray(len(range(i * i, L + 1, i)))
    return s


# ----------------------------------------------------------------------------- arithmetic, method B
_MR_BASES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)


def is_prime_b(n: int) -> bool:
    """Deterministic Miller-Rabin for n < 3.3e24 (independent of any sieve)."""
    if n < 2:
        return False
    for p in _MR_BASES:
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for a in _MR_BASES:
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def odd_sieve_b(L: int) -> list[bool]:
    """Odd-only sieve on a Python list (a second, independent sieve implementation)."""
    half = [True] * (L // 2 + 1)          # half[i] <-> 2i + 1
    half[0] = False
    i = 1
    while (2 * i + 1) ** 2 <= L:
        if half[i]:
            p = 2 * i + 1
            for j in range((p * p) // 2, L // 2 + 1, p):
                half[j] = False
        i += 1
    out = [False] * (L + 1)
    if L >= 2:
        out[2] = True
    for i, v in enumerate(half):
        if v and 2 * i + 1 <= L:
            out[2 * i + 1] = True
    return out


# ----------------------------------------------------------------------------- menu: Goldbach
def _gb_ok(p: int, q: int, odd: bool, cls: tuple[int, int] | None) -> bool:
    if odd and (p == 2 or q == 2):
        return False
    return cls is None or (p % cls[0] == cls[1] and q % cls[0] == cls[1])


def gb_count_a(N: int, odd: bool = True, ordered: bool = False, cls: tuple[int, int] | None = None) -> list[int]:
    """#{p <= q} (or ordered pairs) of primes with p + q = 2n, n = 1..N: numpy FFT convolution."""
    import numpy as np
    M = 2 * N
    s = sieve_a(M)
    ind = np.frombuffer(bytes(s), dtype=np.uint8).astype(np.float64)
    if odd:
        ind[2] = 0.0
    if cls is not None:
        mask = np.zeros(M + 1)
        mask[cls[1]::cls[0]] = 1.0
        ind = ind * mask
    sz = 1 << (2 * M + 1).bit_length()
    f = np.fft.rfft(ind, sz)
    conv = np.rint(np.fft.irfft(f * f, sz)[:M + 1]).astype(np.int64)
    out = []
    for n in range(1, N + 1):
        c = int(conv[2 * n])
        if ordered:
            out.append(c)
        else:
            out.append((c + int(ind[n] > 0)) // 2)
    return out


def gb_count_b(ns: list[int], odd: bool = True, ordered: bool = False, cls: tuple[int, int] | None = None) -> list[int]:
    """Same counts for the given n by direct integer enumeration over an independent odd-only sieve."""
    L = 2 * max(ns)
    pr = odd_sieve_b(L)
    out = []
    for n in ns:
        m, c = 2 * n, 0
        for p in range(2, n + 1):
            if pr[p] and pr[m - p] and _gb_ok(p, m - p, odd, cls):
                c += 2 if (ordered and p != m - p) else 1
        out.append(c)
    return out


def gb_min_a(N: int, cls: tuple[int, int] | None = None) -> list[int]:
    """Least prime p (class-restricted if cls) with 2n - p prime and p <= 2n - p; 0 if none."""
    s = sieve_a(2 * N)
    out = []
    for n in range(1, N + 1):
        v = 0
        for p in range(2, n + 1):
            if s[p] and s[2 * n - p] and _gb_ok(p, 2 * n - p, False, cls):
                v = p
                break
        out.append(v)
    return out


def gb_min_b(ns: list[int], cls: tuple[int, int] | None = None) -> list[int]:
    out = []
    for n in ns:
        v = 0
        for p in range(2, n + 1):
            if is_prime_b(p) and is_prime_b(2 * n - p) and _gb_ok(p, 2 * n - p, False, cls):
                v = p
                break
        out.append(v)
    return out


def gb_close_a(N: int) -> list[int]:
    """n - p for the largest prime p <= n with 2n - p prime (closest Goldbach pair); -1 if none."""
    s = sieve_a(2 * N)
    out = []
    for n in range(1, N + 1):
        v = -1
        for p in range(n, 1, -1):
            if s[p] and s[2 * n - p]:
                v = n - p
                break
        out.append(v)
    return out


def gb_close_b(ns: list[int]) -> list[int]:
    out = []
    for n in ns:
        v = -1
        for k in range(0, n - 1):
            if is_prime_b(n - k) and is_prime_b(n + k):
                v = k
                break
        out.append(v)
    return out


# ----------------------------------------------------------------------------- menu: Collatz
def _collatz_a(N: int) -> tuple[list[int], list[int], list[int], list[int], list[int]]:
    """Memoized: total steps, odd steps, even steps, max excursion, stopping time (first < n)."""
    st, od, mx = [0] * (N + 1), [0] * (N + 1), [0] * (N + 1)
    stop = [0] * (N + 1)
    if N >= 1:
        mx[1] = 1
    for n in range(2, N + 1):
        v, k, o, m = n, 0, 0, n
        first = 0
        while v >= n or (v > N):
            if v % 2:
                v = 3 * v + 1
                o += 1
            else:
                v //= 2
            k += 1
            m = max(m, v)
            if not first and v < n:
                first = k
        if not first:
            first = k
        st[n], od[n], mx[n] = k + st[v], o + od[v], max(m, mx[v])
        stop[n] = first
    ev = [st[i] - od[i] for i in range(N + 1)]
    return st[1:], od[1:], ev[1:], mx[1:], stop[1:]


def _collatz_b(n: int) -> tuple[int, int, int, int, int]:
    """Naive bit-level iteration with the (3v+1)/2 shortcut (counted as two steps)."""
    v, k, o, m, stop = n, 0, 0, n, 0
    while v != 1:
        if v & 1:
            v = (3 * v + 1) >> 1
            k += 2
            o += 1
            m = max(m, 2 * v)
        else:
            v >>= 1
            k += 1
        if not stop and v < n:
            stop = k
    if n == 1:
        stop = 0
    return k, o, k - o, m, stop


def _col_a(i: int) -> Callable[[int], list[int]]:
    return lambda N: list(_collatz_a(N)[i])


def _col_b(i: int) -> Callable[[list[int]], list[int]]:
    return lambda ns: [_collatz_b(n)[i] for n in ns]


MENU: dict[str, dict[str, Any]] = {
    "gb_u_odd": {"a": lambda N: gb_count_a(N, True), "b": lambda ns: gb_count_b(ns, True),
                 "what": "unordered Goldbach partitions of 2n into odd primes"},
    "gb_u_all": {"a": lambda N: gb_count_a(N, False), "b": lambda ns: gb_count_b(ns, False),
                 "what": "unordered Goldbach partitions of 2n (2 allowed)"},
    "gb_o_all": {"a": lambda N: gb_count_a(N, False, True), "b": lambda ns: gb_count_b(ns, False, True),
                 "what": "ordered Goldbach partitions of 2n"},
    "gb_min": {"a": lambda N: gb_min_a(N), "b": lambda ns: gb_min_b(ns),
               "what": "least prime in a Goldbach partition of 2n"},
    "gb_close": {"a": gb_close_a, "b": gb_close_b, "what": "distance from n to the closest Goldbach pair n -/+ k"},
    "col_steps": {"a": _col_a(0), "b": _col_b(0), "what": "Collatz 3x+1 steps to reach 1"},
    "col_odd": {"a": _col_a(1), "b": _col_b(1), "what": "Collatz tripling steps"},
    "col_even": {"a": _col_a(2), "b": _col_b(2), "what": "Collatz halving steps"},
    "col_max": {"a": _col_a(3), "b": _col_b(3), "what": "Collatz maximum excursion"},
    "col_stop": {"a": _col_a(4), "b": _col_b(4), "what": "Collatz stopping time (first iterate below n)"},
}
for _m, _r in ((4, 1), (4, 3), (3, 1), (3, 2), (6, 1), (6, 5)):
    MENU[f"gb_cls{_m}_{_r}"] = {
        "a": (lambda m, r: lambda N: gb_count_a(N, True, False, (m, r)))(_m, _r),
        "b": (lambda m, r: lambda ns: gb_count_b(ns, True, False, (m, r)))(_m, _r),
        "what": f"unordered partitions of 2n into primes p, q = {_r} (mod {_m})"}
    MENU[f"gb_min_cls{_m}_{_r}"] = {
        "a": (lambda m, r: lambda N: gb_min_a(N, (m, r)))(_m, _r),
        "b": (lambda m, r: lambda ns: gb_min_b(ns, (m, r)))(_m, _r),
        "what": f"least prime p = {_r} (mod {_m}) with 2n - p prime and = {_r} (mod {_m})"}
def _compress(fa: Callable, fb: Callable, step: int, n0: int) -> tuple[Callable, Callable]:
    """Index a sequence only on n = n0 + step*(j-1), j = 1, 2, ... (the n where it can be nonzero)."""
    def a(J: int) -> list[int]:
        v = fa(n0 + step * (J - 1))
        return [v[n0 + step * (j - 1) - 1] for j in range(1, J + 1)]

    def b(js: list[int]) -> list[int]:
        return fb([n0 + step * (j - 1) for j in js])
    return a, b


for _m, _r in ((4, 1), (4, 3), (3, 1), (3, 2), (6, 1), (6, 5)):
    _step = _m // math.gcd(_m, 2)
    _n0 = next(n for n in range(1, 50) if (2 * n - 2 * _r) % _m == 0 and n >= _r)
    for _k in (f"gb_cls{_m}_{_r}", f"gb_min_cls{_m}_{_r}"):
        _fa, _fb = _compress(MENU[_k]["a"], MENU[_k]["b"], _step, _n0)
        MENU[_k + "_c"] = {"a": _fa, "b": _fb, "what": MENU[_k]["what"] + f", only at n = {_n0} + {_step}j"}
OPS = ("terms", "recpos", "recval")


def records(v: list[int]) -> tuple[list[int], list[int]]:
    pos, val, best = [], [], None
    for i, x in enumerate(v, start=1):
        if best is None or x > best:
            best = x
            pos.append(i)
            val.append(x)
    return pos, val


def derive(op: str, v: list[int]) -> list[int]:
    if op == "terms":
        return v
    pos, val = records(v)
    return pos if op == "recpos" else val


# ----------------------------------------------------------------------------- published frontier
def _cache_dir() -> Path:
    return Path(os.environ.get("COLONY_BFILE_CACHE") or (Path.home() / ".cache" / "colony" / "bfiles"))


class Net:
    """Polite fetcher: cache first, <= NET_MAX_PER_CYCLE requests, >= NET_GAP_S apart."""

    def __init__(self, allow: bool = True):
        self.allow = allow and os.environ.get("COLONY_NEWDATA_OFFLINE", "") not in ("1", "true")
        self.n, self.last = 0, 0.0

    def get(self, url: str, name: str) -> str | None:
        p = _cache_dir() / name
        if p.exists() and time.time() - p.stat().st_mtime < INDEX_MAX_AGE_DAYS * 86400:
            return p.read_text(encoding="utf-8", errors="replace")
        if not self.allow or self.n >= NET_MAX_PER_CYCLE:
            return None
        wait = NET_GAP_S - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.n += 1
        self.last = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                txt = r.read(8_000_000).decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            return None
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt, encoding="utf-8")
        return txt


def parse_bfile(txt: str) -> list[tuple[int, int]]:
    out = []
    for ln in txt.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        parts = ln.split()
        if len(parts) < 2:
            continue
        try:
            out.append((int(parts[0]), int(parts[1])))
        except ValueError:
            continue
    out.sort()
    # keep the contiguous run from the first index (a b-file is a(k) for consecutive k)
    run = out[:1]
    for k, v in out[1:]:
        if k != run[-1][0] + 1:
            break
        run.append((k, v))
    return run


def published(anum: str, net: Net) -> dict[str, Any] | None:
    num = anum[1:]
    b = net.get(f"https://oeis.org/{anum}/b{num}.txt", f"b{num}.txt")
    if b is None:
        return None
    rows = parse_bfile(b)
    if not rows:
        return None
    meta = net.get(f"https://oeis.org/search?q=id:{anum}&fmt=json", f"{anum}.json")
    name = ""
    try:
        js = json.loads(meta) if meta else None
        rec = (js[0] if isinstance(js, list) else (js or {}).get("results", [None])[0]) if js else None
        name = str((rec or {}).get("name") or "")[:200]
        links = [str(x) for x in (rec or {}).get("link") or []]
    except Exception:  # noqa: BLE001
        links = []
    linked = _linked_extent(links)
    return {"anum": anum, "name": name, "rows": rows, "k_min": rows[0][0], "k_max": rows[-1][0],
            "linked_k_max": linked, "meta_ok": meta is not None,
            "sha256": hashlib.sha256(b.encode()).hexdigest()[:16], "checked": _utc(),
            "source": f"https://oeis.org/{anum}/b{num}.txt"}


def _linked_extent(links: list[str]) -> int:
    """Largest n in 'Table of n, a(n) for n = 1..X' style links of the entry (a-files, external tables)."""
    import re
    best = 0
    for l in links:
        t = re.sub(r"<[^>]+>", "", l)
        for m in re.finditer(r"n\s*=\s*-?\d+\s*\.\.\s*(\d+(?:\^\d+)?(?:,\d{3})*)", t):
            x = m.group(1).replace(",", "")
            v = int(x.split("^")[0]) ** int(x.split("^")[1]) if "^" in x else int(x)
            best = max(best, v)
    return best


def align(ours: list[int], rows: list[tuple[int, int]], op: str) -> dict[str, Any] | None:
    """How the published indexing maps onto ours: terms by index shift d (ours[n] = pub[n + d]);
    record positions additionally by an affine map v -> alpha * v + beta. Every overlapping
    published term must agree (at least 20 of them)."""
    pv = dict(rows)
    for d in range(-3, 4):
        for alpha, beta in ((1, 0),) if op != "recpos" else ((1, 0), (2, 0), (1, 1), (2, 2), (1, -1), (2, -2)):
            ok, n_ov = True, 0
            for i, x in enumerate(ours, start=1):
                k = i + d
                if k in pv:
                    n_ov += 1
                    if pv[k] != alpha * x + beta:
                        ok = False
                        break
            if ok and n_ov >= min(20, len(rows)) and n_ov >= 12:
                return {"d": d, "alpha": alpha, "beta": beta, "overlap": n_ov}
    return None


# ----------------------------------------------------------------------------- state
def _load(p: Path, default: Any) -> Any:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def _save(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _lookup() -> Callable | None:
    try:
        from colony import oeis_terms
        return oeis_terms.lookup if oeis_terms.available() else None
    except Exception:  # noqa: BLE001
        return None


def items() -> list[str]:
    return [f"{k}:{op}" for k in MENU for op in OPS]


# ----------------------------------------------------------------------------- discovery
def discover(item: str, net: Net, lookup: Callable | None) -> dict[str, Any]:
    key, op = item.split(":")
    t0 = time.process_time()
    base = MENU[key]["a"](PROBE_N if op == "terms" else (200000 if key.startswith("col") else 20000))
    seq = derive(op, base)[:PROBE_N]
    out: dict[str, Any] = {"item": item, "what": MENU[key]["what"] + ("" if op == "terms" else f" ({op})"),
                           "probe_cpu_s": round(time.process_time() - t0, 4), "ts": _utc()}
    if lookup is None:
        return out | {"status": LABEL_UNKNOWN, "why": "local OEIS index absent"}
    if len(seq) < 12:
        return out | {"status": "too_short", "why": "fewer than 12 terms in the probe range"}
    found = lookup(seq).get("anums") or []
    if not found:
        return out | {"status": "not_in_oeis", "why": "not found in the local OEIS index (frontier unknown)"}
    for anum in found[:3]:
        pub = published(anum, net)
        if pub is None:
            out.setdefault("unfetched", []).append(anum)
            continue
        # check alignment on a range that reaches the b-file where cheap
        al = align(seq, pub["rows"], op)
        if al:
            return out | {"status": "matched", "anum": anum, "name": pub["name"], "align": al,
                          "pub_k_max": pub["k_max"], "pub_k_min": pub["k_min"], "pub_last": pub["rows"][-1][1],
                          "n_pub_terms": len(pub["rows"]), "source": pub["source"], "sha256": pub["sha256"],
                          "checked": pub["checked"]}
    if out.get("unfetched"):
        return out | {"status": LABEL_UNKNOWN, "why": "b-file not fetched (network / rate limit)"}
    return out | {"status": "no_alignment", "anums": found[:3], "why": "OEIS terms differ beyond the probe"}


# ----------------------------------------------------------------------------- frontier push
def _our_frontier(entry: dict[str, Any], op: str) -> int:
    """Our index n of the last published value (terms) / number of published records (records)."""
    if op == "terms":
        return entry["pub_k_max"] - entry["align"]["d"]
    return entry["n_pub_terms"]


def estimate_cost(entry: dict[str, Any], N: int) -> float:
    """CPU seconds to compute the base sequence to N, scaled from measured costs (N^1.5 model)."""
    c = entry.get("cost") or {}
    if c.get("N") and c.get("cpu_s"):
        a = float(c["cpu_s"]) * (N / c["N"]) ** 1.2
        b = float(c.get("b_per_term_s") or 0.0) * (N / c["N"]) * MAX_BEYOND
        return a + b
    return float(entry.get("probe_cpu_s") or 0.01) * (N / PROBE_N) ** 1.5


def push(entry: dict[str, Any], budget_s: float, net: Net) -> dict[str, Any]:
    """Compute past the published frontier with method A; check every published term A reaches;
    recompute the new part with method B. Returns a result row (never raises)."""
    key, op = entry["item"].split(":")
    pub = published(entry["anum"], net)
    res: dict[str, Any] = {"item": entry["item"], "anum": entry["anum"], "ts": _utc()}
    if pub is None:
        return res | {"status": LABEL_UNKNOWN, "why": "b-file unavailable now"}
    entry.update({"pub_k_max": pub["k_max"], "n_pub_terms": len(pub["rows"]), "sha256": pub["sha256"],
                  "checked": pub["checked"]})
    t0 = time.process_time()
    if op == "terms":
        if not pub.get("meta_ok"):
            return res | {"status": LABEL_UNKNOWN, "why": "entry links not fetched (a longer linked table may exist)"}
        f = max(_our_frontier(entry, op), int(pub.get("linked_k_max") or 0) - entry["align"]["d"])
        N = f + MAX_BEYOND
        _calibrate(entry, key, min(f, 5000))
        while N > f + 10 and estimate_cost(entry, N) > budget_s:
            N = f + (N - f) // 2
        if estimate_cost(entry, N) > budget_s:
            return res | {"status": "intractable", "why": f"published frontier n = {f} beyond the CPU budget",
                          "est_cpu_s": round(estimate_cost(entry, f + 10), 1)}
        v = MENU[key]["a"](N)
        cpu_a = time.process_time() - t0
        entry["cost"] = {"N": N, "cpu_s": max(cpu_a, 1e-4)}
        al = align(v, pub["rows"], op)
        if not al or al["d"] != entry["align"]["d"] or al["overlap"] < min(len(pub["rows"]), f) - 1:
            return res | {"status": "mismatch", "why": "method A disagrees with the published b-file", "cpu_s": round(cpu_a, 3)}
        f_b = _our_frontier(entry, op)              # b-file end: terms between it and f are not claimed
        new_ns = list(range(f + 1, N + 1))
        t1 = time.process_time()
        vb = MENU[key]["b"](new_ns)
        cpu_b = time.process_time() - t1
        va = [v[n - 1] for n in new_ns]
        agree = va == vb
        return res | {"status": LABEL_NEW if agree else LABEL_UNVERIFIED, "op": op,
                      "frontier_n": f, "pub_k_max": pub["k_max"], "d": al["d"], "linked_k_max": pub.get("linked_k_max"),
                      "ns": [new_ns[0], new_ns[-1]], "values": va if agree else [],
                      "first_disagreement": None if agree else next(i for i, (x, y) in enumerate(zip(va, vb)) if x != y),
                      "cpu_s": round(cpu_a + cpu_b, 3), "cpu_a": round(cpu_a, 3), "cpu_b": round(cpu_b, 3),
                      "source": pub["source"], "checked": pub["checked"], "sha256": pub["sha256"],
                      "methods": method_names(key)}
    # records: scan the base sequence from n = 1 up to N; new records come after the published ones
    d, alpha, beta = entry["align"]["d"], entry["align"].get("alpha", 1), entry["align"].get("beta", 0)
    i_last = pub["k_max"] - d                       # our record number of the last published record
    last_pos = (pub["rows"][-1][1] - beta) // alpha if op == "recpos" else None
    need = (last_pos or 0) + 1
    N = max(need * 2, 4000) if op == "recpos" else 200000
    _calibrate(entry, key, min(N, 20000))
    while estimate_cost(entry, N) > budget_s and N > need:
        N = max(need, N * 3 // 4)
    if estimate_cost(entry, N) > budget_s:
        return res | {"status": "intractable", "why": f"published records reach n ~ {need}; beyond the CPU budget",
                      "est_cpu_s": round(estimate_cost(entry, need), 1)}
    base = MENU[key]["a"](N)
    cpu_a = time.process_time() - t0
    entry["cost"] = {"N": N, "cpu_s": max(cpu_a, 1e-4)}
    pos, val = records(base)
    ours = pos if op == "recpos" else val
    al = align(ours, pub["rows"], op)
    if not al or al["d"] != d:
        return res | {"status": "mismatch", "why": "records disagree with the b-file", "cpu_s": round(cpu_a, 3)}
    if len(ours) <= i_last:
        return res | {"status": LABEL_MATCH, "why": f"no record beyond the published ones up to n = {N}",
                      "cpu_s": round(cpu_a, 3)}
    if op == "recval" and (last_pos is None) and pos[i_last - 1] > N:
        return res | {"status": LABEL_MATCH, "cpu_s": round(cpu_a, 3)}
    t1 = time.process_time()
    vb = MENU[key]["b"](list(range(1, N + 1)))
    cpu_b = time.process_time() - t1
    pb, vb_ = records(vb)
    ob = pb if op == "recpos" else vb_
    new = [alpha * x + beta if op == "recpos" else x for x in ours[i_last:]]
    agree = ours == ob
    ks = list(range(pub["k_max"] + 1, pub["k_max"] + 1 + len(new)))
    return res | {"status": LABEL_NEW if agree else LABEL_UNVERIFIED, "op": op, "frontier_n": i_last,
                  "pub_k_max": pub["k_max"], "ns": [ks[0], ks[-1]], "values": new if agree else [],
                  "scan_to": N, "cpu_s": round(cpu_a + cpu_b, 3), "cpu_a": round(cpu_a, 3), "cpu_b": round(cpu_b, 3),
                  "source": pub["source"], "checked": pub["checked"], "sha256": pub["sha256"],
                  "methods": method_names(key), "record_positions": [alpha * x + beta for x in pos[i_last:]]}


def _calibrate(entry: dict[str, Any], key: str, N: int) -> None:
    """Measure method A + B cost at a moderate N once (the learned cost model starts from this)."""
    if (entry.get("cost") or {}).get("N"):
        return
    t = time.process_time()
    MENU[key]["a"](N)
    ta = time.process_time() - t
    t = time.process_time()
    MENU[key]["b"](list(range(max(1, N - 20), N + 1)))
    tb = (time.process_time() - t) / 21
    entry["cost"] = {"N": N, "cpu_s": max(ta, 1e-4), "b_per_term_s": tb}


def method_names(key: str) -> list[str]:
    if key.startswith("gb_min"):
        return ["sieve (bytearray) scan", "Miller-Rabin scan (no sieve)"]
    if key.startswith("gb_close"):
        return ["sieve scan downward from n", "Miller-Rabin scan outward from n"]
    if key.startswith("gb_"):
        return ["numpy FFT convolution of the prime indicator (floating point, rounded)",
                "direct integer enumeration over an independent odd-only sieve"]
    return ["memoized iteration (stops at the first smaller value)", "naive bit-level iteration with the (3x+1)/2 shortcut"]


# ----------------------------------------------------------------------------- learning
PUSH_PER_CYCLE = 4


def _done(e: dict[str, Any]) -> bool:
    """Already pushed against this version of the published b-file: wait for the frontier to move
    (the index is re-fetched after INDEX_MAX_AGE_DAYS; a changed b-file re-opens the target)."""
    if not e.get("done_for_sha"):
        return False
    try:
        age = (datetime.now(timezone.utc) - datetime.strptime(e.get("checked") or "", "%Y-%m-%dT%H:%M:%SZ")
               .replace(tzinfo=timezone.utc)).days
    except ValueError:
        age = 0
    return age < INDEX_MAX_AGE_DAYS


def score(entry: dict[str, Any], total_tries: int) -> float:
    """Expected terms past the frontier per CPU-second (learned), plus exploration."""
    st = entry.get("stats") or {}
    tries, beyond, cpu = st.get("tries", 0), st.get("beyond", 0), st.get("cpu_s", 0.0)
    ev = (beyond + 1.0) / (cpu + 1.0)
    return ev + math.sqrt(2 * math.log(total_tries + 2) / (tries + 1))


def run_cycle(cycle_id: str = "", *, net: Net | None = None, lookup: Any = "default", write: bool = True,
              budget_s: float = CYCLE_BUDGET_S) -> dict[str, Any]:
    if mode() == "off":
        return {"skipped": "COLONY_NEWDATA=off"}
    net = net or Net()
    lookup = _lookup() if lookup == "default" else lookup
    st = _load(STATE, {})
    idx = _load(INDEX, {"note": "Published frontier per OEIS entry (b-file), as learned by colony.new_data.",
                        "entries": {}})
    claims = _load(CLAIMS, {"claims": []})
    st.setdefault("tried_items", {})
    t_start = time.process_time()
    disc = []
    untried = [it for it in items() if it not in st["tried_items"]]
    for it in untried[:DISCOVER_PER_CYCLE]:
        try:
            d = discover(it, net, lookup)
        except Exception as exc:  # noqa: BLE001
            d = {"item": it, "status": "error", "why": str(exc)[:120]}
        st["tried_items"][it] = {k: d.get(k) for k in ("status", "anum", "why", "ts")}
        disc.append(d)
        if d.get("status") == "matched":
            e = idx["entries"].get(d["anum"])
            if e is None or e.get("item") is None:
                idx["entries"][d["anum"]] = d | {"stats": {"tries": 0, "beyond": 0, "cpu_s": 0.0}}
    # choose: tractable entries ranked by learned EV per CPU-second
    ents = [e for e in idx["entries"].values() if e.get("status") == "matched" and not e.get("intractable")
            and not _done(e)]
    total = sum((e.get("stats") or {}).get("tries", 0) for e in ents)
    ents.sort(key=lambda e: -score(e, total))
    pushed = []
    for e in ents:
        left = budget_s - (time.process_time() - t_start)
        if left < 2:
            break
        try:
            r = push(e, min(TARGET_BUDGET_S, left), net)
        except Exception as exc:  # noqa: BLE001
            r = {"item": e["item"], "anum": e["anum"], "status": "error", "why": str(exc)[:120]}
        s = e.setdefault("stats", {"tries": 0, "beyond": 0, "cpu_s": 0.0})
        s["tries"] += 1
        s["cpu_s"] = round(s["cpu_s"] + float(r.get("cpu_s") or 0.0), 3)
        if r["status"] == "intractable":
            e["intractable"] = r.get("why")
        if r["status"] == LABEL_NEW:
            s["beyond"] += len(r["values"])
            _record_claim(claims, e, r, cycle_id)
        e["last"] = {k: r.get(k) for k in ("status", "why", "ns", "cpu_s", "ts")}
        pushed.append({k: v for k, v in r.items() if k != "values"} | {"n_values": len(r.get("values") or [])})
        if r["status"] in (LABEL_NEW, LABEL_MATCH, "mismatch"):
            e["done_for_sha"] = e.get("sha256")       # one claim per published frontier (b-file version)
        if len(pushed) >= PUSH_PER_CYCLE:
            break
    summary = {"ts": _utc(), "cycle_id": cycle_id, "mode": mode(), "discovered": [
        {k: d.get(k) for k in ("item", "status", "anum", "why")} for d in disc], "pushed": pushed,
        "net_requests": net.n, "cpu_s": round(time.process_time() - t_start, 3),
        "oeis_index": "available" if lookup else "absent"}
    st["last"] = summary
    st["history"] = (st.get("history") or [])[-40:] + [summary]
    st["mode"] = mode()
    if write:
        _save(STATE, st)
        _save(INDEX, idx)
        _save(CLAIMS, claims)
        write_ledger(claims, idx)
    return summary


def _record_claim(claims: dict[str, Any], e: dict[str, Any], r: dict[str, Any], cycle_id: str) -> None:
    anum, op = e["anum"], r["op"]
    k0, k1 = r["ns"]
    # published index of each new value
    if op == "terms":
        ks = [n + r["d"] for n in range(k0, k1 + 1)]
    else:
        ks = list(range(k0, k1 + 1))
    data = DATA_DIR / f"{anum}_beyond.txt"
    prev = {}
    if data.exists():
        for ln in data.read_text(encoding="utf-8").splitlines():
            if ln and not ln.startswith("#"):
                a, b = ln.split()
                prev[int(a)] = int(b)
    for k, v in zip(ks, r["values"]):
        prev[k] = v
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data.write_text(f"# {anum} terms computed beyond the OEIS b-file ({r['source']}, checked {r['checked']}).\n"
                    f"# Computed by colony.new_data ({e['item']}); verified 2 ways: {r['methods'][0]} / {r['methods'][1]}.\n"
                    + "".join(f"{k} {prev[k]}\n" for k in sorted(prev)), encoding="utf-8")
    claims["claims"] = [c for c in claims["claims"] if not (c["anum"] == anum and c["k_range"] == [ks[0], ks[-1]])]
    claims["claims"].append({
        "anum": anum, "name": e.get("name"), "item": e["item"], "op": op, "k_range": [ks[0], ks[-1]],
        "d": r.get("d", 0) if op == "terms" else None, "linked_k_max": r.get("linked_k_max"),
        "n_terms": len(ks), "first": [ks[0], r["values"][0]], "last": [ks[-1], r["values"][-1]],
        "label": LABEL_NEW, "methods": r["methods"], "frontier_source": r["source"], "frontier_k_max": r["pub_k_max"],
        "bfile_sha256": r["sha256"], "checked": r["checked"], "cpu_s": r["cpu_s"], "cycle_id": cycle_id,
        "data_file": str(data.relative_to(ROOT)), "ts": _utc(),
        "how_sure": ("beyond the OEIS b-file and every table linked from the entry on the date checked; other "
                     "sources (papers, personal sites) not checked"
                     + ("; easy extension (under 5 CPU-seconds): the b-file is short, not the edge of what is "
                        "known, so these values are very likely computed elsewhere" if float(r["cpu_s"]) < 5 else ""))})


def write_ledger(claims: dict[str, Any], idx: dict[str, Any]) -> None:
    rows = sorted(claims.get("claims") or [], key=lambda c: (c["anum"], c["k_range"][0]))
    lines = ["# New data ledger (colony.new_data)", "",
             "Every term here was computed past the OEIS b-file of its entry and recomputed by an independent "
             "second method; both agree. \"Beyond published frontier\" means beyond the OEIS b-file on the date "
             "checked; papers or external tables may go further. This is new data, not a theorem.", "",
             "| OEIS | name | index range | first new term | last new term | methods (A / B) | frontier source | checked | CPU s | how sure it is unpublished |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for c in rows:
        lines.append(f"| {c['anum']} | {(c.get('name') or '')[:70]} | {c['k_range'][0]}..{c['k_range'][1]} "
                     f"| a({c['first'][0]}) = {c['first'][1]} | a({c['last'][0]}) = {c['last'][1]} "
                     f"| {c['methods'][0]} / {c['methods'][1]} | {c['frontier_source']} (k <= {c['frontier_k_max']}) "
                     f"| {c['checked']} | {c['cpu_s']} | {c.get('how_sure', '')} |")
    if not rows:
        lines.append("| (none yet) | | | | | | | | | |")
    lines += ["", "Full values: `society/frontier/data/<A-number>_beyond.txt` (b-file format).", "",
              "## Targets the colony identified", "",
              "| OEIS | menu item | published frontier (b-file k max) | status | tries | new terms | CPU s |",
              "|---|---|---|---|---|---|---|"]
    for a, e in sorted((idx.get("entries") or {}).items()):
        s = e.get("stats") or {}
        lines.append(f"| {a} | {e.get('item')} | {e.get('pub_k_max')} | "
                     f"{e.get('intractable') or (e.get('last') or {}).get('status') or e.get('status')} | "
                     f"{s.get('tries', 0)} | {s.get('beyond', 0)} | {s.get('cpu_s', 0)} |")
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------- bridge (Oracle recomputation)
def value_b(item: str, k: int) -> int:
    """a(k) in the published indexing of a 'terms' item, recomputed by method B (independent)."""
    idx = _load(INDEX, {}).get("entries") or {}
    e = next((x for x in idx.values() if x.get("item") == item), None)
    if e is None or not item.endswith(":terms"):
        raise ValueError(item)
    key = item.split(":")[0]
    n = int(k) - int(e["align"]["d"])
    return int(MENU[key]["b"]([n])[0])
