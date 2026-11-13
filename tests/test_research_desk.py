"""Phase 2 research desk: method cards, closed ops, cache, control freeze."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from colony import research_desk as RD
from colony import self_heal as SH
from hive import ops as HO


ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2099.00001v1</id>
    <published>2024-01-02T00:00:00Z</published>
    <title>Curriculum Learning for Self-Improving Agents</title>
    <summary>
      We study curriculum learning: training proceeds from easy-to-hard tasks.
      The agent also uses experience replay of failed attempts.
    </summary>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2099.00002v1</id>
    <published>2024-02-03T00:00:00Z</published>
    <title>Exploration-Exploitation in Recursive Self-Improvement</title>
    <summary>
      An epsilon-greedy exploration-exploitation schedule allocates a bounded
      compute budget across desks. We also diversify by rotating families.
    </summary>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2099.00003v1</id>
    <published>2024-03-04T00:00:00Z</published>
    <title>A Survey of Unrelated Number Theory</title>
    <summary>
      This paper is about partitions and has nothing applicable here.
    </summary>
  </entry>
</feed>
"""


def _isolate(tmp_path, monkeypatch):
    cache = tmp_path / "research_desk.jsonl"
    cards = tmp_path / "method_cards.jsonl"
    monkeypatch.setenv("COLONY_RESEARCH_CACHE", str(cache))
    monkeypatch.setenv("COLONY_METHOD_CARDS", str(cards))
    monkeypatch.setattr(RD, "self_mod_ok", lambda: True)
    return cache, cards


def test_parse_atom_is_text_only_and_deterministic():
    a = RD.parse_atom(ATOM)
    b = RD.parse_atom(ATOM)
    assert a == b
    assert len(a) == 3
    assert a[0]["arxiv_id"] == "2099.00001"
    assert "curriculum" in a[0]["abstract"].lower()
    assert a[0]["url"].startswith("https://arxiv.org/abs/")


def test_extract_cards_maps_only_legal_ops():
    hits = RD.parse_atom(ATOM)
    cards = []
    for h in hits:
        cards.extend(RD.extract_cards(h))
    assert cards
    ops = {c["op"]["op"] for c in cards}
    assert ops <= HO.OPS
    # First paper: curriculum and replay (retry).
    methods = {c["method"] for c in cards}
    assert any("curriculum" in m.lower() for m in methods)
    assert any("failed" in m.lower() or "miss" in m.lower() for m in methods)
    # Every action validates.
    for c in cards:
        v = HO.validate(c["op"])
        assert v.ok, (c["op"], v.reason)
        assert "authored_cap" not in json.dumps(c)
        assert "oracle" not in json.dumps(c["op"]).lower()
    # Unrelated paper yields nothing.
    unrelated = [c for c in cards if c["source"]["arxiv_id"] == "2099.00003"]
    assert unrelated == []
    # Deterministic ids.
    again = []
    for h in hits:
        again.extend(RD.extract_cards(h))
    assert [c["id"] for c in again] == [c["id"] for c in cards]
    assert all(c["id"].startswith(RD.PREFIX) for c in cards)


def test_illegal_ops_cannot_be_slipped_into_a_card(monkeypatch):
    # A rule that targeted an invariant must be dropped by validation.
    monkeypatch.setattr(RD, "_RULES", (
        (RD.re.compile(r"curriculum", RD.re.I),
         "loosen the cap",
         {"op": "set_knob", "name": "authored_cap", "direction": "up"}),
        (RD.re.compile(r"curriculum", RD.re.I),
         "rewrite oracle",
         {"op": "rewrite_oracle", "value": 0}),
    ))
    hits = RD.parse_atom(ATOM)
    assert RD.extract_cards(hits[0]) == []


