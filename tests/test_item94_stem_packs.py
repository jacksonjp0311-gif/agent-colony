"""Item 94: wider STEM pack — 10 classical relations, each checked by an independent numerical
route, DISABLED in kinematics_impl until the unchanged Oracle decides (stem_enable)."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest

from colony import domain_packs as DP
from colony.conjecture_mutations import MUTATION_SNIPPETS

ROOT = Path(__file__).resolve().parent.parent
IMPL = ROOT / "society" / "benchmarks" / "artifacts" / "kinematics_impl.py"
NEW = ["stem_elastic_collision", "stem_kepler_third_law", "stem_shm_energy", "stem_resistor_power_balance",
       "stem_isothermal_work", "stem_snell_least_time", "stem_rc_discharge", "stem_thin_lens_matrix",
       "stem_velocity_addition", "stem_wheatstone_balance"]


def _impl():
    spec = importlib.util.spec_from_file_location("k94", IMPL)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.mark.parametrize("name", NEW)
def test_new_stem_family_holds_and_starts_disabled(name):
    m = _impl()
    row = next(r for r in m.STEM_CHECKS if r[0] == name)
    assert row[2] is False  # Oracle decides
    assert row[1]() is True
    assert (name, "stem_enable", f"enable:{name}") in MUTATION_SNIPPETS
    assert name in [n for n, _, _ in DP.STEM_MUTATIONS]
    assert DP.pack_for_kind("stem_enable", name) == "stem_kinematics"
    src = IMPL.read_text()
    enabled = DP.enable_stem(src, name)
    assert enabled is not None and enabled.count(", True),") == src.count(", True),") + 1


def test_disabled_entries_do_not_change_the_live_bench():
    m = _impl()
    assert set(m.run_stem_checks()) == {"suvat_identity", "projectile_range", "circular_centripetal", "energy_work"}


def test_checks_are_not_vacuous():
    m = _impl()
    # wrong physics must fail each independent route
    assert m.check_wheatstone_balance(1, 2, 3, 7, 5) is True       # unbalanced and detected as such
    assert m.check_velocity_addition_rapidity(0.9, 0.9) is True
    assert abs((0.9 + 0.9) - math.tanh(math.atanh(0.9) * 2)) > 0.5  # naive addition disagrees
    assert m.check_kepler_third_circular(1.0, 2.0) is True
    assert m.check_snell_least_time(1.0, 1.0, 1, 1, 2) is True  # equal media: straight line
    # a broken closed form is caught: swap the masses' roles in the elastic formula
    m1, m2, u1, u2 = 1.0, 3.0, 2.0, 0.0
    v1 = ((m2 - m1) * u1) / (m1 + m2)
    v2 = (2 * m2 * u1) / (m1 + m2)
    assert abs((m1 * u1 + m2 * u2) - (m1 * v1 + m2 * v2)) > 1e-3


def test_oracle_stripped_sees_disabled_new_entry():
    from colony.oracle import sense_stripped_baseline
    r = sense_stripped_baseline("stem_rc_discharge", "stem_enable")
    assert r["stripped_fails_usefulness"] is True and r["in_catalog"] is True and r["already_enabled"] is False
