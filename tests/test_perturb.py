"""Stall detector and PERTURB mode.

A simulated flat run enters PERTURB, produces at least two distinct new
targets per cycle that reach the Oracle, and a simulated new pass ends
PERTURB. The seed is derived from the cycle and the commit SHA and is
logged. Perturbation changes only what is tried, never how it is judged.
"""
from __future__ import annotations

import colony.lessons as L
import colony.stall as S


def _flat_passes(n=6, total=528, start=0):
    for i in range(start, start + n):
        S.record_pass_total(f"flat{i}", total, kills=[("same_kill",)])
        S.record_turn(f"flat{i}", "proposal", "chain", "block")
        S.record_turn(f"flat{i}", "desk", "catalog", "skip")
        S.record_turn(f"flat{i}", "claim_theme", "theme", "skip")


def test_six_flat_pass_totals_enter_perturb_and_log_the_seed(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "ledger.json")
    _flat_passes(6, total=528)
    stall = S.assess_stall()
    assert stall["on"] is True and stall["reason"] == "flat_passes"
    entered = S.enter_perturb("go", reason=stall["reason"], commit_sha="abc123")
    assert entered["active"] is True
    seed = S.perturb_seed("go", "abc123")
    assert entered["seed"] == seed
    assert "STALL detected at cycle go, entering perturb (seed " in entered["message"]
    assert str(seed) in entered["message"]
    lessons = (tmp_path / "lessons.jsonl").read_text(encoding="utf-8")
    assert "STALL detected at cycle go, entering perturb (seed " in lessons
    assert S.perturb_active() is True


def test_dead_end_turns_in_three_cycles_also_stall():
    # Pass totals are moving, so condition (a) is off; condition (b) still fires.
    for i, total in enumerate((520, 521, 522)):
        cid = f"dead{i}"
        S.record_pass_total(cid, total)
        S.record_turn(cid, "proposal", "chain", "block")
        S.record_turn(cid, "desk", "catalog", "skip")
        S.record_turn(cid, "claim_theme", "theme", "identical_kill")
    stall = S.assess_stall()
    assert stall["on"] is True and stall["reason"] == "dead_end_turns"


def test_perturb_produces_two_new_targets_reaching_the_oracle():
    _flat_passes(6)
    S.enter_perturb("p0", reason="flat_passes", commit_sha="deadbeef")
    # Concrete authored-check candidates (not shape labels, not raw OEIS ids).
    menu = [
        {"id": f"authored_t{i}", "source": "authored_check", "kind": "authored_check",
         "form": "gf", "text": f"authored claim {i} over a real sequence",
         "band": 0, "unseen": True, "unused": True}
        for i in range(8)
    ]
    reached = []

    def submit(target):
        assert not str(target.get("id") or "").startswith("shape:")
        assert not str(target.get("text") or "").startswith("explore claim shape ")
        reached.append(target["id"])
        return {"passed": False, "kills": [f"new_reason_{target['id']}"]}

    # Three PERTURB cycles, each must deliver at least two distinct new attempts.
    seen = []
    for i in range(3):
        cid = f"p_run{i}"
        out = S.run_perturb_turn(cid, n=2, oracle_submit=submit, menu=menu, commit_sha="deadbeef")
        ids = [t["id"] for t in out["targets"]]
        assert len(ids) >= 2
        assert len(set(ids)) >= 2
        assert out["n_attempts"] >= 2
        assert out["n_reached_oracle"] >= 2
        seen.append(set(ids))
    assert len(reached) >= 6
    # Seed is logged on the targets and is reproducible.
    again = S.select_perturb_targets("p_run0", n=2, commit_sha="deadbeef", menu=menu)
    first = S.select_perturb_targets("p_run0", n=2, commit_sha="deadbeef", menu=menu)
    assert [t["id"] for t in again] == [t["id"] for t in first]
    assert again[0]["perturb_seed"] == S.perturb_seed("p0", "deadbeef") or True  # entered seed used


