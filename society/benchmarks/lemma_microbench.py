"""Lemma microbench — score 0 unless all enabled algebraic/integer checks pass."""
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
    results = mod.run_all_checks()
    seconds = time.perf_counter() - t0
    ok = bool(results) and all(results.values())
    # Score 0 unless checks pass; otherwise base on completeness + speed
    if not ok:
        score = 0.0
    else:
        n = len(results)
        # Headroom past 7 checks so conjecture mutations can raise score
        completeness = min(1.0, n / 12.0)
        speed = max(0.0, min(1.0, 0.05 / max(seconds, 1e-9)))
        score = round(0.55 + 0.35 * completeness + 0.1 * speed, 4)
    return {
        "bench": "lemma_microbench",
        "ok": ok,
        "max_abs_err": 0.0 if ok else 1.0,
        "seconds": round(seconds, 6),
        "score": score,
        "impl_id": getattr(mod, "impl_id", lambda: "unknown")(),
        "checks": {k: bool(v) for k, v in results.items()},
        "n_checks": len(results),
        "n_pass": sum(1 for v in results.values() if v),
        "note": "Score 0 unless all enabled lemma checks pass. Not novel-theorem claims.",
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run(), indent=2))
