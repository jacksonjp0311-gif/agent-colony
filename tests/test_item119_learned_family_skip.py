"""Item 119: no more variants of a mutation family the lesson ledger holds; freed turns go to bank v2."""
from __future__ import annotations

import json

import pytest

import colony.conjecture_desk as D
import colony.learned_family_skip as LFS
import colony.lessons as L
import colony.stall as S
import colony.target_supply as TS
from colony import target_generator as TG
from tests.test_target_generator import _isolate, _claim
from tests.test_target_supply import FakeNet, FakeTool, _hit, paths  # noqa: F401

SRC = "alpha(n) = 0 (mod 7) for all n = 0 (mod 1)"


def _gen(name, src=SRC):
    return {"event": "authored", "name": name, "source_statement": src, "cycle_id": "c0"}


def _les(name, typ, ts="2026-11-19T00:00:00Z"):
    return {"ts": ts, "type": typ, "mutation": name}


def test_family_learned_only_by_a_judged_lesson_not_the_birth_record():
    gen = [_gen("authored_mut_a"), _gen("authored_mut_b"), _gen("authored_mut_c", src="other")]
    snap = LFS.Snapshot(gen, [_les("authored_mut_a", "authored_check")])
    assert snap.learned_by_statement(SRC) is None and snap.learned_by_name("authored_mut_b") is None
    snap = LFS.Snapshot(gen, [_les("authored_mut_a", "authored_check"), _les("authored_mut_a", "revert")])
    assert snap.learned_by_statement(SRC) == "authored_mut_a"
    assert snap.learned_by_name("authored_mut_b") == "authored_mut_a"   # never-judged sibling
    assert snap.learned_by_name("authored_mut_a") is None              # itself: the ledger rule already covers it
    assert snap.learned_by_name("authored_mut_c") is None              # other family
    assert snap.learned_by_name("stem_x") is None                      # only generated checks
    # replay view: a lesson at/after the cut-off does not count yet
    assert LFS.Snapshot(gen, [_les("authored_mut_a", "revert", ts="2026-11-20T00:00:00Z")],
                        before="2026-11-19T12:00:00Z").learned_by_statement(SRC) is None


def test_switch_off_on_control_and_when_off(monkeypatch):
    monkeypatch.delenv("COLONY_LEARNED_FAMILY_SKIP", raising=False)
    monkeypatch.delenv("COLONY_ARM", raising=False)
    assert LFS.enabled()
    monkeypatch.setenv("COLONY_LEARNED_FAMILY_SKIP", "off")
    assert not LFS.enabled() and LFS.snapshot() is None
    monkeypatch.delenv("COLONY_LEARNED_FAMILY_SKIP")
    monkeypatch.setenv("COLONY_ARM", "control")
    assert not LFS.enabled() and LFS.snapshot() is None


def _cong(m=7):
    return {**_claim("cong", "alpha", "", {"m": m, "q": 1, "r": 0, "s": 0}), "sig": f"s{m}", "statement": SRC}


def _gen_setup(tmp_path, monkeypatch, judged):
    lemma, log = _isolate(tmp_path, monkeypatch)
    log.write_text(json.dumps(_gen("authored_mut_old")) + "\n", encoding="utf-8")
    lessons = tmp_path / "lessons.jsonl"
    lessons.write_text((json.dumps(_les("authored_mut_old", "revert")) + "\n") if judged else "", encoding="utf-8")
    monkeypatch.setattr(LFS, "LESSONS", lessons)
    monkeypatch.setattr(TG, "is_trivial", lambda row: "")
    monkeypatch.setattr(TG, "prefilter_holds", lambda *a, **k: True)
    monkeypatch.setenv("COLONY_LEARNED_FAMILY_LOG", str(tmp_path / "lfs.jsonl"))
    return lemma, log


def _ok(*_a, **_k):
    return {"accepted": True, "seconds": 0.01, "reason": "verified"}


def test_generator_skips_a_learned_family_and_logs_it(tmp_path, monkeypatch):
    _gen_setup(tmp_path, monkeypatch, judged=True)
    rows = TG.author_targets(max_new=1, cycle_id="c119", claims=[_cong(7)], verify=_ok)
    assert rows == []
    sup = TG.last_supply()
    assert sup["learned_family_skipped"] == 1 and sup["cycle_id"] == "c119"
    assert sup["tried"] == 0                     # no verify spent on the learned family
    out = [json.loads(x) for x in (tmp_path / "lfs.jsonl").read_text().splitlines()]
    assert out[-1]["event"] == "skip_author" and out[-1]["families"][0]["learned_by"] == "authored_mut_old"
    assert out[-1]["authorized"] is False


