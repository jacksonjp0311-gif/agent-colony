"""Athanor 2.7 eval-gated promotion of gate profiles (James Jackson's ATHANOR), report-only."""
from __future__ import annotations

import json

import pytest

import colony.trust.athanor_promotion as P


def _row(nz, n=20, e=0.1, step=0):
    return {"n_probes": n, "drift_nonzero": nz, "structural": 0.001, "e_cur": e, "e_best": e,
            "step": step, "validity_passed": True}


@pytest.fixture
def out(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "RESULT", tmp_path / "res.json")
    monkeypatch.setattr(P, "LEDGER", tmp_path / "ledger.jsonl")
    return tmp_path


def test_case_tests_read_from_captured_cases():
    cases = dict(P.case_tests())
    assert set(cases) >= {"B2E-COL-001", "B2E-COL-002", "B2E-COL-003", "B2E-COL-004"}
    assert cases["B2E-COL-004"] == "tests/test_proposal_dedupe_cycle.py"


def test_suite_regression_rejects(out):
    rows = [_row([1.0]) for _ in range(5)]
    r = P.promote("tsp/adaptive@1.1.0", rows=rows, runner=lambda tf, env: 1 if "dedupe" in tf else 0)
    assert r["decision"] == "reject" and "re-break" in r["reason"]
    assert r["suite"]["n_pass"] == r["suite"]["n"] - 1


def test_suite_env_carries_candidate(out):
    seen = []
    P.promote("tsp/adaptive@1.1.0", rows=[], runner=lambda tf, env: seen.append(env) or 0)
    assert seen and all(e["COLONY_ATHANOR_GATE"] == "live" and e["COLONY_ATHANOR_PROFILE"] == "tsp/adaptive@1.1.0"
                        for e in seen)


def test_identical_profile_approves_and_ledger_chains(out):
    rows = [_row([1.0, 0.2]), _row([]), _row([3.0] * 10)]
    r = P.promote("selfmod/adaptive@1.1.0", rows=rows, runner=lambda tf, env: 0)
    assert r["gate"]["verdict"] == "APPROVE" and r["gate"]["h7"] == 1.0 and r["decision"] == "promote"
    P.promote("selfmod/adaptive@1.1.0", rows=rows, with_suite=False)
    assert P.verify_ledger(out / "ledger.jsonl")
    lines = (out / "ledger.jsonl").read_text().splitlines()
    assert [json.loads(l)["event"] for l in lines] == ["promote", "hold"]
    lines[0] = lines[0].replace("promote", "reject")
    (out / "ledger.jsonl").write_text("\n".join(lines) + "\n")
    assert not P.verify_ledger(out / "ledger.jsonl")


def test_divergent_profile_is_not_promoted(out):
    # every change drifts 0.3 per probe on all probes: fixed tau 0.70 approves, conservative rejects
    rows = [_row([0.3] * 20) for _ in range(6)]
    r = P.promote("colony/fixed@1.0.0", rows=rows, runner=lambda tf, env: 0)
    assert r["gate"]["verdict"] == "REJECT" and r["decision"] == "reject"


def test_no_suite_holds(out):
    r = P.promote("tsp/adaptive@1.1.0", rows=[_row([])], with_suite=False)
    assert r["decision"] == "hold" and "suite not run" in r["reason"]


def test_profile_env_selects_gate_profile(monkeypatch):
    import colony.trust.athanor_gate as G
    monkeypatch.delenv("COLONY_ATHANOR_PROFILE", raising=False)
    assert G.gate_profile() == "selfmod/adaptive@1.1.0"
    monkeypatch.setenv("COLONY_ATHANOR_PROFILE", "tsp/adaptive@1.1.0")
    r = G.assess_change(before={"score": 0.9, "checks": {"a": True}}, after={"score": 0.9, "checks": {"a": True}})
    assert r["gate_profile"] == "tsp/adaptive@1.1.0"
    monkeypatch.setenv("COLONY_ATHANOR_PROFILE", "not-a-profile")
    assert G.gate_profile() == "selfmod/adaptive@1.1.0"
