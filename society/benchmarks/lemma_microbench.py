"""Lemma microbench — basic + hard tier; textbook-only cannot ace ~0.95.

Honest note: score is a machine-check of coded lemmas, not novel theorem discovery.
"""
from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[0]


def _bust_pyc(path: Path) -> None:
    cache = path.parent / "__pycache__"
    if cache.is_dir():
        for pyc in cache.glob(f"{path.stem}*.pyc"):
            try:
                pyc.unlink()
            except OSError:
                pass


def _load_impl():
    path = ROOT / "artifacts" / "lemma_impl.py"
    spec = importlib.util.spec_from_file_location("colony_lemma_impl", path)
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
    # Prefer split APIs; fall back to flat run_all_checks for older impls.
    if hasattr(mod, "run_basic_checks") and hasattr(mod, "run_hard_checks"):
        basic = mod.run_basic_checks()
        hard = mod.run_hard_checks()
    else:
        flat = mod.run_all_checks()
        basic = {k: v for k, v in flat.items() if not str(k).startswith("hard:")}
        hard = {k[5:]: v for k, v in flat.items() if str(k).startswith("hard:")}
    seconds = time.perf_counter() - t0

    basic_ok = bool(basic) and all(basic.values())
    hard_n = len(hard)
    hard_pass = sum(1 for v in hard.values() if v)
    hard_ok = hard_n > 0 and hard_pass == hard_n
    # Overall ok requires all enabled checks (basic + hard) to pass.
    ok = basic_ok and (hard_n == 0 or hard_ok)

    # Score formula — leave headroom; textbook-only cannot hit ~0.95.
    # Headroom denominators > current catalog so mutations can still raise score.
    BASIC_DENOM = 14.0  # headroom past ~10 basic checks
    HARD_DENOM = 8.0    # headroom past seeded + mutation hard checks
    basic_comp = min(1.0, len(basic) / BASIC_DENOM) if basic else 0.0
    hard_comp = min(1.0, hard_pass / HARD_DENOM) if hard_n else 0.0
    speed = max(0.0, min(1.0, 0.15 / max(seconds, 1e-9)))

    if not basic_ok:
        score = 0.0
    elif hard_n == 0 or hard_pass == 0:
        # Textbook-only / no hard pass: hard ceiling ~0.58 so ~0.95 is unreachable.
        score = round(0.35 + 0.18 * basic_comp + 0.05 * speed, 4)
    elif not hard_ok:
        # Some hard fail → treat as incomplete (score 0 unless all enabled pass).
        score = 0.0
    else:
        # Both tiers green: weight hard so it matters; leave headroom under ~0.95.
        score = round(
            0.42 + 0.22 * basic_comp + 0.28 * hard_comp + 0.05 * speed,
            4,
        )

    checks = {**{f"basic:{k}": bool(v) for k, v in basic.items()},
              **{f"hard:{k}": bool(v) for k, v in hard.items()}}
    return {
        "bench": "lemma_microbench",
        "ok": ok,
        "max_abs_err": 0.0 if ok else 1.0,
        "seconds": round(seconds, 6),
        "score": score,
        "impl_id": getattr(mod, "impl_id", lambda: "unknown")(),
        "checks": checks,
        "n_checks": len(basic) + hard_n,
        "n_pass": sum(1 for v in basic.values() if v) + hard_pass,
        "n_basic": len(basic),
        "n_basic_pass": sum(1 for v in basic.values() if v),
        "n_hard": hard_n,
        "n_hard_pass": hard_pass,
        "basic_ok": basic_ok,
        "hard_ok": hard_ok if hard_n else False,
        "note": (
            "Machine-check of coded lemmas (basic + hard tier). "
            "Textbook-only cannot ace ~0.95. Not novel-theorem discovery."
        ),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run(), indent=2))
