"""Athanor gate on lemma-desk self-edits — ported from ATHANOR 3.0.0 (REPORT-ONLY by default).

ATHANOR is James Jackson's work (github.com/jacksonjp0311-gif/Athanor). Ported from 3.0.0, which
carries the 2.5 validity pre-gate and adaptive tolerance, the 2.7 eval-gated promotion and the
3.0 adapter API / worker memory cap. The ΔΦ / C / H7 math and the APPROVE / REFINE / REJECT rule
are James's and are used unchanged (``colony.athanor_coherence``).

Each desk change (old impl -> new impl) is judged in the shape of Athanor 3.0's
``Governor(probe, scale, check).judge(current, candidate, tolerance=...)``:

* probe: the bench values on fixed inputs — every check (1 pass / 0 fail) plus the speed-neutral
  score divided by κ = 0.10 (Athanor 2.6 TSP: a 10 % score move is one unit). A check added by
  the change counts as no drift if it passes; a lost check counts as drift 1. scale = 1.
* check (validity pre-gate, runs first, hard REJECT): (a) every after-change bench value is
  numeric and finite with no bench error (Athanor 2.5 ``core/validity.py``); (b) the candidate
  impl runs in a separate process under a 2 GB address-space cap and a time limit (Athanor 3.0
  worker memory cap: runaway allocation raises MemoryError instead of killing the run). (b) runs
  *before* the in-process bench and only on the colony's own lemma impl file.
* tolerance: Athanor 2.5 conservative adaptive schedule, registry ``selfmod/adaptive@1.1.0``
  (τ 0.75, γ 6, p 3, basis best-so-far, cap 6, floor 0.7, half-life 50), with e = 1 − lemma score
  before the change and t = assessed changes. The 2.6 TSP retune ``tsp/adaptive@1.1.0`` (τ 0.78,
  no decay) and the colony's fixed τ 0.70 are reported alongside. Only APPROVE lets a keep pass.

Mode (one env var, ``COLONY_ATHANOR_GATE``):

* ``shadow`` (default) — assess and log only. Never changes a keep/revert, a score, a P value,
  an Oracle verdict, authorization or the 0.70 gate.
* ``live``   — the same assessment, and it gates: a keep goes through only on APPROVE; a failed
  memory-capped run skips the in-process bench and the change is reverted. Monotone: it can only
  turn a keep into a revert. It runs after the Oracle and never changes an Oracle verdict, P,
  authorization or the 0.70 gate. Assessment errors fail closed (no keep).
* ``off``    — do nothing (no assessment, no subprocess, no log).

State: society/systems/athanor_gate.json (totals + last rows).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from colony.athanor_coherence import (
    ADAPTIVE_PROFILES,
    CONSERVATIVE_PROFILE,
    Governor,
    scheduled_tolerance,
    snapshot_validity,
    structural_distance,
)

ROOT = Path(__file__).resolve().parent.parent.parent
STATE = ROOT / "society" / "systems" / "athanor_gate.json"
GUARDED_IMPL = ROOT / "society" / "benchmarks" / "artifacts" / "lemma_impl.py"
KEEP_ROWS = 50
MODES = ("off", "shadow", "live")
KAPPA = 0.10                  # score probe scale
GUARD_MEMORY_BYTES = 2 * 1024 ** 3   # Athanor 3.0 WORKER_MEMORY_LIMIT_GB = 2
GUARD_TIMEOUT_S = 120.0
SOURCE = "Athanor 3.0.0 (James Jackson)"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gate_mode() -> str:
    m = (os.environ.get("COLONY_ATHANOR_GATE") or "shadow").strip().lower()
    return m if m in MODES else "shadow"


def gate_profile() -> str:
    """The conservative setting, unless the promotion suite (or a human) names another registered
    profile in COLONY_ATHANOR_PROFILE."""
    p = (os.environ.get("COLONY_ATHANOR_PROFILE") or "").strip()
    return p if p in ADAPTIVE_PROFILES else CONSERVATIVE_PROFILE


# ---------------------------------------------------------------- memory-capped candidate run
_GUARD_CHILD = r"""
import importlib.util, json, math, resource, sys
lim = int(sys.argv[2])
try:
    resource.setrlimit(resource.RLIMIT_AS, (lim, lim))
except (ValueError, OSError):
    pass
