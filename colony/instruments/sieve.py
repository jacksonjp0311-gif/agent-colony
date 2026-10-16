"""Sieve instrument — the colony's reward for the A104062 a(7)..a(11) work (2026-10-16).

Counts consecutive-prime patterns for ANY gap tuple, with optional residue split and
cumulative checkpoints, and forecasts them with the Hardy-Littlewood k-tuple heuristic.
Method taught with it: forecast with HL, count, confirm with two independent counters.

Backends (first available wins, or force one with backend=):
  "c"         compiled sieve_helper.c against libprimesieve (fast)
  "python"    pure-Python segmented sieve (independent; small ranges only)
Hard caps keep evolve cycles fast: span (b - a) <= MAX_SPAN (default 1e10, env
COLONY_SIEVE_MAX_SPAN), python backend <= PY_MAX_SPAN, and a subprocess timeout.
HL predictions are a CONJECTURAL heuristic (the k-tuple conjecture is unproven);
counts are bounded evidence, not proof. Measures only; never touches a gate.
"""
from __future__ import annotations

import itertools
import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable, Sequence

HERE = Path(__file__).resolve().parent
SRC = HERE / "sieve_helper.c"
BUILD_DIR = Path(os.environ.get("COLONY_SIEVE_BUILD", Path.home() / ".cache" / "colony_sieve"))
MAX_SPAN = int(float(os.environ.get("COLONY_SIEVE_MAX_SPAN", "1e10")))
PY_MAX_SPAN = int(float(os.environ.get("COLONY_SIEVE_PY_MAX_SPAN", "2e8")))
TIMEOUT_S = float(os.environ.get("COLONY_SIEVE_TIMEOUT_S", "120"))


class SieveCapExceeded(ValueError):
    pass


# ---------------------------------------------------------------- helpers
def _small_primes(n: int) -> list[int]:
    s = bytearray([1]) * (n + 1); s[0:2] = b"\x00\x00"
    for i in range(2, int(n ** 0.5) + 1):
        if s[i]:
            s[i * i::i] = bytearray(len(range(i * i, n + 1, i)))
    return [i for i in range(n + 1) if s[i]]


def _offsets(gaps: Sequence[int]) -> list[int]:
    return [0] + list(itertools.accumulate(int(g) for g in gaps))


def is_admissible(offsets: Sequence[int]) -> bool:
    H = sorted(set(offsets))
    for p in _small_primes(max(len(H), 2)):
        if len({h % p for h in H}) == p:
            return False
    return True


# ---------------------------------------------------------------- C backend
def _helper() -> Path | None:
    exe = BUILD_DIR / "sieve_helper"
    try:
        if exe.exists() and exe.stat().st_mtime >= SRC.stat().st_mtime:
            return exe
        cc = shutil.which("gcc") or shutil.which("cc")
        if not cc:
            return None
        BUILD_DIR.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([cc, "-O2", str(SRC), "-o", str(exe), "-lprimesieve"],
                           capture_output=True, timeout=60)
        return exe if r.returncode == 0 else None
    except Exception:
        return None


def _count_c(a, b, gaps, mod, checkpoints):
    exe = _helper()
    if exe is None:
        return None
    args = [str(exe), str(a), str(b), str(mod)] + [str(g) for g in gaps] + ["--"] + [str(c) for c in checkpoints]
    out = subprocess.run(args, capture_output=True, text=True, timeout=TIMEOUT_S, check=True).stdout
    tot, res, chk = 0, {}, {}
    for ln in out.splitlines():
        p = ln.split()
        if p[0] == "total":
            tot = int(p[1])
        elif p[0] == "res":
            res[int(p[1])] = int(p[2])
        elif p[0] == "chk":
            chk[int(p[1])] = int(p[2])
    return tot, res, chk


