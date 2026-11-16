"""Item 96: the Oracle pre-screen drops tautological stem_enables (the novelty gate's own trivial kill)."""
from __future__ import annotations

import pytest

import colony.conjecture_desk as D
import colony.lessons as L
import colony.oracle_prescreen as P
import colony.stall as S


@pytest.fixture
def treatment(monkeypatch):
    monkeypatch.delenv("COLONY_ARM", raising=False)
    monkeypatch.delenv("COLONY_SELF_MOD", raising=False)
    monkeypatch.delenv("COLONY_ORACLE_PRESCREEN", raising=False)
    logged: list = []
    monkeypatch.setattr(P, "_append", lambda row: logged.append(row))
    monkeypatch.setattr(P, "_lesson", lambda drop, text: logged.append(("lesson", drop["mutation"])))
    return logged


@pytest.mark.parametrize("name", ["stem_elastic_collision", "stem_kepler_third_law", "stem_thin_lens_matrix"])
def test_tautology_dropped(treatment, name):
    d = P.check(name, "stem_enable")
    assert d and d["would_kill"] == "trivial:stem_symbolic_tautology"


@pytest.mark.parametrize("name", ["stem_isothermal_work", "stem_snell_least_time", "stem_rc_discharge",
                                  "stem_wheatstone_balance", "stem_not_a_check"])
def test_non_trivial_or_unknown_never_dropped(treatment, name):
    assert P.check(name, "stem_enable") is None


def test_only_drops_what_the_gate_kills_as_trivial(treatment):
    from colony.novelty_gate import stem_triviality_kill
    from colony.stem_held_out import HELD_OUT_GRIDS
    for name in HELD_OUT_GRIDS:
        t = stem_triviality_kill(name, "stem_enable")
        assert (P.check(name, "stem_enable") is not None) == bool(t and t.get("trivial")), name


def test_other_kinds_unchanged(treatment):
    # other stem kinds and hard_enable are still never screened
    for kind in ("stem_check", "stem_easy_pad", "hard_enable", "hard_check", "easy_pad", ""):
        assert P.check("stem_elastic_collision", kind) is None


def test_control_arm_off(monkeypatch):
    monkeypatch.setenv("COLONY_SELF_MOD", "off")
    assert P.mode() == "off"
    assert P.stem_trivial_drop("stem_elastic_collision", "stem_enable") is None
    assert P.screen("stem_elastic_collision", "stem_enable") is None


def test_desk_pick_skips_tautology_and_takes_next(treatment, monkeypatch):
    monkeypatch.setattr(S, "load_oracle_rows", lambda limit=2500: [])
    monkeypatch.setattr(D, "_already_has", lambda src, name: False)
    cd = L.MutationCooldown(blocked={}, avoided=set(), penalties={})
    ordered = [("stem_kepler_third_law", "stem_enable", "enable:stem_kepler_third_law"),
               ("stem_snell_least_time", "stem_enable", "enable:stem_snell_least_time")]
    name, kind, _s, cooled = D.pick_mutation(ordered, cooldown=cd, lemma_src="", shift_prescreen=True)
    assert name == "stem_snell_least_time" and kind == "stem_enable"
    assert cooled["stem_kepler_third_law"] == "oracle_prescreen:trivial:stem_symbolic_tautology"
    assert ("lesson", "stem_kepler_third_law") in treatment  # counts toward the kill cooldown
    # shift_prescreen off (control arm path): unchanged pick
    name, *_ = D.pick_mutation(ordered, cooldown=cd, lemma_src="", shift_prescreen=False)
    assert name == "stem_kepler_third_law"


def test_shadow_mode_logs_but_does_not_drop(treatment, monkeypatch):
    monkeypatch.setenv("COLONY_ORACLE_PRESCREEN", "shadow")
    assert P.screen("stem_kepler_third_law", "stem_enable") is None
    assert any(isinstance(r, dict) and r.get("mode") == "shadow" for r in treatment)


def test_replay_never_drops_a_novel_hit_or_non_stem_row(treatment, tmp_path):
    import importlib.util
    import json
    from pathlib import Path

    o = tmp_path / "oracle.jsonl"
    g = tmp_path / "gate.jsonl"
    o.write_text("\n".join(json.dumps(r) for r in [
        {"mutation": "stem_kepler_third_law", "kind": "stem_enable", "passed": True},
        {"mutation": "stem_snell_least_time", "kind": "stem_enable", "passed": True},
        {"mutation": "pisano_prime_period", "kind": "hard_enable", "passed": True},
    ]) + "\n")
    g.write_text("\n".join(json.dumps(r) for r in [
        {"mutation": "stem_snell_least_time", "kind": "stem_enable", "novel_to_commons": True},
        {"mutation": "stem_kepler_third_law", "kind": "stem_enable", "novel_to_commons": False},
    ]) + "\n")
    p = Path(__file__).resolve().parents[1] / "scripts" / "replay_item96_stem_prescreen.py"
    spec = importlib.util.spec_from_file_location("replay96", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rep = mod.main(o, g)
    assert rep["novel_hits_dropped"] == [] and rep["non_stem_rows_dropped"] == 0
    assert rep["oracle_passes_dropped"] == 1  # the tautology only
