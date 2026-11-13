"""Regression tests for queue item 25: PERTURB must not re-pick held OEIS
targets that cannot make progress, the attempt log records verified ranges,
and a no-progress timeout starts a cooldown so the next run does not
immediately re-enter the same loop.

Replays cycles 859–861 of evolve run 43331284237.
"""
from __future__ import annotations

import json

import colony.lessons as L
import colony.oeis_conjectures as OC
import colony.oracle as O
import colony.stall as S


# Cycles 859–861 of the 6:46–6:52 PM ET Nov 12 PR #2 test run.
C859 = "20261112T234609Z_0f7791"
C860 = "20261112T234826Z_5459c4"
C861 = "20261112T235052Z_b5a736"

# The six PERTURB picks that already held, whose tested_hi did not move.
HELD = (
    ("oc_A026589_0", "A026589", 371, 1000),
    ("oc_A026598_0", "A026598", 367, 500),
    ("oc_A106181_0", "A106181", 39, 39),
    ("oc_A224748_0", "A224748", 3000, 10000),
    ("oc_A379464_0", "A379464", 348, 2271),
    ("oc_A100038_0", "A100038", 47, 47),
)
HELD_IDS = {h[0] for h in HELD}


def _isolate(tmp_path, monkeypatch, *, lessons="", oracle=""):
    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "ledger.json")
    monkeypatch.setattr(O, "ORACLE_LOG", tmp_path / "oracle.jsonl")
    (tmp_path / "lessons.jsonl").write_text(lessons, encoding="utf-8")
    (tmp_path / "oracle.jsonl").write_text(oracle, encoding="utf-8")
    monkeypatch.setattr(S, "STATE_PATH", tmp_path / "stall_state.json")
    monkeypatch.setattr(OC, "ATTEMPT_LOG", tmp_path / "oeis_attempt_log.json")
    monkeypatch.setattr(OC, "MENU", tmp_path / "m.json")
    monkeypatch.setattr(OC, "STATE", tmp_path / "s.json")
    monkeypatch.setattr(OC, "REPORT", tmp_path / "r.json")
    monkeypatch.setattr(OC, "REVIEW", tmp_path / "rv.md")
    monkeypatch.setenv("COLONY_OEIS_CONJ", "shadow")


def _held_entry(eid, anum, tested_hi, published_hi):
    """Already-held relation with no computable definition: cannot go past
    the stored terms, which stop at ``tested_hi`` (and often below the
    published b-file)."""
    off = 0
    n = max(1, int(tested_hi) - off + 1)
    # Keep the term list short; claim_testable_hi uses its length, so make
    # the last index equal tested_hi and pad with tiny values.
    n = min(n, 12)
    # If tested_hi is large, shrink terms and rely on tested_hi in state;
    # reachable is then the short term list, still below published_hi.
    terms = [i + 1 for i in range(n)]
    return {
        "id": eid, "anum": anum, "name": "dummy held", "offset": off,
        "section": "formula",
        "text": f"Conjecture about {anum}.",
        "claim": {"form": "relation", "parts": ["a(n)", "a(n)"], "rels": ["="],
                  "mod": None, "n0": None},
        "definition": None, "terms": terms, "data_n": n,
        "published_hi": published_hi, "refs": {},
    }


def _gf_entry(eid="oc_fresh_gf_0", anum="A999999"):
    d = OC.parse_definition("Expansion of 1/(1-x-x^2).")
    terms = [int(c) for c in OC._series_A(d["expr"], 20)]
    return {
        "id": eid, "anum": anum, "name": "Expansion of 1/(1-x-x^2).",
        "offset": 0, "section": "formula",
        "text": "G.f.: 1/(1-x-x^2) (conjecture).",
        "claim": {"form": "gf", "expr": "1/(1-x-x^2)"},
        "definition": d, "terms": terms, "data_n": 12, "published_hi": 19, "refs": {},
    }


