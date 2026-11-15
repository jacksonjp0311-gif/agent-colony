"""Item 69: non-fatal generator_supply_exhausted metric and the wider-offset retry.

The FATAL trust gate went red when live run state (the production lemma at
the 150 cap) made the live-registry supply test fail. The supply test now runs
on a pinned snapshot (tests/test_target_generator.py); these tests cover the
health metric and the generator's reaction. Nothing here loosens the
triviality filter, the prefilter, verify_candidate, or the 150 / per-cycle caps.
"""
from __future__ import annotations

import json

import pytest

from colony import target_generator as TG
from colony import authoring as AU
from colony import self_heal as SH

from tests.test_target_generator import _isolate, _claim


def _filters_pass(monkeypatch, calls=None):
    def triv(row):
        if calls is not None:
            calls.append(dict(row))
        return ""
    monkeypatch.setattr(TG, "is_trivial", triv)
    monkeypatch.setattr(TG, "prefilter_holds", lambda *a, **k: True)


def _cong(m=7, r=0):
    return {**_claim("cong", "alpha", "", {"m": m, "q": 1, "r": r, "s": 0}), "sig": f"s{m}"}


def _log_rows(log):
    if not log.exists():
        return []
    return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()]


# --- wider offsets: same kinds, new constants only ----------------------------

def test_wide_perturb_yields_only_wider_offsets():
    base = {g["params"]["m"] for g in TG.apply_mutation(_cong(7), "perturb_constant")}
    wide = {g["params"]["m"] for g in TG.apply_mutation(_cong(7), "perturb_constant", wide=True)}
    assert base == {8, 9, 6, 10}
    assert wide == {11, 12, 5, 13}
    assert not (base & wide)


def test_wide_perturb_keeps_residue_below_modulus_and_m_at_least_two():
    got = TG.apply_mutation(_cong(3, r=2), "perturb_constant", wide=True)
    ms = {g["params"]["m"] for g in got}
    assert 1 not in ms  # 3-2 = 1 is not a modulus
    assert all(g["params"]["r"] < g["params"]["m"] for g in got)


def test_wide_rec_steps_by_two():
    rec = _claim("rec", "alpha", "", {"c": [1, 0]})
    got = [g["params"]["c"] for g in TG.apply_mutation(rec, "perturb_constant", wide=True)]
    assert got == [[3, 0], [-1, 0], [1, 2], [1, -2]]


@pytest.mark.parametrize("kind", [k for k in TG.MUTATION_KINDS if k not in TG.WIDE_KINDS])
def test_wide_is_empty_for_other_kinds(kind):
    assert TG.apply_mutation(_claim("le", "alpha", "beta"), kind, wide=True) == []


def test_enumerate_wide_marks_rows_and_uses_known_kinds():
    rows = TG.enumerate_mutations([_cong(7), _claim("le", "alpha", "beta")], wide=True)
    assert rows and all(r["wide"] is True for r in rows)
    assert {r["mut_kind"] for r in rows} == {"perturb_constant"}
    assert set(TG.WIDE_KINDS) <= set(TG.MUTATION_KINDS)
    assert not any(r.get("wide") for r in TG.enumerate_mutations([_cong(7)]))


# --- the metric and the reaction ----------------------------------------------

def test_exhausted_flag_and_append_only_log_when_nothing_verifies(tmp_path, monkeypatch):
    lemma, log = _isolate(tmp_path, monkeypatch)
    log.write_text(json.dumps({"event": "authored", "name": "authored_mut_prior", "key": "k0"}) + "\n", encoding="utf-8")
    prior = log.read_text(encoding="utf-8")
    _filters_pass(monkeypatch)
    seen = []

    def reject(_src, name, _c):
        seen.append(name)
        return {"accepted": False, "reason": "does_not_hold_on_new_window"}

    rows = TG.author_targets(max_new=1, cycle_id="c69", claims=[_cong(7)], verify=reject)
    assert rows == []
    sup = TG.last_supply()
    assert sup["generator_supply_exhausted"] is True
    assert sup["reason"] == "supply_exhausted"
    assert sup["widened"] is True
    assert sup["tried"] >= 1 and sup["wide_tried"] >= 1
    assert sup["wide_tried"] <= TG.WIDE_MAX_VERIFY
    text = log.read_text(encoding="utf-8")
    assert text.startswith(prior), "generator log is append-only"
    ev = [r for r in _log_rows(log) if r.get("event") == "supply_exhausted"]
    assert len(ev) == 1 and ev[0]["cycle_id"] == "c69"
    assert "name" not in ev[0] and "key" not in ev[0]  # never pollutes dedupe state


