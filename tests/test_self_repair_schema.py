"""Self-repair: missing attempted_by / blocked_repeat must not KeyError the cycle."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from colony.lessons import load_lessons, write_human_guide, write_lesson


def test_blocked_repeat_prop_includes_attempted_by(tmp_path, monkeypatch):
    """propose_improvement blocked_repeat return must carry attempted_by (Relight schema)."""
    import colony.fitness as F
    import colony.lessons as L

    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")

    class FakeReg:
        def best_for(self, skill: str) -> str:
            return "improver"

    class FakeEvo(F.EvolutionEngine if hasattr(F, "EvolutionEngine") else object):
        pass

    # Build a minimal EvolutionEngine-like object with propose_improvement bound
    # Prefer constructing real EvolutionEngine if signature is light.
    from colony.fitness import EvolutionEngine

    state_data = {
        "improvement_proposals": [
            {"fingerprint": "deadbeef0001", "status": "rejected", "title": "t"},
            {"fingerprint": "deadbeef0001", "status": "rejected", "title": "t"},
            {"fingerprint": "deadbeef0001", "status": "deferred", "title": "t"},
        ]
    }

    class MiniState:
        data = state_data

    class MiniReg:
        def best_for(self, skill: str) -> str:
            return "improver"

    # Seed lessons so fingerprint count >= 3
    for _ in range(3):
        write_lesson(
            decision="block",
            check="dedupe",
            what="seed repeat",
            source="test",
            lesson_type="repeat_proposal",
            proposal_fingerprint="deadbeef0001",
            tags=["repeat_proposal"],
        )

    # Monkeypatch hash to fixed fp by controlling title|action canon
    # sha1 of "same title|same action" — compute real fp from propose_improvement
    import hashlib
    import re

    def _canon(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").strip().lower())

    title = "Same Title"
    action = "same action"
    fp = hashlib.sha1(f"{_canon(title)}|{_canon(action)}".encode()).hexdigest()[:12]

    # Re-seed with the real fp
    (tmp_path / "lessons.jsonl").write_text("", encoding="utf-8")
    for _ in range(3):
        write_lesson(
            decision="block",
            check="dedupe",
            what="seed repeat",
            source="test",
            lesson_type="repeat_proposal",
            proposal_fingerprint=fp,
            tags=["repeat_proposal"],
        )
    state_data["improvement_proposals"] = [
        {"fingerprint": fp, "status": "rejected", "title": title},
        {"fingerprint": fp, "status": "rejected", "title": title},
        {"fingerprint": fp, "status": "deferred", "title": title},
    ]

    evo = EvolutionEngine.__new__(EvolutionEngine)
    evo.data = state_data
    evo.registry = MiniReg()
    evo.workshop = None

    prop = evo.propose_improvement(
        cycle_id="cyc_repair1",
        metrics={"aggregate": 0.7},
        title=title,
        hypothesis="h",
        action=action,
    )
    assert prop.get("status") == "blocked_repeat"
    assert "attempted_by" in prop, "blocked_repeat must include attempted_by (schema)"
    assert prop["attempted_by"] == "improver"


def test_attempt_improvement_missing_attempted_by_writes_lesson(tmp_path, monkeypatch):
    """Crash repro from run 37580467492: prop without attempted_by must not KeyError."""
    import colony.lessons as L
    from colony.emergence.growth_steps_evolve import GrowthSteps3

    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")

    class GS(GrowthSteps3):
        pass

    gs = GS.__new__(GS)

    class FakeEvo:
        def propose_improvement(self, **kwargs):
            # Malformed Relight-era blocked shape (missing attempted_by) — pre-fix schema
            return {
                "id": "imp_blocked_deadbeef",
                "ts": "2026-10-07T06:16:17Z",
                "cycle_id": kwargs.get("cycle_id"),
                "title": kwargs.get("title"),
                "hypothesis": kwargs.get("hypothesis"),
                "action": kwargs.get("action"),
                "status": "candidate",  # not blocked — forces .get path after hearing
                "fingerprint": "deadbeef0001",
                "P": 0.0,
                # deliberately NO attempted_by
            }

        def pick_improvement(self, metrics):
            return ("Test improve", "hypothesis", "skill_boost:spark.research")

    class FakeLedger:
        def set_extra_roles(self, roles):
            pass

        def all(self):
            return []

        def create(self, **kwargs):
            m = MagicMock()
            m.id = "f_test"
            return m

    class FakeWitness:
        def record(self, **kwargs):
            pass

    class FakeRegistry:
        def active(self):
            return ["spark"]

        def record_outcome(self, *a, **k):
            pass

        def best_for(self, skill):
            return "spark"

    class FakeState:
        data = {"improvement_proposals": []}

        def role_names(self):
            return {"spark"}

    gs.evo = FakeEvo()
    gs.ledger = FakeLedger()
    gs.witness = FakeWitness()
    gs.registry = FakeRegistry()
    gs.state = FakeState()

    g = MagicMock()
    g.fitness = {"aggregate": 0.77}
    g.rsi_signal = {}
    g.behavior_signal = None
    g.findings = []
    g.improvements = []
    g.skill_updates = []

    # Must not raise KeyError
    gs._attempt_improvement("cyc_crash_repro", 3, g)

    rows = load_lessons(limit=50)
    assert any(e.get("type") == "schema_drift" for e in rows), rows
    assert any("attempted_by" in (e.get("what") or "") for e in rows)


def test_attempt_improvement_blocked_repeat_returns_quietly(tmp_path, monkeypatch):
    import colony.lessons as L
    from colony.emergence.growth_steps_evolve import GrowthSteps3

    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")

    gs = GrowthSteps3.__new__(GrowthSteps3)

    class FakeEvo:
        def propose_improvement(self, **kwargs):
            return {
                "id": "imp_blocked_x",
                "status": "blocked_repeat",
                "fingerprint": "abc",
                "title": kwargs.get("title"),
                # even without attempted_by, early return must protect
            }

        def pick_improvement(self, metrics):
            return ("Repeat title", "h", "mandate:x")

    gs.evo = FakeEvo()
    gs.ledger = MagicMock()
    gs.witness = MagicMock()
    gs.registry = MagicMock()
    gs.registry.active.return_value = ["spark"]
    gs.state = MagicMock()
    gs.state.data = {"improvement_proposals": [{"title": "Repeat title"}]}
    gs.state.role_names.return_value = {"spark"}

    g = MagicMock()
    g.fitness = {"aggregate": 0.5}
    g.rsi_signal = {}
    g.behavior_signal = None
    g.findings = []
    g.improvements = []

    gs._attempt_improvement("cyc_block", 1, g)
    # ledger.create must NOT be called (early return)
    gs.ledger.create.assert_not_called()


def test_schema_drift_and_self_repair_types_accepted(tmp_path, monkeypatch):
    import colony.lessons as L

    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")
    e1 = write_lesson(
        decision="skip",
        check="schema",
        what="missing field",
        source="test",
        lesson_type="schema_drift",
        family="self_repair",
    )
    e2 = write_lesson(
        decision="skip",
        check="schema",
        what="recovered KeyError",
        source="test",
        lesson_type="self_repair",
        family="self_repair",
    )
    assert e1["type"] == "schema_drift"
    assert e2["type"] == "self_repair"
