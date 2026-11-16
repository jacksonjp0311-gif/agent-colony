"""Item 97: entries that came only from the pre-#59 STEM held-out bug are not prior knowledge."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

import colony.ledger_exemptions as LX
import colony.novelty_gate as ng

ROOT = Path(__file__).resolve().parents[1]
BUG, LED = LX.BUG_KILL, LX.LEDGER_KILL


def _w(p: Path, rows: list[dict]) -> Path:
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


@pytest.fixture
def logs(tmp_path):
    gate = _w(tmp_path / "gate.jsonl", [
        {"ts": "T1", "cycle_id": "c1", "mutation": "stem_a", "kind": "stem_enable", "kills": [BUG]},
        {"ts": "T2", "cycle_id": "c2", "mutation": "stem_b", "kind": "stem_enable", "kills": [BUG, "textbook_reuse=0.6667"]},
        {"ts": "T3", "cycle_id": "c3", "mutation": "stem_a", "kind": "stem_enable", "kills": [LED]},
        {"ts": "T4", "cycle_id": "c4", "mutation": "stem_b", "kind": "stem_enable", "kills": [LED]},
        {"ts": "T5", "cycle_id": "c5", "mutation": "lemma_x", "kind": "hard_enable", "kills": [BUG]},
    ])
    lessons = _w(tmp_path / "lessons.jsonl", [
        {"id": "l1", "ts": "T1", "type": "revert", "mutation": "stem_a", "cycle_id": "c1"},
        {"id": "l2", "ts": "T2", "type": "revert", "mutation": "stem_b", "cycle_id": "c2"},
        {"id": "l3", "ts": "T3", "type": "revert", "mutation": "stem_a", "cycle_id": "c3"},
        {"id": "l4", "ts": "T4", "type": "revert", "mutation": "stem_b", "cycle_id": "c4"},
        {"id": "l5", "ts": "T5", "type": "revert", "mutation": "lemma_x", "cycle_id": "c5"},
    ])
    history = _w(tmp_path / "history.jsonl", [
        {"ts": "T1", "decision": "revert", "mutation": "stem_a"},
        {"ts": "T2", "decision": "revert", "mutation": "stem_b"},
        {"ts": "T3", "decision": "revert", "mutation": "stem_a"},
    ])
    return gate, lessons, history


def test_only_bug_only_entries_are_listed(logs):
    recs = LX.bug_only_rows(*logs)
    got = {(r["source"], r["entry_ts"], r["mutation"]) for r in recs}
    # stem_a: first row (bug only) and its repeat (ledger kill whose earlier traces are all exempt)
    assert got == {("lessons", "T1", "stem_a"), ("history", "T1", "stem_a"),
                   ("lessons", "T3", "stem_a"), ("history", "T3", "stem_a")}
    # stem_b had another kill (textbook) → real decision → its entries stay; so does its repeat.
    # hard_enable rows are never exempt.


def _gate_with(monkeypatch, logs, exempt_path):
    gate, lessons, history = logs
    monkeypatch.setattr(ng, "LESSONS", lessons)
    monkeypatch.setattr(ng, "HISTORY", history)
    monkeypatch.setattr(ng, "KNOWN", exempt_path.parent / "known.json")
    monkeypatch.setattr(LX, "EXEMPT_LOG", exempt_path)


def _build(logs, out):
    p = ROOT / "scripts" / "item97_build_ledger_exemptions.py"
    spec = importlib.util.spec_from_file_location("b97", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    gate, lessons, history = logs
    return mod.main(write=True, out=out, gate=gate, lessons=lessons, history=history)


def test_gate_skips_only_listed_entries_treatment_only(logs, tmp_path, monkeypatch):
    monkeypatch.delenv("COLONY_ARM", raising=False)
    monkeypatch.delenv("COLONY_SELF_MOD", raising=False)
    out = tmp_path / "ledger_exemptions.jsonl"
    _gate_with(monkeypatch, logs, out)
    assert ng.in_ledger_kill("stem_a") and ng.in_ledger_kill("stem_b")
    before_lessons = logs[1].read_text()
    rows = _build(logs, out)
    assert len(rows) == 4 and all(r["decided_by"] for r in rows)
    assert _build(logs, out) == []  # idempotent, append-only
    assert logs[1].read_text() == before_lessons  # nothing edited
    assert not ng.in_ledger_kill("stem_a")  # only bug entries: not prior knowledge
    assert ng.in_ledger_kill("stem_b")  # real decision: still known
    assert ng.in_ledger_kill("lemma_x")
    # control arm: exemptions ignored (frozen)
    monkeypatch.setenv("COLONY_SELF_MOD", "off")
    assert ng.in_ledger_kill("stem_a")


def test_any_other_trace_still_counts(logs, tmp_path, monkeypatch):
    monkeypatch.delenv("COLONY_SELF_MOD", raising=False)
    out = tmp_path / "ledger_exemptions.jsonl"
    _gate_with(monkeypatch, logs, out)
    _build(logs, out)
    with logs[1].open("a") as fh:
        fh.write(json.dumps({"id": "l9", "ts": "T9", "type": "keep", "mutation": "stem_a"}) + "\n")
    assert ng.in_ledger_kill("stem_a")


def test_replay_flips_only_bug_rows(logs, monkeypatch):
    import colony.stem_held_out as SH
    p = ROOT / "scripts" / "replay_item97_ledger_exemptions.py"
    spec = importlib.util.spec_from_file_location("r97", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "held_out", lambda n: {"survives": True, "reason": "stem_harder_instance_green"})
    monkeypatch.setattr(mod, "triviality", lambda n: {"trivial": False, "reason": "not_a_tautology"})
    rep = mod.main(*logs)
    assert rep["exempt_non_stem"] == []
    assert [(f["ts"], f["mutation"], f["flip_cause"]) for f in rep["flips"]] == [
        ("T1", "stem_a", "item95_held_out"), ("T3", "stem_a", "item97_exemption")]
