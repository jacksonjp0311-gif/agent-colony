"""Speed-noise-aware keep/revert, same-day kill block, per-target novelty tally, small py window."""
import json

from colony import conjecture_desk as cd
from colony import instrument_checks as ic


def _b(score, speed, seconds=0.1, w=0.05):
    return {"score": score, "speed": speed, "speed_weight": w, "seconds": seconds}


def test_small_speed_change_is_neutralized():
    b, a, note = cd.speed_neutral_scores(_b(0.9071, 1.0), _b(0.9059, 0.976), "some_lemma")
    assert note.startswith("speed_noise") and abs(a - b) < 1e-9


def test_large_speed_change_still_counts():
    b, a, note = cd.speed_neutral_scores(_b(0.90, 1.0), _b(0.86, 0.2), "some_lemma")
    assert note == "" and a < b


def test_real_score_fall_not_hidden():
    b, a, _ = cd.speed_neutral_scores(_b(0.90, 1.0), _b(0.80, 1.0), "some_lemma")
    assert a < b - 0.05


def test_instrument_check_uses_own_budget():
    b, a, note = cd.speed_neutral_scores(_b(0.9071, 1.0, 0.12), _b(0.8945, 0.75, 0.2), "authored_sieve_x_w1")
    assert note.startswith("instrument_budget") and abs(a - b) < 1e-9
    b, a, note = cd.speed_neutral_scores(_b(0.9, 1.0, 0.1), _b(0.9, 0.0, 200.0), "authored_sieve_x_w1")
    assert note.startswith("instrument_over_budget") and a < b


def test_missing_speed_falls_back_to_raw():
    assert cd.speed_neutral_scores({"score": 0.5}, {"score": 0.4}, "x")[:2] == (0.5, 0.4)


def test_microbench_exposes_speed():
    import sys
    sys.path.insert(0, "society/benchmarks")
    import lemma_microbench as m
    r = m.run()
    assert 0.0 <= r["speed"] <= 1.0 and r["speed_weight"] in (0.0, 0.05)


def test_same_day_kill_blocks_target(tmp_path, monkeypatch):
    from colony import lessons, oracle, novelty_gate
    olog, glog = tmp_path / "o.jsonl", tmp_path / "g.jsonl"
    olog.write_text("\n".join(json.dumps(r) for r in [
        {"ts": "2026-10-17T01:00:00Z", "passed": False, "mutation": "authored_sieve_a_w1"},  # 9 PM ET 10/16
        {"ts": "2026-10-15T12:00:00Z", "passed": False, "mutation": "old_target"},
        {"ts": "2026-10-17T01:00:00Z", "passed": False, "mutation": "Chain `x_y` citing paper"},
        {"ts": "2026-10-17T01:00:00Z", "passed": True, "mutation": "good_one"},
    ]) + "\n")
    glog.write_text(json.dumps({"ts": "2026-10-17T02:00:00Z", "mutation": "authored_sieve_b_w1",
                                "kills": ["oracle_kill:['tentative_not_keep']"]}) + "\n")
    monkeypatch.setattr(oracle, "ORACLE_LOG", olog)
    monkeypatch.setattr(novelty_gate, "GATE_LOG", glog)
    got = lessons.same_day_killed_targets(now="2026-10-17T03:00:00")  # 11 PM ET 10/16
    assert got == {"authored_sieve_a_w1", "authored_sieve_b_w1"}
    assert lessons.same_day_killed_targets(now="2026-10-17T05:00:00") == set()  # 1 AM ET 10/17


def test_same_day_kill_feeds_cooldown_and_chain_block(monkeypatch):
    from colony import lessons
    monkeypatch.setattr(lessons, "same_day_killed_targets", lambda **k: {"authored_sieve_a_w1"})
    bt = lessons.blocked_themes()
    assert bt.get("authored_sieve_a_w1") in ("same_day_kill",) or "authored_sieve_a_w1" in bt
    assert lessons.theme_is_blocked("Chain `authored_sieve_a_w1` citing Some paper (cycle 9)")


def test_novelty_counts_per_target():
    from colony.novelty_gate import per_target_tally
    rows = [
        {"mutation": "authored_sieve_a_w1", "novel_to_commons": False},
        {"mutation": "Chain `authored_sieve_a_w1` citing P (cycle 3)", "novel_to_commons": False},
        {"mutation": "authored_sieve_a_w1", "novel_to_commons": False},
        {"mutation": "authored_sieve_b_w1", "novel_to_commons": True},
    ]
    assert per_target_tally(rows) == (1, 1)


def test_two_counter_python_window_small():
    c = ic.build("two_counter", (2,), 1)
    assert ic.PY_WINDOW <= 50_000
    assert "10050000" in c["expr"]


def test_promotion_sees_neutral_scores():
    from colony.trust.promotion import classify_promotion
    b, a, _ = cd.speed_neutral_scores(_b(0.8956, 0.77, 0.19), _b(0.9071, 1.0, 0.12), "authored_sieve_q_w1")
    pr = classify_promotion(before={"score": b, "n_hard_pass": 1, "ok": True},
                            after={"score": a, "n_hard_pass": 2, "ok": True}, oracle_passed=True,
                            challenger_blocked=False)
    assert pr["category"] != "internal_score"  # a speed blip is not a score rise
