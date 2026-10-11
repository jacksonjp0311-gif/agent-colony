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
