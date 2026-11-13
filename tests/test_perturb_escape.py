"""Regression tests for queue items 27 and 28.

Item 28: ``can_progress_past`` must not treat a legacy attempt-log
``depth`` (the requested window, no ``planned`` field) as already
verified. A target whose ``tested_hi`` is still below
``claim_testable_hi`` stays eligible; a real ceiling (refs exhausted,
evaluator cap already recorded) still blocks.

Item 27: a PERTURB cycle with 0 eligible picks escalates to
mutation-first and a broader pool, and if it is still empty, exits to
the no-progress cooldown with a ``no_candidates`` lesson rather than
burning the 9-cycle timeout. Mutation-first actually loads and prefers
ingredient mutations of recent results.

Replays the stall / attempt-log situation of cycles 865–867 of evolve
run 43336746761 (7:23–7:38 PM ET Nov 12).
"""
from __future__ import annotations

import json

import colony.lessons as L
import colony.oeis_conjectures as OC
import colony.oracle as O
import colony.stall as S


# Cycles 865–867 of run 43336746761, and the session they continued.
C865 = "20261113T002718Z_74e5e5"
C866 = "20261113T003021Z_f1b7ae"
C867 = "20261113T003258Z_094ebd"
ENTERED = "20261113T000751Z_5db176"
SEED = 10750430502206843365
COMMIT = "0b2a2557b72faf436451bae7bdaa9f7d0d45ef65"


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


def _gf_entry(eid="oc_A165064_0", anum="A165064", published_hi=100, n_terms=20):
    d = OC.parse_definition("Expansion of 1/(1-x-x^2).")
    terms = [int(c) for c in OC._series_A(d["expr"], n_terms)]
    return {
        "id": eid, "anum": anum, "name": "Expansion of 1/(1-x-x^2).",
        "offset": 0, "section": "formula",
        "text": "G.f.: 1/(1-x-x^2) (conjecture).",
        "claim": {"form": "gf", "expr": "1/(1-x-x^2)"},
        "definition": d, "terms": terms, "data_n": n_terms,
        "published_hi": published_hi, "refs": {},
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
        "definition": d, "terms": terms_a, "data_n": 20,
        "published_hi": 19,
        "refs": {"A002605": dict(ref), "A026150": dict(ref)},
    }


def _egf_relation_entry(eid="oc_A126089_0", anum="A126089"):
    """A126089 pattern: computable egf/relation, claim_testable_hi at the
    series cap, tested_hi still below that cap (evaluator ceiling is a
    separate mechanism, recorded after a real attempt)."""
    d = OC.parse_definition("Expansion of 1/(1-x-x^2).")
    # kind is forced to egf so claim_testable_hi uses GF_TERMS, matching
    # the live A126089 entry (egf definition, relation claim).
    d = dict(d)
    d["kind"] = "egf"
    terms = [int(c) for c in OC._series_A(d["expr"], 20)]
    return {
        "id": eid, "anum": anum,
        "name": "D-finite recurrence (conjecture).",
        "offset": 0, "section": "formula",
        "text": "Conjecture D-finite with recurrence: (-n+4)*a(n)+2*(2*n-5)*(n-3)*a(n-1)=0.",
        "claim": {"form": "relation", "parts": ["a(n)", "a(n-1)"],
                  "rels": ["="], "mod": None, "n0": None},
        "definition": d, "terms": terms, "data_n": 19,
        "published_hi": 200, "refs": {},
    }


def _legacy_row(eid, anum, form, requested_depth, bfile_hi, status="holds_on_range", cycle="prior"):
    """A pre-PR #4 attempt-log row: requested depth, no planned field."""
    return {
        "id": eid, "anum": anum, "form": form,
        "depth": requested_depth, "bfile_hi": bfile_hi,
        "beyond": requested_depth > bfile_hi,
        "status": status, "cycle_id": cycle,
    }


def _write_legacy_log(rows):
    OC.ATTEMPT_LOG.write_text(json.dumps({"attempts": rows, "by_cycle": {}, "last_forms": ["relation"]}))