spec = importlib.util.spec_from_file_location("colony_lemma_impl_guard", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
basic = mod.run_basic_checks() if hasattr(mod, "run_basic_checks") else {}
hard = mod.run_hard_checks() if hasattr(mod, "run_hard_checks") else {}
print("ATHANOR_GUARD " + json.dumps({"n_basic": len(basic), "n_hard": len(hard),
      "n_pass": sum(1 for v in list(basic.values()) + list(hard.values()) if v)}))
"""


def guarded_run(new_src: str, *, memory_bytes: int = GUARD_MEMORY_BYTES,
                timeout_s: float = GUARD_TIMEOUT_S) -> dict[str, Any]:
    """Run the candidate impl's checks in a child process with an address-space cap and a timeout."""
    t0 = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="athanor_guard_") as td:
        path = Path(td) / "lemma_impl.py"
        path.write_text(new_src, encoding="utf-8")
        env = {**os.environ, "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")}
        try:
            p = subprocess.run([sys.executable, "-c", _GUARD_CHILD, str(path), str(int(memory_bytes))],
                               cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return {"ran": True, "passed": False, "reason": f"timeout>{timeout_s}s",
                    "seconds": round(time.monotonic() - t0, 3)}
    secs = round(time.monotonic() - t0, 3)
    line = next((l for l in (p.stdout or "").splitlines() if l.startswith("ATHANOR_GUARD ")), None)
    if p.returncode != 0 or line is None:
        tail = (p.stderr or "").strip().splitlines()[-1:] or [""]
        reason = "MemoryError" if "MemoryError" in (p.stderr or "") else f"exit={p.returncode}"
        return {"ran": True, "passed": False, "reason": f"{reason}: {tail[0][:160]}", "seconds": secs}
    return {"ran": True, "passed": True, "reason": "ok", "seconds": secs, **json.loads(line.split(" ", 1)[1])}


def pre_bench_guard(*, new_src: str | None, target_impl: Path | str | None, kind: str = "") -> dict[str, Any] | None:
    """Memory-capped run of the candidate before the in-process bench (colony lemma impl only)."""
    if gate_mode() == "off" or not new_src or kind == "stem_easy_pad":
        return None
    try:
        if target_impl is None or Path(target_impl).resolve() != GUARDED_IMPL.resolve():
            return None
        g = guarded_run(new_src)
    except Exception as exc:  # noqa: BLE001
        g = {"ran": False, "passed": False, "reason": f"guard_error:{type(exc).__name__}"}
    g["block"] = bool(gate_mode() == "live" and not g.get("passed"))
    return g


# ---------------------------------------------------------------- probes and verdicts
def probe_pair(before: dict[str, Any] | None, after: dict[str, Any] | None,
               before_score: float | None = None, after_score: float | None = None) -> tuple[list[float], list[float]]:
    """(current, candidate) probe vectors over the same fixed probe set."""
    b = (before or {}).get("checks") or {}
    a = (after or {}).get("checks") or {}
    cur: list[float] = []
    new: list[float] = []
    for k in sorted(set(b) | set(a)):
        if k in b and k in a:
            cur.append(float(bool(b[k]))); new.append(float(bool(a[k])))
        elif k in a:  # newly added check: coverage, not a behaviour change, if it passes
            cur.append(1.0); new.append(float(bool(a[k])))
        else:  # check lost
            cur.append(1.0); new.append(0.0)
    bs = before_score if before_score is not None else (before or {}).get("score")
    as_ = after_score if after_score is not None else (after or {}).get("score")
    cur.append(float(bs) / KAPPA)
    new.append(float(as_) / KAPPA)
    return cur, new


def behaviour_drift(before, after, before_score=None, after_score=None) -> list[float]:
    cur, new = probe_pair(before, after, before_score, after_score)
    return [abs(y - x) for x, y in zip(cur, new)]


def profile_verdict(profile: str, behaviour: list[float], *, e_cur: float, e_best: float, step: int,
                    check: Any = None, candidate: Any = None) -> dict[str, Any]:
    cfg = ADAPTIVE_PROFILES[profile]
    tol = scheduled_tolerance(e_cur ** 2, e_best ** 2, 1.0, step, cfg.get("gamma"), cfg)
    gov = Governor(scale=1.0, threshold=cfg["threshold_h7"], refine_floor=cfg["refine_floor"], check=check)
    d = gov.judge(None, candidate, tolerance=tol, current_probe=[0.0] * len(behaviour),
                  candidate_probe=[float(x) for x in behaviour])
    return {"verdict": d["verdict"], "reason": d["reason"], "h7": round(d["h7"], 6), "tau": cfg["threshold_h7"],
            "tol": round(tol, 6), "dphi_max": round(d["dphi_max"], 6), "valid": d["valid"]}


def _check(candidate: dict[str, Any]) -> bool:
    """Athanor validity pre-gate for the colony: bench values finite + memory-capped run passed."""
    if not candidate["validity"]["passed"]:
        return False
    g = candidate.get("guard")
    return not (isinstance(g, dict) and g.get("ran") and not g.get("passed"))


def assess_change(*, before: dict[str, Any] | None, after: dict[str, Any] | None,
                  src: str = "", new_src: str = "", before_score: float | None = None,
                  after_score: float | None = None, step: int = 0, best_e: float | None = None,
                  guard: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure assessment of one change (no side effects)."""
    validity = snapshot_validity(after)
    bs = before_score if before_score is not None else (before or {}).get("score")
    try:
        e_cur = max(0.0, 1.0 - float(bs))
    except (TypeError, ValueError):
        e_cur = float("inf")
    e_best = min(e_cur, best_e) if best_e is not None else e_cur
    cand = {"validity": validity, "guard": guard}
    out: dict[str, Any] = {"validity": validity, "guard": guard, "e_cur": e_cur, "e_best": e_best,
                           "step": int(step), "source": SOURCE}
    if not _check(cand):
        why = "bench values" if not validity["passed"] else f"guarded run ({(guard or {}).get('reason')})"
        out.update(verdict="REJECT", reason=f"validity pre-gate failed: {why}", profiles={}, gate_profile=gate_profile())
        return out
    beh = behaviour_drift(before, after, before_score, after_score)
    profiles = {name: profile_verdict(name, beh, e_cur=e_cur, e_best=e_best, step=step,
                                      check=_check, candidate=cand) for name in ADAPTIVE_PROFILES}
    gp = gate_profile()
    g = profiles[gp]
    out.update(verdict=g["verdict"], reason=f"{gp}: {g['reason']}", gate_profile=gp, profiles=profiles,
               n_probes=len(beh), drift_nonzero=[round(x, 6) for x in beh if x],
               structural=round(structural_distance(src, new_src), 6) if (src or new_src) else 0.0)
    return out


def _load() -> dict[str, Any]:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"version": 1, "totals": {}, "rows": []}


def _save(st: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, indent=2, default=list) + "\n", encoding="utf-8")


def _bump(tot: dict[str, Any], key: str) -> None:
    tot[key] = int(tot.get(key, 0)) + 1


def gate_desk_change(*, before: dict[str, Any] | None, after: dict[str, Any] | None, src: str = "",
                     new_src: str = "", before_score: float | None = None,
                     after_score: float | None = None, mutation: str = "", kind: str = "",
                     cycle_id: str = "", tentative_keep: bool = False,
                     guard: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Assess one desk change and log it. ``row['block']`` is always False in shadow."""
    mode = gate_mode()
    if mode == "off":
        return None
    row: dict[str, Any] = {"ts": _utc(), "cycle_id": cycle_id, "mutation": mutation, "kind": kind,
                           "mode": mode, "tentative_keep": bool(tentative_keep), "source": SOURCE}
    st = _load()
    sched = st.setdefault("schedule", {"step": 0, "best_e": None})
    try:
        a = assess_change(before=before, after=after, src=src, new_src=new_src, before_score=before_score,
                          after_score=after_score, step=int(sched.get("step") or 0),
                          best_e=sched.get("best_e"), guard=guard)
        row.update(verdict=a["verdict"], reason=a["reason"], gate_profile=a.get("gate_profile"),
                   validity_passed=bool(_check({"validity": a["validity"], "guard": guard})),
                   validity_failures=a["validity"]["failures"],
                   validity_first_failure=a["validity"].get("first_failure"),
                   guard={k: v for k, v in (guard or {}).items() if k != "block"} or None,
                   profiles=a.get("profiles"), n_probes=a.get("n_probes"),
                   drift_nonzero=a.get("drift_nonzero"), structural=a.get("structural"),
                   e_cur=a["e_cur"], e_best=a["e_best"], step=a["step"])
        if a["e_best"] != float("inf"):
            sched["best_e"] = a["e_best"]
        sched["step"] = int(sched.get("step") or 0) + 1
    except Exception as exc:  # noqa: BLE001
        row.update(verdict="ERROR", reason=f"assess_error:{type(exc).__name__}:{exc}"[:200])
    row["would_block"] = bool(tentative_keep and row.get("verdict") != "APPROVE")
    row["block"] = bool(mode == "live" and row["would_block"])
    row["would_block_by_profile"] = {n: bool(tentative_keep and pv["verdict"] != "APPROVE")
                                     for n, pv in (row.get("profiles") or {}).items()}
    try:
        tot = st.setdefault("totals", {})
        _bump(tot, "assessed")
        _bump(tot, f"verdict_{row.get('verdict')}")
        if tentative_keep:
            _bump(tot, "tentative_keeps")
        if row.get("validity_passed") is False:
            _bump(tot, "validity_failed")
        if (row.get("guard") or {}).get("ran"):
            _bump(tot, "guard_ran")
            if not row["guard"].get("passed"):
                _bump(tot, "guard_failed")
        if row["would_block"]:
            _bump(tot, "would_block_keep")
        if row["block"]:
            _bump(tot, "blocked_keep_live")
        for name, pv in (row.get("profiles") or {}).items():
            _bump(tot, f"profile:{name}:{pv['verdict']}")
            if row["would_block_by_profile"].get(name):
                _bump(tot, f"profile:{name}:would_block_keep")
        st["rows"] = (st.get("rows") or [])[-(KEEP_ROWS - 1):] + [row]
        st["updated_at"] = row["ts"]
        st["note"] = (f"Athanor gate ({SOURCE}) on lemma-desk self-edits. shadow = report-only; live = a keep "
                      "needs APPROVE (monotone, after the Oracle; never changes Oracle, P or authorize).")
        _save(st)
    except Exception:  # noqa: BLE001
        pass
    return row
