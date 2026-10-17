"""State-vector probe for the Athanor gate: measures real drift; legacy flag restores today's gate."""
from __future__ import annotations

import json
import math

import pytest

import colony.trust.athanor_gate as G
import colony.trust.athanor_probe as P
from colony.athanor_coherence import ADAPTIVE_PROFILES, CONSERVATIVE_PROFILE
from test_athanor_gate_live import CALM, _run
from test_challenger import art, sandbox  # noqa: F401


def _snap(checks, score=0.8665, ok=True, seconds=0.75):
    hard = [k for k in checks if k.startswith("hard:")]
    return {"checks": dict(checks), "score": score, "ok": ok, "basic_ok": ok, "hard_ok": ok and bool(hard),
            "seconds": seconds}


BASE = {**{f"basic:b{i}": True for i in range(10)}, **{f"hard:cat{i}": True for i in range(40)},
        **{f"hard:authored_x{i}": True for i in range(100)}}
ADD_ONE = {**BASE, "hard:authored_new": True}
WIN = ([True] * 19 + [False], [True] * 20)


def _judge(after, before=BASE, *, s_after=None, oracle=WIN, src="", new_src=""):
    b, a = _snap(before), s_after or _snap(after)
    return G.assess_change(before=b, after=a, before_score=b["score"], after_score=a["score"],
                           src=src, new_src=new_src, oracle=oracle, probe="state", best_e=0.134, step=500)


def test_clean_additive_check_is_small_nonzero_drift_and_approved():
    a = _judge(ADD_ONE)
    raw = a["state_drift_raw"]
    assert raw["checks_authored"] == pytest.approx(0.5)   # one added check = half a bit (absent = 0.5)
    assert raw["coverage"] == pytest.approx(1 / 28, abs=1e-6)
    assert sum(raw.values()) > 0                          # legacy probe: dPhi == 0 for this change
    assert a["legacy_verdict"] == "APPROVE" and a["state_verdict"] == "APPROVE"
    assert max(a["state_dphi"].values()) > 0


def test_perturbing_change_shows_real_drift_and_is_rejected_by_state_not_legacy():
    flipped = {**ADD_ONE, **{f"hard:cat{i}": False for i in range(6)}}
    a = _judge(flipped, s_after=_snap(flipped, score=0.0, ok=False))
    assert a["state_verdict"] != "APPROVE"
    assert a["legacy_verdict"] == "APPROVE"        # the legacy per-check probe dilutes 6 flips over 151 probes
    assert a["state_drift_raw"]["checks_catalog"] == pytest.approx(math.sqrt(6))


def test_bulk_change_is_not_approved_by_state_probe():
    bulk = {**BASE, **{f"hard:cat_new{i}": True for i in range(12)}, "hard:authored_new": True}
    assert _judge(bulk)["state_verdict"] != "APPROVE"


def test_math_is_unchanged_C_and_H7():
    a = _judge(ADD_ONE)
    sp = a["state_profiles"][CONSERVATIVE_PROFILE]
    tol = sp["tol"]
    d = [v / tol for v in a["state_dphi"].values()]
    c = [1 / (1 + x) for x in d]
    tau = ADAPTIVE_PROFILES[CONSERVATIVE_PROFILE]["threshold_h7"]
    assert sp["h7"] == pytest.approx(sum(x >= tau for x in c) / len(c), abs=1e-6)


def test_oracle_window_includes_only_this_changes_own_verdict():
    rows = [{"mutation": "m0", "passed": False}] + [{"mutation": f"m{i}", "passed": True} for i in range(1, 21)]
    b, a = P.oracle_windows("m20", rows)
    assert len(b) == 20 and len(a) == 20 and a[-1] is True and b[0] is False
    b2, a2 = P.oracle_windows("other", rows)
    assert b2 == a2


def test_calibration_file_covers_every_probe_and_follows_the_rule():
    cal = P.load_calibration()
    assert cal["version"] >= 1 and set(cal["scales"]) == set(P.BLOCKS)
    lim = P.coherent_limit(cal["threshold_h7"])
    for k, sc in cal["scales"].items():
        assert sc * lim * cal["tolerance_floor"] >= P.UNITS[k] * (1 - 1e-9)
    drifts = [{k: float(i) for k in P.BLOCKS} for i in range(1, 11)]
    sc = P.scales_from(drifts, 0.9, tol=0.7, threshold=0.75)
    assert sc["score"] * P.coherent_limit(0.75) * 0.7 == pytest.approx(9.0, rel=1e-5)   # 0.9-quantile on the line


