"""Item 95: stem_enable gets its own STEM held-out test + STEM triviality filter (never looser)."""
from __future__ import annotations

import pytest

from colony import novelty_gate as ng
from colony import stem_held_out as sho

GREEN = {"ok": True, "n_hard_pass": 172, "n_hard": 172, "score": 1.0}


@pytest.fixture
def lemma_green(monkeypatch):
    import society.benchmarks.lemma_microbench as lm

    monkeypatch.setattr(lm, "run", lambda *a, **k: dict(GREEN))
    return lm


@pytest.fixture
def treatment(monkeypatch):
    monkeypatch.delenv("COLONY_ARM", raising=False)
    monkeypatch.delenv("COLONY_SELF_MOD", raising=False)


def _src() -> str:
    return sho.STEM_IMPL.read_text(encoding="utf-8")


def test_every_catalog_entry_has_a_disjoint_harder_grid():
    ns, _ = sho._load()
    names = [e[0] for e in ns["STEM_CHECKS"]]
    assert set(names) == set(sho.HELD_OUT_GRIDS)
    for name, window, _enabled in ns["STEM_CHECKS"]:
        fn_name, grid = sho.HELD_OUT_GRIDS[name]
        seen: list[tuple] = []
        real = ns[fn_name]
        ns[fn_name] = lambda *a, _r=real: seen.append(tuple(a)) or _r(*a)
        try:
            assert window()
        finally:
            ns[fn_name] = real
        assert seen, name
        coded = {tuple(float(x) for x in p) for p in seen}
        held = {tuple(float(x) for x in p) for p in grid}
        assert not (coded & held), f"{name}: held-out grid overlaps the coded window"
        assert len(held) >= 6


def test_all_current_stem_entries_pass_their_harder_instance(lemma_green):
    for name in sho.HELD_OUT_GRIDS:
        h = sho.held_out(name)
        assert h["survives"], (name, h)
        assert h["mutants_killed"] >= 1


def test_fail_closed_cases(lemma_green, monkeypatch):
    assert sho.held_out("stem_not_a_check")["reason"] == "not_in_stem_catalog"
    # no registered harder instance → fail closed
    grids = dict(sho.HELD_OUT_GRIDS)
    grids.pop("stem_rc_discharge")
    monkeypatch.setattr(sho, "HELD_OUT_GRIDS", grids)
    assert sho.held_out("stem_rc_discharge")["reason"] == "no_registered_harder_instance_fail_closed"


def test_broken_check_fails_harder_instance(lemma_green):
    src = _src().replace("return abs(n1 * s1 - n2 * s2) < 1e-6", "return abs(n1 * s1 - n2 * s2 * 1.0001) < 1e-6")
    assert src != _src()
    h = sho.held_out("stem_snell_least_time", src=src)
    assert not h["survives"] and h["reason"] in {"coded_window_fails", "harder_instance_fails"}


def test_never_looser_than_old_conditions(monkeypatch):
    import society.benchmarks.lemma_microbench as lm

    monkeypatch.setattr(lm, "run", lambda *a, **k: {"ok": False, "n_hard_pass": 172})
    assert sho.held_out("stem_isothermal_work")["reason"] == "hard_tier_not_green"
    monkeypatch.setattr(lm, "run", lambda *a, **k: {"ok": True, "n_hard_pass": 0})
    assert sho.held_out("stem_isothermal_work")["reason"] == "hard_tier_not_green"


def test_red_stem_bench_fails(lemma_green):
    src = _src().replace("return abs(lhs - rhs) < 1e-9", "return abs(lhs - rhs) < -1.0")
    assert src != _src()
    assert sho.held_out("stem_isothermal_work", src=src)["reason"] == "stem_bench_not_green"


