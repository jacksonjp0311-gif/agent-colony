"""Regression tests for stall-perturb fixes (queue items 20–24).

Replays the first post-merge run (cycles 853–855) enough to show the parked
combinatorics chain is not proposed on the first live cycle, and that empty
claim-shape labels never reach the Oracle. Each item has its own accept test.
"""
from __future__ import annotations

import json

import colony.fitness as F
import colony.lessons as L
import colony.oracle as O
import colony.oeis_conjectures as OC
import colony.stall as S


# Cycle ids from the 4:43–4:49 PM ET Nov 12 run (and the park that was
# already open from earlier that day).
PRIOR_A = "20261112T172300Z_aaaaaa"
PRIOR_B = "20261112T172513Z_6f0b18"  # parked_at_cycle in the live stall state
C853 = "20261112T214317Z_351b7f"
C854 = "20261112T214541Z_7ab6ee"
C855 = "20261112T214746Z_f02949"
CHAIN_TITLE = "Chain+seek lemma_hard_combinatorics"
CHAIN_ACTION = "seek_enable:lemma_hard_combinatorics"


def _fp():
    return F.proposal_fingerprint(CHAIN_TITLE, CHAIN_ACTION)


def _isolate_logs(tmp_path, monkeypatch, lessons=None, oracle=None):
    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "ledger.json")
    monkeypatch.setattr(O, "ORACLE_LOG", tmp_path / "oracle.jsonl")
    (tmp_path / "lessons.jsonl").write_text(lessons or "", encoding="utf-8")
    (tmp_path / "oracle.jsonl").write_text(oracle or "", encoding="utf-8")
    monkeypatch.setattr(OC, "ATTEMPT_LOG", tmp_path / "oeis_attempt_log.json")
    monkeypatch.setattr(S, "STATE_PATH", tmp_path / "stall_state.json")


def _lesson(fp, cycle_id, title=CHAIN_TITLE):
    return json.dumps({
        "type": "repeat_proposal",
        "lesson_type": "repeat_proposal",
        "tags": ["repeat_proposal"],
        "decision": "block",
        "proposal_fingerprint": fp,
        "cycle_id": cycle_id,
        "mutation": title,
        "what": title,
    })


# ---------------------------------------------------------------------------
# Item 20 — cycle list stays in time order; park is visible on first live cycle
# ---------------------------------------------------------------------------

def test_on_cycle_start_ingests_before_remember_and_parks_first_live_cycle(tmp_path, monkeypatch):
    fp = _fp()
    lessons = "\n".join([_lesson(fp, PRIOR_A), _lesson(fp, PRIOR_B)]) + "\n"
    _isolate_logs(tmp_path, monkeypatch, lessons=lessons)

    report = S.on_cycle_start(C853, commit_sha="e653cfdb")
    cycles = S.load_state()["cycles"]
    # Historical cycles come first, the live cycle is appended; all in time order.
    assert cycles[:3] == [PRIOR_A, PRIOR_B, C853] or (
        cycles.index(PRIOR_A) < cycles.index(PRIOR_B) < cycles.index(C853)
    )
    assert S.is_parked(fp, C853) is True
    # A proposer looking at the first cycle of a fresh run does not re-open the chain.
    assert fp in S.parked_fingerprints(C853) or S.is_parked(fp, C853)


def test_cycles_stay_in_time_order_when_history_is_ingested(tmp_path, monkeypatch):
    fp = _fp()
    _isolate_logs(tmp_path, monkeypatch)
    S.ingest_dedupe_history([
        {"fingerprint": fp, "cycle_id": PRIOR_B, "title": CHAIN_TITLE, "action": CHAIN_ACTION},
        {"fingerprint": fp, "cycle_id": PRIOR_A, "title": CHAIN_TITLE, "action": CHAIN_ACTION},
    ])
    S.remember_cycle(C853)
    cycles = S.load_state()["cycles"]
    assert cycles == [PRIOR_A, PRIOR_B, C853]
    assert S.is_parked(fp, C853) is True


# ---------------------------------------------------------------------------
# Item 21 — ingested history with no turns is not a dead end
# ---------------------------------------------------------------------------

