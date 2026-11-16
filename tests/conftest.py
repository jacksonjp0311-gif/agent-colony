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
    import colony.failure_modes as FM  # item 89
    monkeypatch.setattr(FM, "LOG", tmp_path / "self_change_failures.jsonl")



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


# --- Item 71: live mutable run-state guard ------------------------------------
# CI data commits ("ci(colony): ...") rewrite files under data/, society/ and
# control/ every cycle. A test whose outcome depends on those files can turn
# red on data drift alone and stop the FATAL pre-evolve trust gate (items 69
# and 71). During every test body, reads of run-state DATA files under those
# trees are refused (FileNotFoundError), so any dependence shows up at once on
# the PR that adds it, never later through drift. Python sources are code and
# stay readable (imports, ast reads; colony-mutated artifacts are covered by
# the bench gates). Writes are unchanged (the session fixture above restores
# them), and a test may read back a file it wrote itself.
#
# Tests listed in tests/live_state_grandfathered.txt predate the guard and
# still read live data; tests/test_live_state_guard.py caps that list so it
# can only shrink. COLONY_LIVE_STATE_GUARD=audit records without refusing;
# COLONY_LIVE_READ_AUDIT=path writes the per-test read map at session end.
import os as _os
import sys as _sys

LIVE_STATE_ROOTS = tuple(str(ROOT / d) + _os.sep for d in ("data", "society", "control"))
GRANDFATHER_FILE = Path(__file__).resolve().parent / "live_state_grandfathered.txt"
STATIC_FILE = Path(__file__).resolve().parent / "live_state_static.txt"
# Pinned copies of live files (same relative path), seeded into the
# redirected location of a module constant that names them.
PINNED_DIR = Path(__file__).resolve().parent / "fixtures" / "live_state"
LIVE_STATE_GUARD_MODE = (_os.environ.get("COLONY_LIVE_STATE_GUARD") or "block").strip().lower()


def _load_list(path: Path) -> frozenset:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return frozenset()
    return frozenset(x.strip() for x in lines if x.strip() and not x.lstrip().startswith("#"))


GRANDFATHERED = _load_list(GRANDFATHER_FILE)
STATIC_DATA = _load_list(STATIC_FILE)
LIVE_READS: dict = {}
LIVE_REFUSED: dict = {}
_GUARD = {"nodeid": None, "allowed": False, "written": set()}


def guard_key(item) -> str:
    """Stable id ``tests/<file>.py::<name>`` independent of how pytest was invoked."""
    try:
        rel = Path(str(item.path)).resolve().relative_to(ROOT).as_posix()
    except Exception:
        return str(getattr(item, "nodeid", ""))
    return f"{rel}::{item.name}"


def is_live_state_path(path) -> str:
    """Repo-relative path if ``path`` is guarded live run-state data, else ''."""
    try:
        p = _os.path.abspath(_os.fsdecode(path))
    except Exception:
        return ""
    if not p.startswith(LIVE_STATE_ROOTS) or "__pycache__" in p or p.endswith((".py", ".pyc")):
        return ""
    rel = p[len(str(ROOT)) + 1:]
    return "" if rel in STATIC_DATA else rel


def _is_write(mode, flags) -> bool:
    if isinstance(mode, str) and any(c in mode for c in "wax+"):
        return True
    if isinstance(flags, int) and flags & (_os.O_WRONLY | _os.O_RDWR | _os.O_CREAT | _os.O_APPEND):
        return True
    return False


def _live_state_hook(event, args):
    if event != "open":
        return
    nodeid = _GUARD["nodeid"]
    if nodeid is None or LIVE_STATE_GUARD_MODE == "off":
        return
    path, mode, flags = args
    if path is None or isinstance(path, int):
        return
    rel = is_live_state_path(path)
    if not rel:
        return
    if _is_write(mode, flags):
        _GUARD["written"].add(rel)
        return
    if rel in _GUARD["written"]:
        return
    LIVE_READS.setdefault(nodeid, set()).add(rel)
    if LIVE_STATE_GUARD_MODE == "block" and not _GUARD["allowed"]:
        LIVE_REFUSED.setdefault(nodeid, set()).add(rel)
        raise FileNotFoundError(
            2, "live mutable run state is not readable in tests (item 71); pin a fixture", _os.fsdecode(path),
        )


