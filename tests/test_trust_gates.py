"""Trust-loop regression tests (2026-10-11).

Written BEFORE the fixes (Bug2Eval style): each test encodes a verified defect and failed
against commit 9304f97. See evidence/2026-10-11-trust-loop/bug2eval/.
"""
from __future__ import annotations

from pathlib import Path

import re

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows" / "colony-evolve.yml"


# --- Oracle: a positive hard_pass_delta must not override held-out / stripped results ----

def test_delta_cannot_override_failed_held_out():
    from colony.oracle import sense
    # After-apply harness is NOT green (one enabled hard check fails) but hard_pass rose by 1.
    snap = {"ok": False, "n_hard_pass": 69, "n_hard": 71, "score": 0.0}
    r = sense(mutation="pool_dummy_enable", kind="hard_enable", after_snapshot=snap, hard_pass_delta=1)
    assert r["held_out"]["ok_for_oracle"] is False
    assert r["sense_pass"] is False


def test_delta_cannot_override_stripped_when_already_enabled_before():
    from colony.oracle import sense
    before_src = 'HARD_TIER_LEMMAS = [\n    ("pool_dummy_enable", check_x, True),\n]\n'
    snap = {"ok": True, "n_hard_pass": 70, "n_hard": 70, "score": 0.9}
    r = sense(mutation="pool_dummy_enable", kind="hard_enable", after_snapshot=snap,
              hard_pass_delta=1, before_src=before_src)
    assert r["stripped"]["ok_for_oracle"] is False
    assert r["sense_pass"] is False


def test_delta_still_counts_as_usefulness_when_honest():
    from colony.oracle import sense
    before_src = 'HARD_TIER_LEMMAS = [\n    ("pool_dummy_enable", check_x, False),\n]\n'
    snap = {"ok": True, "n_hard_pass": 70, "n_hard": 70, "score": 0.9}
    r = sense(mutation="pool_dummy_enable", kind="hard_enable", after_snapshot=snap,
              hard_pass_delta=1, before_src=before_src)
    assert r["stripped"]["ok_for_oracle"] is True
    assert r["held_out"]["ok_for_oracle"] is True


# --- CI: mandatory failures must fail the job ----------------------------------------------

def _steps():
    """Split the job's steps textually (no yaml dependency in CI)."""
    txt = WF.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^      - name: ", txt)[1:]
    out = []
    for p in parts:
        out.append({"name": p.splitlines()[0], "run": p, "continue-on-error": "continue-on-error: true" in p})
    return out


def test_workflow_bench_failure_not_opt_in():
    txt = WF.read_text(encoding="utf-8")
    assert "AUTOFAIL" not in txt, "bench failure must be fatal without an operator opt-in"


def test_workflow_runs_trust_gate_before_and_after_evolve():
    runs = [str(s.get("run") or "") for s in _steps()]
    gate_idx = [i for i, r in enumerate(runs) if "python -m colony.trust gate" in r]
    evolve_idx = [i for i, r in enumerate(runs) if "python -m colony \"${ARGS[@]}\"" in r]
    commit_idx = [i for i, r in enumerate(runs) if "git commit" in r]
    assert gate_idx and evolve_idx and commit_idx
    assert min(gate_idx) < evolve_idx[0] < max(gate_idx) < commit_idx[0]
    for s in _steps():
        if "python -m colony.trust gate" in str(s.get("run") or ""):
            assert not s.get("continue-on-error")
            assert "|| true" not in str(s.get("run")) and "|| echo" not in str(s.get("run"))


# --- Promotion categories: check-count growth is coverage, never capability --------------

def test_check_growth_without_score_rise_is_coverage():
    from colony.trust.promotion import classify_promotion
    p = classify_promotion(before={"score": 0.9071, "n_hard_pass": 69, "n_checks": 79, "ok": True},
                           after={"score": 0.9071, "n_hard_pass": 70, "n_checks": 80, "ok": True},
                           oracle_passed=True, challenger_blocked=False)
    assert p["category"] == "coverage"
    assert "capability" not in p["category"]
    assert p["eligible"] is True


def test_no_promotion_without_oracle():
    from colony.trust.promotion import classify_promotion
    p = classify_promotion(before={"score": 0.5, "n_hard_pass": 1, "ok": True},
                           after={"score": 0.6, "n_hard_pass": 2, "ok": True},
                           oracle_passed=False, challenger_blocked=False)
    assert p["eligible"] is False and p["category"] == "none"


def test_desk_cannot_assign_capability():
    from colony.trust.promotion import classify_promotion
    p = classify_promotion(before={"score": 0.5, "n_hard_pass": 1, "ok": True},
                           after={"score": 0.6, "n_hard_pass": 2, "ok": True},
                           oracle_passed=True, challenger_blocked=False)
    assert p["category"] == "internal_score"  # capability requires the independent holdout