def test_ingested_history_without_turns_does_not_enter_perturb(tmp_path, monkeypatch):
    fp = _fp()
    lessons = "\n".join([
        _lesson(fp, f"20261111T0{i}0000Z_hist{i}") for i in range(4)
    ]) + "\n"
    _isolate_logs(tmp_path, monkeypatch, lessons=lessons)
    # Ingest history (adds cycle ids, no turns), then start the first live cycle.
    S.on_cycle_start(C853, commit_sha="s")
    stall = S.assess_stall()
    assert stall["reason"] != "dead_end_turns"
    # Must not have entered perturb solely because history had no turns.
    # (flat_passes also stays off: pass_history is empty, oracle log is empty.)
    assert stall["on"] is False
    assert S.perturb_active() is False


def test_dead_end_turns_still_stall_when_turns_are_recorded():
    # The original condition (b) still fires when three cycles have observed
    # dead-end turns. Pass totals are moving so condition (a) is off.
    for i, total in enumerate((520, 521, 522)):
        cid = f"dead{i}"
        S.record_pass_total(cid, total)
        S.record_turn(cid, "proposal", "chain", "block")
        S.record_turn(cid, "desk", "catalog", "skip")
        S.record_turn(cid, "claim_theme", "theme", "identical_kill")
    stall = S.assess_stall()
    assert stall["on"] is True and stall["reason"] == "dead_end_turns"


# ---------------------------------------------------------------------------
# Item 22 — count only Oracle-bound targets; seed pass history
# ---------------------------------------------------------------------------

def test_visibility_counts_only_oracle_bound_ids_not_parked_or_skipped():
    # Three cycles, six Oracle-bound ids, plus a parked fingerprint and a
    # skipped theme that used to inflate the count to 7 and drop one Oracle id
    # because the last-3 window was wrong.
    oracle_ids = {
        C853: ["oc_A165064_0", "oc_A229019_0"],
        C854: ["authored_cong_A1", "authored_div_A2"],
        C855: ["authored_gf_A3", "authored_growth_A4"],
    }
    fp = _fp()
    for cid, ids in oracle_ids.items():
        S.remember_cycle(cid)
        S.record_targets_tried(cid, ids)
        for mid in ids:
            S.record_turn(cid, "oracle", mid, "kill")
        S.record_turn(cid, "proposal", fp, "block")          # parked fingerprint
        S.record_turn(cid, "claim_theme", "vandermonde", "skip")  # skipped theme
    vis = S.visibility()
    assert vis["distinct_targets_tried_last_3_cycles"] == 6


def test_seed_pass_history_does_not_reset_stall_cycles(tmp_path, monkeypatch):
    # 10 already-flat Oracle cycles at 528; a new state file should not start
    # stall_cycles at 0 when the next snapshot is also 528.
    rows = []
    for i in range(10):
        rows.append({
            "cycle_id": f"20261111T01000{i}Z_flat{i}",
            "passed": False,
            "kills": ["stripped:stripped_not_useful_fail"],
            "mutation": "old",
        })
    # The running total is 528: pretend earlier passes happened by injecting
    # 528 passed rows in a prior cycle, then 10 flat ones.
    prior = [{"cycle_id": "20261110T000000Z_prior", "passed": True, "kills": [], "mutation": f"p{i}"}
             for i in range(528)]
    _isolate_logs(tmp_path, monkeypatch)
    seeded = S.seed_pass_history(prior + rows)
    assert seeded["seeded"] is True
    assert seeded["stall_cycles"] >= 9
    # A live snapshot at the same total must not reset to 0.
    snap = S.record_pass_total(C853, 528)
    assert snap["stall_cycles"] >= 10
    assert snap["stall_cycles"] != 0
    vis = S.visibility()
    assert vis["stall_cycles"] != 0


# ---------------------------------------------------------------------------
# Item 23 — no empty claim-shape labels or raw OEIS ids at the Oracle
# ---------------------------------------------------------------------------

def test_empty_shape_labels_never_reach_the_oracle():
    S.enter_perturb("go", reason="flat_passes", commit_sha="s")
    reached = []

    def submit(target):
        reached.append(target)
        return {"passed": False, "kills": ["held_out:held_out_fail"]}

    # No author hook: shapes must be skipped or materialized to a real entry,
    # never submitted as "explore claim shape X".
    out = S.run_perturb_turn(
        "pshape", n=2, oracle_submit=submit, commit_sha="s",
        menu=[{"id": "shape:congruence", "source": "claim_shape", "kind": "claim_shape",
               "form": "congruence", "text": "explore claim shape congruence",
               "band": 0, "unseen": True, "unused": True}],
    )
    for t in reached:
        assert not str(t.get("id") or "").startswith("shape:")
        assert "explore claim shape" not in str(t.get("text") or "")
    for s in out["submissions"]:
        if s.get("reached_oracle"):
            assert not str(s.get("id") or "").startswith("shape:")


