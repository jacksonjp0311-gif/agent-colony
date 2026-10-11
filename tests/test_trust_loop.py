"""Trust loop (2026-10-11): Challenger, learning switch, lessons audit, rollback, provenance,
diff-scope and holdout-isolation regression tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

FALSE_IN_WINDOW = '''
import math
def _t_isprime(n):
    if n < 2:
        return False
    i = 2
    while i * i <= n:
        if n % i == 0:
            return False
        i += 1
    return True

def check_t_euler41() -> bool:
    return all(_t_isprime(n * n + n + 41) for n in range(0, 40))

def check_t_binom_sq() -> bool:
    return all(sum(math.comb(n, k) ** 2 for k in range(n + 1)) == math.comb(2 * n, n) for n in range(0, 25))

HARD_TIER_LEMMAS = [
    ("t_euler41", check_t_euler41, True),
    ("t_binom_sq", check_t_binom_sq, True),
]
'''


# --- isolation ---------------------------------------------------------------------------

def test_colony_never_references_holdout_or_evaluator():
    """AST check (docstrings/comments ignored): no colony code names the holdout pools or
    imports the evaluator. Only colony/trust/gate.py may name evaluation/MANIFEST.sha256."""
    import ast
    offenders = []
    for p in (ROOT / "colony").rglob("*.py"):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        docs = {id(n.body[0].value) for n in ast.walk(tree)
                if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))
                and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        for n in ast.walk(tree):
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in n.names] + [getattr(n, "module", "") or ""]
                if any("evaluator" in x or x.startswith("evaluation") for x in names):
                    offenders.append(f"{p.name}:import")
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
                v = n.value
                if "holdout_v1" in v or "labels.json" in v or "pools" == v:
                    offenders.append(f"{p.name}:{v[:40]}")
                if v == "evaluation" and p.name != "gate.py":
                    offenders.append(f"{p.name}:{v}")
    assert offenders == [], offenders


def test_manifest_detects_tamper(tmp_path):
    from colony.trust.gate import manifest_check
    ev = tmp_path / "evaluation"
    ev.mkdir()
    (ev / "evaluator.py").write_text("X = 1\n")
    import hashlib
    h = hashlib.sha256(b"X = 1\n").hexdigest()
    (ev / "MANIFEST.sha256").write_text(f"{h}  evaluator.py\n")
    assert manifest_check(tmp_path)["ok"] is True
    (ev / "evaluator.py").write_text("X = 2  # tampered\n")
    r = manifest_check(tmp_path)
    assert r["ok"] is False and r["mismatch"] == ["evaluator.py"]


def test_repo_manifest_intact():
    from colony.trust.gate import manifest_check
    assert manifest_check()["ok"] is True


# --- Challenger ----------------------------------------------------------------------------

def test_challenger_blocks_window_only_false_claim_and_passes_sound_one():
    from colony.challenger import challenge_entry
    bad = challenge_entry(FALSE_IN_WINDOW, "t_euler41", cycle_id="t", before_src="")
    good = challenge_entry(FALSE_IN_WINDOW, "t_binom_sq", cycle_id="t", before_src="")
    assert bad.blocked is True and bad.counterexample
    assert good.blocked is False


def test_challenger_switch(monkeypatch):
    from colony.trust.flags import challenger_enabled, ablation_active
    monkeypatch.setenv("COLONY_CHALLENGER", "0")
    assert challenger_enabled() is False and "COLONY_CHALLENGER=0" in ablation_active()


# --- learning switch -----------------------------------------------------------------------

def test_learning_off_drops_outcome_memory_but_keeps_human_guides(monkeypatch):
    from colony.lessons import mutation_cooldown, guide_avoid_themes
    from colony.conjecture_mutations import recent_revert_counts
    on = mutation_cooldown()
    monkeypatch.setenv("COLONY_LEARNING", "0")
    off = mutation_cooldown()
    assert off.blocked == {} and off.penalties == {}
    assert recent_revert_counts() == {}
    assert off.avoided == {t for t in guide_avoid_themes() if len(t) >= 6}
    assert len(on.blocked) >= len(off.blocked)


# --- lessons: provenance, scope, counterexamples, invalidation, retirement ------------------

@pytest.fixture()
def tmp_lessons(monkeypatch, tmp_path):
    import colony.lessons as L
    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "persist_system", lambda **k: None)
    return L


def test_lesson_carries_provenance_scope_counterexample_invalidation(tmp_lessons):
    L = tmp_lessons
    e = L.write_lesson(decision="revert", check="lemma_microbench", what="killed", source="conjecture_desk",
                       cycle_id="cyc_1", mutation="pool_x", counterexamples=[{"n": 40}],
                       evidence=["oracle:row"])
    assert e["provenance"]["source"] == "conjecture_desk" and e["provenance"]["cycle_id"] == "cyc_1"
    assert e["scope"] == "mutation:pool_x" and e["counterexamples"] == [{"n": 40}]
    assert "contradicts" in e["invalidated_if"]


def test_contradicted_lesson_retired_with_audit_trail(tmp_lessons):
    L = tmp_lessons
    e = L.write_lesson(decision="keep", check="lemma_microbench", what="pool_x is sound", source="conjecture_desk",
                       cycle_id="cyc_2", mutation="pool_x")
    assert any(x["id"] == e["id"] for x in L.load_lessons())
    with pytest.raises(ValueError):
        L.retire_lesson(e["id"], reason="no evidence", contradicted_by=[], source="trust_eval")
    r = L.retire_lesson(e["id"], reason="holdout counterexample n=40", contradicted_by=["evaluator:n=40"],
                        source="trust_eval", cycle_id="cyc_3")
    assert not any(x["id"] == e["id"] for x in L.load_lessons())
    raw = L.LESSONS_JSONL.read_text().splitlines()
    assert any(json.loads(x)["id"] == e["id"] for x in raw), "original row must stay on disk (append-only)"
    assert r["supersedes"] == [e["id"]]
    rev = L.write_lesson(decision="revert", check="lemma_microbench", what="pool_y wrong", source="d",
                         cycle_id="cyc_4", mutation="pool_y")
    rv = L.retire_lesson(rev["id"], reason="revised scope", contradicted_by=["x"], source="d",
                         revised={"scope": "family:prime_polynomial"})
    assert rv["type"] == "lesson_revised"


def test_agent_cannot_forge_or_retire_human_guide(tmp_lessons):
    L = tmp_lessons
    with pytest.raises(PermissionError):
        L.write_lesson(decision="guide", check="x", what="trust me", source="improver", lesson_type="human_guide",
                       author="improver")
    g = L.write_lesson(decision="guide", check="x", what="human guide", source="human", lesson_type="human_guide",
                       author="James Paul Jackson")
    with pytest.raises(PermissionError):
        L.retire_lesson(g["id"], reason="agent wants it gone", contradicted_by=["x"], source="improver")


# --- rollback / restart recovery / idempotency ----------------------------------------------

def test_recover_interrupted_restores_and_is_idempotent(monkeypatch, tmp_path):
    import colony.conjecture_desk as D
    monkeypatch.setattr(D, "JOURNAL", tmp_path / ".desk_journal.json")
    monkeypatch.setattr(D, "HISTORY", tmp_path / "hist.jsonl")
    target, backup = tmp_path / "impl.py", tmp_path / "impl_backup.py"
    backup.write_text("ORIGINAL\n")
    target.write_text("MUTATED_UNJUDGED\n")
    D._journal_open(target=target, backup=backup, mutation="pool_x", kind="hard_enable", cycle_id="c1")
    r = D.recover_interrupted(cycle_id="c2")
    assert r["recovered"] and r["restored_bytes"] and target.read_text() == "ORIGINAL\n"
    assert D.recover_interrupted(cycle_id="c3") is None  # idempotent: nothing left to do
    rows = [json.loads(x) for x in (tmp_path / "hist.jsonl").read_text().splitlines()]
    assert [x["decision"] for x in rows] == ["recovered_rollback"]


def test_recover_without_backup_keeps_journal_so_gate_fails(monkeypatch, tmp_path):
    import colony.conjecture_desk as D
    monkeypatch.setattr(D, "JOURNAL", tmp_path / ".desk_journal.json")
    monkeypatch.setattr(D, "HISTORY", tmp_path / "hist.jsonl")
    target = tmp_path / "impl.py"
    target.write_text("MUTATED\n")
    D._journal_open(target=target, backup=tmp_path / "missing.py", mutation="m", kind="hard_enable", cycle_id="c")
    r = D.recover_interrupted()
    assert r["recovered"] is False and D.JOURNAL.exists()


# --- diff scope + provenance (evaluation tampering / fabricated metrics) ---------------------

def test_diff_scope_allows_single_flip_and_kills_tamper():
    from colony.trust.diffscope import enable_diff_ok
    before = 'def run_hard_checks():\n    return real()\nHARD = [\n    ("x", check_x, False),\n]\n'
    ok_after = before.replace('check_x, False', 'check_x, True')
    assert enable_diff_ok(before, ok_after, "x")["ok"] is True
    tampered = ok_after.replace("return real()", "return {k: True for k in real()}")
    r = enable_diff_ok(before, tampered, "x")
    assert r["ok"] is False and r["reason"] == "out_of_scope_change"


def test_fabricated_keep_is_not_oracle_backed(tmp_path):
    from colony.trust.provenance import oracle_backed
    log = tmp_path / "oracle.jsonl"
    log.write_text(json.dumps({"mutation": "real_m", "cycle_id": "c1", "passed": True, "fitness_credit": True}) + "\n"
                   + json.dumps({"mutation": "killed_m", "cycle_id": "c1", "passed": False, "fitness_credit": False}) + "\n")
    assert oracle_backed("real_m", "c1", log=log)["ok"] is True
    assert oracle_backed("killed_m", "c1", log=log)["ok"] is False
    assert oracle_backed("fabricated_m", "c9", log=log)["ok"] is False
    assert oracle_backed("real_m", "c2", log=log)["ok"] is False  # right name, wrong cycle
