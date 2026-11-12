"""The fitness shard records the cycles just run, not only rows leaving the inline window."""
import json

from colony.society_state import SocietyState


def _rows(n):
    return [{"ts": f"2026-01-01T00:{i:02d}:00Z", "cycle_id": f"c{i}", "aggregate": i} for i in range(n)]


def test_fitness_shard_ends_on_the_latest_cycle(tmp_path, monkeypatch):
    monkeypatch.setattr("colony.society_state.SHARDS_DIR", tmp_path / "shards")
    monkeypatch.setattr("colony.society_state.STATE_SHARDS", True)
    path = tmp_path / "society_state.json"
    path.write_text(json.dumps({"fitness_history": _rows(40), "improvement_proposals": _rows(60)}), encoding="utf-8")
    state = SocietyState.load(path)
    state.save()
    fit = (tmp_path / "shards" / "fitness_history.jsonl").read_text(encoding="utf-8").splitlines()
    props = (tmp_path / "shards" / "improvement_proposals.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(fit[-1])["cycle_id"] == "c39"
    assert len(fit) == 40
    assert len(props) == 10
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["fitness_history"][-1]["cycle_id"] == "c39"
    assert len(saved["fitness_history"]) == 30
    state.data["fitness_history"].append({"ts": "2026-01-01T00:40:00Z", "cycle_id": "c40", "aggregate": 40})
    state.save()
    fit = (tmp_path / "shards" / "fitness_history.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(fit) == 41
    assert json.loads(fit[-1])["cycle_id"] == "c40"
    state.save()
    again = (tmp_path / "shards" / "fitness_history.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(again) == 41