# ---------------------------------------------------------------- pure-Python backend
def _primes_from(a: int, seg: int = 1 << 20) -> Iterable[int]:
    lo = max(a, 2)
    while True:
        hi = lo + seg
        base = _small_primes(int(hi ** 0.5) + 1)
        s = bytearray([1]) * (hi - lo)
        for p in base:
            st = max(p * p, (lo + p - 1) // p * p)
            if st < hi:
                s[st - lo::p] = bytearray(len(range(st - lo, hi - lo, p)))
        for i, v in enumerate(s):
            if v:
                yield lo + i
        lo = hi


def _count_py(a, b, gaps, mod, checkpoints):
    k = len(gaps); it = _primes_from(a)
    W = [next(it) for _ in range(k + 1)]
    tot, res, chk = 0, {}, {c: 0 for c in checkpoints}
    while W[0] < b:
        if all(W[j + 1] - W[j] == gaps[j] for j in range(k)):
            tot += 1; r = W[0] % mod; res[r] = res.get(r, 0) + 1
            for c in checkpoints:
                if W[0] < c:
                    chk[c] += 1
        W.pop(0); W.append(next(it))
    return tot, res, chk


# ---------------------------------------------------------------- public API
def count_pattern(gaps: Sequence[int], a: int, b: int, *, mod: int = 1,
                  checkpoints: Sequence[int] = (), backend: str = "auto",
                  max_span: int | None = None) -> dict[str, Any]:
    """Count p in [a, b) where p and the next len(gaps) primes are CONSECUTIVE with those gaps.

    Returns {"total", "by_residue" {p mod `mod`: n}, "checkpoints" {c: matches with p < c}, "backend"}.
    """
    gaps = [int(g) for g in gaps]; a, b = int(a), int(b)
    if not gaps or any(g <= 0 for g in gaps) or a < 0 or b < a:
        raise ValueError("gaps must be positive and 0 <= a <= b")
    cap = MAX_SPAN if max_span is None else int(max_span)
    if b - a > cap:
        raise SieveCapExceeded(f"span {b - a} > cap {cap} (raise COLONY_SIEVE_MAX_SPAN deliberately)")
    cps = sorted(int(c) for c in checkpoints)
    out = None
    if backend in ("auto", "c"):
        out = _count_c(a, b, gaps, int(mod), cps)
        used = "c"
        if out is None and backend == "c":
            raise RuntimeError("C helper unavailable (needs gcc + libprimesieve)")
    if out is None:
        if b - a > PY_MAX_SPAN:
            raise SieveCapExceeded(f"python backend span {b - a} > {PY_MAX_SPAN}")
        out = _count_py(a, b, gaps, int(mod), cps); used = "python"
    tot, res, chk = out
    return {"gaps": gaps, "a": a, "b": b, "mod": int(mod), "total": tot,
            "by_residue": dict(sorted(res.items())), "checkpoints": chk, "backend": used}


def nth_prime(n: int) -> int:
    """n-th prime (1-indexed). Uses the primesieve CLI when present, else pure Python (n <= 2e6)."""
    n = int(n)
    exe = shutil.which("primesieve")
    if exe:
        try:
            r = subprocess.run([exe, "-n", str(n), "-q"], capture_output=True, text=True, timeout=TIMEOUT_S)
            return int(r.stdout.split()[-1])
        except Exception:
            pass
    if n > 2_000_000:
        raise SieveCapExceeded("nth_prime python fallback limited to n <= 2e6")
    lim = max(15, int(n * (math.log(n) + math.log(math.log(max(n, 3)))) + 10))
    return _small_primes(lim)[n - 1]


def status() -> dict[str, Any]:
    """Cheap availability probe for the sensors snapshot (does not compile)."""
    return {"c_helper_built": (BUILD_DIR / "sieve_helper").exists(),
            "compiler": bool(shutil.which("gcc") or shutil.which("cc")),
            "primesieve_cli": bool(shutil.which("primesieve")),
            "max_span": MAX_SPAN, "py_max_span": PY_MAX_SPAN, "timeout_s": TIMEOUT_S}


def log_checkpoints(a: int, b: int, per_decade: int = 10) -> list[int]:
    lo = math.log10(max(a, 10)); hi = math.log10(b)
    n = max(1, int(round((hi - lo) * per_decade)))
    return sorted({int(round(10 ** (lo + (hi - lo) * i / n))) for i in range(1, n + 1)})


# ---------------------------------------------------------------- Hardy-Littlewood
_HL_PRIMES: list[int] = []
_HL_LIMIT = 0


_TAIL: dict[tuple[int, int, int], float] = {}


def hl_constant(offsets: Sequence[int], prime_limit: int = 2_000_000) -> float:
    """Singular series C(H) = prod_p (1 - nu_p/p) / (1 - 1/p)^k for offsets H (0 if inadmissible).
    Product truncated at prime_limit (tail error ~ k^2/(prime_limit log prime_limit))."""
    global _HL_PRIMES, _HL_LIMIT
    if _HL_LIMIT < prime_limit:
        _HL_PRIMES, _HL_LIMIT = _small_primes(prime_limit), prime_limit
    H = sorted(set(int(h) for h in offsets)); k = len(H); span = H[-1] - H[0]; lg = 0.0
    for i, p in enumerate(_HL_PRIMES):
        if p > span:
            key = (k, i, prime_limit)
            if key not in _TAIL:
                _TAIL[key] = sum(math.log1p(-k / q) - k * math.log1p(-1 / q)
                                 for q in _HL_PRIMES[i:] if q <= prime_limit)
            return math.exp(lg + _TAIL[key])
        nu = len({h % p for h in H})
        if nu >= p:
            return 0.0
        lg += math.log1p(-nu / p) - k * math.log1p(-1 / p)
    return math.exp(lg)


def _li_k(a: float, b: float, k: int, steps: int = 4000) -> float:
    """∫_a^b dt / (log t)^k via Simpson in u = log t."""
    ua, ub = math.log(max(a, 2.0)), math.log(b)
    if ub <= ua:
        return 0.0
    n = steps + steps % 2; h = (ub - ua) / n
    f = lambda u: math.exp(u) / u ** k
    s = f(ua) + f(ub) + sum((4 if i % 2 else 2) * f(ua + i * h) for i in range(1, n))
    return s * h / 3


def hl_predict(gaps: Sequence[int], a: int, b: int, *, consecutive: bool = True) -> dict[str, Any]:
    """HL forecast of matches in [a, b). consecutive=True applies inclusion-exclusion over interior
    points (Odlyzko-Rubinstein-Wolf 1999) so it predicts CONSECUTIVE primes. Conjectural heuristic."""
    H = _offsets(gaps); k = len(H)
    lead = hl_constant(H) * _li_k(a, b, k)
    if not consecutive:
        return {"tuple_only": lead, "prediction": lead, "conjectural": True}
    inter = [x for x in range(1, H[-1]) if x not in H]
    if len(inter) > 16:
        raise ValueError("pattern span too wide for inclusion-exclusion")
    tot = 0.0
    for r in range(len(inter) + 1):
        for S in itertools.combinations(inter, r):
            c = hl_constant(H + list(S)) if r else hl_constant(H)
            if c:
                tot += (-1) ** r * c * _li_k(a, b, k + r)
    return {"tuple_only": lead, "prediction": tot, "conjectural": True}


def forecast_and_count(gaps: Sequence[int], a: int, b: int, **kw) -> dict[str, Any]:
    """The rewarded method: forecast (HL) -> count (primary) -> confirm (independent second counter)."""
    fc = hl_predict(gaps, a, b)
    primary = count_pattern(gaps, a, b, **kw)
    confirm = None
    if b - a <= PY_MAX_SPAN and primary["backend"] != "python":
        confirm = count_pattern(gaps, a, b, backend="python", mod=kw.get("mod", 1))["total"]
    return {"forecast": fc["prediction"], "count": primary["total"], "confirm": confirm,
            "agree": confirm is None or confirm == primary["total"],
            "ratio": primary["total"] / fc["prediction"] if fc["prediction"] else None,
            "backend": primary["backend"]}