def _state(targets, families=None):
    return {
        "targets": targets,
        "families": families or {
            "relation": {"attempts": 30, "credit": 0.0},
            "gf": {"attempts": 46, "credit": 0.05},
        },
        "credit_total": 0.05,
    }


def _held_ceiling_entry(eid, anum, tested_hi, published_hi):
    """Already-held, no definition: claim_testable_hi stops at the short terms."""
    n = min(12, max(1, int(tested_hi)))
    terms = [i + 1 for i in range(n)]
    return {
        "id": eid, "anum": anum, "name": "dummy held", "offset": 0,
        "section": "formula", "text": f"Conjecture about {anum}.",
        "claim": {"form": "relation", "parts": ["a(n)", "a(n)"], "rels": ["="],
                  "mod": None, "n0": None},
        "definition": None, "terms": terms, "data_n": n,
        "published_hi": published_hi, "refs": {},
    }


def _seed_865_stall(cycles_in_mode=3):
    """PERTURB mid-session, as at the start of cycle 865: strategy still
    explore, no cooldown, 0 session progress, cycles_in_mode=3."""
    for i in range(10):
        S.record_pass_total(f"20261112T2{i:02d}000Z_flat", 528, kills=[("same_kill",)])
        S.record_turn(f"20261112T2{i:02d}000Z_flat", "proposal", "chain", "block")
        S.record_turn(f"20261112T2{i:02d}000Z_flat", "desk", "catalog", "skip")
    # enter then rewrite to the live mid-session snapshot
    S.enter_perturb(ENTERED, reason="flat_passes", commit_sha=COMMIT)
    st = S.load_state()
    st["perturb"].update({
        "active": True,
        "entered_at": ENTERED,
        "seed": SEED,
        "cycles_in_mode": cycles_in_mode,
        "park_multiplier": 2,
        "epsilon": 0.5,
        "exit_reason": "",
        "exit_cycle": "",
        "commit_sha": COMMIT,
        "reason": "flat_passes",
        "cooldown_until": -1,
        "timeout_count": 0,
        "strategy": "explore",
        "session_progress": False,
        "session_targets": [],
        "exclude_targets": [],
        "last_timeout_cycle": "",
        "zero_pick_streak": 0,
    })
    st["stall_cycles"] = 12
    S.save_state(st)


# ---------------------------------------------------------------------------
# Item 28: legacy depth is not verified depth
# ---------------------------------------------------------------------------

