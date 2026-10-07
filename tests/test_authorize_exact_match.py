"""Authorize matches proposals by exact id — never by title prefix (X_50 must not touch X_51)."""
from __future__ import annotations

from types import SimpleNamespace

from colony.authorize import Authorizer


class _Witness:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def record(self, **kw) -> None:
        self.rows.append(kw)


def _authorizer(tmp_path, props, imps):
    a = object.__new__(Authorizer)
    a.root = tmp_path  # no scoreboard file under tmp → scoreboard step is a no-op
    a.state = SimpleNamespace(data={"improvement_proposals": props, "improvements": imps})
    a.witness = _Witness()
    return a


def _run(a, pid):
    return a._update_proposals(
        cycle_id="authorize_test",
        authorizer="James Jackson",
        delegated_via="test",
        proposal_ids=[(pid, "accepted", "explicit test authorize")],
        accepted_finding_titles=[],
    )


def test_authorize_x50_does_not_touch_x51_same_title(tmp_path):
    t = "Chain `authored_bell_triangle_recurrence__binomial_inversion_small_w1`"
    props = [
        {"id": "imp_abc_50", "title": t, "status": "candidate_measured"},
        {"id": "imp_abc_51", "title": t, "status": "candidate_measured"},
    ]
    imps = [
        {"title": t, "outcome": "attempted", "proposal_id": "imp_abc_50"},
        {"title": t, "outcome": "attempted", "proposal_id": "imp_abc_51"},
    ]
    a = _authorizer(tmp_path, props, imps)
    ups = _run(a, "imp_abc_50")
    assert [u["proposal_id"] for u in ups] == ["imp_abc_50"]
    assert props[0]["status"] == "accepted"
    assert props[1]["status"] == "candidate_measured"
    assert imps[0]["outcome"] == "accepted"
    assert imps[1]["outcome"] == "attempted"
    assert "authorized_at" not in imps[1]


def test_authorize_x50_does_not_touch_cycle_suffixed_x51(tmp_path):
    t = "Chain `authored_oeis_a000108__catalan_bounded` citing Odds"
    props = [
        {"id": "imp_def_50", "title": t, "status": "candidate_measured"},
        {"id": "imp_def_51", "title": t + " (cycle 179)", "status": "candidate_measured"},
    ]
    imps = [
        {"title": t, "outcome": "attempted", "proposal_id": "imp_def_50"},
        {"title": t + " (cycle 179)", "outcome": "attempted", "proposal_id": "imp_def_51"},
        # an unrelated record whose title is a prefix of the accepted one
        {"title": "Chain `authored_oeis_a000108", "outcome": "attempted"},
    ]
    a = _authorizer(tmp_path, props, imps)
    _run(a, "imp_def_50")
    assert imps[0]["outcome"] == "accepted"
    assert imps[1]["outcome"] == "attempted"
    assert imps[2]["outcome"] == "attempted"
    assert props[1]["status"] == "candidate_measured"


def test_exact_title_fallback_only_for_unambiguous_legacy_record(tmp_path):
    t = "Raise system reuse"
    props = [{"id": "imp_ghi_7", "title": t, "status": "candidate_measured"}]
    imps = [{"title": t, "outcome": "attempted"}]  # legacy: no proposal_id
    a = _authorizer(tmp_path, props, imps)
    _run(a, "imp_ghi_7")
    assert imps[0]["outcome"] == "accepted"

    props2 = [{"id": "imp_ghi_8", "title": t, "status": "candidate_measured"}]
    imps2 = [{"title": t, "outcome": "attempted"}, {"title": t, "outcome": "attempted"}]
    a2 = _authorizer(tmp_path, props2, imps2)
    _run(a2, "imp_ghi_8")
    # ambiguous legacy title → fail closed, nothing marked
    assert [i["outcome"] for i in imps2] == ["attempted", "attempted"]


def test_unknown_proposal_id_marks_nothing(tmp_path):
    t = "Chain `x_lemma`"
    props = [{"id": "imp_jkl_50", "title": t, "status": "candidate_measured"}]
    imps = [{"title": t, "outcome": "attempted", "proposal_id": "imp_jkl_50"}]
    a = _authorizer(tmp_path, props, imps)
    assert _run(a, "imp_jkl_5") == []
    assert props[0]["status"] == "candidate_measured"
    assert imps[0]["outcome"] == "attempted"
