"""Item 118: target refill bank v2 (new query families, fair to both arms; no network)."""
from __future__ import annotations

import colony.target_supply as TS
from tests.test_target_supply import FakeNet, FakeTool, _hit, paths  # noqa: F401


def _bank(monkeypatch, v2):
    monkeypatch.setenv("COLONY_SUPPLY_BANK_V2", "live" if v2 else "off")
    return TS.query_bank(FakeTool())


def test_v2_is_appended_and_never_changes_old_keys(monkeypatch):
    old, new = _bank(monkeypatch, False), _bank(monkeypatch, True)
    assert [b["key"] for b in new[:len(old)]] == [b["key"] for b in old]   # done_pages stay valid
    extra = new[len(old):]
    assert extra and all(b.get("bank") == 2 for b in extra)
    assert len({b["key"] for b in new}) == len(new)                       # no page asked twice
    assert {b["kind"] for b in extra} == {"rel", "name"}
    assert all(b["page"] < 10 and "-keyword:dead" in b["q"] for b in extra)


def test_v2_keys_do_not_collide_with_the_exhausted_first_bank(monkeypatch):
    old = {b["key"] for b in _bank(monkeypatch, False)}
    v2 = TS.query_bank(FakeTool())  # env still "off" -> compute v2 keys directly
    import hashlib
    keys = {hashlib.sha256(f"{b['q']}|{b['page']}".encode()).hexdigest()[:16] for b in TS.query_bank_v2()}
    assert v2 and not old & keys   # every v2 page is genuinely new, none was already read


def test_pending_order_def_then_relation_then_name_then_plain(monkeypatch):
    bank = _bank(monkeypatch, True)
    todo = TS.pending_pages(bank, {"done_pages": {}}, {})
    ranks = [TS.KIND_RANK[b["kind"]] for b in todo]
    assert ranks == sorted(ranks)
    # with the first bank fully read (as on 2026-11-18), the next page is a v2 relation page
    done = {b["key"]: {} for b in bank if not b.get("bank")}
    nxt = TS.pending_pages(bank, {"done_pages": done}, {})
    assert nxt and nxt[0]["kind"] == "rel" and all(b.get("bank") == 2 for b in nxt)


def test_refill_reads_v2_after_first_bank_exhausted(paths, monkeypatch):  # noqa: F811
    monkeypatch.setenv("COLONY_SUPPLY_BANK_V2", "live")
    tool = FakeTool()
    bank = TS.query_bank(tool)
    st = TS.load_state()
    st["done_pages"] = {b["key"]: {"n_hits": 0} for b in bank if not b.get("bank")}
    p = TS.pending_pages(bank, st, {})[0]
    tool.pages[(p["q"], p["page"])] = [_hit(9, text="Conjecture: a(n) = A000045(n+1) - 1.")]
    rep = TS.refill("c", net=FakeNet(), tool=tool, menu=[], st=st, library_rows=[], pages=1)
    assert [e["id"] for e in rep["new"]] == ["oc_A000009_0"]
    rows = TS.load_log()
    assert rows[-1]["event"] == "target_added" and rows[-1]["authorized"] is False


def test_switch_off_restores_the_first_bank_only(monkeypatch):
    assert all(not b.get("bank") for b in _bank(monkeypatch, False))


def test_bank_is_the_same_on_both_arms(monkeypatch):
    """Supply is environment: the bank does not depend on the twin arm."""
    monkeypatch.setenv("COLONY_SUPPLY_BANK_V2", "live")
    monkeypatch.setenv("COLONY_ARM", "control")
    a = [b["key"] for b in TS.query_bank(FakeTool())]
    monkeypatch.setenv("COLONY_ARM", "treatment")
    assert a == [b["key"] for b in TS.query_bank(FakeTool())]
