"""Item 70: certified dead-weight retirement + multi-target self-heal preference.

Hermetic: the lemma source, Oracle rows and record are fixtures. Protections,
the Oracle, P >= 0.70, the 150 cap and the Wilson gate are untouched.
"""
from __future__ import annotations

import ast
import json
from datetime import datetime, timezone

import pytest

import colony.arm as arm
from colony import retire as R
from colony import retire_audit as RA
from colony.authoring import FALLBACK_MARKER

DEAD = [f"authored_mut_swap_related_sequence_{i:012x}" for i in (1, 2, 3)]
NA = "authored_frontier_cong_xdeadbeef_w1"
PASSED = "authored_frontier_le_x1_w1"
CALLER = "authored_mut_swap_related_sequence_00000000000a"

SRC = "".join(f'''
def check_{n}() -> bool:
    return all(n >= 0 for n in range(3))
''' for n in DEAD + [NA, PASSED]) + f'''

def check_{CALLER}() -> bool:
    return check_{DEAD[2]}() and True


{FALLBACK_MARKER}
BASIC: list = []
HARD_TIER_LEMMAS: list = [
''' + "".join(f'    ("{n}", check_{n}, False),\n' for n in DEAD + [NA, CALLER]) + f'    ("{PASSED}", check_{PASSED}, True),\n]\n'

NOW = datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc)
SNAP = {"hard_pass": 162, "hard_n": 162, "ok": True, "score": 0.8728, "survives": False, "reason": "held_out_fail"}


def _kill(n, kind="authored_check", kills=("held_out:held_out_fail", "collective_kill"), ts="2026-11-15T04:00:00Z"):
    return {"mutation": n, "passed": False, "kind": kind, "kills": list(kills), "ts": ts,
            "sense": {"held_out": dict(SNAP)}}


def _rows():
    rows = [_kill(n) for n in DEAD]
    rows.append(_kill(NA, kind="hard_enable",
                      kills=("held_out:held_out_shift_not_applicable(no_literal_range)", "collective_kill")))
    rows.append(_kill(CALLER))
    rows.append({"mutation": PASSED, "passed": True, "kind": "hard_enable", "kills": [], "ts": "2026-11-10T00:00:00Z"})
    return rows


@pytest.fixture(autouse=True)
def _treatment(monkeypatch, tmp_path):
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: True)
    monkeypatch.delenv("COLONY_RETIRE_DEAD_WEIGHT", raising=False)
    monkeypatch.setattr(R, "RECORD", tmp_path / "retired_checks.json")


def _plan(rows=None, **kw):
    args = dict(src=SRC, oracle_rows=rows if rows is not None else _rows(), deps=set(), receipts=set(),
                guides=set(), code=set(), k_prior=0.10921, now=NOW, frontier_new=lambda n: True)
    args.update(kw)
    return R.plan(**args)


def test_cause_old_rules_find_nothing_dead_weight_finds_the_killed():
    p = _plan()
    cats = {c["name"]: c["category"] for c in p["candidates"]}
    assert cats == {DEAD[0]: "dead_weight", DEAD[1]: "dead_weight", CALLER: "dead_weight"}
    c = next(c for c in p["candidates"] if c["name"] == DEAD[0])
    assert c["replay"]["kill_replays_agree"] == 1 and c["replay"]["passes_before"] == c["replay"]["passes_after"] == 1
    # DEAD[2] is called by another check: protected by the existing rule, never a candidate
    assert "calls it" in p["protected"][DEAD[2]]
    # a not-applicable kill (has turned into passes before) abstains; a pass is never touched
    assert "not a substantive" in p["dead_weight_abstained"][NA]
    assert PASSED not in cats and PASSED not in p["dead_weight_abstained"]


def test_protections_still_win():
    p = _plan(receipts={DEAD[0]}, code={DEAD[1]})
    names = {c["name"] for c in p["candidates"]}
    assert DEAD[0] not in names and DEAD[1] not in names
    p = _plan(now=datetime(2026, 11, 15, 4, 30, tzinfo=timezone.utc))  # within the 2h grace
    assert not [c for c in p["candidates"] if c["category"] == "dead_weight"]


def test_abstain_when_any_replay_disagrees():
    rows = _rows()
    rows.append({"mutation": PASSED, "passed": True, "kind": "hard_enable", "kills": [], "ts": "2026-11-11T00:00:00Z",
                 "note": f"built on {DEAD[0]}"})
    p = _plan(rows)
    assert "named in the Oracle verdict" in p["dead_weight_abstained"][DEAD[0]]
    impure = [_kill(DEAD[1], kind="hard_enable")] + [r for r in _rows() if r["mutation"] != DEAD[1]]
    assert "not deterministic" in _plan(impure)["dead_weight_abstained"][DEAD[1]]
    nosnap = [dict(_kill(DEAD[0]), sense={})] + [r for r in _rows() if r["mutation"] != DEAD[0]]
    assert _plan(nosnap)["dead_weight_abstained"][DEAD[0]] == "no logged held-out snapshot"
    fns = {f"check_{n}": f for n, f in R._functions(ast.parse(SRC)).items()}
    c = RA.certify(DEAD[0], _rows(), fns={}, archived_src=[f"return check_{DEAD[0]}()"])
    assert not c["ok"] and "archived" in c["why"] and fns is not None


