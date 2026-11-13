"""Test isolation (trust loop 2026-10-11).

Before this file, running the suite rewrote ~25 tracked colony-state files (oracle.jsonl,
lessons.jsonl, society/systems/*.json ...) and CI then committed those test rows as if the
colony had produced them. This session fixture snapshots data/ and society/ and restores them
byte-for-byte (removing files the tests created) when the session ends.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_STATE_DIRS = ("data", "society")


def _snapshot() -> dict[Path, bytes]:
    snap: dict[Path, bytes] = {}
    for d in _STATE_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts:
                snap[p] = p.read_bytes()
    return snap


@pytest.fixture(scope="session", autouse=True)
def _restore_live_colony_state():
    snap = _snapshot()
    yield
    for d in _STATE_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in sorted(base.rglob("*"), reverse=True):
            if p.is_file() and "__pycache__" not in p.parts and p not in snap:
                p.unlink()
            elif p.is_dir() and not any(p.iterdir()):
                if not any(str(k).startswith(str(p) + "/") for k in snap):
                    p.rmdir()
    for p, b in snap.items():
        if not p.exists() or p.read_bytes() != b:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b)


@pytest.fixture(autouse=True)
def _isolate_stall_state(tmp_path, monkeypatch):
    """Each test gets a fresh stall state file so parks and PERTURB cannot leak."""
    import colony.stall as S
    monkeypatch.setattr(S, "STATE_PATH", tmp_path / "stall_state.json")
    import colony.oeis_conjectures as OC
    monkeypatch.setattr(OC, "ATTEMPT_LOG", tmp_path / "oeis_attempt_log.json")


@pytest.fixture(autouse=True)
def _isolate_checker_lane(tmp_path, monkeypatch):
    """Each test gets a fresh checker-lane state so proposals cannot leak."""
    import colony.checker_lane as CL
    monkeypatch.setattr(CL, "STATE_PATH", tmp_path / "checker_lane.json")
    monkeypatch.setattr(CL, "LANE_LOG", tmp_path / "checker_lane.jsonl")
    monkeypatch.setattr(CL, "PROPOSAL_DIR", tmp_path / "checker_proposals")


@pytest.fixture(autouse=True)
def _isolate_self_heal(tmp_path, monkeypatch):
    """Each test gets a fresh self-heal snapshot so trials cannot leak."""
    import colony.self_heal as SH
    monkeypatch.setattr(SH, "STATE_PATH", tmp_path / "self_heal.json")
    monkeypatch.setattr(SH, "EVENT_LOG", tmp_path / "self_heal.jsonl")



@pytest.fixture(autouse=True)
def _bind_and_isolate_hive(tmp_path, monkeypatch):
    """Bind Hive to the colony and give each test a fresh library / state."""
    import colony.hive_adapter as adapter
    adapter.bind()
    import hive.library as FL
    import hive.swarm as SL
    monkeypatch.setattr(FL, "LIBRARY_LOG", tmp_path / "fix_library.jsonl")
    monkeypatch.setattr(SL, "STATE_PATH", tmp_path / "swarm_learn.json")
    monkeypatch.setattr(SL, "EVENT_LOG", tmp_path / "swarm_learn.jsonl")
    monkeypatch.setattr(SL, "RULES_PATH", tmp_path / "swarm_rules.json")