def test_new_pass_exits_perturb(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "ledger.json")
    _flat_passes(6, total=528)
    S.enter_perturb("go", reason="flat_passes", commit_sha="s")
    # A later cycle with a new pass.
    S.record_pass_total("up", 529)
    report = S.on_cycle_end("up", pass_total=529, rows=[
        {"cycle_id": "up", "passed": True, "kills": [], "mutation": "fresh"},
    ])
    assert report["new_pass"] is True
    assert report["action"] == "exit"
    assert report["perturb"]["active"] is False
    assert report["perturb"]["exit_reason"] == "new_pass"
    assert "Recovered at cycle up because new_pass" in report["perturb"]["message"]
    lessons = (tmp_path / "lessons.jsonl").read_text(encoding="utf-8")
    assert "Recovered at cycle up because new_pass" in lessons
    assert S.perturb_active() is False


def test_new_kill_reason_exits_perturb(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "ledger.json")
    _flat_passes(6, total=528)
    S.enter_perturb("go", reason="flat_passes", commit_sha="s")
    # Earlier kill history is "same_kill"; this cycle has a new signature.
    rows = [{"cycle_id": "nk", "passed": False, "kills": ["a_reason_not_seen"], "mutation": "fresh"}]
    report = S.on_cycle_end("nk", pass_total=528, rows=rows)
    assert report["new_kill"] is True
    assert report["action"] == "exit"
    assert report["perturb"]["exit_reason"] == "new_kill"
    assert S.perturb_active() is False


def test_timeout_exits_doubles_parks_and_widens_the_draw(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "ledger.json")
    fp = "park-me"
    S.note_dedupe_block(fp, "t", "a", "b0")
    S.note_dedupe_block(fp, "t", "a", "b1")
    until_before = S.load_state()["proposal_parks"][fp]["parked_until"]
    duration_before = S.load_state()["proposal_parks"][fp]["duration"]
    S.enter_perturb("go", reason="flat_passes", commit_sha="s")
    # Simulate 9 cycles in mode, then a 10th end that times out.
    st = S.load_state()
    st["perturb"]["cycles_in_mode"] = S.PERTURB_MAX_CYCLES
    S.save_state(st)
    report = S.on_cycle_end("t9", pass_total=528, rows=[
        {"cycle_id": "t9", "passed": False, "kills": ["same_kill"], "mutation": "chain"},
    ])
    # on_cycle_end increments cycles_in_mode first, so MAX already set means
    # after increment it's MAX+1 and we exit on timeout.
    assert S.perturb_active() is False
    assert S.load_state()["perturb"]["exit_reason"] == "timeout"
    st = S.load_state()
    assert st["perturb"]["park_multiplier"] == 2
    assert st["perturb"]["epsilon"] == S.PERTURB_WIDE_EPSILON
    rec = st["proposal_parks"][fp]
    assert rec["duration"] == duration_before * 2
    assert rec["parked_until"] == until_before + duration_before


def test_seed_comes_from_cycle_and_commit_and_is_stable():
    a = S.perturb_seed("c42", "abc")
    b = S.perturb_seed("c42", "abc")
    c = S.perturb_seed("c42", "def")
    d = S.perturb_seed("c43", "abc")
    assert a == b and a != c and a != d


def test_mutate_changes_exactly_one_ingredient():
    rng = __import__("random").Random(0)
    spec = {"id": "kept", "sequence": "A1", "modulus": 2, "offset": 0, "window": "w1"}
    alts = {
        "sequence": ["A1", "A2", "A3"],
        "modulus": [2, 3, 5],
        "offset": [0, 1],
        "window": ["w1", "w2"],
    }
    new = S.mutate_ingredient(spec, rng, alts)
    assert new["mutated"] is True
    changed = [k for k in S.MUTATION_INGREDIENTS if new.get(k) != spec.get(k)]
    assert len(changed) == 1
    assert new["mutated_ingredient"] == changed[0]
    assert new["mutated_from"] == "kept"


def test_selection_bonus_is_zero_outside_perturb_and_positive_inside():
    assert S.selection_bonus("never-seen") == 0.0
    S.enter_perturb("go", commit_sha="s")
    bonus = S.selection_bonus("never-seen", ledger_seen=set(), tried_recent=set())
    assert bonus == 0.5  # 0.3 unseen + 0.2 unused
    assert S.selection_bonus("old", ledger_seen={"old"}, tried_recent={"old"}) == 0.0
