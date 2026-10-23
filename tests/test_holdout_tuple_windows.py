"""2026-10-23 (James-approved) fixes: tuple-window held-out shift, authoring holdback,
not-testable record, and the shortlist reading the proposal shard archive."""
import json
from unittest.mock import patch

from colony import frontier_checks as F
from colony import shortlist
from colony.trust.shifted_holdout import shifted_window_check

GENERIC = "def win_ok(a, b):\n    return all({pred} for n in range(a, b + 1))\n"


def _src(tmp_path, pred, wins="[(0, 99), (100, 199)]", extra=""):
    p = tmp_path / "entry.py"
    p.write_text(GENERIC.format(pred=pred) + extra +
                 f"HARD_TIER_LEMMAS = [('test', lambda: all(win_ok(a, b) for a, b in {wins}), True)]\n")
    return p


def test_tuple_windows_true_claim_passes_on_shifted_windows(tmp_path):
    res = shifted_window_check(_src(tmp_path, "n >= 0"), "test")
    assert res["status"] == "pass" and res["applied"] is True and res["ok"] is True
    assert res["shifted"][0]["to"][0][0] == 200          # strictly after the authored windows
    assert res["probes"] == 2


def test_tuple_windows_false_claim_fails(tmp_path):
    res = shifted_window_check(_src(tmp_path, "n < 200"), "test")
    assert res["status"] == "fail" and res["ok"] is False


def test_point_value_tuples_are_not_windows(tmp_path):
    p = tmp_path / "entry.py"
    p.write_text("def term(n):\n    return n * 2\n"
                 "HARD_TIER_LEMMAS = [('test', lambda: all(term(n) == v for n, v in [(10, 20), (11, 22)]), True)]\n")
    res = shifted_window_check(p, "test")
    assert res["status"] == "not_tested" and res["ok"] is False


def test_frontier_windows_without_data_headroom_stay_not_tested(tmp_path):
    claim = {"kind": "le", "lhs": "phi", "params": {}, "rhs": "n"}
    p = tmp_path / "entry.py"
    p.write_text(F.BRIDGE_SRC + "\nHARD_TIER_LEMMAS = [('test', lambda: all(type(c := frontier_holds("
                 f"{claim!r}, a, b)) is int and c > 0 for a, b in [(41, 100), (101, 160), (161, 220)]), True)]\n")
    with patch.object(F, "evaluable_hi", lambda r, hi: 230):   # tables end 10 past the windows
        res = shifted_window_check(p, "test")
    assert res["status"] == "not_tested" and res["ok"] is False
    assert res["reason"] == "shift_not_applicable(no_data_headroom)"


def _frontier_src(tmp_path, claim):
    p = tmp_path / "entry.py"
    p.write_text(F.BRIDGE_SRC + "\nHARD_TIER_LEMMAS = [('test', lambda: all(type(c := frontier_holds("
                 f"{claim!r}, a, b)) is int and c > 0 for a, b in [(41, 300), (301, 560), (561, 820)]), True)]\n")
    return p


def test_frontier_true_claim_passes_within_tables(tmp_path):
    res = shifted_window_check(_frontier_src(tmp_path, {"kind": "le", "lhs": "phi", "params": {}, "rhs": "n"}), "test")
    assert res["status"] == "pass", res
    assert res["shifted"][0]["to"][0][0] == 821


def test_frontier_false_claim_reports_counterexample(tmp_path):
    claim = {"kind": "le", "lhs": "pi", "params": {}, "rhs": "(one+tau)"}
    res = shifted_window_check(_frontier_src(tmp_path, claim), "test")
    assert res["status"] == "fail" and res["ok"] is False
    assert res["counterexample"]["reason"] == "counterexample"


def test_authoring_holds_back_final_slice(tmp_path):
    r = {"kind": "le", "lhs": "phi", "rhs": "n", "params": {}, "sig": "abcdef12", "statement": "phi <= n"}
    with patch.object(F, "data_end", lambda r: 1000):
        plan = F.window_plan(r, 1)
    assert plan["windows"] and plan["windows"][-1][1] <= 1000 - F.holdback(1000)
    assert plan["held_out"][1] == 1000 and plan["held_out"][1] - plan["held_out"][0] + 1 >= F.HOLDBACK_MIN


def test_no_headroom_claim_is_recorded_not_testable(tmp_path):
    r = {"kind": "le", "lhs": "phi", "rhs": "n", "params": {}, "sig": "abcdef12", "statement": "phi <= n"}
    out = tmp_path / "not_testable.json"
    with patch.object(F, "data_end", lambda r: 200), patch.object(F, "NOT_TESTABLE_PATH", out):
        assert F.build(r) is None
        first = out.read_text()
        assert F.build(r) is None
        assert out.read_text() == first                 # written only when it changes
    doc = json.loads(first)
    assert doc["records"]["abcdef12:w1"]["reason"] == "no_data_headroom"


def test_shortlist_reads_shard_after_inline(tmp_path):
    shard = tmp_path / "improvement_proposals.jsonl"
    shard.write_text(json.dumps({"id": "imp_old", "v": 1}) + "\nnot json\n" + json.dumps({"id": "imp_x", "v": 0}) + "\n")
    got = shortlist.shard_proposals(shard)
    assert [p["id"] for p in got] == ["imp_old", "imp_x"]
    assert shortlist.shard_proposals(tmp_path / "missing.jsonl") == []
