"""Fractal pulse — bounded collector for both lineages.

Sends a shallow tree of requests (fractal branches), collects bounded
text, emits exchange receipts and cycle telemetry. Pure stdlib.
Fail-open. Lineage-preserving. No Scrapling required (urllib fallback).

Efficiency: depth/branch/concurrency caps keep the pulse small.
Signal: each successful leaf becomes a receipt the other system can read.
"""
from __future__ import annotations
from typing import Any, Dict, List
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import urllib.request
import hashlib
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_TARGETS = [
    "https://en.wikipedia.org/wiki/Fractal",
    "https://en.wikipedia.org/wiki/Swarm_intelligence",
    "https://export.arxiv.org/api/query?search_query=ti:swarm&max_results=1",
]

def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()

def _fetch(url: str, timeout: float = 12.0, max_bytes: int = 80_000) -> Dict[str, Any]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "fractal-pulse/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(max_bytes)
            text = raw.decode("utf-8", errors="replace")
            return {"ok": True, "url": url, "bytes": len(raw), "preview": text[:400], "status": getattr(resp, "status", 200)}
    except Exception as exc:
        return {"ok": False, "url": url, "error": type(exc).__name__, "preview": ""}

def _fingerprint(url: str, preview: str) -> str:
    h = hashlib.sha256(f"{url}|{preview[:120]}".encode()).hexdigest()[:16]
    return f"pulse:{h}"

def pulse(
    source: str,
    targets: List[str] | None = None,
    *,
    max_depth: int = 2,
    branch_factor: int = 2,
    max_concurrent: int = 4,
) -> Dict[str, Any]:
    """Run one bounded fractal pulse. Returns summary."""
    urls = list(targets or DEFAULT_TARGETS)[: max(1, branch_factor ** max_depth)]
    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_concurrent) as ex:
        futs = {ex.submit(_fetch, u): u for u in urls}
        for fut in as_completed(futs):
            results.append(fut.result())

    # Emit receipts + telemetry
    try:
        from colony.tools.symbiotic_exchange import append_receipt
        from colony.tools.cycle_telemetry import emit
    except Exception:
        append_receipt = None  # type: ignore
        emit = None  # type: ignore

    ok = 0
    for r in results:
        if r.get("ok"):
            ok += 1
            fp = _fingerprint(r["url"], r.get("preview") or "")
            if append_receipt:
                append_receipt(source, "pulse", fp, "observed", extra={"url": r["url"], "bytes": r["bytes"]})
    if emit:
        emit(source, cycle_id="fractal-pulse", residual_max=0.0,
             foreign_fps=0, bias_delta=0, outcome=f"pulse_ok:{ok}/{len(results)}",
             extra={"targets": len(results)})

    return {
        "source": source,
        "lineage": source,
        "ts": _utc(),
        "targets": len(results),
        "ok": ok,
        "results": results,
    }

if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else "colony"
    summary = pulse(src)
    print(json.dumps({k: summary[k] for k in ("source", "targets", "ok", "ts")}, indent=2))
