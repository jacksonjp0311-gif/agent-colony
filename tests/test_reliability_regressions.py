"""Regressions for the October 19 source review; no authorization execution."""
from pathlib import Path
from unittest.mock import patch

import pytest

from colony.registry import AgentRegistry
from colony.fitness import EvolutionEngine
from colony.standing_trust import meets_standing_trust
from colony.trust.shifted_holdout import shifted_window_check


def retired_state():
    data = {"roles": {"courier": {"status": "active"}}, "cycle_count": 5}
    registry = AgentRegistry(data)
    registry.enter("courier")
    registry.leave("courier")
    return data, registry


def test_sync_does_not_revive_retired_agent():
    data, registry = retired_state()
    registry.sync_from_roles(cycle_id="next")
    assert registry.agents()["courier"]["status"] == "retired"


def test_spawn_menu_does_not_revive_without_pressure():
    data, registry = retired_state()
    data["fitness_history"] = [{"comm_reply_rate": 1.0}] * 3
    engine = EvolutionEngine(data, registry, None)
    with patch.object(engine, "hard_tier_emergence", return_value={}):
        engine.maybe_spawn("next", {"comm_reply_rate": 1.0})
    assert registry.agents()["courier"]["status"] == "retired"


@pytest.mark.parametrize("confidence", [float("inf"), float("nan"), 1.1, True, None, 0])
def test_confidence_fails_closed(confidence):
    assert not meets_standing_trust(confidence, machine_checked=True)


@pytest.mark.parametrize("expression", ["True", "all(n < 100 for n in range(limit))",
                                       "True or all(n < 2 for n in range(2))",
                                       "all(n > 0 for n in range(0))",
                                       "all(n < 2 for n in range(2) if n < 2)"])
def test_unapplied_shift_is_not_survival(tmp_path, expression):
    src = tmp_path / "entry.py"
    src.write_text(f"limit = 3\nHARD_TIER_LEMMAS = [('test', lambda: {expression}, True)]\n")
    result = shifted_window_check(src, "test")
    assert result["ok"] is False
    assert result["status"] == "not_tested"


def test_stepped_shift_finds_counterexample(tmp_path):
    src = tmp_path / "entry.py"
    src.write_text("HARD_TIER_LEMMAS = [('test', lambda: all(n < 6 for n in range(0, 6, 2)), True)]\n")
    result = shifted_window_check(src, "test")
    assert result["ok"] is False
    assert result["status"] == "fail"


@pytest.mark.parametrize("expression", ["all(n % 2 == 0 for n in range(0, 6, 2))",
                                       "all(n % 2 == 0 for n in range(6, 0, -2))"])
def test_applicable_shift_records_finite_pass(tmp_path, expression):
    src = tmp_path / "entry.py"
    src.write_text(f"HARD_TIER_LEMMAS = [('test', lambda: {expression}, True)]\n")
    result = shifted_window_check(src, "test")
    assert result["status"] == "pass"
    assert result["applied"] is True
    assert result["probes"] == 3
    assert "not_universal_proof" in result["scope"]


def test_oracle_does_not_credit_unapplied_shift(tmp_path):
    from colony import oracle
    artifact = tmp_path / "society" / "benchmarks" / "artifacts" / "lemma_impl.py"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("HARD_TIER_LEMMAS = [('test', lambda: True, True)]\n")
    with patch.object(oracle, "ROOT", tmp_path):
        result = oracle.sense_held_out("test", "hard_enable",
                                      after_snapshot={"ok": True, "n_hard": 1, "n_hard_pass": 1})
    assert result["survives"] is False
    assert result["ok_for_oracle"] is False


def test_revival_requires_cooldown_pressure_and_capacity():
    data, registry = retired_state()
    evidence = {"cycle_id": "later", "metric": "comm_reply_rate",
                "values": [0.1, 0.1, 0.1], "threshold": 0.35}
    for elapsed in (0, 1, 2):
        data["cycle_count"] = 5 + elapsed
        assert not registry.revive("courier", cycle_id="later", evidence=evidence)
    data["cycle_count"] = 8
    assert not registry.revive("courier", cycle_id="wrong_cycle", evidence=evidence)
    assert not registry.revive("courier", cycle_id="later", evidence={**evidence, "values": [1, 1, 1]})
    registry.enter("spark")
    data["population"]["soft_cap"] = 1
    assert not registry.revive("courier", cycle_id="later", evidence=evidence)
    data["population"]["soft_cap"] = 20
    assert registry.revive("courier", cycle_id="later", evidence=evidence)
    assert data["roles"]["courier"]["status"] == "active"
    assert data["history"][-1]["evidence"] == evidence


