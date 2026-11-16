"""Item 90: novelty fell 0.75 -> 0.17 because Chain / Chain+seek wrappers of an already-passed
target were generated, dropped (or killed), and their row became that target's latest novelty
result, displacing the hit. Fixed at the source:

1. seek_proposal_from_guides never wraps a target the Oracle already passed (live arm only);
2. a pre-screen drop is not recorded in the novelty gate (it never reached the Oracle).

Counting stays per-target-latest (NOT best-per-target); Oracle and new-to-commons tests unchanged.
"""
from __future__ import annotations

import json

import pytest

import colony.arm as arm
from colony import oracle as O

import test_authoring as TA  # noqa: E402  (same tests dir; reuse its hermetic repo builder)


@pytest.fixture(autouse=True)
def _pairs_on(monkeypatch):
    monkeypatch.setenv("COLONY_AUTHOR_PAIRS", "on")


def _oracle_log(tmp_path, monkeypatch, rows):
    p = tmp_path / "oracle.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    monkeypatch.setattr(O, "ORACLE_LOG", p)
    return p


def test_passed_themes_read_from_oracle_log(tmp_path, monkeypatch):
    import colony.lessons as L
    _oracle_log(tmp_path, monkeypatch, [
        {"mutation": "authored_x_w1", "passed": True, "kind": "hard_enable"},
        {"mutation": "Chain+seek `authored_x_w1` from invariant priors", "passed": False, "kind": "process"},
        {"mutation": "authored_y_w1", "passed": False, "kind": "hard_enable"},
    ])
    got = L.oracle_passed_themes()
    assert L.theme_key("authored_x_w1") in got
    assert L.theme_key("authored_y_w1") not in got


def test_seek_never_wraps_an_already_passed_target(tmp_path, monkeypatch):
    import colony.lessons as L
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: True)
    TA._repo(tmp_path, monkeypatch)
    TA._guide()
    rows = TA.A.author_checks(cycle_id="t1")
    name = rows[0]["name"]
    _oracle_log(tmp_path, monkeypatch, [])
    pick = L.seek_proposal_from_guides(cycle_id="t2")
    assert pick is not None and pick[2] == f"seek_enable:{name}"  # unpassed: still sought
    _oracle_log(tmp_path, monkeypatch, [{"mutation": name, "passed": True, "kind": "hard_enable"}])
    pick2 = L.seek_proposal_from_guides(cycle_id="t3")
    assert pick2 is None or L.theme_key(pick2[2]) != L.theme_key(name)


def test_control_arm_unchanged(tmp_path, monkeypatch):
    import colony.lessons as L
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: False)
    TA._repo(tmp_path, monkeypatch)
    TA._guide()
    name = TA.A.author_checks(cycle_id="t1")[0]["name"]
    _oracle_log(tmp_path, monkeypatch, [{"mutation": name, "passed": True, "kind": "hard_enable"}])
    called = []
    monkeypatch.setattr(L, "oracle_passed_themes", lambda: called.append(1) or {L.theme_key(name)})
    L.seek_proposal_from_guides(cycle_id="t2")
    assert called == []  # control arm never consults the new filter


def _gate(tmp_path, monkeypatch):
    import colony.novelty_gate as NG
    from colony import oracle_prescreen as P
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: True)
    monkeypatch.delenv("COLONY_ORACLE_PRESCREEN", raising=False)
    monkeypatch.setattr(P, "PRESCREEN_LOG", tmp_path / "oracle_prescreen.jsonl")
    import colony.lessons as L
    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(NG, "GATE_LOG", tmp_path / "ng.jsonl")
    monkeypatch.setattr(NG, "GATE_SYSTEM", tmp_path / "ng.json")
    monkeypatch.setattr(NG, "known_identities", lambda: set())
    monkeypatch.setattr(NG, "stripped_baseline_fails", lambda *a, **k: {"stripped_fails_usefulness": True})
    monkeypatch.setattr(NG, "held_out_harder_survives", lambda *a, **k: {"survives": True})
    monkeypatch.setattr(NG, "textbook_reuse_score", lambda *a, **k: 0.0)
    return NG, P


def test_prescreen_drop_not_recorded_and_hit_stays_latest(tmp_path, monkeypatch):
    NG, P = _gate(tmp_path, monkeypatch)
    monkeypatch.setattr(O, "evaluate", lambda **k: type("V", (), {"passed": True, "kills": []})())
    hit = NG.evaluate(mutation="authored_z_w1", kind="hard_enable", claim_text="t")
    assert hit["novel_to_commons"] is True
    monkeypatch.setattr(O, "evaluate", lambda **k: (_ for _ in ()).throw(AssertionError("Oracle must not run")))
    drop = NG.evaluate(mutation="Chain+seek `authored_z_w1` from invariant priors", kind="process",
                       claim_text="t", oracle_source="novelty_gate_deferred_title")
    # caller still sees a non-novel verdict with the pre-screen kill reason
    assert drop["novel_to_commons"] is False and drop["oracle_used"] == "prescreen_drop"
    assert drop["recorded"] is False and any(k.startswith("oracle_prescreen:") for k in drop["kills"])
    rows = [json.loads(x) for x in NG.GATE_LOG.read_text().splitlines()]
    assert [r["mutation"] for r in rows] == ["authored_z_w1"]  # the drop is not a gate row
    assert NG.per_target_tally(rows) == (1, 0)
    sysd = json.loads(NG.GATE_SYSTEM.read_text())
    assert sysd["hits"] == 1 and sysd["kills"] == 0 and sysd["counting"] == "per_target_latest"
    assert P.PRESCREEN_LOG.exists()  # the drop is still logged where it belongs


def test_real_oracle_kill_still_recorded_and_counts_latest(tmp_path, monkeypatch):
    NG, _ = _gate(tmp_path, monkeypatch)
    monkeypatch.setattr(O, "evaluate", lambda **k: type("V", (), {"passed": True, "kills": []})())
    NG.evaluate(mutation="authored_q_w1", kind="hard_enable", claim_text="t")
    monkeypatch.setattr(O, "evaluate", lambda **k: type("V", (), {"passed": False, "kills": ["x"]})())
    v = NG.evaluate(mutation="authored_q_w1", kind="hard_enable", claim_text="t")
    assert v["novel_to_commons"] is False and "recorded" not in v
    rows = [json.loads(x) for x in NG.GATE_LOG.read_text().splitlines()]
    assert len(rows) == 2 and NG.per_target_tally(rows) == (0, 1)  # latest still wins: not best-per-target
