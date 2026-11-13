"""Live Hive findings must produce a real margin and the expected op.

The committed society/systems/swarm_learn.json from the first clean
twin run (43359885978) logged 12 stall failures and 3 shadow picks.
Every live decision had margin 0 (empty min_margin=0 bucket) because
the query was a raw dump of evidence, including unique cycle ids,
that barely overlapped the seed prose. Replay margins on the same
router were 75–531.

This test uses the exact logged no_progress_perturb finding (inlined
so Hive's standalone suite does not need the colony tree). After the
structured-token encoding and the historical seeds derived from
those failures (tagged with their source PR), the same finding must
produce a nonzero margin and the PR #4 op add_skip_rule /
already_held_range. The Wilson 95% gate and the 700 permille
threshold are not changed here.
"""
from __future__ import annotations

import hive.library as FL
from hive.bitwork import MARGIN_BUCKETS, margin_bucket
from hive.swarm import _symptom_for

# Exact evidence from society/systems/swarm_learn.json, first abstain
# (cycle 20261113T033803Z_3a7999, shadow pick add_skip_rule /
# already_held_range, margin 0, score -3). The two later cycles
# logged the same finding.
LIVE_NO_PROGRESS = {
    "kind": "no_progress_perturb",
    "evidence": {
        "exit_reason": "no_candidates",
        "exit_cycle": "20261113T015301Z_759b6f",
        "session_targets": [],
        "timeout_count": 2,
    },
}

EXPECTED_OP = "add_skip_rule"
EXPECTED_TARGET = "already_held_range"


def test_live_logged_failure_has_nonzero_margin_and_expected_op(tmp_path, monkeypatch):
    monkeypatch.setattr(FL, "LIBRARY_LOG", tmp_path / "fix_library.jsonl")
    monkeypatch.setattr(FL, "LIBRARY_SNAPSHOT", tmp_path / "swarm_library.json")
    FL.ensure_seeded()
    router = FL.train_router()

    query = _symptom_for(LIVE_NO_PROGRESS)
    # Structured tokens present; unique cycle ids must not be.
    assert "failure_class:no_progress_perturb" in query
    assert "exit_reason:no_candidates" in query
    assert "20261113T015301Z_759b6f" not in query
    assert "session_targets []" not in query

    hit = router.classify(query)
    assert hit is not None
    assert hit.margin > 0
    assert EXPECTED_OP in hit.action_key
    assert EXPECTED_TARGET in hit.action_key

    scored = router.score_action(query, hit.action_key)
    assert scored is not None
    assert scored.margin > 0
    assert EXPECTED_OP in scored.action_key
    assert EXPECTED_TARGET in scored.action_key
    # Live margin should land in the same bucket replay fills (64+),
    # not the empty min_margin=0 bucket that blocked the first run.
    assert margin_bucket(scored.margin) == MARGIN_BUCKETS[-1]
    assert margin_bucket(scored.margin) >= 64


def test_live_dead_end_and_term_cap_also_get_nonzero_margins(tmp_path, monkeypatch):
    monkeypatch.setattr(FL, "LIBRARY_LOG", tmp_path / "fix_library.jsonl")
    monkeypatch.setattr(FL, "LIBRARY_SNAPSHOT", tmp_path / "swarm_library.json")
    FL.ensure_seeded()
    router = FL.train_router()

    dead = {
        "kind": "dead_end_streak",
        "evidence": {
            "cycles": [
                "20261113T033803Z_3a7999",
                "20261113T034047Z_cdd725",
                "20261113T034312Z_c42659",
            ],
            "window": 3,
        },
    }
    q = _symptom_for(dead)
    assert "failure_class:dead_end_streak" in q
    assert "20261113T033803Z_3a7999" not in q
    hit = router.classify(q)
    scored = router.score_action(q, hit.action_key)
    assert scored.margin > 0
    assert "park_cycles" in scored.action_key

    cap = {
        "kind": "depth_at_physical_cap",
        "evidence": {
            "recent": [
                {
                    "anum": "A165064",
                    "cap_reason": "term_cap",
                    "cap_value": 1200,
                    "verified_depth": 1199,
                    "cycle_id": "20261113T010318Z_e7b0b9",
                    "id": "oc_A165064_0",
                }
            ]
        },
    }
    q = _symptom_for(cap)
    assert "failure_class:depth_at_physical_cap" in q
    assert "cap_reason:term_cap" in q
    assert "20261113T010318Z_e7b0b9" not in q
    hit = router.classify(q)
    scored = router.score_action(q, hit.action_key)
    assert scored.margin > 0
    assert "fast_term_cap" in scored.action_key
    assert margin_bucket(scored.margin) >= 64


def test_historical_seeds_are_tagged_with_source_prs():
    rows = [r for r in FL.seed_patterns() if str(r.get("id") or "").startswith("seed:pr") and "hist-" in str(r.get("id") or "")]
    assert len(rows) == 6
    sources = {r["source"] for r in rows}
    assert sources <= {"pr4", "pr6", "pr7"}
    for r in rows:
        ev = r.get("evidence") or {}
        assert ev.get("pr") in {4, 6, 7}
        assert ev.get("derived_from") == "society/systems/swarm_learn.json"
        assert r["outcome"] == "positive"