@pytest.mark.parametrize("meta", [{}, {"P": None}, {"P": 0, "confidence": .99},
                                  {"P": float("inf")}, {"P": 1.1}, {"P": True}])
def test_selector_rejects_missing_invalid_or_zero_confidence(meta):
    from types import SimpleNamespace
    from colony.selective_authorize import select_candidates
    finding = SimpleNamespace(id="f", status="candidate", tags=["keep", "bus_driven"],
                              meta={"cycle_id": "c", "mutation": "m", **meta})
    ledger = SimpleNamespace(all=lambda: [finding])
    state = {"cycle_diagnostics": {"c": {"promotion_allowed": True}}}
    with patch("colony.selective_authorize.oracle_backed", return_value={"ok": True}):
        assert select_candidates(ledger, state, event_name="workflow_dispatch", requested="true") == []


def test_selector_requires_manual_request_evidence_and_healthy_cycle():
    from types import SimpleNamespace
    from colony.selective_authorize import select_candidates
    finding = SimpleNamespace(id="f", status="candidate", tags=["keep"],
                              meta={"cycle_id": "c", "mutation": "m", "P": .8})
    ledger = SimpleNamespace(all=lambda: [finding])
    state = {"cycle_diagnostics": {"c": {"promotion_allowed": True}}}
    with patch("colony.selective_authorize.oracle_backed", return_value={"ok": True}):
        assert not select_candidates(ledger, state, event_name="schedule", requested="true")
        assert not select_candidates(ledger, state, event_name="workflow_dispatch", requested="false")
        assert not select_candidates(ledger, {}, event_name="workflow_dispatch", requested="true")
        selected = select_candidates(ledger, state, event_name="workflow_dispatch", requested="true")
        assert [s["finding_id"] for s in selected] == ["f"]
        state["cycle_diagnostics"]["c"]["promotion_allowed"] = False
        assert not select_candidates(ledger, state, event_name="workflow_dispatch", requested="true")
    state["cycle_diagnostics"]["c"]["promotion_allowed"] = True
    with patch("colony.selective_authorize.oracle_backed", return_value={"ok": False}):
        assert not select_candidates(ledger, state, event_name="workflow_dispatch", requested="true")


@pytest.mark.parametrize("decision", ["accepted", "rejected"])
def test_selector_does_not_repeat_prior_human_decision(decision):
    from types import SimpleNamespace
    from colony.selective_authorize import select_candidates
    finding = SimpleNamespace(id="f", status="candidate", tags=["keep"],
                              meta={"cycle_id": "c", "mutation": "m", "P": .8})
    correction = SimpleNamespace(id="correction", status=decision, tags=[],
                                 meta={"kind": "authorize", "parent_id": "f"})
    ledger = SimpleNamespace(all=lambda: [finding, correction])
    state = {"cycle_diagnostics": {"c": {"promotion_allowed": True}}}
    with patch("colony.selective_authorize.oracle_backed", return_value={"ok": True}):
        assert not select_candidates(ledger, state, event_name="workflow_dispatch", requested="true")


def test_latest_machine_verdict_overrules_prior_pass(tmp_path):
    import json
    from colony.trust.provenance import oracle_backed
    log = tmp_path / "oracle.jsonl"
    rows = [{"mutation": "m", "cycle_id": "c", "passed": True, "fitness_credit": True},
            {"mutation": "m", "cycle_id": "c", "passed": False, "fitness_credit": False}]
    log.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    assert oracle_backed("m", "c", log=log)["ok"] is False
    assert oracle_backed("m", "other", log=log)["ok"] is False


