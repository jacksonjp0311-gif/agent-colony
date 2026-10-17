"""COLONY_HUNT=live|shadow|off: hunt guidance reorders / re-rewards exploration only."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import colony.exploration_budget as B
import colony.hunt as HL
import colony.hunt_shadow as HS

ORA = [{"mutation": f"authored_sweep_g{i}_w1", "passed": True} for i in range(1, 9)] + \
      [{"mutation": "authored_pascal_identity__cassini_identity_w1", "passed": True},
       {"mutation": "authored_pascal_identity__vandermonde_w1", "passed": True}]
V = HL.Valuer(ORA, k=0.1)


def test_mode_default_shadow_and_invalid(monkeypatch):
    monkeypatch.delenv("COLONY_HUNT", raising=False)
    assert HL.mode() == "shadow" and not HL.live()
    monkeypatch.setenv("COLONY_HUNT", "bogus")
    assert HL.mode() == "shadow"
    monkeypatch.setenv("COLONY_HUNT", "LIVE")
    assert HL.live()


def test_off_disables_shadow_reporting(monkeypatch):
    monkeypatch.setenv("COLONY_HUNT", "off")
    assert not HS.enabled()
    monkeypatch.setenv("COLONY_HUNT", "shadow")
    assert HS.enabled()


def test_values_new_family_beats_sweep_and_bare_enable():
    assert V.value("authored_brand_new_idea_w1") == 1.0
    assert V.value("authored_sweep_g9_w1") < 0.02          # 8 passed siblings
    assert V.value("energy_work") == 0.0                   # bare catalog enable
    assert V.value("pascal_identity") == 1.0               # chained by 2 Oracle-passed claims
    assert V.value("cassini_identity") == 0.5


def test_reorder_strength_zero_is_identity_and_full_prefers_unknown():
    items = ["authored_sweep_g9_w1", "energy_work", "authored_brand_new_idea_w1", "pascal_identity"]
    assert HL.reorder(items, str, valuer=V, s=0.0) == items
    out = HL.reorder(items, str, valuer=V, s=1.0)
    assert out[:2] == ["authored_brand_new_idea_w1", "pascal_identity"] or \
        out[:2] == ["pascal_identity", "authored_brand_new_idea_w1"]
    assert out.index("authored_sweep_g9_w1") > out.index("authored_brand_new_idea_w1")
    assert sorted(out) == sorted(items)                    # nothing removed


def test_anti_freeze_strength():
    keep = {"decision": "keep"}
    idle = {"decision": "skip"}
    assert HL.strength([keep] * 6) == 1.0
    assert HL.strength([idle] * 4 + [keep] * 2) == 0.5
    assert HL.strength([idle] * 6) == 0.25
    assert HL.strength([idle] * 3) == 1.0                  # too little history: full strength


def test_keep_multiplier():
    assert HL.keep_multiplier("authored_brand_new_idea_w1", valuer=V, s=1.0) == pytest.approx(1.25)
    assert HL.keep_multiplier("authored_sweep_g9_w1", valuer=V, s=1.0) < 1.01
    assert HL.keep_multiplier("authored_sweep_g9_w1", valuer=V, s=0.0) == pytest.approx(1.25)


CANDS = [("authored_sweep_g9_w1", "hard_enable", ""), ("energy_work", "hard_enable", ""),
         ("authored_brand_new_idea_w1", "hard_enable", "")]


@pytest.fixture
def budget(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "BUDGET_PATH", tmp_path / "b.json")
    monkeypatch.setattr(B, "ensure_distribution",
                        lambda names: {"authored_sweep_g9_w1": 0.5, "energy_work": 0.3,
                                       "authored_brand_new_idea_w1": 0.2})
    import colony.lessons as L
    monkeypatch.setattr(L, "catalog_hints_from_lessons", lambda lookback=20: [])
    monkeypatch.setattr(L, "guide_prefers_invariant_chains", lambda: False)
    monkeypatch.setattr(L, "preferred_variant_mutations", lambda: [])
    monkeypatch.setattr(HL, "Valuer", lambda *a, **k: V)
    monkeypatch.setattr(HL, "strength", lambda *a, **k: 1.0)
    return tmp_path


def test_shadow_restores_old_desk_order(budget, monkeypatch):
    monkeypatch.setenv("COLONY_HUNT", "shadow")
    assert [n for n, _, _ in B.pick_mutation_order(list(CANDS))] == \
        ["authored_sweep_g9_w1", "energy_work", "authored_brand_new_idea_w1"]
    monkeypatch.setenv("COLONY_HUNT", "off")
    assert [n for n, _, _ in B.pick_mutation_order(list(CANDS))][0] == "authored_sweep_g9_w1"


def test_live_desk_order_prefers_unknown(budget, monkeypatch):
    monkeypatch.setenv("COLONY_HUNT", "live")
    out = [n for n, _, _ in B.pick_mutation_order(list(CANDS))]
    assert out[0] == "authored_brand_new_idea_w1" and sorted(out) == sorted(n for n, _, _ in CANDS)


def test_record_outcome_keep_reward_live_vs_shadow(tmp_path, monkeypatch):
    import colony.conjecture_mutations as CM
    import colony.trust.flags as F
    monkeypatch.setattr(B, "BUDGET_PATH", tmp_path / "b.json")
    monkeypatch.setattr(F, "learning_enabled", lambda: True)
    monkeypatch.setattr(CM, "MUTATION_SNIPPETS", [(n, k, s) for n, k, s in CANDS])
    monkeypatch.setattr(HL, "Valuer", lambda *a, **k: V)
    monkeypatch.setattr(HL, "strength", lambda *a, **k: 1.0)

    def ratio(mode, name):
        (tmp_path / "b.json").unlink(missing_ok=True)
        monkeypatch.setenv("COLONY_HUNT", mode)
        d0 = B.ensure_distribution([n for n, _, _ in CANDS])
        r0 = d0[name] / d0["energy_work"]
        B.record_outcome(name, "keep")
        d1 = json.loads((tmp_path / "b.json").read_text())["mutate_distribution"]
        return (d1[name] / d1["energy_work"]) / r0

    assert ratio("shadow", "authored_sweep_g9_w1") == pytest.approx(1.25, rel=1e-3)
    assert ratio("live", "authored_sweep_g9_w1") < 1.02
    assert ratio("live", "authored_brand_new_idea_w1") == pytest.approx(1.25, rel=1e-3)


def test_workflow_runs_hunt_live():
    wf = (Path(__file__).resolve().parents[1] / ".github/workflows/colony-evolve.yml").read_text()
    assert "COLONY_HUNT: live" in wf


def test_hunt_never_imports_P_oracle_or_authorize():
    import ast
    tree = ast.parse((Path(__file__).resolve().parents[1] / "colony/hunt.py").read_text())
    mods = {getattr(n, "module", None) or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    mods |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m for m in mods if any(x in m for x in ("standing_trust", "authorize", "oracle", "charter")))
