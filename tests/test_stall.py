"""A flat Oracle run turns recovery on. A new pass or a new kill reason turns it off."""
from __future__ import annotations

import json

import colony.conjecture_desk as D
import colony.lessons as L
import colony.oracle as O
import colony.pilot_lane as PL
import colony.stall as S


def _row(cycle, *, passed=False, kills=None, mutation="theme_a"):
    return {
        "cycle_id": cycle,
        "passed": passed,
        "kills": [] if passed else (kills if kills is not None else ["held_out:already_saturated_no_harder_window"]),
        "mutation": mutation,
        "kind": "claim_theme",
    }


def _flat(n=6, kill=("held_out:already_saturated_no_harder_window",), mutation="theme_a"):
    return [_row(f"c{i}", kills=list(kill), mutation=mutation) for i in range(n)]


def test_flat_run_enters_recovery_and_a_pass_ends_it():
    rows = _flat(6)
    got = S.assess_recovery(rows)
    assert got["on"] is True and got["reason"] == "flat_passes"
    rows.append(_row("c6", passed=True, kills=[]))
    ended = S.assess_recovery(rows)
    assert ended["on"] is False and ended["reason"] == "new_pass"
    assert ended["pass_total"] == 1


def test_new_kill_reason_ends_recovery():
    rows = _flat(5)
    rows.append(_row("c5", kills=["a_reason_not_seen_in_the_flat_run"]))
    got = S.assess_recovery(rows)
    assert got["on"] is False and got["reason"] == "new_kill"


def test_fewer_than_six_cycles_stays_off():
    assert S.assess_recovery(_flat(5))["on"] is False


def test_recovery_skips_identical_kill_streak():
    rows = []
    for i in range(6):
        rows.append(_row(f"c{i}", kills=["same_kill"], mutation="stuck_lemma"))
        rows.append(_row(f"c{i}", kills=["same_kill"], mutation="stuck_lemma"))
    assert S.assess_recovery(rows)["on"] is True
    assert S.identical_kill_streak("stuck_lemma", rows) is True
    assert S.recovery_skips("stuck_lemma", rows) is True
    assert S.recovery_skips("other_lemma", rows) is False


def test_pick_mutation_skips_stalled_name(monkeypatch):
    rows = _flat(6, kill=("same_kill",), mutation="stuck_lemma") * 1
    # three identical failures inside the flat window
    rows = []
    for i in range(6):
        rows.append(_row(f"c{i}", kills=["same_kill"], mutation="stuck_lemma"))
    monkeypatch.setattr(S, "load_oracle_rows", lambda limit=2500: rows)
    ordered = [
        ("stuck_lemma", "hard_enable", "enable:stuck_lemma"),
        ("fresh_lemma", "hard_enable", "x"),
    ]
    cooldown = L.MutationCooldown(blocked={}, avoided=set(), penalties={})
    name, _kind, _snip, cooled = D.pick_mutation(ordered, cooldown=cooldown, lemma_src='("fresh_lemma", check, False),\n')
    assert name == "fresh_lemma"
    assert cooled["stuck_lemma"] == "recovery_identical_kills"


def test_empty_pilot_in_recovery_skips_the_lesson(tmp_path, monkeypatch):
    rows = _flat(6)
    monkeypatch.setattr(S, "load_oracle_rows", lambda limit=2500: rows)
    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "ledger.json")
    calls = []

    def _idle(cycle_id):
        calls.append(cycle_id)
        return {"purpose": "zero_credit_family", "chosen": [{"id": "t", "anum": "A1", "form": "gf"}]}

    import colony.oeis_conjectures as OC
    monkeypatch.setattr(OC, "idle_turn", _idle)
    row = PL.propose_pilot(name="empty_bias", kind="rsi_bias", body={}, cycle_id="c_rec")
    assert row["status"] == "suppressed"
    assert row["reason"] == "empty_rsi_bias_recovery"
    assert calls == ["c_rec"]
    assert not (tmp_path / "lessons.jsonl").exists()


def test_empty_pilot_outside_recovery_still_writes_the_lesson(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "load_oracle_rows", lambda limit=2500: _flat(2))
    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "ledger.json")
    monkeypatch.setattr(O, "ORACLE_LOG", tmp_path / "oracle.jsonl")
    row = PL.propose_pilot(name="empty_bias", kind="rsi_bias", body={}, cycle_id="c_norm")
    assert row["reason"] == "empty_rsi_bias"
    lessons = [json.loads(ln) for ln in (tmp_path / "lessons.jsonl").read_text(encoding="utf-8").splitlines()]
    assert lessons[-1]["type"] == "skip"
    assert "empty_rsi_bias" in lessons[-1]["tags"]
