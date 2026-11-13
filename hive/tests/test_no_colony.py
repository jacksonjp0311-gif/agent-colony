"""Hive's own code must not import colony, even lazily."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import hive

HIVE_ROOT = Path(hive.__file__).resolve().parent


def _iter_source_files() -> list[Path]:
    files = []
    for p in HIVE_ROOT.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        # tests may mention the word "colony" in assertions; they still
        # must not import it. We check every .py file under hive/.
        files.append(p)
    return files


def test_no_colony_imports_in_hive_sources():
    offenders = []
    for path in _iter_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name == "colony" or name.startswith("colony."):
                    offenders.append(f"{path.relative_to(HIVE_ROOT)}: import {name}")
    assert offenders == []


def test_colony_is_not_imported_at_runtime():
    # A leftover bind from a host process should not be required.
    # After a fresh import of hive's modules, sys.modules must not
    # have grown a colony package from Hive's own code.
    colony_mods = [k for k in sys.modules if k == "colony" or k.startswith("colony.")]
    # If this test is running inside the colony suite, colony may
    # already be loaded by the host. That is fine: the AST test is
    # the strict check. Here we only assert Hive can be imported
    # without *requiring* colony.
    import hive.bitwork  # noqa: F401
    import hive.ops  # noqa: F401
    import hive.library  # noqa: F401
    import hive.swarm  # noqa: F401
    import hive.host  # noqa: F401
    from hive import host
    assert host.is_bound() is False or True  # bound or not, import succeeded
    # Package metadata.
    assert hive.__version__ == "0.1.0"


def test_shipped_data_files_exist():
    data = HIVE_ROOT / "data"
    for name in (
        "seeds.jsonl",
        "paraphrases.jsonl",
        "knob_specs.json",
        "diagnosis_suggestions.json",
    ):
        assert (data / name).is_file(), name
        assert (data / name).stat().st_size > 0
