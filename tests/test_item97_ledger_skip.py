"""Item 97: desk skips STEM picks the novelty gate would kill as already in the ledger (treatment only)."""
from __future__ import annotations

import json

import pytest

import colony.conjecture_desk as D
import colony.lessons as L
import colony.novelty_gate as ng
import colony.stall as S


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    lessons = tmp_path / "lessons.jsonl"
    history = tmp_path / "conjecture_history.jsonl"
    known = tmp_path / "known_identities.json"
    lessons.write_text("\n".join(json.dumps(r) for r in [
        {"ts": "t", "type": "revert", "mutation": "stem_rc_discharge", "family": "stem_enable"},
        {"ts": "t", "type": "authored_check", "mutation": "authored_fresh_w1", "family": "authored"},
    ]) + "\n")
    history.write_text(json.dumps({"ts": "t", "decision": "revert", "mutation": "stem_wheatstone_balance"}) + "\n")
    monkeypatch.setattr(ng, "LESSONS", lessons)
    monkeypatch.setattr(ng, "HISTORY", history)
    monkeypatch.setattr(ng, "KNOWN", known)
    return known


def test_in_ledger_kill_matches_gate_condition(ledger):
    known = ng.known_identities_readonly()
    assert ng.in_ledger_kill("stem_rc_discharge", known)
    assert ng.in_ledger_kill("stem_wheatstone_balance", known)
    assert not ng.in_ledger_kill("stem_snell_least_time", known)
    assert not ng.in_ledger_kill("authored_fresh_w1", known)  # own birth record only: same exception as the gate
    assert not ng.in_ledger_kill("", known)


def test_readonly_does_not_write_snapshot_and_matches(ledger):
    ro = ng.known_identities_readonly()
    assert not ledger.exists()
    assert ng.known_identities() == ro  # the gate's set is unchanged
    assert ledger.exists()  # and the gate still persists its snapshot


def _pick(ordered, shift):
    cd = L.MutationCooldown(blocked={}, avoided=set(), penalties={})
    return D.pick_mutation(ordered, cooldown=cd, lemma_src="", shift_prescreen=shift)


def test_desk_skips_ledgered_stem_enable(ledger, monkeypatch):
    monkeypatch.setattr(S, "load_oracle_rows", lambda limit=2500: [])
    monkeypatch.setattr(D, "_already_has", lambda src, name: False)
    import colony.oracle_prescreen as P
    monkeypatch.setattr(P, "screen", lambda *a, **k: None)
    ordered = [("stem_rc_discharge", "stem_enable", "enable:stem_rc_discharge"),
               ("stem_wheatstone_balance", "stem_enable", "enable:stem_wheatstone_balance"),
               ("stem_snell_least_time", "stem_enable", "enable:stem_snell_least_time")]
    name, kind, _s, cooled = _pick(ordered, True)
    assert name == "stem_snell_least_time"
    assert cooled["stem_rc_discharge"] == cooled["stem_wheatstone_balance"] == "already_in_lesson_ledger_or_history"
    # control arm path (shift_prescreen off): unchanged
    assert _pick(ordered, False)[0] == "stem_rc_discharge"


def test_rule_is_stem_enable_only(ledger, monkeypatch):
    monkeypatch.setattr(S, "load_oracle_rows", lambda limit=2500: [])
    monkeypatch.setattr(D, "_already_has", lambda src, name: False)
    # the Oracle's sieve self-test pad is never skipped by this rule
    assert _pick([("stem_rc_discharge", "stem_easy_pad", "x")], True)[0] == "stem_rc_discharge"
