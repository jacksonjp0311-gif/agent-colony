"""Hold posture — selective authorize only; never accept-all."""
from __future__ import annotations

from colony.hold_posture import (
    DEFAULT_POSTURE,
    ORACLE_SCORE_FLOOR,
    build_selective_decisions,
    persist_hold_state,
    scan_new_authorize_themes,
)
from colony.standing_trust import STANDING_TRUST_P_MIN


class _F:
    def __init__(self, **kw):
        self.id = kw.get("id")
        self.status = kw.get("status", "candidate")
        self.tags = kw.get("tags", [])
        self.meta = kw.get("meta", {})
        self.notes = kw.get("notes", "")
        self.title = kw.get("title", "")


class _Led:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


def test_default_posture_is_hold():
    assert DEFAULT_POSTURE == "HOLD"
    assert ORACLE_SCORE_FLOOR == 0.70
    assert STANDING_TRUST_P_MIN == 0.70


def test_scan_skips_already_accepted_and_below_floor():
    led = _Led(
        [
            _F(
                id="fnd_old",
                status="accepted",
                tags=["hard_checked", "vandermonde"],
                meta={"theme_id": "vandermonde", "hard_ok": True},
                notes="lemma score=0.8771 hard_pass=25/25 | oracle=PASS kills=[]",
            ),
            _F(
                id="fnd_low",
                status="candidate",
                tags=["hard_checked", "catalan"],
                meta={"theme_id": "catalan", "hard_ok": True},
                notes="lemma score=0.55 hard_pass=10/25 | oracle=PASS kills=[]",
            ),
            _F(
                id="fnd_kill",
                status="candidate",
                tags=["hard_checked", "binomial_identities"],
                meta={"theme_id": "binomial_identities", "hard_ok": True},
                notes="lemma score=0.90 hard_pass=20/25 | oracle=KILL kills=['x']",
            ),
            _F(
                id="fnd_new",
                status="candidate",
                tags=["hard_checked", "fibonacci_identities"],
                meta={"theme_id": "fibonacci_identities", "hard_ok": True},
                notes="lemma score=0.81 hard_pass=22/25 | oracle=PASS kills=[]",
                title="Hard-checked claim: fibonacci_identities",
            ),
        ]
    )
    eligible = scan_new_authorize_themes(led)
    themes = {e["theme"] for e in eligible}
    assert "vandermonde" not in themes  # already accepted
    assert "catalan" not in themes  # below floor
    assert "binomial_identities" not in themes  # oracle kill
    assert "fibonacci_identities" in themes
    assert eligible[0]["score"] >= 0.70


def test_selective_decisions_never_accept_all():
    eligible = [
        {"finding_id": "fnd_a", "theme": "fibonacci_identities", "score": 0.81},
        {"finding_id": "fnd_b", "theme": "catalan", "score": 0.82},
        {"finding_id": "fnd_c", "theme": "binomial_identities", "score": 0.83},
        {"finding_id": "fnd_d", "theme": "extra", "score": 0.84},
        {"finding_id": "fnd_e", "theme": "extra2", "score": 0.85},
    ]
    dec = build_selective_decisions(eligible, cap=4)
    assert dec["never_accept_all"] is True
    assert dec["selected"] == 4
    assert len(dec["items"]) == 4
    assert all(i["decision"] == "accepted" for i in dec["items"])
    snap = persist_hold_state(
        posture="HOLD",
        cycle_id="test_hold",
        scan=eligible,
        authorize_action={"did_authorize": False, "reason": "unit_test"},
    )
    assert snap["posture"] == "HOLD"
    assert snap["policy"]["never_accept_all"] is True
    assert snap["policy"]["athanor_inform_only"] is True
