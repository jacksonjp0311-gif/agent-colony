"""Hunt shadow (report-only): unknown reward + building blocks count only when combined."""
from __future__ import annotations

import colony.hunt_shadow as H
import colony.shortlist as S
from test_shortlist import KW, _ora, _p

NO_OEIS = lambda t: 0.1  # noqa: E731


def _sl(props, ora, *, oeis=NO_OEIS, **kw):
    return S.build(proposals=props, oracle_rows=list(ora), novelty_rows=[], athanor_rows=[],
                   **{**KW, "oeis": oeis, **kw})


def _by_id(sl, pid):
    for e in sl["top"] + sl["building_blocks_enabled"]:
        if e["id"] == pid:
            return e
    raise KeyError(pid)


def test_claim_family_strips_parameters():
    assert H.claim_family("authored_sieve_two_counter_g6_2_6_w1") == "authored_sieve_two_counter"
    assert H.claim_family("crt_coprime_pair") == "crt_coprime_pair"


def test_unknown_reward_credits_surviving_unknown_and_discounts_expected():
    lone = _p(1, "authored_new_idea_w1", "c1", _P=0.8)
    sweep = _p(2, "authored_sweep_g9_w1", "c2", _P=0.8)
    ora = [_ora("authored_new_idea_w1", "c1"), _ora("authored_sweep_g9_w1", "c2")] + \
          [_ora(f"authored_sweep_g{i}_w1", "old") for i in range(1, 7)]
    sl = _sl([lone, sweep], ora)
    a, b = _by_id(sl, "imp_1")["hunt"], _by_id(sl, "imp_2")["hunt"]
    assert a["unknown"] and a["siblings_passed"] == 0 and a["novelty_shadow"] == 1.0
    assert b["unknown"] and b["siblings_passed"] == 6 and b["novelty_shadow"] == round(1 - 6 / 9, 4)
    assert a["rank_shadow"] > b["rank_shadow"]


def test_in_oeis_or_textbook_is_not_unknown():
    p = _p(1, "authored_known_w1", "c1")
    sl = _sl([p], [_ora("authored_known_w1", "c1")], oeis=lambda t: 0.9)
    h = _by_id(sl, "imp_1")["hunt"]
    assert h["in_oeis"] and not h["unknown"] and h["novelty_shadow"] == 0.0
    sl = _sl([p], [_ora("authored_known_w1", "c1")], reuse=lambda p: 0.5, block_kind=None)
    assert sl["n_meet_bar"] == 0      # live novelty killer unchanged (textbook_reuse 0.5 kills it)


def test_building_block_counts_only_when_an_authored_claim_chains_it():
    bb = _p(1, "fermat_little", "c1", _P=0.85)
    ora = [_ora("fermat_little", "c1")]
    alone = _by_id(_sl([bb], ora, block_kind=None), "imp_1")["hunt"]
    assert alone["chained_by"] == 0 and alone["novelty_shadow"] == 0.0
    ora2 = ora + [_ora("authored_fermat_little__wilson_theorem_w1", "c9")]
    chained = _by_id(_sl([bb], ora2, block_kind=None), "imp_1")["hunt"]
    assert chained["chained_by"] == 1 and chained["novelty_shadow"] == 0.5
    assert chained["P_shadow"] > alone["P_shadow"]


def test_view_only_P_rank_and_bar_unchanged(monkeypatch):
    props = [_p(1, "authored_a_w1", "c1", _P=0.9), _p(2, "authored_b_g2_w1", "c2", _P=0.75)]
    ora = [_ora("authored_a_w1", "c1"), _ora("authored_b_g2_w1", "c2"), _ora("authored_b_g1_w1", "x")]
    on = _sl(props, ora)
    monkeypatch.setenv("COLONY_HUNT_SHADOW", "0")
    off = _sl(props, ora)
    strip = lambda sl: [(g["id"], g["P"], g["rank"], g["position"]) for g in sl["top"]]  # noqa: E731
    assert strip(on) == strip(off) and on["n_meet_bar"] == off["n_meet_bar"]
    assert off["hunt_shadow"] is None and "hunt" not in off["top"][0]
    assert on["hunt_shadow"]["n_unknown_claims"] == 2
    assert "## Hunt shadow" in S.to_markdown(on) and "## Hunt shadow" not in S.to_markdown(off)
    assert props[0]["_P"] == 0.9 and "hunt" not in props[0]


def test_near_misses_tracks_shifted_window_failures_and_single_reason_kills():
    rows = [{"cycle_id": "c", "mutation": "a", "passed": False, "kills": ["held_out: shifted window fails"],
             "sense": {"held_out": {"shifted_window": {"applied": True, "ok": False}}}},
            {"cycle_id": "c", "mutation": "b", "passed": False, "kills": ["x", "y"]},
            {"cycle_id": "d", "mutation": "z", "passed": False, "kills": ["x"]}]
    n = H.near_misses(rows, "c")
    assert n["shifted_window_failures"] == ["a"] and [k["mutation"] for k in n["single_reason_kills"]] == ["a"]


def test_record_overwrites_with_bounded_history(tmp_path, monkeypatch):
    monkeypatch.setattr(H, "STATE", tmp_path / "h.json")
    sl = _sl([_p(1, "authored_a_w1", "c1")], [_ora("authored_a_w1", "c1")])
    for i in range(H.KEEP_CYCLES + 5):
        H.record({**sl["hunt_shadow"], "cycle_id": f"c{i}"})
    import json
    st = json.loads((tmp_path / "h.json").read_text())
    assert len(st["history"]) == H.KEEP_CYCLES and st["last"]["cycle_id"] == f"c{H.KEEP_CYCLES + 4}"