@pytest.mark.parametrize("name", [
    "suvat_identity", "projectile_range", "circular_centripetal", "energy_work",
    "stem_elastic_collision", "stem_kepler_third_law", "stem_shm_energy",
    "stem_resistor_power_balance", "stem_thin_lens_matrix", "stem_velocity_addition",
])
def test_tautologies_are_trivial(name):
    t = sho.triviality(name)
    assert t["trivial"] and t["reason"] == "stem_symbolic_tautology", t


@pytest.mark.parametrize("name", [
    "stem_isothermal_work", "stem_snell_least_time", "stem_rc_discharge", "stem_wheatstone_balance",
])
def test_independent_routes_are_not_trivial(name):
    assert not sho.triviality(name)["trivial"]


def test_triviality_negative_control_wrong_relation_is_not_a_tautology():
    # energy_work with a wrong work formula is NOT an identity → must not be called trivial
    src = _src().replace("work = m * a * s", "work = m * a * s * 1.1")
    assert src != _src()
    assert sho.triviality("energy_work", src=src)["reason"] == "not_a_tautology"


def test_gate_dispatch_treatment(lemma_green, treatment):
    h = ng.held_out_harder_survives("stem_snell_least_time", "stem_enable")
    assert h["survives"] and h["test"] == "stem_held_out_v1"
    t = ng.stem_triviality_kill("stem_kepler_third_law", "stem_enable")
    assert t["trivial"]
    assert ng.stem_triviality_kill("stem_kepler_third_law", "hard_enable") is None


def test_control_arm_keeps_old_test(lemma_green, monkeypatch):
    monkeypatch.setenv("COLONY_SELF_MOD", "off")
    h = ng.held_out_harder_survives("stem_snell_least_time", "stem_enable")
    assert not h["survives"] and h["reason"] == "hard_tier_green_and_hard_enable"
    assert ng.stem_triviality_kill("stem_snell_least_time", "stem_enable") is None


def test_other_kinds_unchanged(lemma_green, treatment):
    assert ng.held_out_harder_survives("x", "hard_enable") == {
        "survives": True, "reason": "hard_tier_green_and_hard_enable", "hard_pass": 172, "ok": True}
    assert not ng.held_out_harder_survives("x", "claim_theme")["survives"]
    assert ng.held_out_harder_survives("easy_pad_x", "stem_enable")["reason"] == "easy_pad_fails_held_out_harder"


def test_replay_has_no_looser_case_and_flips_are_genuine(lemma_green, tmp_path):
    import importlib.util
    import json
    from pathlib import Path

    old = ["held_out:hard_tier_green_and_hard_enable"]
    rows = [{"mutation": m, "kind": "stem_enable", "novel_to_commons": False, "kills": list(old)}
            for m in ("stem_elastic_collision", "stem_kepler_third_law", "stem_shm_energy",
                      "stem_resistor_power_balance", "stem_isothermal_work", "stem_snell_least_time")]
    rows.append({"mutation": "stem_rc_discharge", "kind": "stem_enable", "novel_to_commons": False,
                 "kills": old + ["textbook_reuse=0.6667"]})
    rows.append({"mutation": "lemma_x", "kind": "hard_enable", "novel_to_commons": False, "kills": ["x"]})
    log = tmp_path / "novelty_gate.jsonl"
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    p = Path(__file__).resolve().parents[1] / "scripts" / "replay_item95_stem_held_out.py"
    spec = importlib.util.spec_from_file_location("replay95", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rep = mod.main(log)
    assert rep["looser_cases"] == []
    assert rep["non_stem_rows_unchanged"] == 1
    flipped = {f["mutation"] for f in rep["flips_kill_to_novel"]}
    # tautologies stay killed (now for the triviality reason); other kills are kept
    assert flipped == {"stem_isothermal_work", "stem_snell_least_time"}
    for f in rep["flips_kill_to_novel"]:
        assert f["held_out"] == "stem_harder_instance_green"
        assert not f["triviality"].startswith("stem_symbolic_tautology")
        # only the old kind-based held-out kill was removed; no other kill disappeared
        assert all(k.startswith("held_out:") for k in f["old_kills"])
