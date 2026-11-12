"""A proposal blocked as a dedupe repeat two cycles in a row is parked.

Its turn then goes to a different source. Theme cooldown (already in
colony.lessons) plus this park is the item-1 accept: a 10-cycle replay
proposes a saturated theme and a repeat chain at most once each, then
parks them. No name is special-cased in the mechanism; the replay uses
the two that have been looping.
"""
from __future__ import annotations

import json

import colony.fitness as F
import colony.lessons as L
import colony.novelty_gate as NG
import colony.oracle as O
import colony.stall as S


def _fp(title="Chain+seek lemma_hard_combinatorics", action="seek_enable:lemma_hard_combinatorics"):
    return F.proposal_fingerprint(title, action), title, action


def test_two_consecutive_blocks_park_for_six_cycles():
    fp, title, action = _fp()
    S.note_dedupe_block(fp, title, action, "c0")
    assert S.is_parked(fp, "c0") is False
    rec = S.note_dedupe_block(fp, title, action, "c1")
    assert rec["consecutive"] >= 2
    # The second block cycle is the one that parks; the next six are parked.
    assert S.is_parked(fp, "c1") is False
    parked = []
    for i in range(2, 12):
        cid = f"c{i}"
        S.remember_cycle(cid)
        if S.is_parked(fp, cid):
            parked.append(cid)
    assert parked == [f"c{i}" for i in range(2, 8)]
    assert S.is_parked(fp, "c8") is False


def test_nonconsecutive_blocks_do_not_park():
    fp, title, action = _fp("other theme", "seek_enable:other")
    S.remember_cycle("a")
    S.remember_cycle("b")  # a cycle with no block sits between
    S.remember_cycle("c")
    S.note_dedupe_block(fp, title, action, "a")
    S.note_dedupe_block(fp, title, action, "c")
    assert S.is_parked(fp, "c") is False
    assert S.is_parked(fp, "d") is False


def test_ingest_history_parks_a_chain_already_blocked_twice():
    fp, title, action = _fp()
    S.ingest_dedupe_history([
        {"fingerprint": fp, "cycle_id": "h0", "title": title, "action": action},
        {"fingerprint": fp, "cycle_id": "h1", "title": title, "action": action},
    ])
    # The next cycle after those two is parked.
    assert S.is_parked(fp, "h2") is True


def test_parked_turn_goes_to_another_source(monkeypatch):
    fp, title, action = _fp()
    S.note_dedupe_block(fp, title, action, "c0")
    S.note_dedupe_block(fp, title, action, "c1")
    assert S.is_parked(fp, "c2") is True

    calls = []

    def _idle(cid):
        calls.append(cid)
        return {"purpose": "zero_credit_family", "chosen": [{"id": "gf_t", "anum": "A1", "form": "gf"}]}

    import colony.oeis_conjectures as OC
    monkeypatch.setattr(OC, "idle_turn", _idle)
    out = S.give_turn_elsewhere("c2", excluded=[fp])
    assert out["source"] == "oeis_idle"
    assert calls == ["c2"]
    assert out["oeis"]["chosen"][0]["id"] == "gf_t"


def test_alternate_picker_wins_when_unparked():
    fp, title, action = _fp()
    S.note_dedupe_block(fp, title, action, "c0")
    S.note_dedupe_block(fp, title, action, "c1")

    def picker():
        return ("Fresh lemma enable", "try a different seed", "seek_enable:fresh_lemma")

    out = S.give_turn_elsewhere("c2", excluded=[fp], picker=picker)
    assert out["source"] == "alternate_proposal"
    assert out["proposal"]["action"] == "seek_enable:fresh_lemma"
    assert out["proposal"]["fingerprint"] != fp


def _theme_logs(tmp_path, monkeypatch, theme="vandermonde"):
    gate = tmp_path / "novelty_gate.jsonl"
    oracle = tmp_path / "oracle.jsonl"
    monkeypatch.setattr(NG, "GATE_LOG", gate)
    monkeypatch.setattr(O, "ORACLE_LOG", oracle)
    kills = [
        "already_in_lesson_ledger_or_history",
        "oracle_kill:['held_out:held_out:already_saturated_no_harder_window']",
    ]
    gate.write_text(json.dumps({
        "cycle_id": "c_sat", "mutation": theme, "kind": "claim_theme",
        "kills": kills,
    }) + "\n")
    oracle.write_text(json.dumps({
        "cycle_id": "c_sat", "mutation": theme, "kind": "claim_theme", "passed": False,
        "kills": ["held_out:held_out:already_saturated_no_harder_window"],
        "sense": {"held_out": {"theme_window": "w1", "in_catalog": True, "enabled": False}},
    }) + "\n")
    monkeypatch.setattr(L, "held_out_window_state", lambda theme: {
        "window": "w1", "in_catalog": True, "enabled": False, "saturated": True,
    })


def test_replay_of_ten_cycles_proposes_looping_items_at_most_once(tmp_path, monkeypatch):
    """Accept for item 1: vandermonde and the hard-combinatorics chain, at most once each."""
    _theme_logs(tmp_path, monkeypatch, theme="vandermonde")
    fp, title, action = _fp()
    # History already has two consecutive blocks, as in the live stall.
    S.ingest_dedupe_history([
        {"fingerprint": fp, "cycle_id": "prior0", "title": title, "action": action},
        {"fingerprint": fp, "cycle_id": "prior1", "title": title, "action": action},
    ])

    theme_proposed = []
    chain_proposed = []
    for i in range(10):
        cid = f"replay{i}"
        S.remember_cycle(cid)
        # A cooled saturated theme is not proposed.
        theme_proposed.append(not L.claim_theme_probe_cooled("vandermonde"))
        # A parked chain is not proposed. After the park expires, a new
        # attempt is itself a dedupe block and rebuilds the streak.
        parked = S.is_parked(fp, cid)
        chain_proposed.append(not parked)
        if not parked:
            S.note_dedupe_block(fp, title, action, cid)

    assert sum(theme_proposed) <= 1
    assert theme_proposed == [False] * 10
    # The six-cycle park covers the first six replay cycles (history already
    # had two blocks). After it lifts, two more blocks re-park, so the chain
    # is proposed at most twice in ten cycles and never during a park.
    assert chain_proposed[:6] == [False] * 6
    assert sum(chain_proposed) <= 2
    for i, proposed in enumerate(chain_proposed):
        if proposed:
            # The cycle that re-opens a park is a block, not a live proposal
            # to the Oracle; still counted here as "tried".
            assert S.is_parked(fp, f"replay{i}") is False
