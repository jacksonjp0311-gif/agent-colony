"""Item 108: MAP-Elites archive over desk proposals (deterministic order factor; shadow by default)."""
from colony import map_elites as ME


def _gate(mut, kind="hard_enable", novel=True, kills=(), cycle="c1", ts="2026-11-16T00:00:00Z", held=None):
    r = {"mutation": mut, "kind": kind, "novel_to_commons": novel, "kills": list(kills), "cycle_id": cycle, "ts": ts}
    if held:
        r["held_out"] = held
    return r


def _keep(mut, cycle="c1"):
    return {"decision": "keep", "mutation": mut, "cycle_id": cycle, "note": "Kept | oracle=PASS fitness_credit=True"}


def test_cells_and_elites():
    gate = [_gate("authored_catalan_convolution__x_w1"), _gate("stem_rc_discharge", "stem_enable", novel=False,
                                                                  kills=["trivial"])]
    arch = ME.build(gate, [_keep("authored_catalan_convolution__x_w1")])
    cells = arch["cells"]
    assert cells["hard_enable:authored|lattice_paths|checked"]["elite"]["mutation"].startswith("authored_catalan")
    assert cells["stem_enable:catalog|circuits|checked"]["elite"] is None


def test_elite_needs_oracle_keep_and_no_kill():
    gate = [_gate("motzkin_bounded")]
    assert ME.build(gate, [])["cells"]["hard_enable:catalog|lattice_paths|checked"]["elite"] is None
    gate = [_gate("motzkin_bounded", kills=["x"])]
    assert ME.build(gate, [_keep("motzkin_bounded")])["cells"]["hard_enable:catalog|lattice_paths|checked"]["elite"] is None


def test_factor_prefers_empty_cells_and_demotes_barren_and_easy_pads():
    gate = [_gate("authored_fibonacci_addition__y_w%d" % i, cycle="c%d" % i) for i in range(6)]
    keeps = [_keep("authored_fibonacci_addition__y_w0", "c0")]
    gate += [_gate("stem_snell_least_time", "stem_enable", novel=False, kills=["k"], cycle="s%d" % i) for i in range(3)]
    arch = ME.build(gate, keeps)
    f = ME.factors([("authored_fibonacci_addition__z_w9", "hard_enable", ""),   # crowded elite cell
                    ("oeis_a000001_lucas_norm", "hard_enable", ""),             # empty cell, elite domain
                    ("stem_snell_lens", "stem_enable", ""),                     # barren cell
                    ("easy_pad_square", "easy_pad", "")], arch)
    assert f["oeis_a000001_lucas_norm"] > 1.0 > f["authored_fibonacci_addition__z_w9"]
    assert f["stem_snell_lens"] < 1.0 and f["easy_pad_square"] < 1.0
    assert f["oeis_a000001_lucas_norm"] == ME.factor("hard_enable", "oeis_a000001_lucas_norm", arch)


def test_deterministic():
    gate = [_gate("gcd_fibonacci"), _gate("pascal_identity")]
    a, b = ME.build(gate, []), ME.build(list(gate), [])
    assert a == b


def test_mode_default_shadow_and_off_on_control(monkeypatch):
    monkeypatch.delenv("COLONY_MAP_ELITES", raising=False)
    assert ME.mode() == "shadow" and ME.enabled() is False
    monkeypatch.setenv("COLONY_MAP_ELITES", "live")
    assert ME.enabled() is True
    from colony import arm
    monkeypatch.setattr(arm, "is_control", lambda: True)
    assert ME.mode() == "off"


def test_pick_order_unchanged_in_shadow(monkeypatch):
    from colony import exploration_budget as EB
    cands = [("gcd_fibonacci", "hard_enable", "s"), ("oeis_a000001_lucas_norm", "hard_enable", "s")]
    monkeypatch.setenv("COLONY_MAP_ELITES", "off")
    base = EB.pick_mutation_order(list(cands))
    monkeypatch.setenv("COLONY_MAP_ELITES", "shadow")
    assert EB.pick_mutation_order(list(cands)) == base


def test_live_mode_applies_factor_order_only(monkeypatch):
    from colony import exploration_budget as EB
    cands = [("gcd_fibonacci", "hard_enable", "s"), ("oeis_a000001_lucas_norm", "hard_enable", "s")]
    monkeypatch.setenv("COLONY_MAP_ELITES", "live")
    monkeypatch.setattr(ME, "factors", lambda c, archive=None: {"gcd_fibonacci": 0.5, "oeis_a000001_lucas_norm": 2.0})
    monkeypatch.setattr(EB, "ensure_distribution", lambda names: {n: 1.0 for n in names})
    out = EB.pick_mutation_order(list(cands))
    assert sorted(out) == sorted(cands)          # nothing added or removed
    assert out[0][0] == "oeis_a000001_lucas_norm"