_sys.addaudithook(_live_state_hook)


def _import_colony_modules() -> None:
    """Load colony/ and hive/ modules once so their path constants can be redirected."""
    import importlib
    import pkgutil
    for pkg_name in ("colony", "hive"):
        try:
            pkg = importlib.import_module(pkg_name)
        except Exception:
            continue
        for info in pkgutil.walk_packages(pkg.__path__, prefix=pkg_name + "."):
            if info.name.endswith(("__main__", ".cli")):
                continue
            try:
                importlib.import_module(info.name)
            except Exception:
                continue


_import_colony_modules()


def _live_path_constants():
    """(module, attribute, repo-relative path) for every module-level Path into live data."""
    out = []
    for name, mod in list(_sys.modules.items()):
        if not name.startswith(("colony", "hive")) or mod is None:
            continue
        for attr, val in list(vars(mod).items()):
            if isinstance(val, Path):
                rel = is_live_state_path(val)
                if rel and rel != "." and (ROOT / rel).suffix:
                    out.append((mod, attr, rel))
    return out


_LIVE_CONSTANTS = _live_path_constants()


@pytest.fixture(autouse=True)
def _isolate_live_state_constants(request, tmp_path, monkeypatch):
    """Item 71: point module-level live-data paths at an empty per-test tree.

    Same idea as the stall / self-heal / Hive isolation above, applied to
    every module constant that names a run-state data file. A pinned copy
    under tests/fixtures/live_state/ (same relative path) seeds the
    redirected file. Grandfathered tests keep the live paths. A test that
    needs other data creates it under the redirected path.
    """
    if guard_key(request.node) in GRANDFATHERED or LIVE_STATE_GUARD_MODE == "off":
        return
    import shutil
    base = tmp_path / "_live_state"
    for mod, attr, rel in _LIVE_CONSTANTS:
        if getattr(mod, attr, None) == ROOT / rel:
            dst = base / rel
            pinned = PINNED_DIR / rel
            if pinned.is_file() and not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(pinned, dst)
            monkeypatch.setattr(mod, attr, dst)
    # Live run-state data is invisible, not half-visible: exists()/is_file()
    # say False during the test body, so code takes its "no file" path
    # instead of passing exists() and then failing the read.
    import pathlib
    real_exists, real_is_file = pathlib.Path.exists, pathlib.Path.is_file
    real_os_exists, real_os_isfile = _os.path.exists, _os.path.isfile

    def _hidden(p) -> bool:
        if _GUARD["nodeid"] is None or _GUARD["allowed"] or LIVE_STATE_GUARD_MODE != "block":
            return False
        rel = is_live_state_path(p)
        return bool(rel) and rel not in _GUARD["written"]

    def exists(self, *a, **k):
        return False if _hidden(self) else real_exists(self, *a, **k)

    def is_file(self, *a, **k):
        return False if _hidden(self) else real_is_file(self, *a, **k)

    def os_exists(p):
        return False if _hidden(p) else real_os_exists(p)

    def os_isfile(p):
        return False if _hidden(p) else real_os_isfile(p)

    monkeypatch.setattr(pathlib.Path, "exists", exists)
    monkeypatch.setattr(pathlib.Path, "is_file", is_file)
    monkeypatch.setattr(_os.path, "exists", os_exists)
    monkeypatch.setattr(_os.path, "isfile", os_isfile)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    _GUARD["nodeid"] = guard_key(item)
    _GUARD["allowed"] = _GUARD["nodeid"] in GRANDFATHERED
    _GUARD["written"] = set()
    try:
        yield
    finally:
        _GUARD["nodeid"] = None
        _GUARD["allowed"] = False
        _GUARD["written"] = set()


def pytest_sessionfinish(session, exitstatus):
    out = _os.environ.get("COLONY_LIVE_READ_AUDIT")
    if out:
        import json as _json
        Path(out).write_text(_json.dumps({
            "reads": {k: sorted(v) for k, v in sorted(LIVE_READS.items())},
            "refused": {k: sorted(v) for k, v in sorted(LIVE_REFUSED.items())},
        }, indent=1), encoding="utf-8")
