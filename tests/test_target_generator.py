"""Phase 1 target generator: mutations, filters, cap, control freeze, PERTURB wiring."""
from __future__ import annotations

import ast
import json
import textwrap
from pathlib import Path

import pytest

from colony import target_generator as TG
from colony import stall as S
from colony import self_heal as SH
from colony import authoring as AU
from colony import arm


# --- fixtures ----------------------------------------------------------------

def _claim(kind="le", lhs="fib", rhs="lucas", params=None, **extra):
    c = {"kind": kind, "lhs": lhs, "rhs": rhs or "", "params": dict(params or {})}
    c.update(extra)
    return c


def _lemma_src() -> str:
    return textwrap.dedent("""\
    # Adversarial aliases used by Oracle theme held-out windows
    # Mutable catalog the conjecture desk may extend / mutate.

    HARD_TIER_LEMMAS: list = [
    ]
    """)


def _isolate(tmp_path, monkeypatch):
    lemma = tmp_path / "lemma_impl.py"
    lemma.write_text(_lemma_src(), encoding="utf-8")
    log = tmp_path / "generated_targets.jsonl"
    monkeypatch.setenv("COLONY_TG_LEMMA", str(lemma))
    monkeypatch.setenv("COLONY_GENERATED_TARGETS_LOG", str(log))
    monkeypatch.setattr(AU, "_lemma_impl", lambda: lemma)
    monkeypatch.setattr(TG, "self_mod_ok", lambda: True)
    return lemma, log


def _accept(*_a, **_k):
    return {"accepted": True, "seconds": 0.01, "reason": "verified"}


# --- mutation mechanics (no I/O, no hardcoded sequence ids) -------------------

def test_flip_inequality_swaps_le_and_divides_sides():
    flipped = TG.apply_mutation(_claim("le", "alpha", "beta"), "flip_inequality")
    assert len(flipped) == 1
    assert flipped[0]["lhs"] == "beta" and flipped[0]["rhs"] == "alpha"
    assert flipped[0]["kind"] == "le"
    div = TG.apply_mutation(_claim("divides", "alpha", "beta"), "flip_inequality")
    assert div[0]["lhs"] == "beta" and div[0]["rhs"] == "alpha"
    # Identities and congruences are not flipped.
    assert TG.apply_mutation(_claim("identity", "alpha", "beta"), "flip_inequality") == []
    assert TG.apply_mutation(_claim("cong", "alpha", "", {"m": 2, "q": 2, "r": 0, "s": 0}), "flip_inequality") == []


def test_tighten_inequality_is_strictly_stronger():
    got = TG.apply_mutation(_claim("le", "alpha", "beta"), "tighten_inequality")
    lhss = {g["lhs"] for g in got}
    assert "(alpha+one)" in lhss
    assert "dbl(alpha)" in lhss
    assert all(g["rhs"] == "beta" and g["kind"] == "le" for g in got)


def test_perturb_constant_changes_modulus_and_rec_coeffs():
    cong = _claim("cong", "alpha", "", {"m": 2, "q": 2, "r": 0, "s": 0})
    got = TG.apply_mutation(cong, "perturb_constant")
    ms = {g["params"]["m"] for g in got}
    assert 2 not in ms
    assert 3 in ms and 4 in ms
    assert all(g["params"]["r"] < g["params"]["m"] for g in got)
    rec = _claim("rec", "alpha", "", {"c": [-1, 0, 2]})
    recs = TG.apply_mutation(rec, "perturb_constant")
    coeffs = [tuple(g["params"]["c"]) for g in recs]
    assert (-1, 0, 2) not in coeffs
    assert (-1, 0, 3) in coeffs or (-1, 0, 1) in coeffs


def test_swap_uses_cooccurrence_not_hardcoded_ids():
    held = [
        _claim("le", "alpha", "beta", sig="s1"),
        _claim("le", "alpha", "gamma", sig="s2"),
        _claim("cong", "delta", "", {"m": 2, "q": 2, "r": 0, "s": 0}, sig="s3"),
    ]
    graph = TG.related_primitives(held)
    # alpha co-occurs with beta and with gamma, so beta and gamma are related to alpha.
    assert "beta" in graph["alpha"] and "gamma" in graph["alpha"]
    # delta is alone: no relatives.
    assert graph.get("delta", set()) == set()
    # Swapping alpha→gamma on the first claim (alpha <= beta) yields gamma <= beta,
    # and does not replace a prim already in the claim.
    swaps = TG.apply_mutation(held[0], "swap_related_sequence", related=graph)
    pairs = {(s["_swap"]["from"], s["_swap"]["to"]) for s in swaps}
    assert ("alpha", "gamma") in pairs
    assert ("alpha", "beta") not in pairs  # beta already present
    # No hardcoded OEIS A-numbers in the mechanism.
    src = Path(TG.__file__).read_text(encoding="utf-8")
    assert "A165064" not in src and "A000045" not in src


