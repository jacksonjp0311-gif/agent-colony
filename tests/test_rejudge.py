"""Re-judge checks killed by held_out_shift_not_applicable(no_literal_range).

A pass under the probe is enabled. No data headroom stays out. The authored cap
is not raised.
"""
import json

from colony.authoring import MAX_AUTHORED_TOTAL
from colony.trust.rejudge import LITERAL_RANGE_KILL, apply_rejudge, literal_range_kills

SRC = '''
def check_authored_keep_w1():
    return 1 == 1

def check_authored_out_w1():
    return 1 == 1

HARD_TIER_LEMMAS = [
    ("authored_keep_w1", check_authored_keep_w1, False),
    ("authored_out_w1", check_authored_out_w1, False),
    ("authored_on_w1", check_authored_on_w1, True),
]

def check_authored_on_w1():
    return 1 == 1
'''

# The catalog list is parsed from the assignment above. The on-check's function
# is defined after the list; that is fine for this test because the probe does
# not execute the source. insert_disabled needs the marker the real file uses
# only when a name is missing, so the missing-name tests use a file that has it.


def _row(name: str) -> str:
    return json.dumps({
        "decision": "revert",
        "mutation": name,
        "note": f"oracle=KILL kills=['held_out:{LITERAL_RANGE_KILL}', 'collective_kill']",
    })


def _history(*names: str) -> str:
    return "\n".join(_row(n) for n in names) + "\n"


def _probe(passes: set[str]):
    def probe(name: str, src: str) -> dict:
        assert name in src
        if name in passes:
            return {"ok": True, "status": "pass", "reason": "shift_window_pass", "applied": True}
        return {"ok": False, "status": "not_tested",
                "reason": "shift_not_applicable(no_data_headroom)", "applied": False}
    return probe


def test_history_lists_each_literal_range_kill_once():
    text = _history("authored_keep_w1", "authored_keep_w1", "authored_out_w1")
    text += json.dumps({"decision": "keep", "mutation": "authored_other_w1",
                        "note": LITERAL_RANGE_KILL}) + "\n"
    assert literal_range_kills(text) == ["authored_keep_w1", "authored_out_w1"]


def test_pass_is_enabled_and_headroom_stays_disabled():
    src, report = apply_rejudge(
        SRC, _history("authored_keep_w1", "authored_out_w1", "authored_on_w1"),
        _probe({"authored_keep_w1"}))
    by = {r["name"]: r for r in report}
    assert by["authored_keep_w1"]["action"] == "restored"
    assert by["authored_out_w1"]["action"] == "kept_out"
    assert by["authored_out_w1"]["headroom"] is True
    assert by["authored_on_w1"]["action"] == "already_enabled"
    assert '("authored_keep_w1", check_authored_keep_w1, True)' in src
    assert '("authored_out_w1", check_authored_out_w1, False)' in src
    assert '("authored_on_w1", check_authored_on_w1, True)' in src


def test_recovered_pass_is_inserted_and_headroom_is_not_kept(monkeypatch):
    monkeypatch.setattr("colony.trust.rejudge.MAX_AUTHORED_TOTAL", MAX_AUTHORED_TOTAL)
    body = "def check_authored_new_w1():\n    return 1 == 1\n"
    base = SRC.replace(
        "HARD_TIER_LEMMAS = [",
        "# Adversarial aliases used by Oracle theme held-out windows\nHARD_TIER_LEMMAS = [",
        1,
    )
    src, report = apply_rejudge(
        base,
        _history("authored_new_w1", "authored_gap_w1"),
        _probe({"authored_new_w1"}),
        recover={"authored_new_w1": body, "authored_gap_w1": "def check_authored_gap_w1():\n    return 1 == 1\n"},
    )
    by = {r["name"]: r for r in report}
    assert by["authored_new_w1"]["action"] == "restored"
    assert by["authored_gap_w1"]["action"] == "kept_out"
    assert "def check_authored_new_w1" in src
    assert '("authored_new_w1", check_authored_new_w1, True)' in src
    assert "authored_gap_w1" not in src


def test_authored_cap_blocks_a_new_name(monkeypatch):
    monkeypatch.setattr("colony.trust.rejudge.MAX_AUTHORED_TOTAL", 2)
    base = SRC.replace(
        "HARD_TIER_LEMMAS = [",
        "# Adversarial aliases used by Oracle theme held-out windows\nHARD_TIER_LEMMAS = [",
        1,
    )
    src, report = apply_rejudge(
        base, _history("authored_new_w1"), _probe({"authored_new_w1"}),
        recover={"authored_new_w1": "def check_authored_new_w1():\n    return 1 == 1\n"},
    )
    assert report == [{"name": "authored_new_w1", "action": "kept_out", "reason": "authored_cap"}]
    assert "authored_new_w1" not in src
    assert MAX_AUTHORED_TOTAL == 150
