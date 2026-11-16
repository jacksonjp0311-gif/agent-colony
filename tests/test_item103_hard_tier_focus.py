"""Item 103: OEIS desk order favours historical near-misses and stated conjectures (order only)."""
from __future__ import annotations

from colony import hard_tier_focus as H

LOG = {"attempts": [
    {"id": "g1", "form": "gf", "status": "proof_rejected", "beyond": False},
    {"id": "g2", "form": "gf", "status": "holds_on_range", "beyond": True},
    {"id": "r1", "form": "relation", "status": "holds_on_range", "beyond": False},
    {"id": "r2", "form": "relation", "status": "holds_on_range", "beyond": False},
    {"id": "r3", "form": "relation", "status": "proved_checked", "beyond": False},
]}


def test_stats_and_form_factor():
    st = H.stats(LOG)
    assert st["forms"]["gf"] == {"attempts": 2, "near_misses": 2}
    assert st["forms"]["relation"] == {"attempts": 3, "near_misses": 0}
    assert H.form_factor("gf", st) > H.form_factor("relation", st)
    assert 0.75 <= H.form_factor("relation", st) <= 1.75


def test_factor_components():
    st = H.stats(LOG)
    base = {"id": "x", "claim": {"form": "relation"}}
    f0 = H.factor(base, {"tested_hi": 500}, st, past=True, bfile_hi=100)
    f_window = H.factor(base, {"tested_hi": 50}, st, past=True, bfile_hi=100)
    assert abs(f_window / f0 - 1.25) < 1e-9
    f_conj = H.factor({**base, "block_header": "Conjectures from X, 2018"}, {"tested_hi": 500}, st,
                      past=True, bfile_hi=100)
    assert abs(f_conj / f0 - 1.5) < 1e-9
    f_nm = H.factor({"id": "g1", "claim": {"form": "relation"}}, {"tested_hi": 500, "attempts": 1}, st,
                    past=True, bfile_hi=100)
    assert abs(f_nm / f0 - 1.2) < 1e-9
    big = H.factor({"id": "g1", "claim": {"form": "gf"}, "section": "conjecture"}, {"attempts": 1}, st,
                   past=True, bfile_hi=100)
    assert big <= H.MAX_F


def test_off_on_control_and_switch(monkeypatch):
    monkeypatch.setenv("COLONY_ARM", "control")
    assert H.enabled() is False
    monkeypatch.delenv("COLONY_ARM", raising=False)
    monkeypatch.setenv("COLONY_HARD_TIER_FOCUS", "off")
    assert H.enabled() is False
    monkeypatch.setenv("COLONY_HARD_TIER_FOCUS", "live")
    assert H.enabled() is True


def test_choose_same_set_only_order(monkeypatch):
    """With every target pickable, the focus changes order, never membership."""
    from colony import oeis_conjectures as oc
    menu = [{"id": f"t{i}", "claim": {"form": "gf" if i % 2 else "relation"}, "terms": [1, 2, 3], "offset": 0,
             **({"block_header": "Conjectures from Y"} if i == 3 else {})} for i in range(6)]
    monkeypatch.setattr(oc, "load_attempt_log", lambda **kw: LOG)
    monkeypatch.setattr(oc, "already_attempted_pair", lambda *a, **k: False)
    monkeypatch.setattr(oc, "held_on_published_only", lambda *a, **k: False)
    monkeypatch.setattr(oc, "can_progress_past", lambda *a, **k: True)
    monkeypatch.setattr(oc, "can_search_past_bfile", lambda e: True)
    monkeypatch.setattr(oc, "computable_definition", lambda e: {"x": 1})
    monkeypatch.setattr(oc, "routine_holonomic", lambda e: False)
    monkeypatch.setattr(oc, "planned_depth", lambda e, hi=None: 10)
    monkeypatch.delenv("COLONY_ARM", raising=False)
    state = {"targets": {}, "families": {}}
    monkeypatch.setenv("COLONY_HARD_TIER_FOCUS", "off")
    off = [e["id"] for e in oc.choose(menu, state, "c1", 6)]
    monkeypatch.setenv("COLONY_HARD_TIER_FOCUS", "live")
    on = [e["id"] for e in oc.choose(menu, state, "c1", 6)]
    assert sorted(off) == sorted(on)
