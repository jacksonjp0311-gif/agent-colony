"""Trust gate — the single mandatory entry point CI executes (and humans can run locally).

    python -m colony.trust gate [--skip-tests] [--report PATH]

Mandatory checks (any failure → exit code 1, and the report is still written):
  1. ablation switches are not set (COLONY_LEARNING / COLONY_CHALLENGER must be on);
  2. full pytest suite passes (not a hand-picked subset);
  3. the suite left live colony state byte-identical (no test rows leak into commits);
  4. hard benches: society/benchmarks/latest.json ok_all is true after a fresh run;
  5. no interrupted desk mutation is pending (rollback journal absent or recoverable);
  6. holdout integrity: evaluation/MANIFEST.sha256 matches (tamper detection).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _tree_digest() -> str:
    h = hashlib.sha256()
    for d in ("data", "society"):
        base = ROOT / d
        for p in sorted(base.rglob("*")) if base.exists() else []:
            if p.is_file() and "__pycache__" not in p.parts:
                h.update(str(p.relative_to(ROOT)).encode())
                h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def manifest_check(root: Path = ROOT) -> dict[str, Any]:
    man = root / "evaluation" / "MANIFEST.sha256"
    if not man.exists():
        return {"ok": False, "reason": "manifest_missing"}
    bad: list[str] = []
    n = 0
    for ln in man.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        digest, rel = ln.split(maxsplit=1)
        rel = rel.strip().lstrip("*")
        p = root / "evaluation" / rel
        n += 1
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            bad.append(rel)
    return {"ok": not bad and n > 0, "files": n, "mismatch": bad}


def run_gate(*, skip_tests: bool = False, python: str = sys.executable) -> dict[str, Any]:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, **detail: Any) -> None:
        checks.append({"check": name, "ok": bool(ok), **detail})

    from colony.trust.flags import ablation_active
    abl = ablation_active()
    add("ablation_switches_off", not abl, active=abl)

    if not skip_tests:
        before = _tree_digest()
        t0 = time.time()
        p = subprocess.run([python, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"],
                           cwd=ROOT, env=env, capture_output=True, text=True)
        tail = (p.stdout or "").strip().splitlines()[-1:] or [""]
        add("pytest_full_suite", p.returncode == 0, returncode=p.returncode, summary=tail[0],
            seconds=round(time.time() - t0, 2),
            failures=[ln for ln in (p.stdout or "").splitlines() if ln.startswith("FAILED")][:40])
        add("tests_left_live_state_unchanged", _tree_digest() == before)

    p = subprocess.run([python, "-m", "society.benchmarks.run_benchmarks"], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    latest: dict[str, Any] = {}
    try:
        latest = json.loads((ROOT / "society" / "benchmarks" / "latest.json").read_text())
    except Exception as exc:  # noqa: BLE001
        latest = {"error": str(exc)}
    add("hard_benches_ok_all", p.returncode == 0 and bool(latest.get("ok_all")),
        returncode=p.returncode, aggregate_score=latest.get("aggregate_score"),
        failing=[b.get("bench") for b in (latest.get("benches") or []) if isinstance(b, dict) and not b.get("ok")])

    from colony.conjecture_desk import JOURNAL
    add("no_pending_interrupted_mutation", not JOURNAL.exists(),
        hint="run `python -m colony.trust recover` to roll back the unjudged mutation")

    m = manifest_check()
    add("holdout_manifest_intact", m["ok"], **{k: v for k, v in m.items() if k != "ok"})

    ok = all(c["ok"] for c in checks)
    return {"ok": ok, "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "checks": checks,
            "failed": [c["check"] for c in checks if not c["ok"]]}


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m colony.trust")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gate")
    g.add_argument("--skip-tests", action="store_true")
    g.add_argument("--report", default="")
    sub.add_parser("recover")
    a = ap.parse_args(argv)
    if a.cmd == "recover":
        from colony.conjecture_desk import recover_interrupted
        print(json.dumps(recover_interrupted(cycle_id="manual_recover") or {"recovered": False,
                                                                           "reason": "no_journal"}))
        return 0
    rep = run_gate(skip_tests=a.skip_tests)
    out = json.dumps(rep, indent=2)
    print(out)
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(out + "\n", encoding="utf-8")
    if not rep["ok"]:
        print(f"::error::TRUST GATE FAIL: {rep['failed']}", file=sys.stderr)
    return 0 if rep["ok"] else 1
