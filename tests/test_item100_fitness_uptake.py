"""Item 100: fitness decomposition script + supply families get their authoring record."""
from __future__ import annotations

import json
from pathlib import Path

import colony.hard_tier_families as H
from colony import lessons as L

ROOT = Path(__file__).resolve().parents[1]


def _base(tmp_path):
    from tests.test_spark_hard_tier_families import _base_src
    p = tmp_path / "lemma_impl.py"
    p.write_text(_base_src(), encoding="utf-8")
    return p


def test_supply_writes_birth_record_and_keep_can_cite_it(tmp_path, monkeypatch):
    monkeypatch.delenv("COLONY_ARM", raising=False)
    monkeypatch.delenv("COLONY_SELF_MOD", raising=False)
    monkeypatch.delenv("COLONY_SUPPLY_BIRTH_RECORD", raising=False)
    les = tmp_path / "lessons.jsonl"
    monkeypatch.setattr(L, "LESSONS_JSONL", les)
    import colony.conjecture_mutations as CM
    monkeypatch.setattr(CM, "register_mutation_candidate", lambda *a, **k: None)
    row = H.build_next(_base(tmp_path), cycle_id="c_build")
    name = H.POOL[0][0]
    assert row["name"] == name and row["birth_record"] is True
    rows = [json.loads(x) for x in les.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["type"] == "authored_check" and rows[0]["mutation"] == name
    from colony.external_mind import lineage_lesson_ids
    assert lineage_lesson_ids(name, lessons=rows, exclude_cycle="c_keep") == [rows[0]["id"]]
    assert lineage_lesson_ids(name, lessons=rows, exclude_cycle="c_build") == []  # same cycle never cited


def test_kill_switch_and_control(tmp_path, monkeypatch):
    les = tmp_path / "lessons.jsonl"
    monkeypatch.setattr(L, "LESSONS_JSONL", les)
    monkeypatch.setenv("COLONY_SUPPLY_BIRTH_RECORD", "off")
    assert H._birth_record("oeis_x", (0, 5), "c") is None
    monkeypatch.delenv("COLONY_SUPPLY_BIRTH_RECORD", raising=False)
    monkeypatch.setenv("COLONY_ARM", "control")
    assert H._birth_record("oeis_x", (0, 5), "c") is None
    assert not les.exists()


def test_real_lesson_log_never_written_under_tests(monkeypatch):
    monkeypatch.delenv("COLONY_ARM", raising=False)
    monkeypatch.delenv("COLONY_SELF_MOD", raising=False)
    real = ROOT / "data" / "commons" / "lessons.jsonl"
    before = real.read_text() if real.exists() else ""
    H._birth_record("oeis_x", (0, 5), "c")  # goes to the per-test live-state copy, never the real log
    assert (real.read_text() if real.exists() else "") == before


def test_decomposition_ranks_biggest_drag(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("fd", ROOT / "scripts" / "item100_fitness_decomposition.py")
    fd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fd)
    t, c = tmp_path / "t.jsonl", tmp_path / "c.jsonl"
    base = {k: 0.8 for k in fd.WEIGHTS}
    t.write_text(json.dumps({**base, "lesson_uptake": 0.36, "novelty": 0.5, "aggregate": 0.8}) + "\n")
    c.write_text(json.dumps({**base, "lesson_uptake": 0.9, "novelty": 0.75, "aggregate": 0.83}) + "\n")
    monkeypatch.setattr(fd, "ARMS", {"treatment": t, "control": c})
    d = fd.decompose(5)
    assert d["biggest_drag"] == "lesson_uptake"
    assert d["terms"][0]["weighted_gap"] == round(0.05 * (0.36 - 0.9), 4)
    assert abs(sum(fd.WEIGHTS.values()) - 1.0) < 1e-9
