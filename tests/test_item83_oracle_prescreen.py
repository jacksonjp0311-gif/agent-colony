"""Item 83: pre-screen before Oracle submission. It is strictly a pre-filter.

The screen is the Oracle's own sense_held_out run on a best-case bench, so it
can only drop what the Oracle would kill. Replay covers every row of the Oracle
history, pinned in tests/fixtures/item83_oracle_rows.jsonl (924 rows, 530
passes). No pass is dropped. Hermetic, with the control arm off.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import colony.arm as arm
from colony import oracle as O
from colony import oracle_prescreen as P

FIX = Path(__file__).resolve().parent / "fixtures" / "item83_oracle_rows.jsonl"


@pytest.fixture(autouse=True)
def _treatment(monkeypatch, tmp_path):
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: True)
    monkeypatch.delenv("COLONY_ORACLE_PRESCREEN", raising=False)
    monkeypatch.setattr(P, "PRESCREEN_LOG", tmp_path / "oracle_prescreen.jsonl")
    import colony.lessons as L
    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")


def _rows():
    return [json.loads(x) for x in FIX.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_replay_no_historical_pass_is_dropped():
    rows = _rows()
    passes = [r for r in rows if r["passed"]]
    assert len(passes) == 530
    assert [r["mutation"] for r in passes if P.replay_drop(r)] == []


def test_replay_drops_only_deterministic_kills():
    rows = _rows()
    dropped = [r for r in rows if not r["passed"] and P.replay_drop(r)]
    # every dropped row was killed by held-out at the time
    assert dropped and all(any(k.startswith("held_out:") for k in r["kills"]) for r in dropped)
    # the Chain / Chain+seek wrappers after the 528 -> 530 passes are dropped
    chains = [r for r in rows if str(r["mutation"]).startswith(("Chain `authored_mut_", "Chain+seek `authored_mut_"))]
    assert chains and all(P.replay_drop(r) for r in chains)
    # hard_enable verdicts always reach the Oracle
    assert not any(P.replay_drop(r) for r in rows if r["kind"] == "hard_enable")


@pytest.mark.parametrize("kind", ["process", "authored_check", "oeis_conjecture", "claim_shape"])
def test_kinds_that_cannot_survive_are_dropped(kind):
    d = P.check("Chain `authored_mut_x` citing y", kind)
    assert d and d["would_kill"] == "held_out:held_out_fail"


@pytest.mark.parametrize("kind", ["hard_enable", "hard_check", "", "stem_enable", "easy_pad"])
def test_kinds_never_screened(kind, monkeypatch):
    monkeypatch.setattr(O, "sense_held_out", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no")))
    assert P.check("authored_x", kind) is None


def test_screen_is_monotone_in_the_bench():
    """Whenever the Oracle's held-out survives on SOME snapshot, the best-case screen keeps it."""
    snaps = [{"ok": ok, "n_hard_pass": hp, "n_hard": 3, "score": 0.5} for ok in (True, False) for hp in (0, 2, 3)]
    for kind in ("process", "authored_check", "oeis_conjecture", "claim_shape", "claim_theme"):
        for s in snaps:
            if O.sense_held_out("vandermonde", kind, after_snapshot=s).get("survives"):
                assert P.check("vandermonde", kind) is None


def _lemma(tmp_path, monkeypatch, flag):
    art = tmp_path / "society" / "benchmarks" / "artifacts"
    art.mkdir(parents=True)
    (art / "lemma_impl.py").write_text(
        f'HARD_TIER_LEMMAS = [\n    ("adversarial_vandermonde_asymmetric", lambda: True, {flag}),\n]\n', encoding="utf-8")
    monkeypatch.setattr(O, "ROOT", tmp_path)


def test_claim_theme_window_disabled_is_dropped_with_the_kill_hint(tmp_path, monkeypatch):
    _lemma(tmp_path, monkeypatch, False)
    d = P.check("vandermonde", "claim_theme")
    assert d["would_kill"] == "held_out:held_out:already_saturated_no_harder_window"
    assert d["catalog_hint"] == {"add_mutation": "vandermonde_asymmetric", "kind": "hard_enable"}


def test_claim_theme_window_enabled_reaches_the_oracle(tmp_path, monkeypatch):
    _lemma(tmp_path, monkeypatch, True)
    assert P.check("vandermonde", "claim_theme") is None


def test_live_writes_log_and_cooldown_lesson_shadow_and_control(monkeypatch):
    import colony.lessons as L
    d = P.screen("Chain `authored_mut_x` citing y", "process", source="novelty_gate_deferred_title", cycle_id="c1")
    assert d and d["dropped"] and d["not_an_oracle_verdict"]
    log = [json.loads(x) for x in P.PRESCREEN_LOG.read_text().splitlines()]
    assert log[-1]["mutation"].startswith("Chain")
    les = [e for e in L.load_lessons(limit=50, include_expired=True) if e.get("type") == "oracle_prescreen"]
    assert les and les[-1]["source"] == "novelty_gate_deferred_title"
    assert sum(L.oracle_kill_theme_counts().values()) >= 1  # counts toward the kill cooldown
    monkeypatch.setenv("COLONY_ORACLE_PRESCREEN", "shadow")
    assert P.screen("Chain `b` citing y", "process") is None and len(P.PRESCREEN_LOG.read_text().splitlines()) == 2
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: False)
    assert P.mode() == "off" and P.screen("Chain `c` citing y", "process") is None


def test_novelty_gate_skips_the_oracle_on_a_drop(monkeypatch, tmp_path):
    import colony.novelty_gate as NG
    monkeypatch.setattr(NG, "GATE_LOG", tmp_path / "ng.jsonl")
    monkeypatch.setattr(NG, "GATE_SYSTEM", tmp_path / "ng.json")
    monkeypatch.setattr(NG, "known_identities", lambda: set())
    monkeypatch.setattr(NG, "stripped_baseline_fails", lambda *a, **k: {"stripped_fails_usefulness": False})
    monkeypatch.setattr(O, "evaluate", lambda **k: (_ for _ in ()).throw(AssertionError("Oracle must not run")))
    v = NG.evaluate(mutation="Chain `authored_mut_x` citing y", kind="process", claim_text="t",
                    oracle_source="novelty_gate_deferred_title")
    assert v["novel_to_commons"] is False and v["oracle_used"] == "prescreen_drop"
    assert "oracle_prescreen:held_out:held_out_fail" in v["kills"]
    calls = []
    monkeypatch.setattr(O, "evaluate", lambda **k: calls.append(k) or type("V", (), {"passed": False, "kills": ["x"]})())
    NG.evaluate(mutation="authored_y", kind="hard_enable", claim_text="t")
    assert calls  # unscreened kinds go to the Oracle as before


def test_stall_bus_path_skips_a_dropped_candidate(monkeypatch):
    import colony.stall as S
    monkeypatch.setattr(O, "gate_keep", lambda **k: (_ for _ in ()).throw(AssertionError("Oracle must not run")))
    S.enter_perturb("q0", reason="flat_passes", commit_sha="deadbeef")
    menu = [{"id": f"authored_t{i}", "source": "authored_check", "kind": "authored_check", "form": "gf",
             "text": f"claim {i}", "band": 0, "unseen": True, "unused": True} for i in range(4)]
    out = S.run_perturb_turn("q_run", n=2, bus=object(), menu=menu, commit_sha="deadbeef")
    subs = [s for s in out["submissions"] if str(s.get("id") or "").startswith("authored_t")]
    assert any(s.get("skipped") == "oracle_prescreen" for s in subs)
    assert not any(s.get("attempt") or s.get("reached_oracle") for s in subs)
