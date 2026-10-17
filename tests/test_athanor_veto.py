"""Per-area hard veto beside Athanor's verdict (COLONY_ATHANOR_VETO=off|shadow|live)."""
from __future__ import annotations

import json

import pytest

import colony.trust.athanor_gate as G
import colony.trust.athanor_probe as P
from test_athanor_probe import ADD_ONE, BASE, WIN, _snap


def _row(tmp_path, monkeypatch, after, *, veto=None, probe="state", before=None, tentative=True):
    monkeypatch.setenv("COLONY_ATHANOR_GATE", "live")
    monkeypatch.setenv("COLONY_ATHANOR_PROBE", probe)
    if veto is None:
        monkeypatch.delenv("COLONY_ATHANOR_VETO", raising=False)
    else:
        monkeypatch.setenv("COLONY_ATHANOR_VETO", veto)
    monkeypatch.setattr(G, "STATE", tmp_path / "s.json")
    monkeypatch.setattr(P, "oracle_windows", lambda *a, **k: WIN)
    b = before or _snap(BASE)
    return G.gate_desk_change(before=b, after=after, before_score=b["score"], after_score=after["score"],
                              mutation="authored_new", tentative_keep=tentative)


INFLATED = _snap(ADD_ONE, score=0.8665 + 0.05)          # one-area alarm: H7 alone approves it
SWAP = _snap({**{k: v for k, v in BASE.items() if not k.startswith("hard:authored_x")},
              **{f"hard:authored_x{i}": True for i in range(8, 100)},
              **{f"hard:authored_y{i}": True for i in range(8)}})


def test_one_area_alarms_pass_h7_but_are_vetoed_live(tmp_path, monkeypatch):
    for after in (INFLATED, SWAP):
        r = _row(tmp_path, monkeypatch, after, veto="live")
        assert r["state_verdict"] == "APPROVE"               # Athanor's math unchanged and recorded as is
        assert r["veto"]["vetoed"] and r["would_veto"] and r["block"]
        assert r["block_reason"].startswith("area veto:")


def test_veto_shadow_is_default_and_never_blocks(tmp_path, monkeypatch):
    r = _row(tmp_path, monkeypatch, INFLATED)
    assert r["veto"]["mode"] == "shadow" and r["would_veto"] and r["block"] is False
    tot = json.loads((tmp_path / "s.json").read_text())["totals"]
    assert tot["veto:shadow:would_veto_keep"] == 1 and "blocked_keep_live" not in tot


def test_veto_off_and_legacy_probe_restore_todays_gate(tmp_path, monkeypatch):
    r = _row(tmp_path, monkeypatch, INFLATED, veto="off")
    assert r["veto"] is None and r["block"] is False
    r = _row(tmp_path, monkeypatch, INFLATED, veto="live", probe="legacy")
    assert r["block"] is False and r["verdict"] == "APPROVE"


def test_clean_additive_change_not_vetoed(tmp_path, monkeypatch):
    r = _row(tmp_path, monkeypatch, _snap(ADD_ONE), veto="live")
    assert r["veto"]["vetoed"] is False and r["block"] is False


def test_veto_only_downgrades_keeps(tmp_path, monkeypatch):
    r = _row(tmp_path, monkeypatch, INFLATED, veto="live", tentative=False)
    assert r["veto"]["vetoed"] and r["would_veto"] is False and r["block"] is False


@pytest.mark.parametrize("sa,expect", [(0.3, False), (2.0, True)])
def test_runtime_veto_needs_relative_and_absolute_slowdown(sa, expect):
    cal = P.load_calibration()
    raw = {k: 0.0 for k in P.BLOCKS}
    import math
    raw["runtime"] = abs(math.log(sa / 0.06))
    assert raw["runtime"] > cal["veto"]["thresholds"]["runtime"]          # both are big relative jumps
    assert P.veto_check(raw, seconds_before=0.06, seconds_after=sa, calibration=cal)["vetoed"] is expect


def test_calibrated_veto_covers_integrity_areas_only():
    v = P.load_calibration()["veto"]
    assert set(v["thresholds"]) == set(P.VETO_AREAS)
    assert "novelty_mix" not in v["thresholds"] and "oracle_pattern" not in v["thresholds"]
    assert v["tuning"]["veto_rate_oracle_passed_keeps"] <= 0.10       # anti-freeze rule held on tuning


def test_workflow_runs_veto_live_with_state_probe():
    from pathlib import Path
    wf = (Path(__file__).resolve().parents[1] / ".github/workflows/colony-evolve.yml").read_text()
    assert "COLONY_ATHANOR_VETO: live" in wf and "COLONY_ATHANOR_PROBE: state" in wf