def test_missing_calibration_falls_back_to_units(tmp_path):
    cal = P.load_calibration(tmp_path / "nope.json")
    assert cal["version"] == 0 and set(cal["scales"]) == set(P.BLOCKS)


def test_probe_flag_defaults_to_legacy(monkeypatch):
    monkeypatch.delenv("COLONY_ATHANOR_PROBE", raising=False)
    assert P.probe_mode() == "legacy"
    monkeypatch.setenv("COLONY_ATHANOR_PROBE", "state")
    assert P.probe_mode() == "state"
    monkeypatch.setenv("COLONY_ATHANOR_PROBE", "bogus")
    assert P.probe_mode() == "legacy"


def test_state_probe_error_falls_back_to_legacy_never_blocks(monkeypatch):
    monkeypatch.setattr(P, "state_probe", lambda *a, **k: 1 / 0)
    b = _snap(BASE)
    a = G.assess_change(before=b, after=_snap(ADD_ONE), probe="state", best_e=0.134, step=500)
    assert a["probe"] == "legacy" and a["verdict"] == "APPROVE" and a["state_error"]


# --- through the real desk: live gate + probe flag -------------------------------------------------
PERTURB = {**{f"c{i}": True for i in range(10)}, "odd_sum": True,
           **{f"extra{i}": True for i in range(12)}}   # bulk: 13 checks appear in one edit


@pytest.fixture()
def quiet_oracle_log(tmp_path, monkeypatch):
    p = tmp_path / "oracle.jsonl"
    p.write_text("".join(json.dumps({"mutation": f"m{i}", "passed": True}) + "\n" for i in range(20)))
    monkeypatch.setattr(P, "ORACLE_LOG", p)


def test_state_probe_live_blocks_perturbing_keep(sandbox, tmp_path, monkeypatch, quiet_oracle_log):
    monkeypatch.setenv("COLONY_ATHANOR_PROBE", "state")
    r, impl, calls, verdict, _ = _run(monkeypatch, sandbox, tmp_path, "live", PERTURB)
    assert r.decision == "revert" and "athanor_gate=BLOCK" in r.note
    assert verdict.passed is True and len(calls) == 1          # Oracle untouched
    row = json.loads((tmp_path / "s_live.json").read_text())["rows"][-1]
    assert row["probe"] == "state" and row["would_block_by_probe"] == {"legacy": False, "state": True}


@pytest.mark.parametrize("flag", [None, "legacy"])
def test_legacy_flag_restores_todays_gate(sandbox, tmp_path, monkeypatch, quiet_oracle_log, flag):
    if flag is None:
        monkeypatch.delenv("COLONY_ATHANOR_PROBE", raising=False)
    else:
        monkeypatch.setenv("COLONY_ATHANOR_PROBE", flag)
    r, impl, *_ = _run(monkeypatch, sandbox, tmp_path, "live", PERTURB)
    assert r.decision == "keep" and "athanor_gate" not in r.note   # legacy verdict decides: APPROVE
    row = json.loads((tmp_path / "s_live.json").read_text())["rows"][-1]
    assert row["probe"] == "legacy" and row["state_verdict"] != "APPROVE"   # state still logged in shadow


def test_state_probe_live_keeps_clean_change(sandbox, tmp_path, monkeypatch, quiet_oracle_log):
    monkeypatch.setenv("COLONY_ATHANOR_PROBE", "state")
    r, *_ = _run(monkeypatch, sandbox, tmp_path, "live", CALM)
    assert r.decision == "keep" and "athanor_gate" not in r.note


def test_gate_only_turns_keep_into_revert(tmp_path, monkeypatch):
    monkeypatch.setenv("COLONY_ATHANOR_GATE", "live")
    monkeypatch.setenv("COLONY_ATHANOR_PROBE", "state")
    monkeypatch.setattr(G, "STATE", tmp_path / "s.json")
    flipped = {**ADD_ONE, **{f"hard:cat{i}": False for i in range(6)}}
    row = G.gate_desk_change(before=_snap(BASE), after=_snap(flipped, score=0.0, ok=False), tentative_keep=False)
    assert row["state_verdict"] != "APPROVE" and row["block"] is False and row["would_block"] is False
