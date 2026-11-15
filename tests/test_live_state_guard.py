"""Item 71: the trust-gate suite must not depend on live mutable run state.

CI data commits rewrite data/, society/ and control/ every cycle. Twice
(items 69 and 71) a test that read that state went red on drift alone and
stopped the FATAL pre-evolve trust gate. tests/conftest.py now refuses those
reads during every test body; these tests prove the guard is on and that the
grandfathered list can only shrink.
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"

# Ratchet: may only go DOWN. Lower it when a grandfathered test is pinned.
GRANDFATHER_CEILING = 9


_GUARD_MOD: list = []


@pytest.fixture(autouse=True)
def _find_guard_module(request):
    # Look the conftest up through pytest's plugin manager by file: with
    # `pytest tests hive/tests` hive's conftest owns the bare module name.
    if not _GUARD_MOD:
        want = (TESTS / "conftest.py").resolve()
        for plugin in request.config.pluginmanager.get_plugins():
            f = getattr(plugin, "__file__", None)
            if f and Path(f).resolve() == want and hasattr(plugin, "LIVE_STATE_GUARD_MODE"):
                _GUARD_MOD.append(plugin)
                break


def _conftest():
    if not _GUARD_MOD:
        raise AssertionError("tests/conftest.py guard not loaded")
    return _GUARD_MOD[0]


def _live_file() -> Path:
    for rel in ("society/systems/self_heal.json", "society/systems/oeis_conjecture_state.json",
                "data/commons/oracle.jsonl"):
        p = ROOT / rel
        try:
            os.stat(p)  # stat is not a read and is not hidden
        except OSError:
            continue
        return p
    pytest.skip("no live run-state file in this checkout")


def test_guard_is_blocking_by_default():
    if os.environ.get("COLONY_LIVE_STATE_GUARD"):
        pytest.skip("guard mode overridden for an audit run")
    assert _conftest().LIVE_STATE_GUARD_MODE == "block"


def test_reading_live_run_state_is_refused():
    if _conftest().LIVE_STATE_GUARD_MODE != "block":
        pytest.skip("guard mode overridden for an audit run")
    p = _live_file()
    assert p.exists() is False and os.path.exists(p) is False
    with pytest.raises(FileNotFoundError):
        p.read_text(encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        open(p, "rb").close()


def test_code_static_data_and_own_writes_stay_readable(tmp_path):
    assert (ROOT / "society" / "benchmarks" / "run_benchmarks.py").read_text(encoding="utf-8")
    static = sorted(_conftest().STATIC_DATA)
    assert static, "static data list must not be empty"
    first = next((ROOT / s for s in static if (ROOT / s).is_file()), None)
    if first is not None:
        first.read_bytes()
    own = tmp_path / "x.json"
    own.write_text("{}", encoding="utf-8")
    assert own.read_text(encoding="utf-8") == "{}"


def test_module_constants_point_away_from_live_data():
    import colony.oeis_conjectures as OC
    import colony.frontier as FR
    for path in (OC.STATE, OC.MENU, FR.CATALOG, FR.LOG):
        rel = _conftest().is_live_state_path(path)
        assert not rel, f"{path} still names live data during a test"


def test_pinned_frontier_catalog_is_seeded():
    import colony.frontier as FR
    assert FR.CATALOG.is_file()
    assert "targets" in FR.CATALOG.read_text(encoding="utf-8")


def _grandfathered() -> list[str]:
    lines = (TESTS / "live_state_grandfathered.txt").read_text(encoding="utf-8").splitlines()
    return [x.strip() for x in lines if x.strip() and not x.lstrip().startswith("#")]


def test_grandfathered_list_only_shrinks_and_names_real_tests():
    items = _grandfathered()
    assert len(items) == len(set(items)), "duplicate grandfathered entries"
    assert len(items) <= GRANDFATHER_CEILING, (
        "the live-state grandfather list may only shrink; pin a fixture instead"
    )
    for nodeid in items:
        file_part, _, name = nodeid.partition("::")
        func = name.split("[", 1)[0]
        src = (ROOT / file_part).read_text(encoding="utf-8")
        names = {n.name for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef)}
        assert func in names, f"stale grandfathered entry {nodeid}"


@pytest.mark.parametrize("nodeid", [
    "tests/test_baseline_exclude_knob.py::test_start_knob_trial_opens_after_just_closed_cooldown_trial",
    "tests/test_target_generator.py::test_pinned_registry_can_verify_one_mutation",
])
def test_previous_drift_failures_are_not_grandfathered(nodeid):
    assert nodeid not in _grandfathered()
