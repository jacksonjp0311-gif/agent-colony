"""COLONY_FRONTIER=live: surviving self-chosen conjectures become authored checks (Oracle judges)."""
from __future__ import annotations

import ast

import colony.authoring as A
import colony.frontier_checks as FK

REG = {
    "a": {"kind": "divides", "lhs": "(n+n)", "rhs": "dbl((mu*rad))", "params": {}, "unknown": True,
          "sig": "f0461a58aa", "hunt_value": 1.0, "statement": "(n+n)(n) divides dbl((mu*rad))(n) for all n >= 1",
          "label": "conjecture surviving 59970 checks", "found_at": "t1"},
    "b": {"kind": "le", "lhs": "phi", "rhs": "n", "params": {}, "unknown": False, "sig": "11111111aa",
          "hunt_value": 0.0, "statement": "x", "label": "y", "found_at": "t0"},
    "c": {"kind": "le", "lhs": "pi", "rhs": "(one+tau)", "params": {}, "unknown": True, "falsified_later": True,
          "sig": "22222222aa", "hunt_value": 1.0, "statement": "z", "label": "falsified on re-test", "found_at": "t2"},
}


def test_candidates_only_live_surprises_not_yet_authored():
    c = FK.candidates(set(), state={"registry": REG})
    assert [x["name"] for x in c] == ["authored_frontier_divides_xf0461a58_w1"]
    assert FK.candidates({"authored_frontier_divides_xf0461a58_w1"}, state={"registry": REG}) == []
    ast.parse(c[0]["fn_src"])
    assert "__import__" not in c[0]["fn_src"] and "not proof" in c[0]["fn_src"]


def test_built_check_passes_the_authoring_guards():
    from colony.conjecture_desk import LEMMA_IMPL
    src = LEMMA_IMPL.read_text(encoding="utf-8")
    marker = A.INSERT_MARKER if A.INSERT_MARKER in src else A.FALLBACK_MARKER
    src = FK.ensure_bridges(src, marker)
    cand = FK.candidates(set(), state={"registry": REG})[0]
    new_src = A.insert_disabled(src, cand["name"], cand["fn_src"])
    res = A.verify_candidate(new_src, cand["name"], cand["verify_fns"])
    assert res["accepted"], res
    assert res["falsifiable"]["frontier_holds"] and res["counts"]["frontier_holds"] >= 3


def test_authoring_uses_frontier_candidates_only_when_live(monkeypatch):
    calls = []
    monkeypatch.setattr(FK, "candidates", lambda names, **k: calls.append(1) or [])
    monkeypatch.setattr(FK, "pending", lambda src: [])
    monkeypatch.setattr(A, "MAX_AUTHORED_TOTAL", 10 ** 6)   # independent of how many checks main holds
    # The coverage gate (hard score already pinned) returns before any builder. This test
    # is about the frontier live switch, so the pin is held off here. The gate itself stays.
    monkeypatch.setattr(A, "hard_pass_cannot_raise_score", lambda: False)
    monkeypatch.setenv("COLONY_FRONTIER", "shadow")
    A.author_checks(write=False, cycle_id="t")
    assert calls == []
    monkeypatch.setenv("COLONY_FRONTIER", "live")
    A.author_checks(write=False, cycle_id="t")
    assert calls == [1]


def test_old_registry_rewrites_are_rescreened():
    old = {"kind": "cong", "lhs": "D((digsum+lpf))", "rhs": "", "params": {"m": 2, "r": 0, "q": 2, "s": 0},
           "unknown": True, "sig": "33333333aa", "hunt_value": 1.0, "statement": "s", "label": "l", "found_at": "t"}
    assert not FK.still_new(old)
    assert FK.still_new(REG["a"])


def test_label_bucket_keeps_range_checks_out_of_the_two_labels():
    assert FK.label_bucket("known_in_principle(definition_parity)") == "known_in_principle"
    assert FK.label_bucket("known_in_principle(compositional)") == "known_in_principle"
    assert FK.label_bucket("implied_parts") == "trivial"
    assert FK.label_bucket("loose") == "trivial"
    assert FK.label_bucket("") is None
    assert FK.label_bucket(None) is None
    assert FK.label_bucket("confirmed on range") is None


def test_dry_run_lists_labels_and_does_not_retire(tmp_path, monkeypatch):
    reasons = {
        "authored_frontier_cong_a_w1": "known_in_principle(definition_parity)",
        "authored_frontier_cong_b_w1": "parity_rules",
        "authored_frontier_cong_c_w1": "",
        "authored_frontier_cong_d_w1": "confirmed on range",
        "authored_frontier_cong_e_w1": None,
    }
    monkeypatch.setattr(FK, "reason_now", lambda name, **k: reasons[name])
    rows = FK.dry_run_labels(list(reasons), lambda name: FK.reason_now(name))
    assert [(r["name"], r["label"]) for r in rows] == [
        ("authored_frontier_cong_a_w1", "known_in_principle"),
        ("authored_frontier_cong_b_w1", "trivial"),
    ]
    assert rows[1]["reason"] == "parity_rules"
    assert not (tmp_path / "retired_checks.json").exists()
    src = (
        "HARD_TIER_LEMMAS = [\n"
        '    ("authored_frontier_cong_a_w1", check_authored_frontier_cong_a_w1, True),\n'
        '    ("authored_sieve_x_w1", check_authored_sieve_x_w1, True),\n'
        "]\n"
    )
    assert FK.frontier_names(src) == ["authored_frontier_cong_a_w1"]


def test_reason_now_flags_a_rewrite_the_rescreen_rejects():
    old = {"kind": "cong", "lhs": "D((digsum+lpf))", "rhs": "", "params": {"m": 2, "r": 0, "q": 2, "s": 0},
           "unknown": True, "sig": "33333333aa", "hunt_value": 1.0, "statement": "s", "label": "l", "found_at": "t"}
    reason = FK.reason_now(FK.check_name(old), registry={"k": old})
    assert reason
    assert FK.label_bucket(reason) == "trivial"
    assert FK.still_new(old) is False


def test_dry_run_skips_a_name_whose_reader_fails():
    def boom(name):
        if name == "bad":
            raise RuntimeError("unreadable")
        return "implied_parts" if name == "good" else ""

    rows = FK.dry_run_labels(["bad", "good", "plain"], boom)
    assert rows == [{"name": "good", "label": "trivial", "reason": "implied_parts"}]


def test_frontier_links_proven_only_with_bridge_and_self_test():
    cand = FK.candidates(set(), state={"registry": REG})[0]
    fn = ast.parse(cand["fn_src"]).body[0]
    assert FK.self_test()["ok"]
    with_bridge = FK.BRIDGE_SRC + "\n" + cand["fn_src"]
    links = FK.frontier_links(fn, with_bridge)
    assert links and all(l["proven"] for l in links)
    assert not any(l["proven"] for l in FK.frontier_links(fn, cand["fn_src"]))   # bridge missing
    assert FK.frontier_links(ast.parse("def f():\n    return True\n").body[0], with_bridge) == []