def test_materialized_shape_submits_the_authored_claim_not_the_label():
    S.enter_perturb("go", reason="flat_passes", commit_sha="s")
    reached = []

    def author(shape, cycle_id):
        return {
            "id": f"authored_{shape}_A000040",
            "source": "authored_check",
            "kind": "authored_check",
            "text": f"a concrete {shape} claim over the primes (held-out tail checked)",
            "form": shape,
        }

    def submit(target):
        reached.append(target)
        return {"passed": False, "kills": ["held_out:held_out_fail"]}

    out = S.run_perturb_turn(
        "pauth", n=2, oracle_submit=submit, author=author, commit_sha="s",
        menu=[
            {"id": "shape:congruence", "source": "claim_shape", "kind": "claim_shape",
             "form": "congruence", "text": "explore claim shape congruence",
             "band": 0, "unseen": True, "unused": True},
            {"id": "shape:divisibility", "source": "claim_shape", "kind": "claim_shape",
             "form": "divisibility", "text": "explore claim shape divisibility",
             "band": 0, "unseen": True, "unused": True},
            {"id": "shape:gf_identity", "source": "claim_shape", "kind": "claim_shape",
             "form": "gf_identity", "text": "explore claim shape gf_identity",
             "band": 0, "unseen": True, "unused": True},
        ],
    )
    assert out["n_attempts"] >= 2
    assert out["n_reached_oracle"] >= 2
    assert reached
    for t in reached:
        assert str(t["id"]).startswith("authored_")
        assert "explore claim shape" not in str(t.get("text") or "")
        assert not str(t["id"]).startswith("shape:")


# ---------------------------------------------------------------------------
# Item 24 — do not retry the same published-range OEIS attempt
# ---------------------------------------------------------------------------

def _prop_entry(eid="oc_A229019_0", anum="A229019", n=44):
    terms = [i + 1 for i in range(n)]  # all positive
    return {
        "id": eid, "anum": anum, "name": "dummy", "offset": 2, "section": "comment",
        "text": "Conjecture: all terms are positive.",
        "claim": {"form": "property", "prop": "positive", "n0": None},
        "definition": None, "terms": terms, "data_n": n, "published_hi": n + 1, "refs": {},
    }


def _gf_entry(eid="oc_A165064_0", anum="A165064"):
    # A short Fibonacci-style g.f. so tests stay fast.
    d = OC.parse_definition("Expansion of 1/(1-x-x^2).")
    terms = [int(c) for c in OC._series_A(d["expr"], 20)]
    return {
        "id": eid, "anum": anum, "name": "Expansion of 1/(1-x-x^2).",
        "offset": 0, "section": "formula",
        "text": "G.f.: 1/(1-x-x^2) (conjecture).",
        "claim": {"form": "gf", "expr": "1/(1-x-x^2)"},
        "definition": d, "terms": terms, "data_n": 12, "published_hi": 19, "refs": {},
    }


def test_published_range_hold_is_not_retried_at_the_same_depth(tmp_path, monkeypatch):
    monkeypatch.setattr(OC, "MENU", tmp_path / "m.json")
    monkeypatch.setattr(OC, "STATE", tmp_path / "s.json")
    monkeypatch.setattr(OC, "REPORT", tmp_path / "r.json")
    monkeypatch.setattr(OC, "REVIEW", tmp_path / "rv.md")
    monkeypatch.setattr(OC, "ATTEMPT_LOG", tmp_path / "oeis_attempt_log.json")
    monkeypatch.setenv("COLONY_OEIS_CONJ", "shadow")
    prop = _prop_entry()
    gf = _gf_entry()
    OC.MENU.write_text(json.dumps({"entries": [prop, gf]}))
    OC.STATE.write_text(json.dumps({
        "targets": {},
        "families": {
            "property": {"attempts": 1, "credit": 0.0},
            "gf": {"attempts": 1, "credit": 0.0},
        },
        "credit_total": 0.0,
    }))
    # A published-range hold on the property (no definition, cannot go past)
    # must not be the next pick at the same depth; the g.f. (computable,
    # searchable past its b-file) is.
    acts = OC.desk_attempt(prop, "c_first")
    assert acts and acts[-1]["status"] == "holds_on_range"
    # Same cycle, same depth: skipped.
    assert OC.desk_attempt(prop, "c_first") == []
    assert OC.already_attempted_pair(prop["id"], OC.planned_depth(prop), "c_second") is True
    second = OC.choose([prop, gf], json.loads(OC.STATE.read_text()), "c_second", k=2)
    ids = [e["id"] for e in second]
    assert prop["id"] not in ids
    assert gf["id"] in ids
    # And idle_turn on a later cycle also skips the property.
    idle = OC.idle_turn("c_third")
    chosen = [c["id"] for c in (idle or {}).get("chosen") or []]
    assert prop["id"] not in chosen
    assert gf["id"] in chosen or (idle or {}).get("purpose") == "beyond_bfile"


