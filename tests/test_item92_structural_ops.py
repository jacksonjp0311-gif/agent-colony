"""Item 92: structural blueprint mutations beyond sizes/knobs (insert_front, move, merge, split,
inline_macro). Each candidate is an ordinary blueprint trial: strictly better than baseline AND
twin to keep, auto-revert otherwise (unchanged machinery)."""
from __future__ import annotations

from colony import self_build as SB

NO_EV: dict = {}


def _st(steps, macros=None):
    st = SB.empty_state()
    st["active"] = SB.make_blueprint(steps)
    if macros:
        st["macros"] = macros
    return st


def _by_op(st, op):
    return [c["steps"] for c in SB.candidates(st, NO_EV) if c["operator"] == op]


def test_insert_front_and_move_reorder():
    a, b, c = ({"component": n, "n": 1} for n in ("oeis_extra_pass", "oeis_replay_buffer", "new_data_extra_push"))
    st = _st([a, b, c])
    assert [c, a, b] in _by_op(st, "move") and [b, c, a] in _by_op(st, "move")
    fronts = _by_op(st, "insert_front")
    assert fronts and all(f[1:] == [a, b, c] for f in fronts)
    st2 = _st([a, b])
    assert [{"component": "oeis_form_router", "n": 1}, a, b] in _by_op(st2, "insert_front")


def test_merge_and_split():
    st = _st([{"component": "oeis_extra_pass", "n": 1}, {"component": "oeis_extra_pass", "n": 1}])
    assert [{"component": "oeis_extra_pass", "n": 2}] in _by_op(st, "merge")
    st2 = _st([{"component": "oeis_extra_pass", "n": 3}])
    assert [{"component": "oeis_extra_pass", "n": 2}, {"component": "oeis_extra_pass", "n": 1}] in _by_op(st2, "split")


def test_inline_macro():
    macros = {"macro_ab": {"steps": [{"component": "oeis_form_router", "n": 1},
                                     {"component": "oeis_beyond_bfile", "n": 1}]}}
    st = _st([{"component": "macro_ab", "n": 1}], macros)
    assert [{"component": "oeis_form_router", "n": 1}, {"component": "oeis_beyond_bfile", "n": 1}] in _by_op(st, "inline_macro")


def test_structural_children_valid_unique_and_bounded():
    st = _st([{"component": "oeis_extra_pass", "n": 2}, {"component": "oeis_replay_buffer", "n": 1},
              {"component": "new_data_extra_push", "n": 1}])
    cands = SB.candidates(st, NO_EV)
    sigs = [c["signature"] for c in cands]
    assert len(sigs) == len(set(sigs))  # no duplicate child under two operators
    for c in cands:
        ok, why = SB.validate(c)
        assert ok, why
    assert {"move", "split", "insert_front"} <= {c["operator"] for c in cands}


def test_learned_operator_stats_cover_structural_ops():
    rows = [{"event": "blueprint_trial_open", "blueprint": "b1", "operator": "move"},
            {"event": "blueprint_trial_close", "blueprint": "b1", "outcome": "reverted"}]
    stats = SB.operator_stats_from_log(rows)
    assert stats["move"] == {"tried": 1, "kept": 0, "reverted": 1}
    assert SB.operator_factor("move", stats) < SB.operator_factor("move", {})
