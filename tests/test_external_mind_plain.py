"""external_mind is plain code (no b64/exec) and desk keep/revert bookkeeping runs again."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EM = ROOT / "colony" / "external_mind.py"


def test_external_mind_has_no_decode_or_exec():
    src = EM.read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = set()
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
        elif isinstance(node, ast.Call):
            f = node.func
            called.add(f.id if isinstance(f, ast.Name) else getattr(f, "attr", ""))
    assert not imported & {"base64", "binascii", "zlib", "gzip", "marshal", "subprocess",
                           "socket", "urllib", "requests", "http", "importlib", "types"}
    assert not called & {"exec", "eval", "compile", "__import__", "b64decode", "system", "popen"}
    assert ".b64" not in src.replace("``society/briefs/external_mind_py_*.b64``", "")


def test_desk_import_succeeds_and_propose_is_absent():
    from colony.external_mind import record_desk_outcome, lineage_lesson_ids  # noqa: F401
    import colony.external_mind as em

    assert not hasattr(em, "propose")  # growth.py witnesses this as a skip; not faked


def _lessons():
    return [
        {"id": "les_auth_X_old", "type": "authored_check", "mutation": "authored_x_w1", "cycle_id": "c0"},
        {"id": "les_auth_X", "type": "authored_check", "mutation": "authored_x_w1", "cycle_id": "c1"},
        {"id": "les_guide_X", "type": "human_guide", "cycle_id": "",
         "catalog_hint": {"prefer_mutations": ["authored_x_w1"]}},
        {"id": "les_hint_X", "type": "catalog_exhausted", "cycle_id": "c2",
         "catalog_hint": {"add_mutation": "authored_x_w1"}},
        {"id": "les_other", "type": "authored_check", "mutation": "authored_x_w10", "cycle_id": "c1"},
        {"id": "les_guide_fuzzy", "type": "human_guide", "catalog_hint": {"prefer": ["authored_x"]}},
        {"id": "les_same_cycle", "type": "authored_check", "mutation": "authored_y", "cycle_id": "now"},
    ]


def test_lineage_cites_only_exact_real_prior_lessons():
    from colony.external_mind import lineage_lesson_ids

    ids = lineage_lesson_ids("authored_x_w1", lessons=_lessons(), exclude_cycle="now")
    # newest authoring record first; exact-name guide and queue hint; never the fuzzy/other ones
    assert ids == ["les_auth_X", "les_guide_X", "les_hint_X"]
    assert "les_other" not in ids and "les_guide_fuzzy" not in ids
    assert len(ids) <= 3
    # nothing real → nothing cited
    assert lineage_lesson_ids("never_seen", lessons=_lessons()) == []
    assert lineage_lesson_ids("", lessons=_lessons()) == []
    # a lesson from this very judgment's cycle is not "prior"
    assert lineage_lesson_ids("authored_y", lessons=_lessons(), exclude_cycle="now") == []


def test_lineage_newest_authoring_record():
    from colony.external_mind import lineage_lesson_ids

    rows = [
        {"id": "a_old", "type": "authored_check", "mutation": "m", "cycle_id": "1"},
        {"id": "a_new", "type": "authored_check", "mutation": "m", "cycle_id": "2"},
    ]
    assert lineage_lesson_ids("m", lessons=rows) == ["a_new"]


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    import colony.external_mind as EMmod
    import colony.exploration_budget as B
    import colony.lessons as L

    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")
    monkeypatch.setattr(EMmod, "DESK_OUTCOMES_JSONL", tmp_path / "desk_outcomes.jsonl")
    monkeypatch.setattr(B, "BUDGET_PATH", tmp_path / "exploration_budget.json")
    monkeypatch.setattr(B, "HISTORY", tmp_path / "conjecture_history.jsonl")
    return tmp_path


def _seed(path: Path, rows):
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_desk_keep_writes_lesson_outcome_and_budget_with_real_cites(sandbox):
    import colony.conjecture_desk as D
    from colony.lessons import load_lessons

    _seed(sandbox / "lessons.jsonl", [
        {"id": "les_auth_m", "type": "authored_check", "decision": "skip", "mutation": "binomial_hockey_deep",
         "cycle_id": "prev", "catalog_hint": {}, "tags": [], "evidence": []},
    ])
    w = D._record_desk_bookkeeping(
        decision="keep", chosen="binomial_hockey_deep", kind="hard_enable", before_score=0.9,
        after_score=0.92, note="Kept `binomial_hockey_deep`", cycle_id="20261008T000000Z_abcdef",
        proposals=[{"arxiv_id": "1706.03762"}],
    )
    assert w["lesson_cites"] == ["les_auth_m"]
    assert w["outcome"]["lesson_cites"] == ["les_auth_m"]
    assert w["outcome"]["paper_cites"] == ["arxiv:1706.03762"]
    assert w["budget"] is not None
    rows = load_lessons(limit=10)
    keep = [e for e in rows if e.get("decision") == "keep"]
    assert len(keep) == 1 and keep[0]["source"] == "conjecture_desk"
    assert "lesson:les_auth_m" in keep[0]["evidence"]
    assert keep[0]["skill_bias"]["improver.improve"] > 0
    assert (sandbox / "desk_outcomes.jsonl").exists()


def test_desk_keep_without_lineage_cites_nothing(sandbox):
    import colony.conjecture_desk as D

    w = D._record_desk_bookkeeping(
        decision="keep", chosen="fresh_mutation", kind="hard_enable", before_score=0.9,
        after_score=0.92, note="Kept", cycle_id="c", proposals=[],
    )
    assert w["lesson_cites"] == []
    assert w["lesson"]["evidence"] == ["society/benchmarks/lemma_microbench.py", "artifacts:lemma_impl"]
    assert not any(str(t).startswith("lesson:") for t in w["lesson"]["tags"])


def test_desk_revert_writes_negative_lesson_and_budget_shift(sandbox):
    import colony.conjecture_desk as D

    w = D._record_desk_bookkeeping(
        decision="revert", chosen="easy_pad_square_again", kind="easy_pad", before_score=0.9,
        after_score=0.9, note="Reverted", cycle_id="c", proposals=[],
    )
    assert w["lesson"]["decision"] == "revert"
    assert w["lesson"]["skill_bias"]["geometer.gather"] < 0
    assert w["budget"] is not None


def test_bookkeeping_steps_are_independent(sandbox, monkeypatch):
    import colony.conjecture_desk as D
    import colony.external_mind as EMmod

    def boom(**_):
        raise RuntimeError("commons down")

    monkeypatch.setattr(EMmod, "record_desk_outcome", boom)
    w = D._record_desk_bookkeeping(
        decision="revert", chosen="x", kind="easy_pad", before_score=1.0, after_score=1.0,
        note="r", cycle_id="c", proposals=[],
    )
    assert w["outcome"] is None
    assert w["lesson"] is not None and w["budget"] is not None
