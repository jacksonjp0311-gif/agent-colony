"""Isolate Hive I/O and unbind any host. No colony imports."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_hive_paths(tmp_path, monkeypatch):
    from hive import host
    import hive.library as library
    import hive.swarm as swarm

    # Hive's own tests always run without a host, even when they share
    # a pytest process with the colony suite.
    host.bind(heal=None, checker=None)
    monkeypatch.setattr(library, "LIBRARY_LOG", tmp_path / "fix_library.jsonl")
    monkeypatch.setattr(library, "LIBRARY_SNAPSHOT", tmp_path / "swarm_library.json")
    monkeypatch.setattr(swarm, "STATE_PATH", tmp_path / "swarm_learn.json")
    monkeypatch.setattr(swarm, "EVENT_LOG", tmp_path / "swarm_learn.jsonl")
    monkeypatch.setattr(swarm, "RULES_PATH", tmp_path / "swarm_rules.json")
    yield
    host.bind(heal=None, checker=None)