def test_legacy_row_does_not_inflate_verified_depth(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    e = _egf_relation_entry()
    # Live A126089 situation: requested 20_000, tested_hi 956, no planned.
    _write_legacy_log([_legacy_row(e["id"], e["anum"], "relation", 20000, 200)])
    OC.STATE.write_text(json.dumps(_state({
        e["id"]: {"attempts": 15, "status": "holds_on_range", "tested_hi": 956, "credit": 0.034},
    })))
    # claim_testable_hi is the series cap (1200), above tested_hi.
    assert OC.claim_testable_hi(e) >= 1200 or OC.claim_testable_hi(e) > 956
    assert OC.can_progress_past(e, 956, require_past_published=True) is True
    assert OC.can_progress_past(e, 956) is True
    # The next planned depth is not "already attempted" just because a
    # legacy row asked for 20_000.
    assert OC.already_attempted_pair(e["id"], OC.planned_depth(e, 956)) is False
    # The log itself is untouched (no data churn).
    row = OC.load_attempt_log()["attempts"][-1]
    assert "planned" not in row
    assert "verified_depth" not in row
    assert row["depth"] == 20000


def test_legacy_gf_one_term_below_cap_is_open(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    e = _gf_entry()
    # Live A165064: depth 1200, tested_hi 1199, GF_TERMS = 1200.
    _write_legacy_log([_legacy_row(e["id"], e["anum"], "gf", 1200, 100)])
    OC.STATE.write_text(json.dumps(_state({
        e["id"]: {"attempts": 46, "status": "holds_on_range", "tested_hi": 1199, "credit": 0.05},
    })))
    assert OC.claim_testable_hi(e) == OC.GF_TERMS == 1200
    assert OC.can_progress_past(e, 1199, require_past_published=True) is True
    assert OC.already_attempted_pair(e["id"], OC.planned_depth(e, 1199)) is False


def test_legacy_ref_ceiling_still_blocks(tmp_path, monkeypatch):
    """Item 25 must not come back: A108476's claim_testable_hi=30 is a real
    ceiling, even when the legacy row says depth 20_000."""
    _isolate(tmp_path, monkeypatch)
    e = _ref_limited_entry()
    _write_legacy_log([_legacy_row(e["id"], e["anum"], "relation", 20000, 19)])
    OC.STATE.write_text(json.dumps(_state({
        e["id"]: {"attempts": 49, "status": "holds_on_range", "tested_hi": 30, "credit": 0.0099},
    })))
    assert OC.claim_testable_hi(e) == 30
    assert OC.can_progress_past(e, 30, require_past_published=True) is False
    assert OC.can_progress_past(e, 30) is False
    picked = OC.choose(
        [e],
        _state({e["id"]: {"attempts": 49, "status": "holds_on_range", "tested_hi": 30}}),
        "next", k=1, beyond_bfile=True,
    )
    assert picked == []


def test_post_pr4_row_still_uses_planned_as_aimed_ceiling(tmp_path, monkeypatch):
    """A real post-PR #4 attempt that already aimed at the reachable cap
    and verified a lower range is not retried (item 25)."""
    _isolate(tmp_path, monkeypatch)
    e = _ref_limited_entry()
    OC.remember_attempt(
        e, [{"status": "holds_on_range", "range": [0, 30], "tested": 31}],
        "prior", planned=20000,
    )
    assert "planned" in OC.load_attempt_log()["attempts"][-1]
    assert OC.can_progress_past(e, 30, require_past_published=True) is False
    assert OC.already_attempted_pair(e["id"], 20000) is True


def test_choose_opens_legacy_headroom_not_ceilings(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    gf = _gf_entry()          # tested 1199, reachable 1200
    rel = _egf_relation_entry()  # tested 956, reachable 1200
    ref = _ref_limited_entry()   # tested 30, reachable 30
    _write_legacy_log([
        _legacy_row(gf["id"], gf["anum"], "gf", 1200, 100, cycle="20261112T234609Z_0f7791"),
        _legacy_row(rel["id"], rel["anum"], "relation", 20000, 200, cycle="20261112T234609Z_0f7791"),
        _legacy_row(ref["id"], ref["anum"], "relation", 20000, 19, cycle="20261112T234826Z_5459c4"),
    ])
    state = _state({
        gf["id"]: {"attempts": 46, "status": "holds_on_range", "tested_hi": 1199, "credit": 0.05},
        rel["id"]: {"attempts": 15, "status": "holds_on_range", "tested_hi": 956, "credit": 0.034},
        ref["id"]: {"attempts": 49, "status": "holds_on_range", "tested_hi": 30, "credit": 0.0099},
    })
    OC.STATE.write_text(json.dumps(state))
    OC.MENU.write_text(json.dumps({"entries": [gf, rel, ref]}))
    picked = OC.choose([gf, rel, ref], state, "c865", k=3, beyond_bfile=True)
    ids = [e["id"] for e in picked]
    assert ref["id"] not in ids
    assert gf["id"] in ids or rel["id"] in ids
    # Idle desk is no longer empty.
    assert picked, ids


# ---------------------------------------------------------------------------
# Item 27: 0-pick PERTURB escalates, then exits
# ---------------------------------------------------------------------------

def test_zero_pick_escalates_then_exits_immediately(tmp_path, monkeypatch):
    """When every menu entry is already at a real ceiling, PERTURB does
    not sit until the 9-cycle timeout. It switches to mutation-first,
    broadens the pool, and if still empty, exits with no_candidates,
    starts the cooldown, and records a lesson."""
    _isolate(tmp_path, monkeypatch)
    held = [
        _held_ceiling_entry("oc_A026589_0", "A026589", 371, 1000),
        _held_ceiling_entry("oc_A100038_0", "A100038", 47, 47),
        _ref_limited_entry(),  # real ceiling at 30
    ]
    # Legacy inflated depths, same as the live log.
    _write_legacy_log([
        _legacy_row("oc_A026589_0", "A026589", "relation", 1000, 1000),
        _legacy_row("oc_A100038_0", "A100038", "relation", 47, 47),
        _legacy_row("oc_A108476_0", "A108476", "relation", 20000, 19),
    ])
    OC.MENU.write_text(json.dumps({"entries": held}))
    OC.STATE.write_text(json.dumps(_state({
        "oc_A026589_0": {"attempts": 5, "status": "holds_on_range", "tested_hi": 371},
        "oc_A100038_0": {"attempts": 5, "status": "holds_on_range", "tested_hi": 47},
        "oc_A108476_0": {"attempts": 49, "status": "holds_on_range", "tested_hi": 30},
    })))
    _seed_865_stall(cycles_in_mode=6)
    assert S.load_state()["perturb"]["strategy"] == "explore"

    def submit(target):
        raise AssertionError(f"held or ceiling id reached the Oracle: {target}")

    S.on_cycle_start(C865, commit_sha=COMMIT)
    assert S.perturb_active() is True
    out = S.run_perturb_turn(
        C865, n=2, oracle_submit=submit, author=lambda shape, c: None,
        commit_sha=COMMIT,
    )
    assert out["n_attempts"] == 0
    assert out.get("escalated") is True
    # K defaults to 1: exit this same cycle, do not burn cycles 7–9.
    st = S.load_state()
    assert st["perturb"]["active"] is False
    assert st["perturb"]["exit_reason"] == "no_candidates"
    assert st["perturb"]["strategy"] == "mutate"
    assert st["perturb"]["cooldown_until"] >= 0
    assert S.in_perturb_cooldown(C865) or S.perturb_cooldown_remaining(C865, st) > 0
    assert out.get("exit_reason") == "no_candidates"
    lessons = (tmp_path / "lessons.jsonl").read_text(encoding="utf-8")
    assert "no_candidates" in lessons
    assert "escalating to mutation-first" in lessons
    # Next cycle does not immediately re-enter.
    nxt = S.on_cycle_start("20261113T010000Z_next", commit_sha=COMMIT)
    assert nxt["perturb_active"] is False
    assert S.in_perturb_cooldown("20261113T010000Z_next") is True


def test_mutation_first_activates_and_uses_recent_seeds(tmp_path, monkeypatch):
    """When strategy is mutate, select_perturb_targets loads recent
    results and prefers ingredient mutations even if the caller passed
    no kept_seeds (the live path)."""
    _isolate(tmp_path, monkeypatch)
    held = _held_ceiling_entry("oc_old_0", "A000001", 10, 10)
    # Two progressable g.f. entries: a recent result and an alternative sequence.
    recent = _gf_entry("oc_A165064_0", "A165064", published_hi=19, n_terms=12)
    alt = _gf_entry("oc_fresh_gf_0", "A999999", published_hi=19, n_terms=12)
    OC.MENU.write_text(json.dumps({"entries": [held, recent, alt]}))
    OC.STATE.write_text(json.dumps(_state({
        held["id"]: {"attempts": 5, "status": "holds_on_range", "tested_hi": 10},
        recent["id"]: {"attempts": 2, "status": "holds_on_range", "tested_hi": 19, "credit": 0.0},
        alt["id"]: {"attempts": 0, "status": "", "tested_hi": 0, "credit": 0.0},
    }, families={
        "relation": {"attempts": 5, "credit": 0.0},
        "gf": {"attempts": 2, "credit": 0.0},
    })))
    # A *post-PR #4* row for the recent g.f.: verified 19, planned 1200,
    # so the same sequence is not itself a progressable candidate at this
    # cap, but its sequence can mutate to the untried alternative.
    OC.remember_attempt(
        recent,
        [{"status": "holds_on_range", "range": [0, 19], "tested": 20}],
        "prior", planned=1200,
    )
    S.enter_perturb("go", reason="flat_passes", commit_sha="abc")
    st = S.load_state()
    st["perturb"]["strategy"] = "mutate"
    S.save_state(st)

    picked = S.select_perturb_targets("p_mut", n=4, commit_sha="abc")
    assert picked, "mutation-first produced an empty pool"
    # At least one pick is a mutation, or the untried alternative that
    # a sequence mutation would bind to.
    flags = []
    ids = []
    for t in picked:
        ids.append(t.get("id"))
        flags.append(bool(t.get("mutated") or t.get("source") == "mutated_seed" or t.get("untried")))
    assert any(flags), ids
    # The already-held ceiling entry is not replayed.
    assert held["id"] not in ids


def test_zero_pick_respects_self_heal_knob(tmp_path, monkeypatch):
    """K is read from the live self-heal override: with K=2, the first
    empty cycle escalates and stays in mode; the second exits."""
    import colony.self_heal as SH
    monkeypatch.setattr(SH, "STATE_PATH", tmp_path / "self_heal.json")
    _isolate(tmp_path, monkeypatch)
    held = [_held_ceiling_entry("oc_A100038_0", "A100038", 47, 47)]
    _write_legacy_log([_legacy_row("oc_A100038_0", "A100038", "relation", 47, 47)])
    OC.MENU.write_text(json.dumps({"entries": held}))
    OC.STATE.write_text(json.dumps(_state({
        "oc_A100038_0": {"attempts": 5, "status": "holds_on_range", "tested_hi": 47},
    })))
    # Adopt K=2 as a live override (in bounds, not the code default).
    raw = SH.load_state()
    raw.setdefault("knobs", {})
    raw["knobs"]["perturb_zero_pick_cycles"] = 2
    SH.save_state(raw)
    assert SH.active_knob("perturb_zero_pick_cycles") == 2

    _seed_865_stall(cycles_in_mode=3)
    S.on_cycle_start(C865, commit_sha=COMMIT)
    out1 = S.run_perturb_turn(
        C865, n=2, oracle_submit=lambda t: (_ for _ in ()).throw(AssertionError(t)),
        author=lambda s, c: None, commit_sha=COMMIT,
    )
    assert out1["n_attempts"] == 0
    assert out1.get("escalated") is True
    st = S.load_state()
    assert st["perturb"]["active"] is True
    assert st["perturb"]["strategy"] == "mutate"
    assert int(st["perturb"].get("zero_pick_streak") or 0) == 1
    # Second empty cycle exits.
    S.on_cycle_end(C865, pass_total=528, rows=[])
    S.on_cycle_start(C866, commit_sha=COMMIT)
    out2 = S.run_perturb_turn(
        C866, n=2, oracle_submit=lambda t: (_ for _ in ()).throw(AssertionError(t)),
        author=lambda s, c: None, commit_sha=COMMIT,
    )
    st = S.load_state()
    assert st["perturb"]["active"] is False
    assert st["perturb"]["exit_reason"] == "no_candidates"
    assert st["perturb"]["strategy"] == "mutate"


# ---------------------------------------------------------------------------
# Replay of cycles 865–867
# ---------------------------------------------------------------------------

def test_replay_cycles_865_to_867_opens_headroom_and_does_not_burn_timeout(
    tmp_path, monkeypatch,
):
    """Accept for run 43336746761: at the start of cycle 865, PERTURB was
    mid-session (cycles_in_mode=3, strategy=explore, n=0 every cycle)
    because legacy attempted depths (A126089 20_000, A108476 20_000,
    A165064 1_200) were treated as verified. After the fix:

    - A165064 (tested 1199, reachable 1200) and A126089 (tested 956,
      reachable 1200) are eligible; A108476 (claim_testable_hi=30) is not.
    - The idle desk / PERTURB is therefore not empty, so the session
      does not burn cycles 4–9 of the timeout clock with n=0.
    - If a menu of only real ceilings is used instead, PERTURB exits
      on no_candidates the first empty cycle (covered separately).
    """
    _isolate(tmp_path, monkeypatch)
    gf = _gf_entry()
    rel = _egf_relation_entry()
    ref = _ref_limited_entry()
    _write_legacy_log([
        _legacy_row(gf["id"], gf["anum"], "gf", 1200, 100,
                    cycle="20261112T234609Z_0f7791"),
        _legacy_row(rel["id"], rel["anum"], "relation", 20000, 200,
                    cycle="20261112T234609Z_0f7791"),
        _legacy_row(ref["id"], ref["anum"], "relation", 20000, 19,
                    cycle="20261112T234826Z_5459c4"),
    ])
    state = _state({
        gf["id"]: {"attempts": 46, "status": "holds_on_range", "tested_hi": 1199, "credit": 0.05},
        rel["id"]: {"attempts": 15, "status": "holds_on_range", "tested_hi": 956, "credit": 0.034},
        ref["id"]: {"attempts": 49, "status": "holds_on_range", "tested_hi": 30, "credit": 0.0099},
    })
    OC.STATE.write_text(json.dumps(state))
    OC.MENU.write_text(json.dumps({"entries": [gf, rel, ref]}))

    # Unit-level: the 865–867 log + tested_hi snapshot.
    assert OC.can_progress_past(gf, 1199, require_past_published=True) is True
    assert OC.can_progress_past(rel, 956, require_past_published=True) is True
    assert OC.can_progress_past(ref, 30, require_past_published=True) is False

    _seed_865_stall(cycles_in_mode=3)
    attempted = []
    desk_ids = []

    def submit(target):
        # OEIS stays on the desk; authored shapes may reach a test hook.
        tid = str(target.get("id") or "")
        assert tid != ref["id"]
        attempted.append(tid)
        return {"passed": False, "kills": ["stripped:stripped_not_useful_fail"]}

    # First cycle of the replay: must not deliver n=0 and sit in explore.
    S.on_cycle_start(C865, commit_sha=COMMIT)
    assert S.perturb_active() is True
    assert S.load_state()["perturb"]["strategy"] in ("explore", "mutate")
    out = S.run_perturb_turn(
        C865, n=2, oracle_submit=submit, author=lambda shape, c: None,
        commit_sha=COMMIT,
    )
    for s in out["submissions"]:
        if s.get("attempt"):
            desk_ids.append(s.get("id"))
    # A108476 is never a desk/Oracle target: real ceiling.
    assert ref["id"] not in desk_ids
    # At least one of the two headroom targets is attempted, so n>0
    # and we do not exit for no_candidates just because of legacy depth.
    open_ids = {gf["id"], rel["id"]}
    assert out["n_attempts"] >= 1, (out["n"], out.get("submissions"))
    assert any(i in open_ids for i in desk_ids), desk_ids
    st = S.load_state()
    # Did not burn the remaining 6 cycles of a 9-cycle timeout with n=0.
    assert st["perturb"].get("exit_reason") != "timeout"
    if st["perturb"]["active"]:
        assert int(st["perturb"].get("cycles_in_mode") or 0) <= 3  # end tick is later
    # The attempt log is still the legacy file until a real remember_attempt
    # (desk may append a *new* row with planned; it must not rewrite the
    # original legacy rows).
    log = OC.load_attempt_log()
    legacy = [r for r in log["attempts"] if "planned" not in r and r["id"] in {gf["id"], rel["id"], ref["id"]}]
    assert any(r["depth"] == 20000 and r["id"] == rel["id"] for r in legacy)
    assert any(r["depth"] == 20000 and r["id"] == ref["id"] for r in legacy)
    assert any(r["depth"] == 1200 and r["id"] == gf["id"] for r in legacy)
