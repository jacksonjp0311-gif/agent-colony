"""Item 98: the Athanor area veto is scoped to the bench it was calibrated on (no Athanor math change)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from colony.trust import athanor_veto_scope as S

ROOT = Path(__file__).resolve().parents[1]
STEM_RAW = {"checks_basic": 0.0, "checks_catalog": 0.5, "checks_authored": 0.0, "coverage": 0.035714,
            "score": 0.056515, "tier_ok": 0.0, "runtime": 0.0, "structure": 0.0, "novelty_mix": 0.0,
            "oracle_pattern": 0.05}
VETO = {"vetoed": True, "areas": ["score"], "thresholds": {"score": 0.015}, "mode": "live"}


def _sm(**kw):
    base = dict(kind="stem_enable", veto=VETO, raw=STEM_RAW, hard_pass_before=4, hard_pass_after=5,
                score_before=0.825, score_after=0.8688)
    base.update(kw)
    return S.structural_match(**base)


def test_one_added_stem_check_matches():
    assert _sm()["match"] is True


@pytest.mark.parametrize("kw,why", [
    (dict(kind="hard_enable"), "kind_not_stem_enable"),
    (dict(kind=""), "kind_not_stem_enable"),
    (dict(veto={**VETO, "areas": ["score", "runtime"]}), "areas_not_only_score"),
    (dict(veto={**VETO, "areas": ["checks_catalog"]}), "areas_not_only_score"),
    (dict(raw={**STEM_RAW, "checks_basic": 1.0}), "checks_basic_drift"),
    (dict(raw={**STEM_RAW, "checks_catalog": 1.0}), "not_exactly_one_added_check"),
    (dict(raw={**STEM_RAW, "tier_ok": 1.0}), "tier_ok_drift"),
    (dict(hard_pass_after=4), "hard_pass_not_plus_one"),
    (dict(hard_pass_after=6), "hard_pass_not_plus_one"),
    (dict(score_after=0.80), "score_fell"),
])
def test_anything_else_keeps_the_veto(kw, why):
    r = _sm(**kw)
    assert r["match"] is False and why in r["why_not"]


def test_off_on_control_arm(monkeypatch):
    monkeypatch.setenv("COLONY_ARM", "control")
    assert S.scope_mode() == "off"
    out = S.assess(kind="stem_enable", mutation="stem_rc_discharge", veto=VETO, raw=STEM_RAW,
                   before={"n_hard_pass": 4}, after={"n_hard_pass": 5}, score_before=0.825, score_after=0.8688)
    assert out["waive"] is False


def test_kill_switch(monkeypatch):
    monkeypatch.delenv("COLONY_ARM", raising=False)
    monkeypatch.setenv("COLONY_ATHANOR_VETO_SCOPE", "off")
    assert S.scope_mode() == "off"
    monkeypatch.setenv("COLONY_ATHANOR_VETO_SCOPE", "shadow")
    monkeypatch.setattr(S, "stem_quality", lambda m: {"ok": True, "why": "x"})
    out = S.assess(kind="stem_enable", mutation="m", veto=VETO, raw=STEM_RAW, before={"n_hard_pass": 4},
                   after={"n_hard_pass": 5}, score_before=0.825, score_after=0.8688)
    assert out["would_waive"] is True and out["waive"] is False


def test_tautology_never_waived(monkeypatch):
    monkeypatch.delenv("COLONY_ARM", raising=False)
    monkeypatch.setenv("COLONY_ATHANOR_VETO_SCOPE", "live")
    monkeypatch.setattr(S, "stem_quality", lambda m: {"ok": False, "why": "trivial_or_unknown:stem_symbolic_tautology"})
    out = S.assess(kind="stem_enable", mutation="stem_elastic_collision", veto=VETO, raw=STEM_RAW,
                   before={"n_hard_pass": 4}, after={"n_hard_pass": 5}, score_before=0.825, score_after=0.8688)
    assert out["waive"] is False


def test_gate_waives_only_the_scoped_veto(monkeypatch, tmp_path):
    from colony.trust import athanor_gate as G
    monkeypatch.setattr(G, "STATE", tmp_path / "athanor_gate.json")
    monkeypatch.setenv("COLONY_ATHANOR_GATE", "live")
    monkeypatch.delenv("COLONY_ARM", raising=False)
    fake = {"verdict": "APPROVE", "reason": "ok", "gate_profile": "p", "validity": {"passed": True, "failures": []},
            "profiles": {}, "probe": "state", "state_drift_raw": STEM_RAW, "veto": VETO, "e_cur": 0.1,
            "e_best": 0.1, "step": 0}
    monkeypatch.setattr(G, "assess_change", lambda **kw: dict(fake))
    calls = []

    def fake_assess(**kw):
        calls.append(kw["kind"])
        return {"mode": "live", "waive": kw["kind"] == "stem_enable"}
    monkeypatch.setattr("colony.trust.athanor_veto_scope.assess", fake_assess)
    stem = G.gate_desk_change(before={}, after={}, kind="stem_enable", mutation="stem_rc_discharge",
                              tentative_keep=True)
    assert stem["block"] is False and stem["veto_scoped_out"] is True
    hard = G.gate_desk_change(before={}, after={}, kind="hard_enable", mutation="x", tentative_keep=True)
    assert hard["block"] is True and "area veto" in hard["block_reason"]


def test_calibration_file_untouched():
    cal = json.loads((ROOT / "colony/trust/athanor_probe_calibration.json").read_text(encoding="utf-8"))
    assert cal["veto"]["thresholds"]["score"] == 0.015
