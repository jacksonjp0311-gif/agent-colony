"""Same seed, same decision. A disagreeing pair is a break."""
from colony.tools.seeded import decide, record, pairs, seed_of

def test_same_inputs_agree(tmp_path, monkeypatch):
    import colony.tools.seeded as S
    monkeypatch.setattr(S, "STORE", tmp_path / "seeded.jsonl")
    a = record(10.0, 12.0, decide(10.0, 12.0), "t")
    b = record(10.0, 12.0, decide(10.0, 12.0), "t")
    assert a["seed"] == b["seed"] == seed_of(10.0, 12.0)
    got = pairs()
    assert got and got[-1]["agree"] is True

def test_equal_refuses():
    assert decide(10.0, 10.0) is False
    assert decide(10.0, 9.0) is False
