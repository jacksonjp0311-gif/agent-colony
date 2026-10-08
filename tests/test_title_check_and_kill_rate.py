"""Seek proposals with a resolved target submit the TARGET to the Oracle, not their title.

- resolved + judged this cycle → target verdict is the evidence; no title-text process check
- resolved + not yet judged at propose time → title check deferred, settled at measurement:
  target judged → skipped; still no verdict → legacy title check runs (fail closed)
- unresolved → legacy title check, unchanged
Also: one kill_rate (fitness == oracle.json == counts()), and uptake excludes hintless
pure-recognition guides only.
"""
from __future__ import annotations

import json

import pytest

import colony.novelty_gate as NG
import colony.standing_trust as ST
from colony.standing_trust import STANDING_TRUST_P_MIN, compute_proposal_P

TARGET = "adversarial_hockey_deep"
TITLE = f"Chain `{TARGET}` citing Some paper"
ACTION = f"seek_enable:{TARGET}"


def _row(mutation, *, passed, cycle_id, kind="hard_enable"):
    return {
        "mutation": mutation, "kind": kind, "passed": passed, "fitness_credit": passed,
        "cycle_id": cycle_id, "sense": {"sense_pass": passed}, "hear": {"bus_ok": False},
        "kills": [] if passed else ["held_out:held_out_fail"],
    }


calls_sources: list = []


@pytest.fixture
def title_calls(tmp_path, monkeypatch):
    """Record every title-text submission (novelty gate → Oracle) instead of running it."""
    calls: list[dict] = []
    sources: list[str] = []
    calls_sources[:] = []

    def fake_eval(*, mutation, kind="", claim_text="", cycle_id="", oracle_source="novelty_gate"):
        calls.append({"mutation": mutation, "kind": kind, "claim_text": claim_text})
        sources.append(oracle_source)
        return {"textbook_reuse": NG.textbook_reuse_score(mutation.strip(), claim_text),
                "novel_to_commons": False, "kills": ["oracle_kill:[stub]"]}

    monkeypatch.setattr(NG, "evaluate", fake_eval)
    calls_sources.append(sources)
    log = tmp_path / "oracle.jsonl"
    log.write_text("", encoding="utf-8")
    monkeypatch.setattr(ST, "ORACLE_LOG", log)
    return calls, log


def _write(log, rows):
    log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_propose_time_resolved_target_defers_title_check(title_calls):
    calls, _log = title_calls
    P, terms = compute_proposal_P(mutation=TITLE, action=ACTION, cycle_id="c1",
                                  lesson_consistency=1.0, defer_title_check=True)
    assert calls == []  # title text never submitted to the Oracle
    assert terms["title_check_deferred"] == 1.0
    assert terms["P_oracle"] == 0.0  # fail closed until the target is judged
    # P_novelty is the same textbook-reuse score the gate would have computed
    assert terms["P_novelty"] == round(1.0 - NG.textbook_reuse_score(TITLE, ACTION), 4)
    assert P < STANDING_TRUST_P_MIN


def test_resolved_target_judged_this_cycle_skips_title_check(title_calls):
    calls, log = title_calls
    _write(log, [_row(TARGET, passed=False, cycle_id="c1")])  # target KILLED this cycle
    P, terms = compute_proposal_P(mutation=TITLE, action=ACTION, cycle_id="c1", lesson_consistency=1.0)
    assert calls == []
    assert terms["title_check_skipped_target_judged"] == 1.0
    assert terms["P_oracle"] == 0.0  # the kill still counts
    assert P < STANDING_TRUST_P_MIN


def test_resolved_target_not_judged_without_defer_keeps_title_check(title_calls):
    calls, log = title_calls
    _write(log, [_row(TARGET, passed=True, cycle_id="other_cycle")])
    compute_proposal_P(mutation=TITLE, action=ACTION, cycle_id="c1", lesson_consistency=1.0)
    assert len(calls) == 1 and calls[0]["kind"] == "process"


def test_unresolved_proposal_keeps_legacy_title_check(title_calls):
    calls, _log = title_calls
    t, a = "Deepen compute-useful math from accepted findings", "mandate:cite_accepted_compute_findings"
    compute_proposal_P(mutation=t, action=a, cycle_id="c1", lesson_consistency=1.0, defer_title_check=True)
    assert calls == [{"mutation": t, "kind": "process", "claim_text": a}]
    assert calls_sources[-1] == ["novelty_gate"]  # legacy path, legacy label


def _engine(prop):
    from colony.fitness import EvolutionEngine
    eng = EvolutionEngine.__new__(EvolutionEngine)
    eng.data = {"improvement_proposals": [prop]}
    eng.workshop = None
    return eng


def _prop(**kw):
    p = {"id": "imp_t_50", "cycle_id": "c1", "title": TITLE, "action": ACTION, "fingerprint": "",
         "status": "candidate", "P": 0.4, "P_terms": {"P_novelty": 1.0}, "title_check": "deferred",
         "before_metrics": {"aggregate": 0.8}, "after_metrics": None}
    p.update(kw)
    return p


def test_measure_target_killed_same_cycle_no_title_check_kill_counts(title_calls):
    calls, log = title_calls
    _write(log, [_row(TARGET, passed=False, cycle_id="c1")])
    closed = _engine(_prop()).close_open_proposals("c2", {"aggregate": 0.9})
    pr = closed[0]
    assert calls == []
    assert pr["title_check"] == "skipped_target_judged"
    assert pr["target_oracle"]["target"] == TARGET and pr["target_oracle"]["passed"] is False
    assert pr["P_terms"]["P_oracle"] == 0.0 and pr["P"] < STANDING_TRUST_P_MIN
    assert "title_check_deferred" not in pr["P_terms"]