@pytest.mark.parametrize("scenario", ["retirement", "diagnostics"])
def test_two_normal_cycles_and_failed_stage_diagnostics(tmp_path, scenario):
    """Run the actual Society -> Spark -> GrowthLoop path in a disposable source tree."""
    import json
    import os
    import shutil
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    for directory in ("colony", "society"):
        shutil.copytree(root / directory, tmp_path / directory,
                        ignore=shutil.ignore_patterns("__pycache__", "*.jsonl", "*.b64"))
    # Historical sieve entries assume the optional C backend. Use the repository's
    # ordinary finite catalog here so this lifecycle regression also runs offline
    # without libprimesieve; retain the real bench, growth, fitness and spawn code.
    import ast
    artifact = tmp_path / "society" / "benchmarks" / "artifacts" / "lemma_impl.py"
    source = artifact.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    flags = []
    for node in ast.walk(ast.parse(source)):
        if (isinstance(node, ast.Tuple) and len(node.elts) == 3
                and isinstance(node.elts[0], ast.Constant)
                and str(node.elts[0].value).startswith("authored_sieve_")
                and isinstance(node.elts[2], ast.Constant)):
            flag = node.elts[2]
            flags.append((flag.lineno - 1, flag.col_offset, flag.end_col_offset))
    for line, start, end in sorted(flags, reverse=True):
        lines[line] = lines[line][:start] + "False" + lines[line][end:]
    artifact.write_text("".join(lines), encoding="utf-8")
    shutil.copy2(root / "CHARTER.md", tmp_path / "CHARTER.md")
    (tmp_path / "data").mkdir()
    shutil.copy2(root / "data" / "seed_corpus.json", tmp_path / "data" / "seed_corpus.json")
    (tmp_path / "data" / "society_state.json").write_text(json.dumps({
        "roles": {"spark": {"status": "active"}, "tribute_keeper": {"status": "active"}},
        "founding_roles": ["spark", "tribute_keeper"], "cycle_count": 5,
    }))
    worker = r'''
import json
import sys
import socket
from pathlib import Path
from unittest.mock import patch
from colony.society import Society
from colony.registry import AgentRegistry
from colony.fitness import EvolutionEngine
def offline(*args, **kwargs):
    raise OSError("test has no network")
socket.socket.connect = offline
socket.create_connection = offline

s = Society(root=Path.cwd(), live_fetch=False)
s.state.add_role("courier", "test retired role")
r = AgentRegistry(s.state.data)
r.enter("courier")
r.agents()["courier"].update(cycles_served=6, contribution_score=0)
assert "courier" in EvolutionEngine(s.state.data, r, None).maybe_retire("fixture")
if sys.argv[1] == "retirement":
    original_enter = AgentRegistry.enter
    revivals = []
    def observe_enter(registry, role, *args, **kwargs):
        before = (registry.agents().get(role) or {}).get("status")
        entry = original_enter(registry, role, *args, **kwargs)
        if role == "courier" and before == "retired" and entry["status"] == "active":
            revivals.append(kwargs.get("reason"))
        return entry
    with patch.object(AgentRegistry, "enter", observe_enter):
        for _ in range(2):
            result = s.run_cycle()
            assert r.agents()["courier"]["status"] == "retired"
            assert not revivals, revivals  # Re-retirement at cycle end must not hide revival.
            assert result.tribute_count > 0
            assert result.fitness, result.stage_diagnostics
    print("NORMAL_CYCLES_AND_DIAGNOSTICS_OK")
    sys.exit(0)

from colony import retire, surprise_credit, frontier_conjectures, new_data, shortlist
def fail(*args, **kwargs):
    raise RuntimeError("injected stage fault")
with patch.object(retire, "mode", return_value="shadow"), patch.object(retire, "run_cycle", fail), \
     patch.object(surprise_credit, "mode", return_value="shadow"), patch.object(surprise_credit, "ranking_check", fail), \
     patch.object(frontier_conjectures, "mode", return_value="shadow"), patch.object(frontier_conjectures, "run_cycle", fail), \
     patch.object(new_data, "mode", return_value="shadow"), patch.object(new_data, "run_cycle", fail), \
     patch.object(shortlist, "write", fail):
    result = s.run_cycle()
assert result.promotion_allowed is False
for stage in ("retire", "surprise_credit", "frontier", "new_data"):
    assert result.stage_diagnostics[stage]["status"] == "failed"
assert result.stage_diagnostics["shortlist"]["status"] == "degraded"
assert result.stage_diagnostics["emergence"]["status"] == "blocked"
assert result.fitness == {}
saved = json.loads(s.state.path.read_text())
assert saved["cycle_diagnostics"][result.cycle_id]["promotion_allowed"] is False
assert "injected stage fault" in result.report_path.read_text()
assert any(e.kind == "stage_failure" for e in s.witness.all())
print("NORMAL_CYCLES_AND_DIAGNOSTICS_OK")
'''
    env = {**os.environ, "PYTHONPATH": str(tmp_path), "COLONY_NEWDATA_OFFLINE": "1",
           "COLONY_FRONTIER": "off", "COLONY_NEWDATA": "off", "COLONY_RETIRE": "off",
           "COLONY_SURPRISE": "off", "STATE_SHARDS": "0", "PYTHONIOENCODING": "utf-8",
           "COLONY_SIEVE_MAX_SPAN": "100000"}
    run = subprocess.run([sys.executable, "-c", worker, scenario], cwd=tmp_path, env=env,
                         capture_output=True, text=True, encoding="utf-8", timeout=180,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-5000:]
    assert "NORMAL_CYCLES_AND_DIAGNOSTICS_OK" in run.stdout
