"""Prove Hive can be copied out of the colony and tested on its own."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HIVE = REPO / "hive"


def test_hive_copied_alone_has_no_colony_and_its_tests_pass(tmp_path):
    dest_root = tmp_path / "extract"
    dest = dest_root / "hive"
    shutil.copytree(
        HIVE,
        dest,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".pytest_cache"),
    )
    assert dest.is_dir()
    assert (dest / "README.md").is_file()
    assert (dest / "pyproject.toml").is_file()
    assert (dest / "bitwork.py").is_file()
    assert (dest / "data" / "seeds.jsonl").is_file()
    # The extract must not include the colony, even as a leftover path.
    assert not (dest_root / "colony").exists()
    assert not (dest / "colony").exists()
    # And Hive's own sources must not import it.
    env = {**os.environ, "PYTHONPATH": str(dest_root), "PYTHONDONTWRITEBYTECODE": "1"}
    probe = subprocess.run(
        [
            sys.executable, "-c",
            "import hive, hive.bitwork, hive.ops, hive.library, hive.swarm, hive.host; "
            "import sys; "
            "hits = [k for k in sys.modules if k == 'colony' or k.startswith('colony.')]; "
            "assert hits == [], hits; "
            "print('hive', hive.__version__, 'ok')",
        ],
        cwd=dest_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode == 0, probe.stdout + "\n" + probe.stderr
    assert "0.1.0" in probe.stdout

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(dest / "tests"), "-q", "--tb=short"],
        cwd=dest_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr


def test_python_m_hive_runs_standalone(tmp_path):
    dest_root = tmp_path / "extract"
    shutil.copytree(
        HIVE,
        dest_root / "hive",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".pytest_cache"),
    )
    env = {**os.environ, "PYTHONPATH": str(dest_root), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        [sys.executable, "-m", "hive"],
        cwd=dest_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "Hive 0.1.0" in result.stdout
    assert "held-out replay" in result.stdout
    assert "ok" in result.stdout
    # Does not mention banned hype words.
    combined = (result.stdout + result.stderr).lower()
    for banned in ("breakthrough", "consciousness", "general intelligence", "agi"):
        assert banned not in combined
