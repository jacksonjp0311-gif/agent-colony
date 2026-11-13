"""Item 33: depth extensions count toward stall visibility and postpone STALL.

A strict tested_hi / scoreboard extension increase resets stall_cycles
and is counted in targets_tried / distinct_targets_tried_last_3_cycles.
After a no_candidates exit, PERTURB does not re-enter on the same Oracle
pass total until a new-depth target is actually eligible.

Does not loosen the Oracle, the P ≥ 0.70 gate, or the 150 cap.
"""
from __future__ import annotations

import json

import colony.lessons as L
import colony.oeis_conjectures as OC
import colony.oracle as O
import colony.self_heal as SH
import colony.stall as S


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
    monkeypatch.setattr(SH, "STATE_PATH", tmp_path / "self_heal.json")
    monkeypatch.setattr(SH, "EVENT_LOG", tmp_path / "self_heal.jsonl")
    OC.MENU.write_text(json.dumps({"entries": []}))
    OC.STATE.write_text(json.dumps({"targets": {}, "families": {}, "credit_total": 0}))
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


def _held_ceiling(eid, anum, tested_hi, published_hi):
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


def _flat(n=10, total=528, prefix="c", *, dead_ends=False):
    for i in range(n):
        cid = f"{prefix}{i}"
        S.remember_cycle(cid)
        S.record_pass_total(cid, total, kills=[("same_kill",)])
        if dead_ends:
            S.record_turn(cid, "proposal", "chain", "block")
            S.record_turn(cid, "desk", "catalog", "skip")


def _empty_menu_state(entries, targets):
    OC.MENU.write_text(json.dumps({"entries": entries}))
    OC.STATE.write_text(json.dumps({
        "targets": targets,
        "families": {"relation": {"attempts": 10, "credit": 0.0},
                     "gf": {"attempts": 10, "credit": 0.0}},
        "credit_total": 0.0,
    }))


# ---------------------------------------------------------------------------
# Depth extensions count and reset stall_cycles
# ---------------------------------------------------------------------------

def test_depth_extensions_count_toward_visibility(tmp_path, monkeypatch):
    """Cycle 874 extended two targets; those must show up in the last-3 count."""
    _isolate(tmp_path, monkeypatch)
    _flat(10)
    vis0 = S.visibility()
    assert vis0["distinct_targets_tried_last_3_cycles"] == 0
    assert vis0["stall_cycles"] >= 6
    ids = S.record_verified_depth_progress("c9", ["oc_A165064_0", "oc_A126089_0"])
    assert ids == ["oc_A165064_0", "oc_A126089_0"]
    vis = S.visibility()
    assert vis["distinct_targets_tried_last_3_cycles"] == 2
    assert vis["stall_cycles"] == 0
    # Parked fingerprints and skipped themes still do not inflate the count.
    S.record_turn("c9", "proposal", "254f76bd3854", "block")
    S.record_turn("c9", "claim_theme", "vandermonde", "skip")
    vis2 = S.visibility()
    assert vis2["distinct_targets_tried_last_3_cycles"] == 2


