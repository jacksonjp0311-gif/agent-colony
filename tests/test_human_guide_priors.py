"""human_guide lessons must be readable as Spark/genome/exploration priors."""
from __future__ import annotations

from colony.lessons import (
    write_human_guide,
    skill_bias_from_lessons,
    catalog_hints_from_lessons,
    digest,
    apply_lesson_bias_to_genomes,
)
from colony.emergence.spark import lesson_priors_for_spark


def test_human_guide_survives_oracle_kill_flood(tmp_path, monkeypatch):
    import colony.lessons as L
    import json

    lessons_path = tmp_path / "lessons.jsonl"
    monkeypatch.setattr(L, "LESSONS_JSONL", lessons_path)
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")

    # Flood with kills that would bury a short lookback
    for i in range(50):
        L.write_lesson(
            decision="revert",
            check="oracle",
            what=f"kill {i}",
            source="test",
            lesson_type="oracle_kill",
            mutation=f"m{i}",
            skill_bias={"improver.improve": 0.01},
        )

    write_human_guide(
        what="SEEK INFORMATION: gather before propose",
        author="James Jackson",
        mutation="seek_test",
        skill_bias={"gather": 0.12},
        genome_prior={"gather": 0.08, "explore": 0.05},
        catalog_hint={"seek": ["ledger"], "add_mutation": "lemma_hard_test"},
        tags=["human_guide", "seek"],
    )

    bias = skill_bias_from_lessons(lookback=40)
    assert "gather" in bias and bias["gather"] > 0

    hints = catalog_hints_from_lessons(lookback=40)
    assert any(h.get("add_mutation") == "lemma_hard_test" or "ledger" in (h.get("seek") or []) for h in hints)

    d = digest(limit=8)
    assert "human_guide" in d or "SEEK INFORMATION" in d

    priors = lesson_priors_for_spark(limit=8)
    assert "SEEK INFORMATION" in priors or "seek_test" in priors

    # Genome prior fold
    gdir = tmp_path / "society" / "genomes"
    gdir.mkdir(parents=True)
    (gdir / "spark.json").write_text(
        json.dumps({"traits": {"gather": 0.5, "explore": 0.5, "build": 0.5, "reply": 0.5}}) + "\n"
    )
    monkeypatch.setattr(L, "ROOT", tmp_path)
    n = apply_lesson_bias_to_genomes(tmp_path)
    assert n >= 1
    g = json.loads((gdir / "spark.json").read_text())
    assert g["traits"]["gather"] > 0.5 or g["traits"]["explore"] > 0.5


def test_spark_emerge_records_lesson_priors(tmp_path, monkeypatch):
    """Spark.emerge witnesses lesson_priors (human_guide first)."""
    import json
    import colony.lessons as L
    import colony.emergence.spark as S
    from colony.emergence.spark import Spark
    from colony.emergence.growth import GrowthResult
    from colony.ledger import Ledger
    from colony.society_state import SocietyState
    from colony.witness import WitnessLog

    monkeypatch.setattr(L, "LESSONS_JSONL", tmp_path / "lessons.jsonl")
    monkeypatch.setattr(L, "LEDGER_SYSTEM", tmp_path / "lesson_ledger.json")
    write_human_guide(
        what="BECOME SOMETHING MORE: prefer novelty",
        author="James Jackson",
        mutation="become_test",
        tags=["human_guide", "become"],
    )

    class FakeGrowth:
        def __init__(self, *a, **k):
            pass

        def grow(self, *a, **k):
            return GrowthResult()

    monkeypatch.setattr(S, "GrowthLoop", FakeGrowth)
    # Skip post-grow spawn path
    monkeypatch.setattr(S, "AgentRegistry", lambda *a, **k: type("R", (), {"agents": lambda self: {}, "enter": lambda *a, **k: {}})())
    monkeypatch.setattr(
        S.EvolutionEngine,
        "SPAWN_MENU",
        [],
        raising=False,
    )

    state = SocietyState(
        path=tmp_path / "state.json",
        data={"roles": {"spark": {}}, "tribute_mandate": {"active_ask": "grow evolve learn"}},
    )
    wpath = tmp_path / "witness.jsonl"
    witness = WitnessLog(wpath)
    ledger = Ledger(tmp_path / "ledger.jsonl")
    spark = Spark(ledger, state, witness)
    try:
        spark.emerge("cyc_prior_test", tribute_topics=["math"], tribute_count=3)
    except Exception as exc:
        # Priors are recorded before growth/spawn; tolerate later stub gaps
        print("emerge post-prior exception:", type(exc).__name__, exc)

    rows = [json.loads(ln) for ln in wpath.read_text().splitlines() if ln.strip()]
    kinds = [r.get("kind") for r in rows]
    assert "lesson_priors" in kinds, kinds
    prior_rows = [r for r in rows if r.get("kind") == "lesson_priors"]
    blob = str((prior_rows[0].get("detail") or {}).get("priors") or "")
    assert "become" in blob.lower() or "BECOME" in blob or "human_guide" in blob