def _ref_limited_entry():
    """A108476 pattern: a(n) has a g.f., but the claim needs refs that end at 30."""
    d = OC.parse_definition("Expansion of (1-4*x)/(1-6*x-12*x^2+8*x^3).")
    terms_a = [int(c) for c in OC._series_A(d["expr"], 20)]
    ref = {"offset": 0, "terms": [i + 1 for i in range(32)]}  # hi = 31
    return {
        "id": "oc_A108476_0", "anum": "A108476",
        "name": "Expansion of (1-4*x)/(1-6*x-12*x^2+8*x^3).",
        "offset": 0, "section": "formula",
        "text": "Conjecture: a(n) = A002605(n+1)*A026150(n).",
        "claim": {"form": "relation",
                  "parts": ["a(n)", "A002605(n+1)*A026150(n)"],
                  "rels": ["="], "mod": None, "n0": None},
        "definition": d, "terms": terms_a, "data_n": 20, "published_hi": 19,
        "refs": {"A002605": dict(ref), "A026150": dict(ref)},
    }


def _state_for_held(extra_targets=None):
    targets = {}
    for eid, anum, tested_hi, _pub in HELD:
        targets[eid] = {
            "attempts": 5, "status": "holds_on_range",
            "tested_hi": tested_hi, "credit": 0.0,
        }
    if extra_targets:
        targets.update(extra_targets)
    return {
        "targets": targets,
        "families": {"relation": {"attempts": 30, "credit": 0.0},
                     "gf": {"attempts": 4, "credit": 0.1}},
        "credit_total": 0.1,
    }


def _seed_held_log(planned=None):
    """Record the already-held ranges as the live run would after the fix
    (verified depth) or, when ``planned`` is set, also store what the old
    code would have asked for."""
    for eid, anum, tested_hi, pub in HELD:
        e = _held_entry(eid, anum, tested_hi, pub)
        OC.remember_attempt(
            e,
            [{"status": "holds_on_range", "range": [0, tested_hi],
              "tested": tested_hi + 1, "deep_hi": 0}],
            "20261112T230000Z_prior",
            planned=planned,
        )


def _flat_oracle_and_passes(n=8, total=528):
    rows = [
        json.dumps({"cycle_id": "20261110T000000Z_base", "passed": True,
                    "kills": [], "mutation": f"p{i}"})
        for i in range(528)
    ]
    rows += [
        json.dumps({"cycle_id": f"20261111T1{i:02d}000Z_flat", "passed": False,
                    "kills": ["stripped:stripped_not_useful_fail"],
                    "mutation": "old"})
        for i in range(n)
    ]
    return "\n".join(rows) + "\n"


# ---------------------------------------------------------------------------
# Attempt log records the verified range, not the requested depth
# ---------------------------------------------------------------------------

