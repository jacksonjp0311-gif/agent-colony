"""Obscure-OEIS pool: gated menu entry, honest cached terms, report-only shadow pass."""
import json

from colony import frontier_conjectures as FC
from colony import obscure_pool as OP


def test_pool_is_obscure_and_verified():
    d = json.loads(OP.POOL.read_text())
    assert d["pool"], "pool built"
    for e in d["pool"]:
        assert e["obscurity"] <= d["filter"]["obscurity_max"]
        assert not set(e["keyword"].split(",")) & set(d["filter"]["excluded_keywords"])
        assert e["verified"].startswith("b-file agrees with DATA")
        assert len(e["terms"]) >= 120
    assert not set(OP.ANUM.values()) & OP.taken_anums()


def test_gating(monkeypatch):
    monkeypatch.setenv("COLONY_OBSCURE", "off")
    assert not set(FC.menu_prims()) & set(OP.PRIMS)
    monkeypatch.setenv("COLONY_OBSCURE", "shadow")
    assert not set(FC.menu_prims()) & set(OP.PRIMS)
    monkeypatch.setenv("COLONY_OBSCURE", "live")
    # open-target entries resolve as ox primitives but join the menu only with COLONY_OPEN_TARGETS=live
    from colony import open_targets as OT
    monkeypatch.delenv("COLONY_OPEN_TARGETS", raising=False)
    assert set(OP.PRIMS) - set(OT.PRIMS) <= set(FC.menu_prims())
    assert not set(OT.PRIMS) & set(FC.menu_prims())
    monkeypatch.setenv("COLONY_OPEN_TARGETS", "live")
    assert set(OP.PRIMS) <= set(FC.menu_prims())


def test_lazy_table_and_eval():
    T = FC.Tables(lim=3000, exp_n=300)
    p = OP.PRIMS[0]
    assert p in T.t
    assert T.t[p] == OP.table(p)
    v = FC.evaluate(FC.parse(f"D({p})"), 50, T, T.t)
    assert v is not None and v[3] == OP.table(p)[5] - OP.table(p)[4]


def test_shadow_registers_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(OP, "REPORT", tmp_path / "rep.json")
    before = FC.STATE.read_text() if FC.STATE.exists() else ""
    T = FC.Tables(lim=6000, exp_n=300)
    r = OP.shadow_cycle("test", T=T)
    assert r["history"][-1]["counts"]["produced"] > 0
    assert (FC.STATE.read_text() if FC.STATE.exists() else "") == before
