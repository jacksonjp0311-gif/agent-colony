"""FFT microbench — fixed seed, correctness vs reference, wall time.

Score is 0 unless ok; otherwise blends error and speed vs a soft time budget.
"""
from __future__ import annotations

import importlib.util
import math
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
N = 1024
SEED = 20260926
ERR_TOL = 1e-6
# Soft time budget (seconds) for full score on this box; slower still ok if correct
TIME_BUDGET_S = 0.05


def _load_impl():
    path = ROOT / "artifacts" / "fft_impl.py"
    spec = importlib.util.spec_from_file_location("colony_fft_impl", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _signal(n: int = N, seed: int = SEED) -> list[complex]:
    # Deterministic mix of tones + phase — no RNG dependency drift
    out: list[complex] = []
    for i in range(n):
        t = 2 * math.pi * i / n
        re = math.sin(3 * t) + 0.5 * math.cos(17 * t + seed % 97 / 97)
        im = math.cos(5 * t) + 0.25 * math.sin(11 * t)
        out.append(complex(re, im))
    return out


def _reference_fft(x: list[complex]) -> list[complex]:
    try:
        import numpy as np  # type: ignore

        return [complex(v) for v in np.fft.fft(np.asarray(x, dtype=np.complex128))]
    except Exception:
        # Pure DFT fallback (O(n^2)) — only for environments without numpy
        n = len(x)
        out: list[complex] = []
        for k in range(n):
            s = 0j
            for m, xm in enumerate(x):
                ang = -2 * math.pi * k * m / n
                s += xm * complex(math.cos(ang), math.sin(ang))
            out.append(s)
        return out


def run() -> dict[str, Any]:
    mod = _load_impl()
    x = _signal()
    ref = _reference_fft(x)
    t0 = time.perf_counter()
    got = mod.fft(x)
    seconds = time.perf_counter() - t0
    if len(got) != len(ref):
        return {
            "bench": "fft_microbench",
            "n": N,
            "ok": False,
            "max_abs_err": None,
            "mse": None,
            "seconds": round(seconds, 6),
            "score": 0.0,
            "impl_id": getattr(mod, "impl_id", lambda: "unknown")(),
            "error": "length_mismatch",
        }
    errs = [abs(a - b) for a, b in zip(got, ref)]
    max_abs_err = max(errs) if errs else 0.0
    mse = sum(e * e for e in errs) / max(len(errs), 1)
    ok = max_abs_err <= ERR_TOL
    if not ok:
        score = 0.0
    else:
        # 0.55 correctness locked + 0.45 speed vs budget (cap 1.0)
        speed = max(0.0, min(1.0, TIME_BUDGET_S / max(seconds, 1e-9)))
        score = round(0.55 + 0.45 * speed, 4)
    return {
        "bench": "fft_microbench",
        "n": N,
        "seed": SEED,
        "ok": ok,
        "max_abs_err": float(max_abs_err),
        "mse": float(mse),
        "seconds": round(seconds, 6),
        "score": score,
        "impl_id": getattr(mod, "impl_id", lambda: "unknown")(),
        "err_tol": ERR_TOL,
        "time_budget_s": TIME_BUDGET_S,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run(), indent=2))
