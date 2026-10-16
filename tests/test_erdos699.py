"""Erdős #699 target: both checkers reproduce the known strict exceptions; labeled evidence, not proof."""
from __future__ import annotations

import json
import shutil

import pytest

import colony.erdos699 as E

pytestmark = pytest.mark.skipif(shutil.which("gcc") is None, reason="needs gcc")


def test_target_label():
    t = json.loads(E.TARGET.read_text())
    assert t["label"] == "bounded evidence, not proof" and t["proof"] is False and t["status"] == "open"


def test_fast_and_brute_reproduce_known_strict(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "BIN", tmp_path / "bin")
    b = E.build()
    want = sorted(t for t in E.KNOWN_STRICT if t[0] <= 3000)
    fast = E.run_bin([b["fast699"], "4", "3000"])
    assert sorted(fast["strict"]) == want and fast["main"] == []
    full = E.run_bin([b["brute699"], "full", "4", "600"])
    assert sorted(full["strict"]) == [t for t in want if t[0] <= 600] and full["main"] == []
    lite = E.run_bin([b["brute699"], "lite", "4", "3000"])
    assert sorted(lite["strict"]) == want and lite["main"] == []


def test_ranges_merge_and_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "RANGES", tmp_path / "r")
    (tmp_path / "r").mkdir()
    for lo, hi in [(4, 1_000_000), (1_000_001, 3_000_000), (5_000_001, 6_000_000)]:
        (tmp_path / "r" / f"{lo}_{hi}.json").write_text(json.dumps({"lo": lo, "hi": hi}))
    assert E.verified_up_to() == 3_000_000
    assert E.gaps(4, 7_000_000) == [(3_000_001, 5_000_000), (6_000_001, 7_000_000)]
    pl = E.plan(4, 7_000_000, 3)
    assert pl[0]["lo"] == 3_000_001 and pl[-1]["hi"] == 7_000_000