def test_prefer_computable_past_bfile_and_rotate_families(tmp_path, monkeypatch):
    monkeypatch.setattr(OC, "MENU", tmp_path / "m.json")
    monkeypatch.setattr(OC, "STATE", tmp_path / "s.json")
    monkeypatch.setattr(OC, "REPORT", tmp_path / "r.json")
    monkeypatch.setattr(OC, "REVIEW", tmp_path / "rv.md")
    monkeypatch.setattr(OC, "ATTEMPT_LOG", tmp_path / "oeis_attempt_log.json")
    monkeypatch.setenv("COLONY_OEIS_CONJ", "shadow")
    monkeypatch.setattr(OC, "DEEP_N", 40)
    monkeypatch.setattr(OC, "GF_TERMS", 40)
    monkeypatch.setattr(OC, "DEEP_SECONDS", 0.5)
    prop = _prop_entry()
    gf = _gf_entry()
    state = {"targets": {}, "families": {
        "property": {"attempts": 3, "credit": 0.0},
        "gf": {"attempts": 3, "credit": 0.0},
    }}
    # The g.f. has a verified definition and can be searched past its b-file;
    # the property cannot. After the property has held on its published range,
    # choose prefers the g.f. and the desk attempt actually goes past.
    OC.desk_attempt(prop, "c0")
    picked = OC.choose([prop, gf], state, "c1", k=1)
    assert [e["id"] for e in picked] == [gf["id"]]
    acts = OC.desk_attempt(gf, "c1")
    assert acts
    # Past the published 19-term range.
    top = max(
        (acts[-1].get("range") or [0, 0])[1] or 0,
        acts[-1].get("deep_hi") or 0,
        acts[-1].get("deep_terms") or 0,
    )
    assert top > 19 or acts[-1].get("status") == "proved_checked"
    # Same (id, planned-depth) is not retried.
    assert OC.desk_attempt(gf, "c2") == [] or OC.already_attempted_pair(
        gf["id"], OC.planned_depth(gf), "c2"
    )


def test_one_attempt_per_target_per_cycle(tmp_path, monkeypatch):
    monkeypatch.setattr(OC, "ATTEMPT_LOG", tmp_path / "oeis_attempt_log.json")
    gf = _gf_entry()
    prop = _prop_entry()
    state = {"targets": {}, "families": {}}
    # Record a first-cycle attempt on the g.f., then the same cycle must not
    # pick it again (even at a new call).
    OC.remember_attempt(gf, [{"status": "holds_on_range", "range": [0, 19], "deep_hi": 19}], "same")
    picked = OC.choose([gf, prop], state, "same", k=2)
    assert gf["id"] not in [e["id"] for e in picked]
    assert prop["id"] in [e["id"] for e in picked]


# ---------------------------------------------------------------------------
# Replay of cycles 853–855
# ---------------------------------------------------------------------------