def test_measure_target_passed_same_cycle_uses_target_verdict(title_calls):
    calls, log = title_calls
    _write(log, [_row(TARGET, passed=True, cycle_id="c1")])
    pr = _engine(_prop()).close_open_proposals("c2", {"aggregate": 0.8})[0]
    assert calls == []
    assert pr["title_check"] == "skipped_target_judged" and pr["target_oracle"]["passed"] is True
    assert pr["P_terms"]["P_oracle"] == 1.0


def test_measure_target_never_judged_runs_deferred_title_check(title_calls):
    calls, log = title_calls
    _write(log, [_row(TARGET, passed=True, cycle_id="old")])  # stale pass ≠ judged in c1
    pr = _engine(_prop()).close_open_proposals("c2", {"aggregate": 0.9})[0]
    assert len(calls) == 1 and calls[0]["mutation"] == TITLE and calls[0]["kind"] == "process"
    assert pr["title_check"] == "ran_deferred"
    assert pr["P_terms"]["P_oracle"] == 0.0 and pr["P"] < STANDING_TRUST_P_MIN
    # labelled as the fail-closed deferred check (its kill counts toward the cooldown)
    assert calls_sources[-1] == [ST.DEFERRED_TITLE_SOURCE]


def test_legacy_proposal_without_flag_is_not_rechecked(title_calls):
    calls, _log = title_calls
    p = _prop()
    p.pop("title_check")
    _engine(p).close_open_proposals("c2", {"aggregate": 0.9})
    assert calls == []


# ------------------------------------------------------------------ kill_rate consistency

class _V:
    def __init__(self, d):
        self._d = d

    def to_dict(self):
        return self._d


def test_kill_rate_same_in_fitness_and_oracle_json(tmp_path, monkeypatch):
    import colony.oracle as O
    from colony import fitness as F

    log = tmp_path / "oracle.jsonl"
    monkeypatch.setattr(O, "ORACLE_LOG", log)
    monkeypatch.setattr(O, "ORACLE_SYSTEM", tmp_path / "oracle.json")
    monkeypatch.setattr(O, "WITNESS_NOTE", tmp_path / "WITNESS_ORACLE.md")
    # 70 old passes then 30 kills: last-60 window (30/60=0.5) differs from full log (30/100)
    rows = [_row(f"m{i}", passed=True, cycle_id="c") for i in range(70)]
    rows += [_row(f"k{i}", passed=False, cycle_id="c") for i in range(29)]
    log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    O._persist(_V(_row("k_last", passed=False, cycle_id="c")))
    sysj = json.loads((tmp_path / "oracle.json").read_text())
    assert sysj["kill_rate"] == O.counts()["kill_rate"] == 0.3
    assert sysj["kill_rate_scope"] == "full_log"
    assert sysj["recent_window"]["kill_rate"] == 0.5 and sysj["recent_window"]["rows"] == 60
    assert F.oracle_kill_rate() == sysj["kill_rate"]
    # the scored sieve term is derived from that same raw rate
    assert F._oracle_kill_rate_term() == round(0.55 + 0.45 * (1.0 - abs(0.3 - 0.5) / 0.5), 4)


def test_sensors_trend_reads_legacy_rows_as_term():
    from colony.sensors import trends
    rows = [{"aggregate": 0.8, "kill_rate": 0.89},  # legacy: kill_rate held the term
            {"aggregate": 0.8, "kill_rate": 0.39, "kill_rate_term": 0.90}]
    tr = trends(rows)
    assert tr["kill_rate_term"]["last"] == 0.9 and tr["kill_rate_term"]["min"] == 0.89
    assert tr["kill_rate"]["last"] == 0.39 and tr["kill_rate"]["max"] == 0.39


# ------------------------------------------------------------------ uptake

def test_pure_recognition_guide_excluded_from_uptake(monkeypatch):
    import colony.lessons as L
    from colony.fitness import _lesson_uptake_term, is_pure_recognition_guide

    rec = {"id": "les_rec", "type": "human_guide", "tags": ["human_guide", "human_recognition"],
           "skill_bias": {}, "genome_prior": {}, "catalog_hint": {}}
    live = {"id": "les_live", "type": "human_guide", "tags": ["human_guide"],
            "skill_bias": {"geometer.gather": 0.1}}
    hintless_plain = {"id": "les_plain", "type": "human_guide", "tags": ["human_guide"]}
    rec_with_hint = dict(rec, id="les_rec2", catalog_hint={"prefer": ["x"]})
    assert is_pure_recognition_guide(rec) is True
    assert is_pure_recognition_guide(rec_with_hint) is False
    assert is_pure_recognition_guide(hintless_plain) is False

    monkeypatch.setattr(L, "load_lessons", lambda limit=120, **k: [])
    monkeypatch.setattr(L, "skill_bias_from_lessons", lambda lookback=40: {"geometer.gather": 0.1})
    monkeypatch.setattr(L, "load_human_guides", lambda: [live, rec])
    assert _lesson_uptake_term() == 1.0  # recognition is not an instruction → not in denominator
    # a hintless guide that is NOT pure recognition still counts against uptake
    monkeypatch.setattr(L, "load_human_guides", lambda: [live, rec, hintless_plain])
    assert _lesson_uptake_term() == 0.5
    # recognition guide that DOES carry a hint is measured like any guide
    monkeypatch.setattr(L, "load_human_guides", lambda: [live, rec_with_hint])
    assert _lesson_uptake_term() == 0.75