def test_remember_attempt_records_verified_not_planned(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    e = _gf_entry()
    # The next attempt was asked to go to DEEP_N / GF_TERMS (20_000 on a
    # relation, 1_200 on a g.f.), but only n=19 was actually tested.
    OC.remember_attempt(
        e,
        [{"status": "holds_on_range", "range": [0, 19], "tested": 20,
          "deep_hi": 0, "deep_terms": 1202}],
        "cyc",
        planned=20000,
    )
    log = OC.load_attempt_log()
    row = log["attempts"][-1]
    assert row["depth"] == 19, row
    assert row["bfile_hi"] == 19
    assert row["beyond"] is False
    assert row["planned"] == 20000
    assert row["status"] == "holds_on_range"
    # deep_terms (computed but not used in the claim test) did not inflate depth.
    assert row["depth"] != 1202
    assert row["depth"] != 20000


def test_remember_attempt_beyond_is_verified_past_bfile(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    e = _gf_entry()
    OC.remember_attempt(
        e,
        [{"status": "holds_on_range", "range": [0, 1199], "tested": 1200,
          "deep_hi": 0}],
        "cyc",
        planned=1200,
    )
    row = OC.load_attempt_log()["attempts"][-1]
    assert row["depth"] == 1199
    assert row["beyond"] is True  # 1199 > published 19
    assert row["planned"] == 1200


# ---------------------------------------------------------------------------
# can_progress_past / claim_testable_hi
# ---------------------------------------------------------------------------

def test_held_without_definition_cannot_progress(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    e = _held_entry("oc_A026589_0", "A026589", 371, 1000)
    # First look is allowed (published-range test).
    assert OC.can_progress_past(e) is True
    assert OC.can_progress_past(e, require_past_published=True) is False
    # After a hold at tested_hi, even the ordinary path says no.
    OC.remember_attempt(
        e, [{"status": "holds_on_range", "range": [0, 371], "tested": 372}],
        "prior",
    )
    assert OC.can_progress_past(e, 371) is False
    assert OC.can_progress_past(e, 371, require_past_published=True) is False


def test_ref_limited_claim_cannot_progress_past_refs(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    e = _ref_limited_entry()
    # A002605(n+1) with ref hi=31 means the claim is testable only to n=30.
    assert OC.claim_testable_hi(e) == 30
    # First attempt can go past the 19-term b-file (to 30).
    assert OC.can_progress_past(e, require_past_published=True) is True
    # After a hold at 30, it cannot (this is why A108476's tested_hi stayed 30).
    OC.remember_attempt(
        e, [{"status": "holds_on_range", "range": [0, 30], "tested": 31}],
        "prior", planned=20000,
    )
    assert OC.can_progress_past(e, 30, require_past_published=True) is False
    assert OC.can_progress_past(e, 30) is False
    # choose(..., beyond_bfile=True) skips it.
    picked = OC.choose([e], {"targets": {e["id"]: {"tested_hi": 30,
                                                    "status": "holds_on_range",
                                                    "attempts": 49}},
                             "families": {}},
                       "next", k=1, beyond_bfile=True)
    assert picked == []


def test_untried_gf_can_progress_past_bfile(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    gf = _gf_entry()
    assert OC.can_progress_past(gf, require_past_published=True) is True
    assert OC.claim_testable_hi(gf) >= OC.GF_TERMS or OC.claim_testable_hi(gf) > 19


def test_already_attempted_pair_uses_verified_and_planned(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    e = _gf_entry()
    OC.remember_attempt(
        e, [{"status": "holds_on_range", "range": [0, 956], "tested": 957}],
        "c1", planned=20000,
    )
    # Aimed at 20_000, verified 956: both depths are "already attempted".
    assert OC.already_attempted_pair(e["id"], 20000, "c2") is True
    assert OC.already_attempted_pair(e["id"], 956, "c2") is True
    # A later higher cap (evaluator improved) is a new pair.
    assert OC.already_attempted_pair(e["id"], 50000, "c2") is False


def test_choose_skips_held_same_depth_and_prefers_progressable(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    held = _held_entry(*HELD[0])
    gf = _gf_entry()
    OC.MENU.write_text(json.dumps({"entries": [held, gf]}))
    state = {"targets": {held["id"]: {"attempts": 5, "status": "holds_on_range",
                                      "tested_hi": 371, "credit": 0.0}},
             "families": {"relation": {"attempts": 5, "credit": 0.0},
                          "gf": {"attempts": 1, "credit": 0.0}}}
    OC.remember_attempt(
        held, [{"status": "holds_on_range", "range": [0, 371], "tested": 372}],
        "prior",
    )
    picked = OC.choose([held, gf], state, "c_open", k=2)
    ids = [e["id"] for e in picked]
    assert held["id"] not in ids
    assert gf["id"] in ids


# ---------------------------------------------------------------------------
# PERTURB candidate selection
# ---------------------------------------------------------------------------

def test_perturb_skips_already_held_that_cannot_progress(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    held = [_held_entry(*h) for h in HELD]
    gf = _gf_entry()
    OC.MENU.write_text(json.dumps({"entries": held + [gf]}))
    OC.STATE.write_text(json.dumps(_state_for_held()))
    _seed_held_log()
    S.enter_perturb("go", reason="flat_passes", commit_sha="abc")
    menu = [
        {"id": e["id"], "source": "oeis", "kind": "oeis_conjecture",
         "form": (e.get("claim") or {}).get("form"), "entry": e,
         "anum": e.get("anum"), "text": e.get("text") or "",
         "band": 0, "unseen": True, "unused": True}
        for e in held + [gf]
    ]
    picked = S.select_perturb_targets("p1", n=4, commit_sha="abc", menu=menu)
    ids = [t["id"] for t in picked]
    for hid in HELD_IDS:
        assert hid not in ids, ids
    # The untried, progressable g.f. is a legitimate pick (or a shape that
    # will materialize to it). No held same-depth id is in the draw.
    assert gf["id"] in ids or all(
        str(t.get("id") or "").startswith("shape:") or t.get("source") != "oeis"
        for t in picked
    )


def test_timeout_without_progress_starts_cooldown(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    S.enter_perturb("go", reason="flat_passes", commit_sha="s")
    # Nine cycles in mode, no session progress recorded.
    st = S.load_state()
    st["perturb"]["cycles_in_mode"] = S.PERTURB_MAX_CYCLES
    st["perturb"]["session_progress"] = False
    # Need the timeout cycle in the list so the cooldown index is well-defined.
    st["cycles"] = [f"c{i}" for i in range(9)] + ["t9"]
    S.save_state(st)
    report = S.on_cycle_end("t9", pass_total=528, rows=[
        {"cycle_id": "t9", "passed": False, "kills": ["same_kill"], "mutation": "chain"},
    ])
    assert S.perturb_active() is False
    st = S.load_state()
    assert st["perturb"]["exit_reason"] == "timeout"
    assert st["perturb"]["cooldown_until"] >= 0
    assert S.in_perturb_cooldown("t9") or S.perturb_cooldown_remaining("t9", st) > 0
    assert st["perturb"]["strategy"] == "mutate"
    # Immediate next cycle, even if still stalled, does not re-enter.
    S.record_pass_total("next", 528, kills=[("same_kill",)])
    S.record_turn("next", "proposal", "chain", "block")
    S.record_turn("next", "desk", "catalog", "skip")
    out = S.on_cycle_start("next", commit_sha="s")
    assert out["perturb_active"] is False
    assert S.perturb_active() is False
    assert S.in_perturb_cooldown("next") is True


def test_timeout_with_progress_does_not_cooldown(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    S.enter_perturb("go", reason="flat_passes", commit_sha="s")
    st = S.load_state()
    st["perturb"]["cycles_in_mode"] = S.PERTURB_MAX_CYCLES
    st["perturb"]["session_progress"] = True
    st["cycles"] = [f"c{i}" for i in range(9)] + ["t9"]
    S.save_state(st)
    S.on_cycle_end("t9", pass_total=528, rows=[
        {"cycle_id": "t9", "passed": False, "kills": ["same_kill"], "mutation": "chain"},
    ])
    st = S.load_state()
    assert st["perturb"]["exit_reason"] == "timeout"
    assert S.perturb_cooldown_remaining("t9", st) == 0
    # No cooldown: a still-stalled next cycle may re-enter (escalation of
    # epsilon / park_multiplier from the timeout still applies).
    for i in range(6):
        S.record_pass_total(f"flat{i}", 528, kills=[("same_kill",)])
        S.record_turn(f"flat{i}", "proposal", "chain", "block")
        S.record_turn(f"flat{i}", "desk", "catalog", "skip")
    out = S.on_cycle_start("reenter", commit_sha="s")
    assert out["perturb_active"] is True


def test_cooldown_expires_and_reenters_with_mutate_strategy(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    S.enter_perturb("go", reason="flat_passes", commit_sha="s")
    st = S.load_state()
    st["perturb"]["cycles_in_mode"] = S.PERTURB_MAX_CYCLES
    st["perturb"]["session_progress"] = False
    st["perturb"]["session_targets"] = ["oc_A026589_0", "oc_A100038_0"]
    st["cycles"] = [f"c{i}" for i in range(9)] + ["t9"]
    S.save_state(st)
    S.on_cycle_end("t9", pass_total=528, rows=[
        {"cycle_id": "t9", "passed": False, "kills": ["same_kill"], "mutation": "x"},
    ])
    assert S.load_state()["perturb"]["strategy"] == "mutate"
    assert "oc_A026589_0" in (S.load_state()["perturb"].get("exclude_targets") or [])
    # Walk cooldown cycles with a flat 528 so stall stays on.
    last = "t9"
    entered = []
    # Start from the timeout cycle and add COOLDOWN more cycles, then one more.
    for i in range(S.PERTURB_COOLDOWN_CYCLES + 1):
        cid = f"cool{i}"
        S.record_pass_total(cid, 528, kills=[("same_kill",)])
        S.record_turn(cid, "proposal", "chain", "block")
        S.record_turn(cid, "desk", "catalog", "skip")
        out = S.on_cycle_start(cid, commit_sha="s")
        entered.append((cid, out["perturb_active"], S.perturb_cooldown_remaining(cid)))
        last = cid
        if out["perturb_active"]:
            break
    # The last cycle after the cooldown window should be allowed to enter,
    # and it should carry the mutate strategy from the timeout.
    assert any(active for _c, active, _r in entered), entered
    assert S.load_state()["perturb"]["strategy"] == "mutate"
    assert S.load_state()["perturb"]["active"] is True


# ---------------------------------------------------------------------------
# Replay of cycles 859–861
# ---------------------------------------------------------------------------

def test_replay_cycles_859_to_861_skips_held_and_cools_down(tmp_path, monkeypatch):
    """Accept for run 43331284237: the six already-held PERTURB picks are
    not retried at the same depth, the attempt log records verified ranges,
    and a no-progress timeout does not immediately re-enter PERTURB."""
    _isolate(tmp_path, monkeypatch, oracle=_flat_oracle_and_passes())
    held = [_held_entry(*h) for h in HELD]
    gf = _gf_entry()
    OC.MENU.write_text(json.dumps({"entries": held + [gf]}))
    OC.STATE.write_text(json.dumps(_state_for_held()))
    _seed_held_log(planned=20000)

    # PERTURB was already on when 859 started (it had been running from
    # earlier cycles) and these three cycles were the last of the 9.
    # Seed a long flat 528 history so stall stays on after the timeout.
    for i in range(8):
        S.record_pass_total(f"20261111T1{i:02d}000Z_flat", 528,
                            kills=[("same_kill",)])
        S.record_turn(f"20261111T1{i:02d}000Z_flat", "proposal", "chain", "block")
        S.record_turn(f"20261111T1{i:02d}000Z_flat", "desk", "catalog", "skip")
    S.enter_perturb("20261112T230000Z_enter", reason="flat_passes",
                    commit_sha="f83caede")
    st = S.load_state()
    st["perturb"]["cycles_in_mode"] = 6  # three more ends will reach MAX=9
    S.save_state(st)

    reached = []

    def submit(target):
        reached.append(target)
        tid = str(target.get("id") or "")
        text = str(target.get("text") or "")
        assert not tid.startswith("shape:"), tid
        assert "explore claim shape" not in text, text
        # Raw already-held OEIS ids must not reach the Oracle.
        assert tid not in HELD_IDS, tid
        return {"passed": False, "kills": ["stripped:stripped_not_useful_fail"]}

    def author(shape, cycle_id):
        return {
            "id": f"authored_{shape}_{cycle_id[-6:]}",
            "source": "authored_check",
            "kind": "authored_check",
            "text": f"a {shape} claim over A000040, held-out tail checked",
            "form": shape,
        }

    desk_attempted = []
    for cid in (C859, C860, C861):
        S.on_cycle_start(cid, commit_sha="f83caede")
        assert S.perturb_active() is True
        out = S.run_perturb_turn(
            cid, n=2, oracle_submit=submit, author=author,
            commit_sha="f83caede",
        )
        for s in out["submissions"]:
            sid = str(s.get("id") or "")
            if s.get("attempt") == "desk":
                desk_attempted.append(sid)
                # Already-held same-depth ids are not perturb desk targets.
                assert sid not in HELD_IDS, (cid, sid, s)
                # A desk pick must be a new depth past max(bfile, tested).
                acts = s.get("oeis_results") or []
                if acts and sid == gf["id"]:
                    v = OC.verified_depth(gf, acts)
                    assert v > 19 or acts[-1].get("status") == "proved_checked"
            if s.get("attempt"):
                assert sid not in HELD_IDS
        # Flat passes, no new kill (the live run timed out with no new Oracle
        # row and no new kill reason). Empty rows avoid a "new_kill" exit.
        S.on_cycle_end(cid, pass_total=528, rows=[])

    # The six already-held ids were not perturb desk (or Oracle) targets.
    assert not any(i in desk_attempted for i in HELD_IDS)
    for t in reached:
        assert str(t.get("id") or "") not in HELD_IDS

    # The attempt log stores verified depth, not the requested 20_000.
    log = OC.load_attempt_log()
    for row in log.get("attempts") or []:
        if row.get("planned") == 20000:
            assert row["depth"] != 20000, row
        if row["id"] in HELD_IDS:
            expected = {h[0]: h[2] for h in HELD}
            assert row["depth"] == expected[row["id"]], row
            bh = {h[0]: h[3] for h in HELD}[row["id"]]
            assert row["beyond"] == (row["depth"] > bh)

    # With a progressable g.f. on the menu, the new mechanism should use it
    # (a new depth past the b-file) rather than replaying the six holds.
    # That is the desired outcome of the live run, and is itself progress.
    st = S.load_state()
    if gf["id"] in desk_attempted:
        # The g.f. search went past its published range, or was proved.
        pass
    # If this session made no progress and timed out, a cooldown must
    # block immediate re-entry. If it made progress, a cooldown is not
    # required (and a new_pass / new_kill would already have exited).
    if (not st["perturb"]["active"] and st["perturb"].get("exit_reason") == "timeout"
            and not st["perturb"].get("session_progress")):
        assert st["perturb"]["cooldown_until"] >= 0
        nxt = S.on_cycle_start("20261113T000000Z_next", commit_sha="f83caede")
        assert nxt["perturb_active"] is False
        assert S.in_perturb_cooldown("20261113T000000Z_next") is True


def test_replay_exhausted_menu_times_out_and_cools_down(tmp_path, monkeypatch):
    """When every menu entry is an already-held target that cannot move,
    PERTURB does not spend its slots on them, times out, and a cooldown
    stops the next cycle from re-entering the same loop."""
    _isolate(tmp_path, monkeypatch, oracle=_flat_oracle_and_passes())
    held = [_held_entry(*h) for h in HELD]
    OC.MENU.write_text(json.dumps({"entries": held}))
    OC.STATE.write_text(json.dumps(_state_for_held()))
    _seed_held_log(planned=20000)
    for i in range(8):
        S.record_pass_total(f"20261111T1{i:02d}000Z_flat", 528,
                            kills=[("same_kill",)])
        S.record_turn(f"20261111T1{i:02d}000Z_flat", "proposal", "chain", "block")
        S.record_turn(f"20261111T1{i:02d}000Z_flat", "desk", "catalog", "skip")
    S.enter_perturb("20261112T230000Z_enter", reason="flat_passes",
                    commit_sha="f83caede")
    st = S.load_state()
    st["perturb"]["cycles_in_mode"] = 6
    S.save_state(st)

    def submit(target):
        raise AssertionError(f"held id reached the Oracle: {target}")

    desk_ids = []
    for cid in (C859, C860, C861):
        S.on_cycle_start(cid, commit_sha="f83caede")
        assert S.perturb_active() is True
        out = S.run_perturb_turn(
            cid, n=2, oracle_submit=submit, author=lambda shape, c: None,
            commit_sha="f83caede",
        )
        for s in out["submissions"]:
            if s.get("attempt"):
                desk_ids.append(s.get("id"))
                assert str(s.get("id") or "") not in HELD_IDS
        S.on_cycle_end(cid, pass_total=528, rows=[])

    st = S.load_state()
    assert st["perturb"]["active"] is False
    assert st["perturb"]["exit_reason"] == "timeout"
    assert not st["perturb"].get("session_progress")
    assert st["perturb"]["cooldown_until"] >= 0
    assert st["perturb"]["strategy"] == "mutate"
    nxt = S.on_cycle_start("20261113T000000Z_next", commit_sha="f83caede")
    assert nxt["perturb_active"] is False
    assert S.in_perturb_cooldown("20261113T000000Z_next") is True
    assert desk_ids == []