def test_kill_replay_is_the_oracle_sense():
    ok, why = RA.replay_kill(_kill(DEAD[0]))
    assert ok and why == "kill replay agrees"
    assert not RA.replay_pure("hard_enable") and not RA.replay_pure("") and RA.replay_pure("authored_check")


def test_control_arm_and_off_mode(monkeypatch):
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: False)
    assert RA.mode() == "off"
    assert not [c for c in _plan()["candidates"] if c["category"] == "dead_weight"]
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: True)
    monkeypatch.setenv("COLONY_RETIRE_DEAD_WEIGHT", "off")
    assert not [c for c in _plan()["candidates"] if c["category"] == "dead_weight"]


def _apply(tmp_path, monkeypatch, p, *, agree=True):
    lemma = tmp_path / "lemma_impl.py"
    lemma.write_text(SRC, encoding="utf-8")
    record = tmp_path / "retired_checks.json"
    record.write_text(json.dumps({"version": 1, "records": [{"name": "authored_old", "category": "sweep",
                                                             "reason": "earlier", "ts": "x"}]}), encoding="utf-8")
    outcome = {"basic": {}, "hard": {PASSED: True}}
    calls = []

    def fake(src):
        calls.append(src)
        return outcome if agree or len(calls) == 1 else {"basic": {}, "hard": {PASSED: False}}
    monkeypatch.setattr(R, "bench_outcomes", fake)
    monkeypatch.setattr(R, "bench_ok", lambda src: {"ok": True})
    monkeypatch.setattr(R, "_invalidate", lambda *a, **k: None, raising=False)
    res = R.apply(p, cycle_id="c1", path=lemma, record=record, state_path=None)
    return res, lemma.read_text(encoding="utf-8"), json.loads(record.read_text(encoding="utf-8"))


def test_apply_appends_records_when_bench_replay_agrees(tmp_path, monkeypatch):
    res, src, rec = _apply(tmp_path, monkeypatch, _plan())
    assert res["applied"] == 3
    assert f"check_{DEAD[0]}" not in src and f"check_{PASSED}" in src
    assert rec["records"][0]["name"] == "authored_old"  # earlier records kept (append-only)
    new = [r for r in rec["records"] if r.get("cycle_id") == "c1"]
    assert {r["category"] for r in new} == {"dead_weight"} and all(r["replay"] and r["fn_src"] for r in new)


def test_apply_abstains_when_bench_replay_disagrees(tmp_path, monkeypatch):
    res, src, rec = _apply(tmp_path, monkeypatch, _plan(), agree=False)
    assert res["applied"] == 0 and "outcome changed" in res["dead_weight_abstained_bench"]
    assert src == SRC and len(rec["records"]) == 1


def test_shadow_lists_but_does_not_retire(tmp_path, monkeypatch):
    monkeypatch.setenv("COLONY_RETIRE_DEAD_WEIGHT", "shadow")
    p = _plan()
    assert p["by_category"].get("dead_weight") == 3
    res, src, _rec = _apply(tmp_path, monkeypatch, p)
    assert res["applied"] == 0 and len(res["dead_weight_not_live"]) == 3 and src == SRC


def test_dead_family_blocks_reauthoring_only_when_certified():
    assert RA.dead_families(_rows()) == {"authored_mut_swap_related_sequence"}
    two = [r for r in _rows() if r["mutation"] in DEAD[:2]]
    assert RA.dead_families(two) == set()  # fewer than DEAD_FAMILY_MIN members
    mixed = _rows() + [{"mutation": "authored_mut_swap_related_sequence_0000000000ff", "passed": True,
                        "kind": "authored_check", "kills": [], "ts": "x"}]
    assert RA.dead_families(mixed) == set()
    from colony.target_generator import _dead_family
    assert _dead_family(DEAD[0]) == "authored_mut_swap_related_sequence"


# --- part 2: self-heal --------------------------------------------------------

def test_last_adopt_single_target():
    from colony.self_heal import _last_adopt_single_target
    st = {"evidence": [{"event": "adopt", "predicted_targets": ["a", "b"]},
                       {"event": "adopt", "predicted_targets": ["oc_A126089_0"]}, {"event": "revert"}]}
    assert _last_adopt_single_target(st) == {"oc_A126089_0"}
    st["evidence"].append({"event": "adopt", "predicted_targets": ["a", "b"]})
    assert _last_adopt_single_target(st) == set()


def test_stall_audit_records_once(monkeypatch):
    p = _plan()
    st = {"trial_skip": {"reason": "no_signal_baseline"}, "evidence": []}
    a = RA.stall_audit(st, "c1", plan_fn=lambda: p)
    assert a["would_free"] == 3 and a["dead_weight"] == 3 and st["trial_skip"]["retirement_audit"] == a
    assert a["abstain_reasons"] == {"a kill that is not a substantive held-out fail": 1}
    RA.stall_audit(st, "c2", plan_fn=lambda: p)
    ev = st["retirement_audits"]
    assert len(ev) == 1 and ev[0]["authorized"] is False and st["evidence"] == []
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: False)
    assert RA.stall_audit({"evidence": []}, "c3", plan_fn=lambda: p) is None
