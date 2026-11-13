"""Narrower confound fingerprint: docs, tests, and dashboard do not void a trial."""
from __future__ import annotations

from pathlib import Path

import colony.self_heal as SH


def test_include_behavior_path_excludes_docs_tests_dashboard():
    # Behavior-affecting: code and knob/cap config.
    assert SH.include_behavior_path("colony/self_heal.py") is True
    assert SH.include_behavior_path("colony/self_heal_defaults.json") is True
    assert SH.include_behavior_path("colony/oracle.py") is True
    assert SH.include_behavior_path("hive/swarm.py") is True
    assert SH.include_behavior_path("hive/bitwork.py") is True
    assert SH.include_behavior_path("hive/data/knob_specs.json") is True
    assert SH.include_behavior_path("hive/data/diagnosis_suggestions.json") is True
    # Docs.
    assert SH.include_behavior_path("hive/README.md") is False
    assert SH.include_behavior_path("colony/genomes_ALIGN_PATCH.md") is False
    assert SH.include_behavior_path("colony/docs/note.md") is False
    # Tests.
    assert SH.include_behavior_path("hive/tests/test_core.py") is False
    assert SH.include_behavior_path("hive/tests/conftest.py") is False
    assert SH.include_behavior_path("colony/test_helpers.py") is False
    # Dashboard and rendering.
    assert SH.include_behavior_path("colony/dashboard.py") is False
    assert SH.include_behavior_path("colony/plaque_render.py") is False
    assert SH.include_behavior_path("colony/chart.html") is False
    # Library JSONL and bytecode stay out, as before.
    assert SH.include_behavior_path("hive/data/seeds.jsonl") is False
    assert SH.include_behavior_path("colony/__pycache__/oracle.cpython-313.pyc") is False


def test_real_tree_omits_dashboard_and_tests_includes_knobs():
    files = SH.behavior_source_files()
    rels = {f"{label}/{rel}" for label, _path, rel in files}
    assert "colony/self_heal.py" in rels
    assert "colony/self_heal_defaults.json" in rels
    assert "colony/oracle.py" in rels
    assert "hive/swarm.py" in rels
    assert "hive/data/knob_specs.json" in rels
    assert "colony/dashboard.py" not in rels
    assert not any(r.startswith("hive/tests/") for r in rels)
    assert not any(r.endswith(".md") for r in rels)
    assert not any(r.endswith("conftest.py") for r in rels)


def _write_tree(root: Path) -> list[tuple[str, Path]]:
    colony = root / "colony"
    hive = root / "hive"
    (colony / "docs").mkdir(parents=True)
    (hive / "tests").mkdir(parents=True)
    (hive / "data").mkdir(parents=True)
    (colony / "self_heal.py").write_text("KNOB = 1\n", encoding="utf-8")
    (colony / "self_heal_defaults.json").write_text('{"fast_term_cap": 8000}\n', encoding="utf-8")
    (colony / "oracle.py").write_text("P = 0.70\n", encoding="utf-8")
    (colony / "dashboard.py").write_text("def refresh():\n    return 'chart'\n", encoding="utf-8")
    (colony / "docs" / "notes.md").write_text("# docs\n", encoding="utf-8")
    (hive / "swarm.py").write_text("ROLES = ()\n", encoding="utf-8")
    (hive / "data" / "knob_specs.json").write_text('{"park_cycles": {"default": 8}}\n', encoding="utf-8")
    (hive / "tests" / "test_core.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (hive / "README.md").write_text("# Hive\n", encoding="utf-8")
    return [("colony", colony), ("hive", hive)]


def test_digest_ignores_docs_tests_dashboard_and_notices_behavior_code(tmp_path):
    roots = _write_tree(tmp_path)
    before = SH.file_digest_for(roots)
    assert before

    # Docs, tests, and dashboard-only edits must not change the digest.
    (tmp_path / "colony" / "dashboard.py").write_text("def refresh():\n    return 'new chart'\n", encoding="utf-8")
    (tmp_path / "colony" / "docs" / "notes.md").write_text("# edited docs\n", encoding="utf-8")
    (tmp_path / "hive" / "README.md").write_text("# Hive, edited\n", encoding="utf-8")
    (tmp_path / "hive" / "tests" / "test_core.py").write_text("def test_ok():\n    assert 1 == 1\n", encoding="utf-8")
    after_noise = SH.file_digest_for(roots)
    assert after_noise == before

    # A knob/cap config change is a real confound.
    (tmp_path / "colony" / "self_heal_defaults.json").write_text('{"fast_term_cap": 16000}\n', encoding="utf-8")
    after_cap = SH.file_digest_for(roots)
    assert after_cap != before

    # A behavior-code change is a real confound.
    (tmp_path / "hive" / "swarm.py").write_text("ROLES = ('improver',)\n", encoding="utf-8")
    after_code = SH.file_digest_for(roots)
    assert after_code != after_cap
    assert after_code != before


def test_environment_fingerprint_still_moves_when_a_cap_knob_moves(tmp_path, monkeypatch):
    monkeypatch.setattr(SH, "STATE_PATH", tmp_path / "self_heal.json")
    monkeypatch.setattr(SH, "EVENT_LOG", tmp_path / "self_heal.jsonl")
    # Clear the process cache so this test does not depend on order.
    SH._CODE_FINGERPRINT_CACHE = None
    st = SH.load_state()
    before = SH.environment_fingerprint(exclude_knob="perturb_cooldown_cycles", state=st)
    st["knobs"]["fast_term_cap"] = 16000
    after = SH.environment_fingerprint(exclude_knob="perturb_cooldown_cycles", state=st)
    assert before["digest"] != after["digest"]
    assert before["code"] == after["code"]
    assert before["knobs"]["fast_term_cap"] != after["knobs"]["fast_term_cap"]
    # The digest still includes the narrowed code and tree parts.
    assert before["code"]
    assert "code" in before
    assert "tree" in before
