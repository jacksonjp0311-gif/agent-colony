"""Spark idea: every Hive cycle that voted but started no trial logs its exact cause
(abstain reason, lower bound vs the unchanged 700 gate, margin, bucket) to the append-only
self-change failure log. Logging only: no penalty, no gate change; control arm writes nothing."""
from __future__ import annotations

import json

import colony.arm as arm
from colony import failure_modes as FM

ABSTAIN = {"ok": True, "cycle_id": "c1", "n_proposals": 3, "started": None,
           "vote": {"winner": {"fingerprint": "set_knob:direction=up:name=perturb_epsilon:value=0.39",
                               "label": "no_progress_perturb", "card_id": "mc_x", "role": "improver"},
                    "abstained": True, "reason": "wilson_abstain", "lower_permille": 342, "margin": 8,
                    "bucket": 8, "bucket_n": 2, "n_votes": 3, "n_vetoes": 0, "runner_up": None,
                    "wilson_gate": 700}}


def test_abstain_logged_with_exact_cause(tmp_path, monkeypatch):
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: True)
    p = tmp_path / "f.jsonl"
    row = FM.log_hive_pick(ABSTAIN, path=p)
    assert row["mode"] == "abstained:wilson_abstain" and row["short_by_permille"] == 358
    assert row["card_id"] == "mc_x" and row["wilson_gate"] == 700
    assert json.loads(p.read_text())["kind"] == "hive_pick"
    # no penalty path reads hive_pick rows
    assert FM.component_losses([row]) == {} and FM.heal_repeat_failures("perturb_epsilon", "up", [row]) == 0


def test_started_skipped_or_control_logs_nothing(tmp_path, monkeypatch):
    p = tmp_path / "f.jsonl"
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: True)
    assert FM.log_hive_pick({**ABSTAIN, "started": {"id": "t"}}, path=p) is None
    assert FM.log_hive_pick({"ok": True, "skipped": True}, path=p) is None
    assert FM.log_hive_pick({"ok": True, "vote": None}, path=p) is None
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: False)
    assert FM.log_hive_pick(ABSTAIN, path=p) is None
    assert not p.exists()