def test_generator_unchanged_when_family_not_learned_or_switch_off(tmp_path, monkeypatch):
    _gen_setup(tmp_path, monkeypatch, judged=False)
    assert len(TG.author_targets(max_new=1, cycle_id="c1", claims=[_cong(7)], verify=_ok)) == 1
    other = tmp_path / "x"
    other.mkdir()
    _gen_setup(other, monkeypatch, judged=True)
    monkeypatch.setenv("COLONY_LEARNED_FAMILY_SKIP", "off")
    assert len(TG.author_targets(max_new=1, cycle_id="c2", claims=[_cong(7)], verify=_ok)) == 1


def test_desk_cools_never_judged_variant_of_learned_family(tmp_path, monkeypatch):
    log = tmp_path / "gen.jsonl"
    log.write_text("\n".join(json.dumps(_gen(n)) for n in ("authored_mut_old", "authored_mut_new")) + "\n")
    monkeypatch.setenv("COLONY_GENERATED_TARGETS_LOG", str(log))
    lessons = tmp_path / "lessons.jsonl"
    lessons.write_text(json.dumps(_les("authored_mut_old", "revert")) + "\n")
    monkeypatch.setattr(LFS, "LESSONS", lessons)
    monkeypatch.setattr(S, "load_oracle_rows", lambda limit=2500: [])
    monkeypatch.setattr(D, "_already_has", lambda src, name: False)
    import colony.authoring as AU
    monkeypatch.setattr(AU, "ledger_view", lambda: None)
    cd = L.MutationCooldown(blocked={}, avoided=set(), penalties={})
    ordered = [("authored_mut_new", "hard_enable", "x"), ("other_check", "hard_enable", "y")]
    name, _k, _s, cooled = D.pick_mutation(ordered, cooldown=cd, lemma_src="")
    assert name == "other_check" and cooled["authored_mut_new"] == "learned_family"
    monkeypatch.setenv("COLONY_LEARNED_FAMILY_SKIP", "off")
    name, *_ = D.pick_mutation(ordered, cooldown=cd, lemma_src="")
    assert name == "authored_mut_new"


def test_slot_refill_treatment_only_once_per_cycle_and_keeps_open_min(paths, monkeypatch):
    tool = FakeTool()
    bank = TS.query_bank(tool)
    tool.pages[(bank[0]["q"], bank[0]["page"])] = [_hit(11)]
    monkeypatch.setattr(TS, "open_count", lambda *a, **k: 0)
    monkeypatch.setattr(TS, "_heal", lambda: {})
    st = TS.load_state()
    st["last_refill_index"] = st["cycle_index"] = 5     # the regular refill is cooling: slot ignores that
    TS.save_state(st)
    rep = TS.slot_refill("cA", net=FakeNet(), tool=tool, menu=[])
    assert [e["id"] for e in rep["new"]] == ["oc_A000011_0"] and rep["slot"] is True
    assert TS.load_log()[-1]["event"] == "target_added"            # shared log: both arms adopt next run
    assert TS.slot_refill("cA", net=FakeNet(), tool=tool, menu=[])["skipped"] == "already_this_cycle"
    monkeypatch.setattr(TS, "open_count", lambda *a, **k: TS.OPEN_MIN)
    assert TS.slot_refill("cB", net=FakeNet(), tool=tool, menu=[])["skipped"] == "enough_open"
    monkeypatch.setenv("COLONY_ARM", "control")
    assert TS.slot_refill("cC", net=FakeNet(), tool=tool, menu=[])["skipped"] == "not_treatment_or_supply_off"


def test_give_slot_logs_and_is_off_on_control(tmp_path, monkeypatch):
    monkeypatch.setenv("COLONY_LEARNED_FAMILY_LOG", str(tmp_path / "lfs.jsonl"))

    class Sup:
        calls = []

        def slot_refill(self, cid):
            self.calls.append(cid)
            return {"new": [{"id": "oc_A1_0"}], "pages_read": 8}

    sup = Sup()
    out = LFS.give_slot("c9", freed=["authored_mut_new"], source="t", supply=sup)
    assert out["given"] and sup.calls == ["c9"]
    row = json.loads((tmp_path / "lfs.jsonl").read_text().splitlines()[-1])
    assert row["event"] == "slot_given" and row["refill"]["new"][0]["id"] == "oc_A1_0"
    assert not LFS.give_slot("c9", freed=[], source="t", supply=sup)["given"]
    monkeypatch.setenv("COLONY_ARM", "control")
    assert not LFS.give_slot("c9", freed=["x"], source="t", supply=sup)["given"] and sup.calls == ["c9"]
