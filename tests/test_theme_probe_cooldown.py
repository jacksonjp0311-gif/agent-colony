"""Claim-theme probes cool after a saturated-window plus ledger kill.

The title-kill cooldown does not cover a bare theme probe. The theme stays
unproposed until a harder unused window exists. The skip is not an Oracle kill.
"""
from __future__ import annotations

import json

import colony.claim_pipeline as CP
import colony.lessons as L
import colony.novelty_gate as NG
import colony.oracle as O


def _write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _pair_kills():
    return [
        "already_in_lesson_ledger_or_history",
        "oracle_kill:['held_out:held_out:already_saturated_no_harder_window', 'collective_kill']",
    ]


def _logs(tmp_path, monkeypatch, *, theme="vandermonde", window="adversarial_vandermonde_asymmetric",
          kills=None, kind="claim_theme"):
    gate = tmp_path / "novelty_gate.jsonl"
    oracle = tmp_path / "oracle.jsonl"
    monkeypatch.setattr(NG, "GATE_LOG", gate)
    monkeypatch.setattr(O, "ORACLE_LOG", oracle)
    _write(gate, [{
        "ts": "2026-11-11T23:25:28Z",
        "cycle_id": "c_sat",
        "mutation": theme,
        "kind": kind,
        "novel_to_commons": False,
        "kills": kills if kills is not None else _pair_kills(),
    }])
    _write(oracle, [{
        "ts": "2026-11-11T23:25:26Z",
        "cycle_id": "c_sat",
        "mutation": theme,
        "kind": kind,
        "passed": False,
        "kills": ["held_out:held_out:already_saturated_no_harder_window", "collective_kill"],
        "sense": {"held_out": {
            "theme_window": window,
            "in_catalog": True,
            "enabled": False,
            "reason": "held_out:already_saturated_no_harder_window",
        }},
    }])
    return gate, oracle


def test_saturated_ledger_pair_cools_the_same_window(tmp_path, monkeypatch):
    _logs(tmp_path, monkeypatch)
    monkeypatch.setattr(L, "held_out_window_state", lambda theme: {
        "window": "adversarial_vandermonde_asymmetric",
        "in_catalog": True,
        "enabled": False,
        "saturated": True,
    })
    assert L.saturated_claim_theme_windows()["vandermonde"] == "adversarial_vandermonde_asymmetric"
    assert L.harder_unused_window("vandermonde", "adversarial_vandermonde_asymmetric") == ""
    assert L.claim_theme_probe_cooled("vandermonde") is True
    # A theme with no such kill is free.
    assert L.claim_theme_probe_cooled("catalan") is False


def test_one_mark_does_not_cool(tmp_path, monkeypatch):
    _logs(tmp_path, monkeypatch, kills=["already_in_lesson_ledger_or_history"])
    monkeypatch.setattr(L, "held_out_window_state", lambda theme: {
        "window": "adversarial_vandermonde_asymmetric", "in_catalog": True,
        "enabled": False, "saturated": True,
    })
    assert L.saturated_claim_theme_windows() == {}
    assert L.claim_theme_probe_cooled("vandermonde") is False


def test_title_only_kill_is_not_a_theme_probe(tmp_path, monkeypatch):
    _logs(tmp_path, monkeypatch, theme="Seek `vandermonde` citing paper", kind="process")
    assert "vandermonde" not in L.saturated_claim_theme_windows()


def test_different_unused_window_lifts_cooldown(tmp_path, monkeypatch):
    _logs(tmp_path, monkeypatch)
    monkeypatch.setattr(L, "held_out_window_state", lambda theme: {
        "window": "adversarial_vandermonde_deeper",
        "in_catalog": True,
        "enabled": False,
        "saturated": True,
    })
    assert L.harder_unused_window("vandermonde", "adversarial_vandermonde_asymmetric") == (
        "adversarial_vandermonde_deeper"
    )
    assert L.claim_theme_probe_cooled("vandermonde") is False


def test_enabled_harder_window_lifts_cooldown(tmp_path, monkeypatch):
    _logs(tmp_path, monkeypatch)
    monkeypatch.setattr(L, "held_out_window_state", lambda theme: {
        "window": "adversarial_vandermonde_asymmetric",
        "in_catalog": True,
        "enabled": True,
        "saturated": False,
    })
    assert L.harder_unused_window("vandermonde", "adversarial_vandermonde_asymmetric") == (
        "adversarial_vandermonde_asymmetric"
    )
    assert L.claim_theme_probe_cooled("vandermonde") is False


def test_propose_skips_cooled_theme_and_writes_no_kill(tmp_path, monkeypatch):
    gate, oracle = _logs(tmp_path, monkeypatch)
    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")
    monkeypatch.setattr(CP, "CLAIMS_JSONL", tmp_path / "claims.jsonl")
    monkeypatch.setattr(CP, "PIPELINE_SYSTEM", tmp_path / "claim_pipeline.json")
    monkeypatch.setattr(CP, "_oracle_seen_claims", lambda limit=500: set())
    monkeypatch.setattr(CP, "_theme_pass_count", lambda theme_id, limit=500: 0)
    monkeypatch.setattr(L, "held_out_window_state", lambda theme: {
        "window": "adversarial_vandermonde_asymmetric" if theme == "vandermonde" else "",
        "in_catalog": theme == "vandermonde",
        "enabled": False,
        "saturated": theme == "vandermonde",
    })

    def _boom(**kwargs):
        raise AssertionError("cooled theme must not reach the Oracle")

    monkeypatch.setattr(O, "evaluate", _boom)
    before_gate = gate.read_text(encoding="utf-8")
    before_oracle = oracle.read_text(encoding="utf-8")
    claim = CP.ExtractedClaim(
        claim_id="cl_vandermonde_x",
        theme_id="vandermonde",
        text="CLAIM CANDIDATE (not discovered): `vandermonde`",
        provenance={"arxiv_id": "2611.00001"},
        bench_hint="lemma_microbench hard:vandermonde*",
        status="hard_checked",
        hard_ok=True,
    )
    assert CP.propose_checked([claim], cycle_id="c_next", bus=None) == []
    assert claim.status == "rejected_raw"
    assert "theme_probe_cooldown:saturated_no_harder_window" in claim.note
    assert gate.read_text(encoding="utf-8") == before_gate
    assert oracle.read_text(encoding="utf-8") == before_oracle
    lessons = [
        json.loads(ln) for ln in (tmp_path / "lessons.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert lessons[-1]["type"] == "skip"
    assert lessons[-1]["decision"] == "skip"
    assert "oracle_kill" not in (lessons[-1].get("tags") or [])
