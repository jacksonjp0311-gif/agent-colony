"""Autodiff microbench — grads vs central finite differences + wall time."""
from __future__ import annotations

import importlib.util
import math
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
X, A, B, C = 0.37, 1.25, -0.4, 0.8
EPS = 1e-6
GRAD_TOL = 5e-5
TIME_BUDGET_S = 0.01


def _load_impl():
    path = ROOT / "artifacts" / "autodiff_impl.py"
    spec = importlib.util.spec_from_file_location("colony_autodiff_impl", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _f(x, a, b, c):
    return math.sin(a * x + b) * (x + c)


def _fd_grads():
    def d(param: str) -> float:
        kw = {"x": X, "a": A, "b": B, "c": C}
        hi = dict(kw); lo = dict(kw)
        hi[param] += EPS; lo[param] -= EPS
        return (_f(**hi) - _f(**lo)) / (2 * EPS)
    return {k: d(k) for k in ("x", "a", "b", "c")}


def run() -> dict[str, Any]:
    mod = _load_impl()
    ref = _fd_grads()
    t0 = time.perf_counter()
    got = mod.grads(X, A, B, C)
    seconds = time.perf_counter() - t0
    errs = {k: abs(got.get(k, float("nan")) - ref[k]) for k in ref}
    max_abs_err = max(errs.values()) if errs else float("inf")
    ok = max_abs_err <= GRAD_TOL and all(math.isfinite(v) for v in got.values())
    if not ok:
        score = 0.0
    else:
        speed = max(0.0, min(1.0, TIME_BUDGET_S / max(seconds, 1e-9)))
        score = round(0.6 + 0.4 * speed, 4)
    return {
        "bench": "autodiff_microbench",
        "ok": ok,
        "max_abs_err": float(max_abs_err),
        "errs": {k: float(v) for k, v in errs.items()},
        "got": {k: float(got.get(k, float("nan"))) for k in ref},
        "ref_fd": {k: float(v) for k, v in ref.items()},
        "seconds": round(seconds, 6),
        "score": score,
        "impl_id": getattr(mod, "impl_id", lambda: "unknown")(),
        "grad_tol": GRAD_TOL,
        "time_budget_s": TIME_BUDGET_S,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2))
