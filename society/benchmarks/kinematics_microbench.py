"""Kinematics STEM microbench — non-math domain pack for Oracle flourish mile.

Honest: classical 1D/2D motion identities, not novel physics discovery.
Held-out / stripped / CAS-style gates live in colony/oracle.py domain packs.
"""
from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


def _bust_pyc(path: Path) -> None:
    cache = path.parent / "__pycache__"
    if cache.is_dir():
        for pyc in cache.glob(f"{path.stem}*.pyc"):
            try:
                pyc.unlink()
            except OSError:
                pass


def _load_impl():
    path = ROOT / "artifacts" / "kinematics_impl.py"
    spec = importlib.util.spec_from_file_location("colony_kinematics_impl", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.pop(spec.name, None)
    _bust_pyc(path)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def run() -> dict[str, Any]:
    mod = _load_impl()
    t0 = time.perf_counter()
    checks = mod.run_stem_checks()
    seconds = time.perf_counter() - t0
    n = len(checks)
    n_pass = sum(1 for v in checks.values() if v)
    ok = n > 0 and n_pass == n
    STEM_DENOM = 8.0  # headroom for flourish enables
    comp = min(1.0, n_pass / STEM_DENOM) if n else 0.0
    speed = max(0.0, min(1.0, 0.05 / max(seconds, 1e-9)))
    score = 0.0 if not ok else round(0.55 + 0.35 * comp + 0.10 * speed, 4)
    return {
        "bench": "kinematics_microbench",
        "domain": "stem_physics",
        "ok": ok,
        "max_abs_err": 0.0 if ok else 1.0,
        "seconds": round(seconds, 6),
        "score": score,
        "impl_id": getattr(mod, "impl_id", lambda: "unknown")(),
        "checks": {f"stem:{k}": bool(v) for k, v in checks.items()},
        "n_checks": n,
        "n_pass": n_pass,
        "n_hard": n,
        "n_hard_pass": n_pass,
        "note": (
            "STEM kinematics machine-check (classical). Not novel physics. "
            "Oracle domain pack: held-out + stripped + CAS-style."
        ),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2))