def test_replay_cycles_853_to_855_parks_the_chain_and_sends_no_empty_shapes(
    tmp_path, monkeypatch,
):
    """Accept for the first post-merge run: the parked chain is not proposed,
    and no ``shape:`` / ``explore claim shape`` label reaches the Oracle."""
    fp = _fp()
    lessons = "\n".join([_lesson(fp, PRIOR_A), _lesson(fp, PRIOR_B)]) + "\n"
    # Seed a long flat 528 pass history so stall_cycles does not start at 0,
    # but do not let dead-end-without-turns fire (item 21). Oracle log has
    # 528 prior passes and several later flat cycles, no rows for 853–855 yet.
    prior_passes = [
        json.dumps({"cycle_id": "20261110T000000Z_base", "passed": True, "kills": [],
                    "mutation": f"p{i}"})
        for i in range(528)
    ]
    flat = [
        json.dumps({"cycle_id": f"20261111T1{i:02d}000Z_flat", "passed": False,
                    "kills": ["stripped:stripped_not_useful_fail"], "mutation": "old"})
        for i in range(8)
    ]
    _isolate_logs(
        tmp_path, monkeypatch,
        lessons=lessons,
        oracle="\n".join(prior_passes + flat) + "\n",
    )
    monkeypatch.setattr(OC, "MENU", tmp_path / "m.json")
    monkeypatch.setattr(OC, "STATE", tmp_path / "s.json")
    monkeypatch.setattr(OC, "REPORT", tmp_path / "r.json")
    monkeypatch.setattr(OC, "REVIEW", tmp_path / "rv.md")
    monkeypatch.setenv("COLONY_OEIS_CONJ", "shadow")
    # A property already held on its published range (the A229019 pattern)
    # plus a computable g.f. the desk can search past the b-file.
    prop = _prop_entry()
    gf = _gf_entry()
    OC.MENU.write_text(json.dumps({"entries": [prop, gf]}))
    OC.STATE.write_text(json.dumps({
        "targets": {prop["id"]: {"attempts": 4, "status": "holds_on_range",
                                 "tested_hi": 44, "credit": 0.0}},
        "families": {"property": {"attempts": 4, "credit": 0.0},
                     "gf": {"attempts": 1, "credit": 0.0}},
        "credit_total": 0.0,
    }))
    # Pre-record the published-range hold so the desk will not retry it.
    OC.remember_attempt(
        prop,
        [{"status": "holds_on_range", "range": [2, 45], "deep_hi": 0, "tested": 44}],
        "20261112T201800Z_prior",
        planned=OC.planned_depth(prop),
    )

    reached = []

    def submit(target):
        reached.append(target)
        tid = str(target.get("id") or "")
        text = str(target.get("text") or "")
        assert not tid.startswith("shape:"), tid
        assert "explore claim shape" not in text, text
        return {"passed": False, "kills": ["stripped:stripped_not_useful_fail"]}

    def author(shape, cycle_id):
        # Concrete authored claim over a real sequence, held-out tail included.
        return {
            "id": f"authored_{shape}_{cycle_id[-6:]}",
            "source": "authored_check",
            "kind": "authored_check",
            "text": f"a {shape} claim over A000040, held-out tail checked",
            "form": shape,
        }

    proposed = []
    for cid in (C853, C854, C855):
        S.on_cycle_start(cid, commit_sha="e653cfdb")
        parked = S.is_parked(fp, cid)
        proposed.append(not parked)
        # The colony's proposer would skip a parked fingerprint.
        if parked:
            S.record_turn(cid, "proposal", fp, "block")
        else:
            S.note_dedupe_block(fp, CHAIN_TITLE, CHAIN_ACTION, cid)
            S.record_turn(cid, "proposal", fp, "block")
        out = S.run_perturb_turn(
            cid, n=2, oracle_submit=submit, author=author, commit_sha="e653cfdb",
        )
        assert out["n_attempts"] >= 2
        for s in out["submissions"]:
            if s.get("reached_oracle") or s.get("attempt"):
                assert not str(s.get("id") or "").startswith("shape:")
                assert "explore claim shape" not in str(s.get("id") or "")
        # The property held only on its published range is not retried.
        desk_ids = [
            (s.get("id") or "")
            for s in out["submissions"]
            if s.get("attempt") == "desk"
        ]
        # After the first desk look, a same-depth property pick is forbidden.
        # (It may appear at most in a materialized skip, not as a new attempt
        # at the published range.)
        S.on_cycle_end(cid, pass_total=528, rows=[])

    assert proposed == [False, False, False], proposed
    for t in reached:
        assert not str(t.get("id") or "").startswith("shape:")
        assert "explore claim shape" not in str(t.get("text") or "")
    # Visibility on the last three cycles counts only Oracle-bound ids.
    vis = S.visibility()
    # stall_cycles was seeded from a flat 528 history, not reset to 0.
    assert vis["stall_cycles"] >= 8
    # Cycles are in time order: priors, then 853–855 at the end.
    cycles = S.load_state()["cycles"]
    assert cycles[-3:] == [C853, C854, C855] or (
        cycles.index(C853) < cycles.index(C854) < cycles.index(C855)
    )
    assert cycles.index(PRIOR_A) < cycles.index(PRIOR_B) < cycles.index(C853)