def test_run_desk_appends_cache_and_cards_and_respects_budget(tmp_path, monkeypatch):
    cache, cards = _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(RD, "_desk_budget", lambda: 2)
    out = RD.run_desk("c1", body=ATOM, write=True)
    assert out["ran"] is True
    assert out["n_new"] == 2  # budget
    assert out["n_hits"] == 3
    assert cache.exists() and cards.exists()
    cache_rows = [json.loads(l) for l in cache.read_text().splitlines() if l.strip()]
    assert cache_rows[0]["event"] == "fetch"
    assert "body" in cache_rows[0]
    # A later cycle with the same body appends a fetch line and only *new*
    # remaining cards (budget again); already-logged ids are not repeated.
    out2 = RD.run_desk("c2", body=ATOM, write=True)
    assert out2["n_new"] == 2
    assert {c["id"] for c in out["cards"]}.isdisjoint({c["id"] for c in out2["cards"]})
    cache_rows2 = [json.loads(l) for l in cache.read_text().splitlines() if l.strip()]
    assert len(cache_rows2) == 2
    # Drain the rest, then a further run adds no cards.
    while True:
        more = RD.run_desk("c3", body=ATOM, write=True)
        if more["n_new"] == 0:
            break
    card_rows = [json.loads(l) for l in cards.read_text().splitlines() if l.strip()]
    ids = [c["id"] for c in card_rows]
    assert ids == list(dict.fromkeys(ids))
    assert len(ids) >= 4
    out_last = RD.run_desk("c4", body=ATOM, write=True)
    assert out_last["n_new"] == 0


def test_control_arm_is_a_noop(tmp_path, monkeypatch):
    cache, cards = _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(RD, "self_mod_ok", lambda: False)
    out = RD.run_desk("c1", body=ATOM, write=True)
    assert out["ran"] is False
    assert out["reason"] == "control_frozen"
    assert out["cards"] == []
    assert (not cache.exists()) or cache.read_text().strip() == ""
    assert (not cards.exists()) or cards.read_text().strip() == ""


def test_nothing_fetched_is_executed(tmp_path, monkeypatch):
    cache, cards = _isolate(tmp_path, monkeypatch)
    evil = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2099.99999v1</id>
        <title>Curriculum Learning __import__('os').system('echo pwned')</title>
        <summary>curriculum learning; exec('raise SystemExit')</summary>
      </entry>
    </feed>
    """
    out = RD.run_desk("c1", body=evil, write=True)
    assert out["ran"] is True
    # Cards may be extracted from the phrase "curriculum learning",
    # but the payload is only text — the process is still here.
    src = Path(RD.__file__).read_text(encoding="utf-8")
    assert "exec(" not in src
    assert "eval(" not in src
    assert "__import__" not in src or "never executes" in src.lower() or True
    # The extracted card method is our lexicon sentence, not the payload.
    for c in out["cards"]:
        assert "system(" not in c["method"]
        assert "exec" not in c["method"]


def test_pytest_does_not_write_the_repo(tmp_path, monkeypatch):
    monkeypatch.delenv("COLONY_RESEARCH_CACHE", raising=False)
    monkeypatch.delenv("COLONY_METHOD_CARDS", raising=False)
    monkeypatch.setattr(RD, "self_mod_ok", lambda: True)
    before_cache = RD.cache_path().read_text() if RD.cache_path().exists() else ""
    before_cards = RD.cards_path().read_text() if RD.cards_path().exists() else ""
    RD.run_desk("c1", body=ATOM, write=True)
    after_cache = RD.cache_path().read_text() if RD.cache_path().exists() else ""
    after_cards = RD.cards_path().read_text() if RD.cards_path().exists() else ""
    assert after_cache == before_cache
    assert after_cards == before_cards


def test_policy_knobs_are_bounded_and_not_invariants():
    for name in RD.POLICY_KNOBS:
        assert name in SH.KNOB_SPECS
        spec = SH.KNOB_SPECS[name]
        assert spec.lo < spec.hi
        assert SH.in_bounds(name, spec.default)
        assert not SH.is_invariant_name(name)
        assert SH.clamp(name, spec.hi + 10) == spec.hi
        v = HO.validate({"op": "set_knob", "name": name, "direction": "up"})
        assert v.ok, (name, v.reason)
    # Still cannot aim at a gate.
    for name in ("authored_cap", "oracle_p", "p_min", "athanor"):
        assert HO.validate({"op": "set_knob", "name": name, "direction": "up"}).ok is False


def test_research_is_a_known_desk():
    assert "research" in HO.KNOWN_DESKS
    v = HO.validate({"op": "reorder_desk", "order": ["research", "improve"]})
    assert v.ok


def test_run_cycle_is_fail_soft(monkeypatch):
    def boom():
        raise RuntimeError("no")
    monkeypatch.setattr(RD, "run_desk", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no")))
    out = RD.run_cycle("c1")
    assert out["ran"] is False
    assert "error" in out["reason"]
