"""Item 81: stall-perturb hands generated checks to the conjecture desk.

Why: the stall path sent ``authored_mut_`` checks to the Oracle as kind
``authored_check``. sense_held_out sets kind_ok only for "" / hard_* kinds, so
that kind can never survive held-out (51 verdicts, 0 passes). The desk path
enables the check, keeps the whole bench green, and asks the Oracle with kind
``hard_enable``: the same stripped-baseline / held-out (plus the real shifted
window) / CAS / collective checks that judged every one of the 285 passing
authored checks. Re-screened with the current triviality filter at pick time.
P >= 0.70, the 150 cap and the Oracle code are unchanged. Hermetic fixtures.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import colony.arm as arm
import colony.stall as S
import colony.target_generator as TG
from colony import oracle as O
from colony import retire_audit as RA

ROOT = Path(__file__).resolve().parent.parent
SNAP = {"n_hard_pass": 162, "n_hard": 162, "ok": True, "score": 0.8728}


def _menu(prefix):
    return [{"id": f"{prefix}{i:012x}", "source": "authored_check", "kind": "authored_check",
             "form": "gf", "text": f"authored claim {i}", "band": 0, "unseen": True, "unused": True}
            for i in range(6)]


def _run(menu):
    S.enter_perturb("h0", reason="flat_passes", commit_sha="deadbeef")
    reached = []

    def submit(t):
        reached.append(t["id"])
        return {"passed": False, "kills": ["x"]}
    out = S.run_perturb_turn("h_run", n=2, oracle_submit=submit, menu=menu, commit_sha="deadbeef")
    return out, reached


def test_generated_checks_are_handed_to_the_desk(monkeypatch):
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: True)
    monkeypatch.setattr(S, "choose_open", lambda *a, **k: [], raising=False)
    out, reached = _run(_menu("authored_mut_swap_related_sequence_"))
    assert reached == []  # never judged as kind authored_check
    subs = out.get("submissions") or out.get("targets_submitted") or []
    flat = [s for s in subs if isinstance(s, dict)]
    assert any(s.get("skipped") == "handed_to_conjecture_desk" and s["handoff"]["desk_kind"] == "hard_enable"
               for s in flat)
    assert not any(s.get("attempt") for s in flat if str(s.get("id") or "").startswith("authored_mut_"))


def test_other_authored_candidates_and_control_arm_unchanged(monkeypatch):
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: True)
    _out, reached = _run(_menu("authored_t"))
    assert len(reached) >= 2  # not a generated check: old path
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: False)
    assert TG.perturb_handoff_live() is False
    _out, reached = _run(_menu("authored_mut_swap_related_sequence_"))
    assert len(reached) >= 2  # control arm frozen: old behaviour


def test_off_switch(monkeypatch):
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: True)
    monkeypatch.setenv("COLONY_PERTURB_HANDOFF", "off")
    assert TG.perturb_handoff_live() is False


# --- the Oracle is not looser for these, and no past verdict changes ----------

def test_held_out_kinds_unchanged():
    """authored_check never survives; hard_enable needs a green hard tier AND the shifted window."""
    r = O.sense_held_out("authored_mut_x", "authored_check", after_snapshot=SNAP)
    assert r["survives"] is False and r["reason"] == "held_out_fail"
    red = dict(SNAP, n_hard_pass=161)
    r = O.sense_held_out("authored_mut_x", "hard_enable", after_snapshot=red)
    assert r["survives"] is False  # a red bench fails before the shifted window is tried


def test_hard_enable_requires_shifted_window(monkeypatch):
    import colony.trust.shifted_holdout as SHO
    monkeypatch.setattr(SHO, "shifted_window_check", lambda p, n: {"status": "not_tested", "applied": False,
                                                                  "ok": False, "reason": "shift_not_applicable(no_data_headroom)"})
    r = O.sense_held_out("authored_mut_x", "hard_enable", after_snapshot=SNAP)
    assert r["survives"] is False and r["reason"].startswith("held_out_shift_not_applicable")
    monkeypatch.setattr(SHO, "shifted_window_check", lambda p, n: {"status": "pass", "applied": True, "ok": True})
    assert O.sense_held_out("authored_mut_x", "hard_enable", after_snapshot=SNAP)["survives"] is True


def test_replay_of_past_verdicts_is_identical():
    """Every past authored_check kill replays to the same kill (item 81 does not touch the Oracle)."""
    rows = [{"mutation": f"authored_mut_swap_related_sequence_{i:012x}", "kind": "authored_check",
             "passed": False, "kills": ["held_out:held_out_fail", "collective_kill"],
             "sense": {"held_out": {"hard_pass": 162, "hard_n": 162, "ok": True, "score": 0.87}}} for i in range(5)]
    assert all(RA.replay_kill(r) == (True, "kill replay agrees") for r in rows)



def test_desk_variant_needs_current_triviality_filter(tmp_path, monkeypatch):
    import colony.lessons as L
    from colony import frontier_checks as FK
    from colony.authoring import FALLBACK_MARKER
    art = tmp_path / "artifacts"
    art.mkdir()
    name = "authored_mut_swap_related_sequence_0123456789ab"
    (art / "lemma_impl.py").write_text(f'''
# frontier bridge
def frontier_holds(c, a, b):
    return b - a


def check_{name}() -> bool:
    return all(type(c := frontier_holds({{'kind': 'divides', 'lhs': 'a', 'params': {{}}, 'rhs': 'b'}}, a, b)) is int and c > 0 for a, b in [(40, 80)])


{FALLBACK_MARKER}
BASIC: list = []
HARD_TIER_LEMMAS: list = [
    ("{name}", check_{name}, False),
]
''', encoding="utf-8")
    monkeypatch.setattr(L, "BENCH_ARTIFACTS_DIR", art)
    monkeypatch.setattr(L, "mutation_cooldown", lambda: None)
    monkeypatch.setattr(L, "chain_citations", lambda n: {"artifact": "lemma_impl.py", "links": []})
    monkeypatch.setattr(FK, "frontier_links", lambda fn, src: [{"lemma": "frontier:frontier_holds", "proven": True}])
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: True)
    monkeypatch.setattr(FK, "trivial_now", lambda n, src=None: False)
    assert [v["name"] for v in L.unenabled_chain_variants()] == [name]
    assert L.unenabled_chain_variants()[0]["kind"] == "hard_enable"
    monkeypatch.setattr(FK, "trivial_now", lambda n, src=None: True)   # flagged by the current filter
    assert L.unenabled_chain_variants() == []
    monkeypatch.setattr(FK, "trivial_now", lambda n, src=None: None)   # cannot tell: fail closed
    assert L.unenabled_chain_variants() == []
    monkeypatch.setattr(FK, "trivial_now", lambda n, src=None: False)
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: False)        # control arm: not handed
    assert L.unenabled_chain_variants() == []


def test_dead_family_block_only_without_handoff(monkeypatch):
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: True)
    assert TG.perturb_handoff_live() is True
    monkeypatch.setenv("COLONY_PERTURB_HANDOFF", "off")
    assert TG.perturb_handoff_live() is False


def test_perturb_menu_skips_generated_while_handed_off(monkeypatch):
    monkeypatch.setattr(TG, "oracle_reachable_generated", lambda state=None, src=None: [
        {"id": "authored_mut_demo_abcd", "can_progress": True, "source": "authored_check"}])
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: True)
    assert TG.perturb_candidates() == []
    monkeypatch.setenv("COLONY_PERTURB_HANDOFF", "off")
    assert [t["id"] for t in TG.perturb_candidates()] == ["authored_mut_demo_abcd"]
