"""Items 38–40: honest twin fitness, frozen flag, swarm_rules snapshot."""
from __future__ import annotations

import json
from pathlib import Path

import colony.hive_adapter as adapter
import colony.systems as systems
import colony.twin as twin
import hive.swarm as SL
from colony.systems import SystemWorkshop
from tests.test_twin_control import _tiny_society, _write


def test_scoreboard_uses_control_shard_when_systems_history_is_stale(tmp_path):
    """True fitness gap is +0.0017, not the stale-seed +0.0006."""
    treatment = _tiny_society(
        tmp_path / "treatment",
        fitness=0.8591,
        novelty=0.75,
        cycle_count=882,
        adopts=0,
        trial=None,
    )
    control = _tiny_society(
        tmp_path / "control",
        fitness=0.8585,  # stale seed row in systems history
        novelty=0.75,
        cycle_count=882,
        adopts=0,
        trial=None,
    )
    # Live control rows landed only in the shard (item 38).
    shard = control / "data" / "society_shards" / "fitness_history.jsonl"
    shard.parent.mkdir(parents=True, exist_ok=True)
    shard.write_text(
        json.dumps({
            "ts": "2026-11-13T03:45:00Z",
            "cycle_id": "20261113T034312Z_c42659",
            "aggregate": 0.8574,
            "novelty": 0.75,
        }) + "\n",
        encoding="utf-8",
    )
    # Seed row is older.
    (control / "society" / "systems" / "fitness_history.jsonl").write_text(
        json.dumps({
            "ts": "2026-11-13T02:56:51Z",
            "cycle_id": "20261113T025651Z_8fbc4a",
            "aggregate": 0.8585,
            "novelty": 0.75,
        }) + "\n",
        encoding="utf-8",
    )
    t = twin.collect_arm_metrics(treatment)
    c = twin.collect_arm_metrics(control)
    assert t["fitness"] == 0.8591
    assert c["fitness"] == 0.8574
    delta = twin._delta(t, c)
    assert delta["fitness"] == 0.0017


def test_control_metrics_report_self_heal_frozen(tmp_path):
    control = _tiny_society(tmp_path / "control", adopts=0, trial=None)
    # self_heal.json has no frozen key, as on the live control snapshot.
    heal = json.loads((control / "society" / "systems" / "self_heal.json").read_text())
    heal.pop("frozen", None)
    (control / "society" / "systems" / "self_heal.json").write_text(
        json.dumps(heal, indent=2) + "\n", encoding="utf-8",
    )
    _write(control / ".fork.json", {
        "frozen": True,
        "control_seeded": True,
        "arm": "control",
    })
    c = twin.collect_arm_metrics(control)
    assert c["self_heal_frozen"] is True

    treatment = _tiny_society(tmp_path / "treatment", adopts=0, trial=None)
    t = twin.collect_arm_metrics(treatment)
    assert t["self_heal_frozen"] is False


def test_append_fitness_joins_through_workshop_dir(tmp_path):
    """A multi-component stored path must not escape the workshop tree."""
    root = tmp_path / "control"
    (root / "society" / "systems").mkdir(parents=True)
    data = {
        "systems": [{
            "name": "fitness_ledger",
            "kind": "ledger",
            "path": "society/systems/fitness_history.jsonl",
            "use_count": 0,
        }]
    }
    ws = SystemWorkshop(data, root=root)
    ws.append_fitness({"cycle_id": "c-live", "aggregate": 0.8574})
    path = root / "society" / "systems" / "fitness_history.jsonl"
    assert path.is_file()
    row = json.loads(path.read_text(encoding="utf-8").strip())
    assert row["aggregate"] == 0.8574
    assert row["cycle_id"] == "c-live"
    # Must not have written next to a fake repo-relative join off cwd.
    stray = Path("society") / "systems" / "fitness_history.jsonl"
    # If a leftover exists from the process cwd, it must not be ours.
    if stray.exists() and stray.resolve() != path.resolve():
        assert "c-live" not in stray.read_text(encoding="utf-8")


def test_save_state_writes_swarm_rules_even_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(SL, "STATE_PATH", tmp_path / "swarm_learn.json")
    monkeypatch.setattr(SL, "RULES_PATH", tmp_path / "swarm_rules.json")
    st = SL._empty_state()
    st["seeded"] = True
    SL.save_state(st)
    rules_path = tmp_path / "swarm_rules.json"
    assert rules_path.is_file()
    payload = json.loads(rules_path.read_text(encoding="utf-8"))
    assert payload["rules"] == []
    assert payload["n"] == 0
    assert payload["authorized"] is False
    assert payload["applied_to_live_oracle"] is False
    # A non-empty list also persists.
    st["rules"] = [{"id": "r1", "op": "add_skip_rule", "active": True}]
    SL.save_state(st)
    payload = json.loads(rules_path.read_text(encoding="utf-8"))
    assert payload["n"] == 1
    assert payload["rules"][0]["id"] == "r1"


def test_adapter_enriches_live_finding_with_structured_tokens():
    raw = {
        "kind": "no_progress_perturb",
        "evidence": {
            "exit_reason": "no_candidates",
            "exit_cycle": "20261113T015301Z_759b6f",
            "session_targets": [],
            "timeout_count": 2,
        },
    }
    out = adapter.enrich_finding(raw)
    assert out["failure_class"] == "no_progress_perturb"
    assert out["exit_reason"] == "no_candidates"
    cap = adapter.enrich_finding({
        "kind": "depth_at_physical_cap",
        "evidence": {"recent": [{"cap_reason": "term_cap", "anum": "A165064"}]},
    })
    assert cap["cap_reason"] == "term_cap"


def test_control_seed_does_not_copy_huge_logs(tmp_path, monkeypatch):
    """Going forward, control seed points at a frozen treatment prefix."""
    import colony.arm as arm
    monkeypatch.delenv("COLONY_ARM", raising=False)
    src = tmp_path / "treatment"
    dest = tmp_path / "control"
    _tiny_society(src, cycle_count=10, adopts=0, trial=None)
    # Fake huge append-only logs (content is small; the skip is by name).
    ledger = src / "data" / "ledger.jsonl"
    witness = src / "data" / "witness.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(json.dumps({"id": "f1", "claim": "seed-row"}) + "\n", encoding="utf-8")
    witness.write_text(json.dumps({"id": "w1", "summary": "seed-event"}) + "\n", encoding="utf-8")
    rec = arm.ensure_control_seed(source_root=src, dest_root=dest, force=True)
    assert rec["control_seeded"] is True
    # The huge logs themselves are not copied.
    assert not (dest / "data" / "ledger.jsonl").is_file() or (dest / "data" / "ledger.jsonl").stat().st_size == 0
    assert not (dest / "data" / "witness.jsonl").is_file() or (dest / "data" / "witness.jsonl").stat().st_size == 0
    # Pointers and manifests exist.
    assert "log_pointers" in rec
    assert "ledger.jsonl" in rec["log_pointers"]
    assert "witness.jsonl" in rec["log_pointers"]
    from colony.log_segments import iter_lines, manifest_path
    assert manifest_path(dest / "data" / "witness.jsonl").is_file()
    rows = [json.loads(l) for l in iter_lines(dest / "data" / "witness.jsonl") if l.strip()]
    assert rows and rows[0]["id"] == "w1"
    # Treatment files are untouched.
    assert "seed-event" in witness.read_text(encoding="utf-8")