def test_stall_cycles_reset_and_assess_postpones(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _flat(10)
    assert S.assess_stall()["on"] is True
    assert S.assess_stall()["reason"] == "flat_passes"
    before = S.load_state()["stall_cycles"]
    assert before >= 6
    S.record_verified_depth_progress("c9", ["oc_A165064_0"])
    assert S.load_state()["stall_cycles"] == 0
    stall = S.assess_stall()
    assert stall["on"] is False
    assert stall["reason"] == "clear"
    assert stall["stall_cycles"] == 0
    # Six more flat cycles with no depth advance: STALL may fire again.
    for i in range(10, 16):
        cid = f"c{i}"
        S.remember_cycle(cid)
        S.record_pass_total(cid, 528, kills=[("same_kill",)])
        S.record_turn(cid, "proposal", "chain", "block")
    # last_depth is c9, no longer in the last-6 window (c10–c15).
    stall = S.assess_stall()
    assert stall["on"] is True
    assert stall["reason"] == "flat_passes"
    assert S.load_state()["stall_cycles"] >= 6


def test_oracle_and_depth_targets_union_in_visibility(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    for i, cid in enumerate(("x0", "x1", "x2")):
        S.remember_cycle(cid)
        S.record_pass_total(cid, 528)
        S.record_targets_tried(cid, [f"authored_{i}a", f"authored_{i}b"])
        S.record_turn(cid, "oracle", f"authored_{i}a", "kill")
        S.record_turn(cid, "oracle", f"authored_{i}b", "kill")
    S.record_verified_depth_progress("x2", ["oc_A165064_0", "oc_A126089_0"])
    vis = S.visibility()
    # 2 oracle ids per cycle × 3 cycles = 6, plus 2 depth ids on x2.
    assert vis["distinct_targets_tried_last_3_cycles"] == 8
    assert vis["stall_cycles"] == 0


def test_depth_progress_is_not_an_oracle_target_metric(tmp_path, monkeypatch):
    """new_oracle_targets stays 0 for a desk depth extension; new_depth counts it."""
    _isolate(tmp_path, monkeypatch)
    S.remember_cycle("d1")
    S.record_pass_total("d1", 528)
    S.record_verified_depth_progress("d1", ["oc_A165064_0"])
    stall = S.load_state()
    log = {
        "attempts": [{
            "id": "oc_A165064_0", "anum": "A165064", "form": "gf",
            "depth": 7999, "bfile_hi": 100, "beyond": True,
            "status": "holds_on_range", "cycle_id": "d1",
            "planned": 8000, "verified_depth": 7999,
            "extended": 6800, "prior_tested_hi": 1199,
        }],
    }
    m = SH.collect_metrics("d1", stall_state=stall, attempt_log=log)
    assert m["new_depth"] == 1
    assert m["new_oracle_targets"] == 0


def test_on_cycle_end_records_depth_from_attempt_log(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    _flat(8, prefix="p")
    log = {
        "attempts": [
            {
                "id": "oc_A165064_0", "anum": "A165064", "form": "gf",
                "depth": 7999, "bfile_hi": 100, "beyond": True,
                "status": "holds_on_range", "cycle_id": "live",
                "planned": 8000, "verified_depth": 7999,
                "extended": 6800, "prior_tested_hi": 1199,
            },
            {
                "id": "oc_A126089_0", "anum": "A126089", "form": "relation",
                "depth": 1199, "bfile_hi": 200, "beyond": True,
                "status": "holds_on_range", "cycle_id": "live",
                "planned": 1200, "verified_depth": 1199,
                "extended": 243, "prior_tested_hi": 956,
            },
        ],
    }
    OC.save_attempt_log(log)
    # Seed pass history already at 528 so this cycle is a flat snapshot.
    S.remember_cycle("live")
    out = S.on_cycle_end("live", pass_total=528, rows=[])
    vis = out["visibility"]
    assert vis["distinct_targets_tried_last_3_cycles"] == 2
    assert vis["stall_cycles"] == 0
    assert S.assess_stall()["on"] is False
    tried = S.load_state()["targets_tried"]
    depth_ids = {
        t for r in tried if r.get("cycle_id") == "live" and r.get("kind") == "depth"
        for t in (r.get("targets") or [])
    }
    assert depth_ids == {"oc_A165064_0", "oc_A126089_0"}


# ---------------------------------------------------------------------------
# no_candidates re-entry
# ---------------------------------------------------------------------------

def test_no_candidates_does_not_reenter_on_same_passes_while_empty(tmp_path, monkeypatch):
    """After a no_candidates exit, cooldown expiry alone must not re-enter
    on the same 528 pass total when the eligible pool is still empty."""
    _isolate(tmp_path, monkeypatch)
    held = [
        _held_ceiling("oc_A026589_0", "A026589", 371, 1000),
        _held_ceiling("oc_A100038_0", "A100038", 47, 47),
    ]
    _empty_menu_state(held, {
        "oc_A026589_0": {"attempts": 5, "status": "holds_on_range", "tested_hi": 371},
        "oc_A100038_0": {"attempts": 5, "status": "holds_on_range", "tested_hi": 47},
    })
    _flat(10)
    assert S.has_eligible_progress_target() is False
    S.enter_perturb("go", reason="flat_passes", commit_sha="s")
    S.exit_perturb("go", "no_candidates")
    st = S.load_state()
    assert st["perturb"]["exit_reason"] == "no_candidates"
    assert st["perturb"]["no_candidates_pass_total"] == 528
    assert st["perturb"]["cooldown_until"] >= 0
    # Walk past the cooldown with the same pass total.
    entered = []
    for i in range(S.PERTURB_COOLDOWN_CYCLES + 3):
        cid = f"cool{i}"
        S.remember_cycle(cid)
        S.record_pass_total(cid, 528, kills=[("same_kill",)])
        S.record_turn(cid, "proposal", "chain", "block")
        S.record_turn(cid, "desk", "catalog", "skip")
        out = S.on_cycle_start(cid, commit_sha="s")
        entered.append((cid, out["perturb_active"], S.perturb_cooldown_remaining(cid)))
        if out["perturb_active"]:
            break
    assert S.perturb_cooldown_remaining(entered[-1][0]) == 0
    assert all(not active for _c, active, _r in entered), entered
    assert S.load_state()["perturb"]["active"] is False
    assert S.load_state()["perturb"]["timeout_count"] == 1  # not inflated by a re-enter/exit


def test_no_candidates_reenters_when_a_target_becomes_eligible(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    held = [_held_ceiling("oc_A026589_0", "A026589", 371, 1000)]
    _empty_menu_state(held, {
        "oc_A026589_0": {"attempts": 5, "status": "holds_on_range", "tested_hi": 371},
    })
    _flat(10)
    S.enter_perturb("go", reason="flat_passes", commit_sha="s")
    S.exit_perturb("go", "no_candidates")
    # Expire the cooldown.
    for i in range(S.PERTURB_COOLDOWN_CYCLES + 1):
        cid = f"cool{i}"
        S.remember_cycle(cid)
        S.record_pass_total(cid, 528, kills=[("same_kill",)])
        S.record_turn(cid, "proposal", "chain", "block")
        out = S.on_cycle_start(cid, commit_sha="s")
        assert out["perturb_active"] is False
    # A new-depth target becomes eligible (raised headroom / new menu entry).
    gf = _gf_entry()
    _empty_menu_state([held[0], gf], {
        "oc_A026589_0": {"attempts": 5, "status": "holds_on_range", "tested_hi": 371},
        gf["id"]: {"attempts": 0, "status": "", "tested_hi": 100},
    })
    assert S.has_eligible_progress_target() is True
    out = S.on_cycle_start("ready", commit_sha="s")
    assert out["perturb_active"] is True
    assert S.load_state()["perturb"].get("no_candidates_pass_total") is None


def test_timeout_exit_still_reenters_after_cooldown(tmp_path, monkeypatch):
    """Item 27 / existing contract: a timeout (not no_candidates) may
    re-enter after the cooldown, even on a flat pass total."""
    _isolate(tmp_path, monkeypatch)
    _flat(10)
    S.enter_perturb("go", reason="flat_passes", commit_sha="s")
    st = S.load_state()
    st["perturb"]["cycles_in_mode"] = S.PERTURB_MAX_CYCLES
    st["perturb"]["session_progress"] = False
    S.save_state(st)
    S.on_cycle_end("t9", pass_total=528, rows=[
        {"cycle_id": "t9", "passed": False, "kills": ["same_kill"], "mutation": "x"},
    ])
    assert S.load_state()["perturb"]["exit_reason"] == "timeout"
    entered = False
    for i in range(S.PERTURB_COOLDOWN_CYCLES + 2):
        cid = f"to{i}"
        S.remember_cycle(cid)
        S.record_pass_total(cid, 528, kills=[("same_kill",)])
        S.record_turn(cid, "proposal", "chain", "block")
        out = S.on_cycle_start(cid, commit_sha="s")
        if out["perturb_active"]:
            entered = True
            break
    assert entered is True
    assert S.load_state()["perturb"]["strategy"] == "mutate"
