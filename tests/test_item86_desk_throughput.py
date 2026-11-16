"""Item 86: shifted-window pre-screen on desk picks, extra hard_enable picks per cycle (self-mod only)."""
from __future__ import annotations

import textwrap

import colony.conjecture_desk as D
import colony.lessons as L
import colony.stall as S

LEMMA_SRC = textwrap.dedent('''
    def check_pair(m, n):
        return m + n >= 0

    def check_two_stmt() -> bool:
        windows = [(1, 2), (3, 4)]
        return all(check_pair(a, b) for a, b in windows)

    CATALOG = [
        ("shiftable_ok", lambda: all(check_pair(m, 1) for m in range(0, 40)), False),
        ("two_stmt_window", check_two_stmt, False),
    ]
''')


def _cooldown():
    return L.MutationCooldown(blocked={}, avoided=set(), penalties={})


def test_shift_prescreen_flags_only_structurally_untestable_entries(tmp_path):
    p = tmp_path / "lemma_impl.py"
    p.write_text(LEMMA_SRC)
    assert D.shift_prescreen_reason("two_stmt_window", src_path=p) == \
        "prescreen_shift:shift_not_applicable(entry_shape)"
    assert D.shift_prescreen_reason("shiftable_ok", src_path=p) is None


def test_pick_skips_prescreened_entry_and_takes_next(monkeypatch):
    monkeypatch.setattr(S, "load_oracle_rows", lambda limit=2500: [])
    monkeypatch.setattr(D, "shift_prescreen_reason",
                        lambda name, src_path=None: "prescreen_shift:x" if name == "dead" else None)
    ordered = [("dead", "hard_enable", "x"), ("alive", "hard_enable", "x")]
    src = '("dead", f, False),\n("alive", g, False),\n'
    name, _k, _s, cooled = D.pick_mutation(ordered, cooldown=_cooldown(), lemma_src=src, shift_prescreen=True)
    assert name == "alive" and cooled["dead"] == "prescreen_shift:x"
    # Off (control arm): unchanged order.
    name, *_ = D.pick_mutation(ordered, cooldown=_cooldown(), lemma_src=src, shift_prescreen=False)
    assert name == "dead"


def test_only_kinds_restricts_extra_picks(monkeypatch):
    monkeypatch.setattr(S, "load_oracle_rows", lambda limit=2500: [])
    ordered = [("pad", "easy_pad", "x"), ("hard", "hard_enable", "x")]
    name, kind, *_ = D.pick_mutation(ordered, cooldown=_cooldown(), lemma_src='("hard", f, False)\n',
                                     only_kinds=("hard_enable",))
    assert (name, kind) == ("hard", "hard_enable")


def _fake(seq, calls):
    def improve_once(*, ledger=None, cycle_id="", extra_pick=False, force_mutation=None):
        calls.append(extra_pick)
        dec, kind = seq[len(calls) - 1]
        return D.ConjectureResult(ts="t", decision=dec, before_score=1, after_score=1, delta=0,
                                  mutation=f"m{len(calls)}", kind=kind)
    return improve_once


def test_extra_picks_follow_a_pass_and_stop_on_first_non_keep(monkeypatch):
    monkeypatch.delenv("COLONY_ARM", raising=False)
    monkeypatch.setenv("COLONY_SELF_MOD", "on")
    calls = []
    monkeypatch.setattr(D, "improve_once", _fake([("keep", "hard_enable"), ("revert", "hard_enable"),
                                                  ("keep", "hard_enable")], calls))
    r = D.run_from_growth("c1")
    assert calls == [False, True] and r.mutation == "m1"
    assert r.extras == [{"mutation": "m2", "kind": "hard_enable", "decision": "revert"}]


def test_extra_picks_capped(monkeypatch):
    monkeypatch.delenv("COLONY_ARM", raising=False)
    monkeypatch.setenv("COLONY_SELF_MOD", "on")
    calls = []
    monkeypatch.setattr(D, "improve_once", _fake([("keep", "hard_enable")] * 9, calls))
    r = D.run_from_growth("c1")
    assert len(calls) == 1 + D.DESK_EXTRA_PICKS and len(r.extras) == D.DESK_EXTRA_PICKS


def test_no_extra_pick_after_kill_or_non_hard_kind(monkeypatch):
    monkeypatch.delenv("COLONY_ARM", raising=False)
    for seq in ([("revert", "hard_enable")], [("keep", "easy_pad")], [("skip", "")]):
        calls = []
        monkeypatch.setattr(D, "improve_once", _fake(seq + [("keep", "hard_enable")] * 3, calls))
        assert D.run_from_growth("c").extras == [] and calls == [False]


def test_control_arm_takes_one_pick(monkeypatch):
    monkeypatch.setenv("COLONY_ARM", "control")
    calls = []
    monkeypatch.setattr(D, "improve_once", _fake([("keep", "hard_enable")] * 4, calls))
    assert D.run_from_growth("c").extras == [] and calls == [False]
    assert D._self_mod() is False


def test_extra_pick_also_follows_an_oracle_pass_the_desk_reverted(monkeypatch):
    monkeypatch.delenv("COLONY_ARM", raising=False)
    monkeypatch.setenv("COLONY_SELF_MOD", "on")
    calls = []

    def improve_once(*, ledger=None, cycle_id="", extra_pick=False, force_mutation=None):
        calls.append(extra_pick)
        note = "| oracle=PASS fitness_credit=True | coverage_slot_refused" if len(calls) == 1 else "| oracle=KILL"
        return D.ConjectureResult(ts="t", decision="revert", before_score=1, after_score=1, delta=0,
                                  mutation=f"m{len(calls)}", kind="hard_enable", note=note)
    monkeypatch.setattr(D, "improve_once", improve_once)
    r = D.run_from_growth("c")
    assert calls == [False, True] and r.extras[0]["mutation"] == "m2"
