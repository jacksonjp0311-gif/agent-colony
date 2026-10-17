"""Ranked proposal shortlist: a view only (bar filter, ranking, near-duplicate grouping)."""
from __future__ import annotations

import json

import colony.shortlist as S


def _p(i, target, cycle, **kw):
    base = {"id": f"imp_{i}", "title": f"Chain `{target}` citing X", "action": f"seek_enable:{target}",
            "cycle_id": cycle, "status": "candidate_measured", "hearing_verdict": "accept_candidate",
            "hypothesis": "Harder variant built from proven lemmas [instrument:sieve.sieve_count]."}
    base.update(kw)
    return base


def _ora(target, cycle, passed=True):
    return {"mutation": target, "cycle_id": cycle, "passed": passed}


KW = dict(resolve=lambda p: p["action"].split(":", 1)[1], reuse=lambda p: 0.1, p_rule=lambda p: p.get("_P", 0.8))


def _build(props, ora, nov=(), ath=()):
    return S.build(proposals=props, oracle_rows=list(ora), novelty_rows=list(nov), athanor_rows=list(ath), **KW)


def test_bar_filters_each_condition():
    props = [_p(1, "a_w1", "c1"),
             _p(2, "b_w1", "c2", status="candidate"),
             _p(3, "c_w1", "c3", hearing_verdict="reject"),
             _p(4, "d_w1", "c4"),                      # no oracle pass in its own cycle
             _p(5, "e_w1", "c5"),                      # novelty killed
             _p(6, "f_w1", "c6", _P=0.69)]             # P below 0.70
    ora = [_ora("a_w1", "c1"), _ora("b_w1", "c2"), _ora("c_w1", "c3"), _ora("d_w1", "other"),
           _ora("e_w1", "c5"), _ora("f_w1", "c6")]
    nov = [{"mutation": "e_w1", "cycle_id": "c5", "kills": ["textbook_reuse=0.6667"]}]
    sl = _build(props, ora, nov)
    assert [g["id"] for g in sl["top"]] == ["imp_1"] and sl["n_meet_bar"] == 1
    assert set(sl["excluded_reasons"]) == {"status", "hearing", "no_oracle_pass_in_own_cycle", "novelty_killed", "P"}


def test_oracle_kill_in_own_cycle_and_live_reuse_line():
    props = [_p(1, "a_w1", "c1"), _p(2, "b_w1", "c2")]
    ora = [_ora("a_w1", "c1"), _ora("a_w1", "c1", passed=False), _ora("b_w1", "c2")]
    sl = S.build(proposals=props, oracle_rows=ora, novelty_rows=[], athanor_rows=[],
                 resolve=KW["resolve"], p_rule=KW["p_rule"], reuse=lambda p: 0.34 if "b_w1" in p["action"] else 0.0)
    assert sl["n_meet_bar"] == 0
    assert sl["excluded_reasons"] == {"oracle_killed_in_own_cycle": 1, "novelty_killed": 1}


def test_rank_is_transparent_composite():
    props = [_p(1, "authored_x__y_w1", "c1", _P=0.75, hypothesis=""),
             _p(2, "plain_w1", "c2", _P=0.80, hypothesis=""),
             _p(3, "inst_w1", "c3", _P=0.75)]
    ora = [_ora("authored_x__y_w1", "c1"), _ora("plain_w1", "c2"), _ora("inst_w1", "c3"), _ora("x", "c0"), _ora("y", "c0")]
    sl = _build(props, ora)
    top = {g["id"]: g for g in sl["top"]}
    assert top["imp_1"]["builds_on"] == 1.0 and top["imp_1"]["rank"] == round(0.6 * 0.75 + 0.2 * 0.9 + 0.2 * 1.0, 4)
    assert top["imp_3"]["builds_on"] == 0.5 and top["imp_2"]["builds_on"] == 0.0
    assert [g["id"] for g in sl["top"]] == ["imp_1", "imp_3", "imp_2"]  # building on proven lemmas lifts rank


def test_near_duplicates_grouped_with_count():
    props = [_p(1, "fam_g6_w1", "c1", _P=0.75), _p(2, "fam_g6_w2", "c2", _P=0.9), _p(3, "fam_g6_w1", "c3", _P=0.8),
             _p(4, "other_w1", "c4")]
    ora = [_ora("fam_g6_w1", "c1"), _ora("fam_g6_w2", "c2"), _ora("fam_g6_w1", "c3"), _ora("other_w1", "c4")]
    sl = _build(props, ora)
    assert sl["n_meet_bar"] == 4 and sl["n_groups"] == 2
    rep = sl["top"][0]
    assert rep["id"] == "imp_2" and rep["group_count"] == 3 and set(rep["group_ids"]) == {"imp_1", "imp_2", "imp_3"}


def test_top_n_and_athanor_verdict_and_markdown():
    props = [_p(i, f"t{i}_w1", f"c{i}", _P=0.7 + i / 100) for i in range(15)]
    ora = [_ora(f"t{i}_w1", f"c{i}") for i in range(15)]
    ath = [{"mutation": "t14_w1", "verdict": "APPROVE"}]
    sl = _build(props, ora, ath=ath)
    assert len(sl["top"]) == 10 and sl["top"][0]["id"] == "imp_14" and sl["top"][0]["athanor_verdict"] == "APPROVE"
    md = S.to_markdown(sl)
    assert "View only" in md and "imp_14" in md and md.count("\n| ") >= 11


def test_write_overwrites_and_changes_nothing_else(tmp_path, monkeypatch):
    st = {"improvement_proposals": [_p(1, "a_w1", "c1", P=0.9)]}
    sp = tmp_path / "state.json"
    sp.write_text(json.dumps(st))
    ol = tmp_path / "oracle.jsonl"
    ol.write_text(json.dumps(_ora("a_w1", "c1")) + "\n")
    monkeypatch.setattr(S, "STATE_PATH", sp)
    monkeypatch.setattr(S, "ORACLE_LOG", ol)
    monkeypatch.setattr(S, "NOVELTY_LOG", tmp_path / "none.jsonl")
    monkeypatch.setattr(S, "ATHANOR_STATE", tmp_path / "none.json")
    monkeypatch.setattr(S, "OUT_DIR", tmp_path / "shortlist")
    before = (sp.read_bytes(), ol.read_bytes())
    S.write("cyc1", **KW); S.write("cyc2", **KW)
    assert (sp.read_bytes(), ol.read_bytes()) == before          # view only: inputs untouched
    out = json.loads((tmp_path / "shortlist" / "SHORTLIST.json").read_text())
    assert out["cycle_id"] == "cyc2" and out["view_only"] is True   # overwritten, not appended
    assert sorted(p.name for p in (tmp_path / "shortlist").iterdir()) == ["SHORTLIST.json", "SHORTLIST.md"]
    assert st["improvement_proposals"][0]["P"] == 0.9 and "status" in st["improvement_proposals"][0]