def test_widen_skipped_for_certified_claims():
    raw = _claim("le", "alpha", "beta", certificate={"checker": "ok"})
    assert TG.apply_mutation(raw, "widen_range") == []
    raw2 = _claim("le", "alpha", "beta", certificate=None)
    got = TG.apply_mutation(raw2, "widen_range")
    assert len(got) == 1 and got[0].get("_widen")


def test_degenerate_rejects_self_gcd_and_identical_sides():
    assert TG.is_degenerate(_claim("cong", "gcd(phi,phi)", "", {"m": 2, "q": 2, "r": 0, "s": 0})) == "gcd_same"
    assert TG.is_degenerate(_claim("le", "alpha", "alpha")) == "identical_sides"
    assert TG.is_degenerate(_claim("cong", "(fib*fib)", "", {"m": 2, "q": 2, "r": 0, "s": 0})) == "product_same"
    assert TG.is_degenerate(_claim("le", "alpha", "beta")) == ""


def test_enumerate_is_deterministic():
    held = [
        _claim("le", "alpha", "beta", sig="a"),
        _claim("cong", "gamma", "", {"m": 2, "q": 2, "r": 0, "s": 0}, sig="b"),
    ]
    a = [TG.canonical_key(r, r["mut_kind"]) for r in TG.enumerate_mutations(held)]
    b = [TG.canonical_key(r, r["mut_kind"]) for r in TG.enumerate_mutations(held)]
    assert a == b and a
    assert any(r["mut_kind"] == "flip_inequality" for r in TG.enumerate_mutations(held))
    assert any(r["mut_kind"] == "perturb_constant" for r in TG.enumerate_mutations(held))


# --- authoring, cap, control, dedupe -----------------------------------------

def test_author_targets_writes_one_check_under_the_cap(tmp_path, monkeypatch):
    lemma, log = _isolate(tmp_path, monkeypatch)
    held = [_claim("le", "alpha", "beta", sig="s1", statement="alpha <= beta")]
    # Skip live filters; inject a passing verify.
    rows = TG.author_targets(
        max_new=1, cycle_id="c1", write=True, claims=held,
        verify=_accept, skip_filters=True,
    )
    assert len(rows) == 1
    assert rows[0]["accepted"] is True
    assert rows[0]["name"].startswith(TG.PREFIX)
    assert rows[0]["name"].startswith(AU.AUTHORED_PREFIX)
    text = lemma.read_text(encoding="utf-8")
    assert rows[0]["name"] in text
    assert f"check_{rows[0]['name']}" in text
    # Disabled until the Oracle passes it.
    assert f'("{rows[0]["name"]}"' in text and ", False)" in text
    # Append-only log.
    events = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert events and events[0]["event"] == "authored"
    # A second call dedupes the same mutation.
    rows2 = TG.author_targets(
        max_new=1, cycle_id="c2", write=True, claims=held,
        verify=_accept, skip_filters=True,
    )
    # Other mutations of the same source may still author, but the first key is spent.
    names = {rows[0]["name"]} | {r["name"] for r in rows2}
    authored_lines = [l for l in lemma.read_text(encoding="utf-8").splitlines() if TG.PREFIX in l and l.strip().startswith("(")]
    assert len(authored_lines) == len(names)
    assert rows[0]["name"] not in {r["name"] for r in rows2}