def test_wide_pass_authors_when_default_pass_is_exhausted(tmp_path, monkeypatch):
    lemma, log = _isolate(tmp_path, monkeypatch)
    calls = []
    _filters_pass(monkeypatch, calls)
    wide_ms = {7 + d for d in TG.WIDE_CONG_STEPS}

    def only_wide(src, name, _c):
        ok = any(f"'m': {m}," in src.split(f"def check_{name}")[1].split("\n\n")[0] for m in wide_ms)
        return {"accepted": ok, "reason": "verified" if ok else "does_not_hold_on_new_window", "seconds": 0.01}

    rows = TG.author_targets(max_new=1, cycle_id="c69w", claims=[_cong(7)], verify=only_wide)
    assert len(rows) == 1
    assert rows[0]["wide"] is True and rows[0]["mut_kind"] == "perturb_constant"
    assert rows[0]["claim"]["params"]["m"] in wide_ms
    assert rows[0]["name"] in lemma.read_text(encoding="utf-8")
    sup = TG.last_supply()
    assert sup["generator_supply_exhausted"] is False and sup["wide_accepted"] == 1
    # Wide candidates went through the same triviality filter.
    assert any(c.get("wide") for c in calls)
    assert not [r for r in _log_rows(log) if r.get("event") == "supply_exhausted"]


def test_wide_pass_respects_triviality_filter(tmp_path, monkeypatch):
    lemma, log = _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(TG, "is_trivial", lambda row: "case_split" if row.get("wide") else "")
    monkeypatch.setattr(TG, "prefilter_holds", lambda *a, **k: True)
    verified = []

    def rec(_src, name, _c):
        verified.append(name)
        return {"accepted": False, "reason": "x"}

    TG.author_targets(max_new=1, claims=[_cong(7)], verify=rec)
    assert TG.last_supply()["wide_tried"] == 0
    assert TG.last_supply()["generator_supply_exhausted"] is True


def test_default_success_does_not_widen(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _filters_pass(monkeypatch)
    monkeypatch.setattr(TG, "enumerate_mutations", _no_wide(TG.enumerate_mutations))
    rows = TG.author_targets(max_new=1, claims=[_cong(7)],
                             verify=lambda *a: {"accepted": True, "reason": "verified", "seconds": 0.01})
    assert rows and rows[0]["wide"] is False
    sup = TG.last_supply()
    assert sup == {**sup, "generator_supply_exhausted": False, "widened": False, "wide_tried": 0}


def _no_wide(orig):
    def f(claims=None, *, wide=False):
        if wide:
            pytest.fail("wide pass must not run after a default-pass success")
        return orig(claims)
    return f


def test_control_arm_never_widens_or_logs(tmp_path, monkeypatch):
    lemma, log = _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(TG, "self_mod_ok", lambda: False)
    monkeypatch.setattr(TG, "enumerate_mutations", lambda *a, **k: pytest.fail("control enumerated"))
    assert TG.author_targets(max_new=1, claims=[_cong(7)]) == []
    assert TG.last_supply() == {"reason": "control", "generator_supply_exhausted": False}
    assert not log.exists()


def test_at_cap_is_not_supply_exhaustion(tmp_path, monkeypatch):
    lemma, log = _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(AU, "authored_count", lambda: AU.MAX_AUTHORED_TOTAL)
    monkeypatch.setattr(TG, "enumerate_mutations", lambda *a, **k: pytest.fail("enumerated at cap"))
    assert AU.MAX_AUTHORED_TOTAL == 150  # the cap is unchanged
    assert TG.author_targets(max_new=1, claims=[_cong(7)]) == []
    sup = TG.last_supply()
    assert sup["reason"] == "at_authored_cap" and sup["generator_supply_exhausted"] is False
    assert sup["n"] == 150 and sup["cap"] == 150
    assert not log.exists()


def test_self_heal_supply_reports_generator_metric(monkeypatch):
    kind = sorted(SH.SUPPLY_FINDINGS)[0]
    monkeypatch.setattr(AU, "authored_count", lambda: 10)
    monkeypatch.setattr(AU, "author_checks", lambda **k: [])

    def fake_author_targets(**_k):
        TG._LAST_SUPPLY.clear()
        TG._LAST_SUPPLY.update({"reason": "supply_exhausted", "generator_supply_exhausted": True})
        return []

    monkeypatch.setattr(TG, "author_targets", fake_author_targets)
    out = SH.maybe_supply_oracle_targets("c69", findings=[{"kind": kind}])
    assert out["generator_supply"]["generator_supply_exhausted"] is True
    assert out["authored"] == []
