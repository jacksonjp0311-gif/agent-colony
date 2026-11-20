"""Item 115: externally authored Hive priors and live fetches behind COLONY_EXTERNAL_PRIORS."""
from __future__ import annotations

import urllib.request

import pytest

from colony import external_priors as XP
from hive import host


class _M:
    def __init__(self, score):
        self.score = score


def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network fetch while switch is off")
    monkeypatch.setattr(urllib.request, "urlopen", boom)


@pytest.mark.parametrize("arm,switch", [("control", None), ("control", "live"), ("treatment", "off")])
def test_off_means_no_bias_and_no_fetch(monkeypatch, arm, switch):
    monkeypatch.setenv("COLONY_ARM", arm)
    if switch is None:
        monkeypatch.delenv(XP.SWITCH, raising=False)
    else:
        monkeypatch.setenv(XP.SWITCH, switch)
    _no_network(monkeypatch)
    assert XP.enabled() is False
    assert XP.failure_penalty("park_cycles") == 0
    assert XP.ucb_bonus("park_cycles") == 0
    assert XP.bias_delta(type("P", (), {"fingerprint": "park_cycles", "match": _M(500)})()) == 0
    from colony.tools.reciprocal_exchange import fetch_remote, merge_remote
    from colony.tools.locus_link import ask_locus
    assert fetch_remote("colony") == []
    assert merge_remote("colony") == 0
    assert ask_locus()["available"] is False
    XP.after_propose(None, None)
    XP.cycle_habit()
    assert XP.attribution()["external_priors"] is False
    assert XP.attribution()["colony_chosen"] is False


def test_treatment_live_is_default(monkeypatch):
    monkeypatch.setenv("COLONY_ARM", "treatment")
    monkeypatch.delenv(XP.SWITCH, raising=False)
    assert XP.enabled() is True
    assert XP.attribution()["external_priors"] is True


def test_hive_unbound_has_no_bias(monkeypatch):
    import hive.swarm as s
    monkeypatch.setattr(host, "_priors", None)
    p = type("P", (), {"fingerprint": "park_cycles", "match": _M(500)})()
    assert s._apply_evolutionary_bias(p) is p
    assert s._failure_penalty("park_cycles") == 0 and s._ucb_bonus("park_cycles") == 0


def test_adapter_binds_provider(monkeypatch):
    from colony import hive_adapter
    monkeypatch.setattr(host, "_priors", None)
    hive_adapter.bind()
    assert host._priors is XP
    # Rebinding heal/checker alone never drops the provider.
    host.bind(heal=host._heal, checker=host._checker)
    assert host._priors is XP


def test_bound_bias_matches_provider(monkeypatch):
    import hive.swarm as s
    from hive.bitwork import Match
    from dataclasses import dataclass
    monkeypatch.setenv("COLONY_ARM", "treatment")
    monkeypatch.delenv(XP.SWITCH, raising=False)
    _no_network(monkeypatch)  # fetch is fail-open: an error means "no remote rows"
    monkeypatch.setattr(host, "_priors", XP)

    @dataclass
    class P:
        fingerprint: str
        match: Match
    m = Match(category="t", action_key="park_cycles", score=500, margin=0, overlap=0, hamming=0,
              prototype_key="", polarity="", lower_permille=0, accuracy_permille=0, bucket_n=0,
              accepted=False, abstained=True, reason="")
    out = s._apply_evolutionary_bias(P("park_cycles", m))
    assert out.match.score == 500 + XP.bias_delta(P("park_cycles", m))


def test_scoreboard_marks_external_attribution(tmp_path, monkeypatch):
    import json
    from colony import twin
    board = tmp_path / "board.json"
    board.write_text(json.dumps({"history": [{"ts": "old"}]}))
    t = {k: 0 for k in twin.NUMERIC_FIELDS}
    monkeypatch.delenv(XP.SWITCH, raising=False)
    out = twin.update_scoreboard(path=board, treatment=t, control=dict(t), append=True,
                                 control_root_path=tmp_path / "nope")
    assert out["attribution"]["treatment_external_priors"] is True
    assert out["attribution"]["control_external_priors"] is False
    assert out["attribution"]["colony_chosen"] is False
    assert out["history"][0] == {"ts": "old"}
    assert out["history"][-1]["external_priors"] == {"treatment": True, "control": False, "colony_chosen": False}
    monkeypatch.setenv(XP.SWITCH, "off")
    out = twin.update_scoreboard(path=board, treatment=t, control=dict(t), append=True,
                                 control_root_path=tmp_path / "nope")
    assert out["history"][-1]["external_priors"]["treatment"] is False