def test_author_targets_respects_the_150_cap(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(AU, "authored_count", lambda: 150)
    held = [_claim("le", "alpha", "beta", sig="s1")]
    rows = TG.author_targets(max_new=1, write=True, claims=held, verify=_accept, skip_filters=True)
    assert rows == []


def test_author_targets_disabled_on_control(tmp_path, monkeypatch):
    lemma, _ = _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(TG, "self_mod_ok", lambda: False)
    held = [_claim("le", "alpha", "beta", sig="s1")]
    rows = TG.author_targets(max_new=1, write=True, claims=held, verify=_accept, skip_filters=True)
    assert rows == []
    assert TG.PREFIX not in lemma.read_text(encoding="utf-8")


def test_author_targets_ignores_lemma_score_saturation(tmp_path, monkeypatch):
    """The whole reason maybe_supply authored nothing: hard_pass is already pinned."""
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(AU, "hard_pass_cannot_raise_score", lambda: True)
    held = [_claim("le", "alpha", "beta", sig="s1")]
    rows = TG.author_targets(max_new=1, write=True, claims=held, verify=_accept, skip_filters=True)
    assert len(rows) == 1


def test_author_targets_silent_during_unisolated_pytest(tmp_path, monkeypatch):
    # Default paths point at the repo; the guard must refuse to write.
    monkeypatch.delenv("COLONY_TG_LEMMA", raising=False)
    monkeypatch.delenv("COLONY_GENERATED_TARGETS_LOG", raising=False)
    monkeypatch.setattr(TG, "self_mod_ok", lambda: True)
    # Do not redirect AU._lemma_impl — that's the real file.
    before = AU._lemma_impl().read_text(encoding="utf-8") if AU._lemma_impl().exists() else ""
    held = [_claim("le", "alpha", "beta", sig="s1")]
    rows = TG.author_targets(max_new=1, write=True, claims=held, verify=_accept, skip_filters=True)
    assert rows == []
    after = AU._lemma_impl().read_text(encoding="utf-8") if AU._lemma_impl().exists() else ""
    assert after == before


def test_build_check_is_valid_python_and_uses_frontier_holds():
    c = _claim("le", "alpha", "beta", statement="alpha(n) <= beta(n)")
    c = TG._with_statement(c)
    built = TG.build_check(c, "flip_inequality")
    assert built is not None
    ast.parse(built["fn_src"])
    assert "frontier_holds" in built["fn_src"]
    assert built["name"].startswith(TG.PREFIX)
    assert "Disabled until the Oracle" in built["fn_src"]


def test_cap_constants_unchanged():
    assert AU.MAX_AUTHORED_TOTAL == 150
    assert AU.MAX_AUTHORED_PER_CYCLE == 1


# --- Oracle-reachable wiring -------------------------------------------------

def test_reachable_only_counts_disabled_authored_mut_checks(tmp_path, monkeypatch):
    lemma, log = _isolate(tmp_path, monkeypatch)
    src = textwrap.dedent("""\
    def check_authored_mut_swap_aaa() -> bool:
        return True
    def check_authored_mut_swap_bbb() -> bool:
        return True
    def check_authored_other() -> bool:
        return True
    # Adversarial aliases used by Oracle theme held-out windows
    HARD_TIER_LEMMAS: list = [
        ("authored_mut_swap_aaa", check_authored_mut_swap_aaa, False),
        ("authored_mut_swap_bbb", check_authored_mut_swap_bbb, True),
        ("authored_other", check_authored_other, False),
    ]
    """)
    lemma.write_text(src, encoding="utf-8")
    got = TG.oracle_reachable_generated(src=src)
    ids = {t["id"] for t in got}
    assert ids == {"authored_mut_swap_aaa"}
    assert all(t["can_progress"] and t["source"] == "authored_check" for t in got)
    # A reject log entry removes reachability.
    log.write_text(json.dumps({"event": "killed", "name": "authored_mut_swap_aaa"}) + "\n")
    assert TG.oracle_reachable_generated(src=src) == []


def test_has_eligible_true_when_a_generated_target_is_reachable(tmp_path, monkeypatch):
    lemma, _ = _isolate(tmp_path, monkeypatch)
    # Real wiring: oracle_reachable_alternatives includes generated targets.
    monkeypatch.setattr(S, "_oeis_candidates", lambda *a, **k: [])
    monkeypatch.setattr(TG, "oracle_reachable_generated", lambda state=None, src=None: [
        {"id": "authored_mut_demo_abcd", "can_progress": True, "source": "authored_check"},
    ])
    # Re-import path: stall calls TG.oracle_reachable_generated inside the function,
    # so patch the name stall will import. It does `from colony.target_generator import ...`
    # each call, so we patch the module attribute — the import binds at call time
    # from the module, which we just patched. Good.
    alts = S.oracle_reachable_alternatives()
    # Because stall imports inside the function, our patch on TG is seen.
    assert any(t["id"] == "authored_mut_demo_abcd" and t["can_progress"] for t in alts)
    assert S.has_eligible_progress_target() is True


def test_has_eligible_false_without_real_generated_or_oeis(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(S, "_oeis_candidates", lambda *a, **k: [])
    monkeypatch.setattr(TG, "oracle_reachable_generated", lambda state=None, src=None: [])
    assert S.has_eligible_progress_target() is False
    # Empty id or can_progress False does not count.
    monkeypatch.setattr(TG, "oracle_reachable_generated", lambda state=None, src=None: [
        {"id": "", "can_progress": True},
        {"id": "authored_mut_x", "can_progress": False},
    ])
    assert S.has_eligible_progress_target() is False


def test_select_perturb_includes_generated_targets(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(S, "_oeis_candidates", lambda *a, **k: [])
    monkeypatch.setattr(S, "load_state", lambda: S._empty_state())
    monkeypatch.setattr(TG, "perturb_candidates", lambda tried=None, ledger=None, src=None: [
        {"id": "authored_mut_demo_abcd", "source": "authored_check", "kind": "authored_check",
         "can_progress": True, "untried": True, "unseen": True, "unused": True, "band": 0, "mutated": True},
    ])
    picked = S.select_perturb_targets("cycle_x", n=1)
    assert any(t["id"] == "authored_mut_demo_abcd" for t in picked)
    # An explicit menu is unchanged (tests / callers that pass one).
    picked2 = S.select_perturb_targets("cycle_x", n=1, menu=[
        {"id": "oc_only", "source": "oeis", "kind": "oeis_conjecture", "untried": True, "band": 0},
    ])
    assert all(t["id"] != "authored_mut_demo_abcd" for t in picked2)


def test_maybe_supply_prefers_the_generator(tmp_path, monkeypatch):
    lemma, _ = _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(SH, "STATE_PATH", tmp_path / "self_heal.json")
    monkeypatch.setattr(AU, "authored_count", lambda: 12)
    monkeypatch.setattr(AU, "author_checks", lambda **k: (_ for _ in ()).throw(AssertionError("fallback should not run")))
    monkeypatch.setattr(TG, "author_targets", lambda **k: [
        {"name": "authored_mut_swap_abcd", "accepted": True, "source": "target_generator", "mut_kind": "swap_related_sequence"},
    ])
    out = SH.maybe_supply_oracle_targets("c9", findings=[{"kind": "empty_perturb_pool"}])
    assert out["invited"] is True
    assert out["reason"] == "generated"
    assert out["authored"][0]["name"].startswith(TG.PREFIX)
    assert out["cap"] == 150


def test_maybe_supply_still_skips_at_the_150_cap(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(AU, "authored_count", lambda: 150)
    monkeypatch.setattr(TG, "author_targets", lambda **k: (_ for _ in ()).throw(AssertionError("no")))
    monkeypatch.setattr(AU, "author_checks", lambda **k: (_ for _ in ()).throw(AssertionError("no")))
    out = SH.maybe_supply_oracle_targets("c9", findings=[{"kind": "empty_perturb_pool"}])
    assert out["invited"] is False and out["reason"] == "at_authored_cap"


def test_control_arm_self_mod_ok_is_false(monkeypatch):
    monkeypatch.setattr(arm, "self_mod_enabled", lambda: False)
    assert TG.self_mod_ok() is False


def test_no_oeis_code_execution_in_generator():
    src = Path(TG.__file__).read_text(encoding="utf-8")
    # The module must not exec/eval fetched text or call a fetcher.
    assert "exec(" not in src
    assert "_fetch_b" not in src
    assert "fetch=True" not in src
    # Mentions of OEIS are documentation only, or explicit refusals.
    assert "Never executes" in src or "never executes" in src.lower() or "Never executes fetched" in Path(TG.__file__).read_text()


def test_live_registry_can_verify_one_mutation(tmp_path, monkeypatch):
    """End-to-end on the real held registry, writing only to a temp lemma.

    Guards the supply path: at least one mutation of a held claim must pass
    the triviality filter, hold on a local window, and pass verify_candidate.
    Skips if the registry is empty (not the case in this repo).
    """
    lemma, log = _isolate(tmp_path, monkeypatch)
    repo_lemma = Path(__file__).resolve().parents[1] / "society" / "benchmarks" / "artifacts" / "lemma_impl.py"
    before = repo_lemma.read_text(encoding="utf-8") if repo_lemma.exists() else ""
    if repo_lemma.exists():
        lemma.write_text(before, encoding="utf-8")
    held = TG.held_claims()
    if not held:
        pytest.skip("no held frontier claims in this checkout")
    rows = TG.author_targets(
        max_new=1, cycle_id="test_live", write=True, claims=held,
    )
    assert rows, "expected at least one mutation of a held claim to verify"
    assert rows[0]["accepted"] is True
    assert rows[0]["name"].startswith(TG.PREFIX)
    assert rows[0]["mut_kind"] in TG.MUTATION_KINDS
    assert rows[0]["name"] in lemma.read_text(encoding="utf-8")
    after = repo_lemma.read_text(encoding="utf-8") if repo_lemma.exists() else ""
    assert after == before, "must not write the production lemma"
    reached = TG.oracle_reachable_generated(src=lemma.read_text(encoding="utf-8"))
    assert any(t["id"] == rows[0]["name"] and t["can_progress"] for t in reached)
