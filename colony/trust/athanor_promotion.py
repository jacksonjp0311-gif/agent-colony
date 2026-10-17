"""Eval-gated promotion of Athanor gate profiles (REPORT-ONLY). Athanor 2.7 idea, James Jackson.

Ported from ATHANOR v2.7.0 ``evals/promotion.py`` (github.com/jacksonjp0311-gif/Athanor): a
tuned setting is only a *candidate*; it may replace the incumbent only if

1. suite: every captured regression case still passes with the candidate active (the colony's
   own bug2eval cases in evals/bug2eval/cases; each case's regression test is re-run on the
   current tree with ``COLONY_ATHANOR_GATE=live`` and ``COLONY_ATHANOR_PROFILE=<candidate>``).
   Any failure or error -> REJECT ("cannot re-break a captured case"). Suite not run -> HOLD.
2. gate: the candidate's behaviour vs the incumbent's on the recorded desk changes is judged by
   the unchanged Athanor rule. Per recorded change i: sigma_i(p) = (H7_i(p), [verdict_i(p) =
   APPROVE]); d_i = (sigma_i(cand) - sigma_i(inc)) / sqrt(2); X = [0; cumsum(d)];
   ΔΦ_i = ‖d_i‖, C_i = 1/(1+ΔΦ_i), H7 = mean_i[C_i >= 0.70]. APPROVE -> promote, REFINE -> hold,
   REJECT -> reject.

Report-only: the result is written to society/systems/athanor_v27_promotion.json and a
hash-chained society/systems/athanor_v27_promotion_ledger.jsonl. Nothing reads it to pick a
profile; the gate profile is fixed in code. It never touches the Oracle, P, authorize or 0.70.

CLI: python -m colony.trust.athanor_promotion --candidate tsp/adaptive@1.1.0 [--no-suite]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from colony.athanor_coherence import ADAPTIVE_PROFILES, CONSERVATIVE_PROFILE, CoherenceGovernor, delta_phi

ROOT = Path(__file__).resolve().parent.parent.parent
CASES_DIR = ROOT / "evals" / "bug2eval" / "cases"
RESULT = ROOT / "society" / "systems" / "athanor_v27_promotion.json"
LEDGER = ROOT / "society" / "systems" / "athanor_v27_promotion_ledger.jsonl"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def case_tests(cases_dir: Path = CASES_DIR) -> list[tuple[str, str]]:
    """(case_id, regression test path) for every captured case, from its metadata.json."""
    out: list[tuple[str, str]] = []
    for p in sorted(Path(cases_dir).glob("*.b2e")):
        try:
            meta = json.loads(zipfile.ZipFile(p).read("metadata.json"))
            argv = (meta.get("verification") or {}).get("argv") or []
            tf = next((a for a in argv if str(a).endswith(".py")), None)
            if tf:
                out.append((str(meta.get("case_id") or p.stem), str(tf)))
        except Exception:  # noqa: BLE001
            out.append((p.stem, ""))
    return out


def _run_pytest(test_file: str, env: dict[str, str]) -> int:
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", test_file]
    return subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, timeout=900).returncode


def run_suite(candidate: str, *, runner: Callable[[str, dict[str, str]], int] = _run_pytest,
              cases_dir: Path = CASES_DIR) -> dict[str, Any]:
    env = {**os.environ, "PYTHONPATH": str(ROOT), "COLONY_ATHANOR_GATE": "live",
           "COLONY_ATHANOR_PROFILE": candidate}
    cases = []
    for cid, tf in case_tests(cases_dir):
        if not tf or not (ROOT / tf).exists():
            cases.append({"case": cid, "test": tf, "status": "ERROR", "why": "regression test not found"})
            continue
        try:
            rc = runner(tf, env)
            cases.append({"case": cid, "test": tf, "status": "PASS" if rc == 0 else "REGRESSION", "rc": rc})
        except Exception as exc:  # noqa: BLE001
            cases.append({"case": cid, "test": tf, "status": "ERROR", "why": f"{type(exc).__name__}"})
    digest = hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest()
    return {"ran": True, "cases": cases, "n": len(cases),
            "n_pass": sum(c["status"] == "PASS" for c in cases), "digest": digest}


def _rebuild(row: dict[str, Any]) -> list[float] | None:
    n = row.get("n_probes")
    nz = row.get("drift_nonzero")
    if not isinstance(n, int) or not isinstance(nz, list) or len(nz) > n:
        return None
    return [float(x) for x in nz] + [0.0] * (n - len(nz))


def signature(profile: str, row: dict[str, Any]) -> tuple[float, float] | None:
    from colony.trust.athanor_v27 import profile_verdict
    beh = _rebuild(row)
    if beh is None:
        return None
    pv = profile_verdict(profile, beh, float(row.get("structural") or 0.0),
                         e_cur=float(row.get("e_cur") or 0.0), e_best=float(row.get("e_best") or 0.0),
                         step=int(row.get("step") or 0))
    return float(pv["h7"]), 1.0 if pv["verdict"] == "APPROVE" else 0.0


def gate(candidate: str, incumbent: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    ds: list[list[float]] = []
    for r in rows:
        if r.get("validity_passed") is False:
            continue  # hard-rejected before coherence under every profile: no behaviour difference
        sc, si = signature(candidate, r), signature(incumbent, r)
        if sc is None or si is None:
            continue
        ds.append([(sc[0] - si[0]) / math.sqrt(2.0), (sc[1] - si[1]) / math.sqrt(2.0)])
    if not ds:
        return {"verdict": None, "reason": "no recorded desk changes to compare", "n": 0}
    X = [[0.0, 0.0]]
    for d in ds:
        X.append([X[-1][0] + d[0], X[-1][1] + d[1]])
    v = CoherenceGovernor().verify_trajectory(X)
    dp = delta_phi(X)
    return {"verdict": v.verdict, "reason": v.reason, "h7": round(v.h7, 6), "n": len(ds),
            "dphi_mean": round(sum(dp) / len(dp), 6), "dphi_max": round(max(dp), 6)}


def decide(suite: dict[str, Any] | None, g: dict[str, Any]) -> tuple[str, str]:
    if not suite or not suite.get("ran"):
        return "hold", "suite not run (a profile cannot be promoted without the regression suite)"
    bad = [c for c in suite.get("cases") or [] if c["status"] != "PASS"]
    if bad:
        return "reject", f"suite: {len(bad)} case(s) {sorted({c['status'] for c in bad})} — cannot re-break a captured case"
    if g.get("verdict") is None:
        return "hold", g.get("reason") or "no gate evidence"
    return {"APPROVE": ("promote", "suite passed; Athanor APPROVE"),
            "REFINE": ("hold", "suite passed; Athanor REFINE"),
            "REJECT": ("reject", "suite passed; Athanor REJECT")}[g["verdict"]]


def _append_ledger(entry: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    path = path or LEDGER
    prev = "0" * 64
    if path.exists():
        lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        if lines:
            prev = json.loads(lines[-1]).get("row_hash", prev)
    row = {**entry, "prev_hash": prev}
    row["row_hash"] = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def verify_ledger(path: Path | None = None) -> bool:
    path = path or LEDGER
    prev = "0" * 64
    if not path.exists():
        return True
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        h = row.pop("row_hash", None)
        if row.get("prev_hash") != prev or hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest() != h:
            return False
        prev = h
    return True


def promote(candidate: str, incumbent: str = CONSERVATIVE_PROFILE, *, with_suite: bool = True,
            rows: list[dict[str, Any]] | None = None,
            runner: Callable[[str, dict[str, str]], int] = _run_pytest, write: bool = True) -> dict[str, Any]:
    if candidate not in ADAPTIVE_PROFILES or incumbent not in ADAPTIVE_PROFILES:
        raise ValueError(f"unknown profile; known: {sorted(ADAPTIVE_PROFILES)}")
    if rows is None:
        from colony.trust.athanor_v27 import STATE
        try:
            rows = json.loads(STATE.read_text(encoding="utf-8")).get("rows") or []
        except Exception:  # noqa: BLE001
            rows = []
    suite = run_suite(candidate, runner=runner) if with_suite else {"ran": False}
    g = gate(candidate, incumbent, rows)
    decision, why = decide(suite, g)
    out = {"ts": _utc(), "candidate": candidate, "incumbent": incumbent, "decision": decision,
           "reason": why, "suite": suite, "gate": g, "mode": "report_only",
           "spec_hash": hashlib.sha256(json.dumps(ADAPTIVE_PROFILES[candidate], sort_keys=True).encode()).hexdigest(),
           "note": ("Athanor 2.7 eval-gated promotion (James Jackson). Report-only: the gate profile "
                    "in use is fixed in code; this never changes it.")}
    if write:
        RESULT.parent.mkdir(parents=True, exist_ok=True)
        RESULT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        _append_ledger({"ts": out["ts"], "event": decision, "candidate": candidate, "incumbent": incumbent,
                        "spec_hash": out["spec_hash"], "suite_digest": suite.get("digest"),
                        "verdict": g.get("verdict"), "h7": g.get("h7"), "n": g.get("n")})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m colony.trust.athanor_promotion")
    ap.add_argument("--candidate", required=True, choices=sorted(ADAPTIVE_PROFILES))
    ap.add_argument("--incumbent", default=CONSERVATIVE_PROFILE, choices=sorted(ADAPTIVE_PROFILES))
    ap.add_argument("--no-suite", action="store_true")
    a = ap.parse_args(argv)
    out = promote(a.candidate, a.incumbent, with_suite=not a.no_suite)
    print(json.dumps({k: out[k] for k in ("candidate", "incumbent", "decision", "reason", "gate")}, indent=2))
    print(json.dumps({"suite": [(c["case"], c["status"]) for c in out["suite"].get("cases") or []]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
