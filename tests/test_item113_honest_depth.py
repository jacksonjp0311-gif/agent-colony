"""Item 113: beyond-published depth needs an independent definition (metric only)."""
from __future__ import annotations

import json
from pathlib import Path

from colony import twin


def _entry(eid, *, claim_expr="1/(1-x-x^2)", definition=None, terms=(1, 1, 2, 3, 5)):
    e = {"id": eid, "anum": eid.split("_")[1], "offset": 0, "terms": list(terms),
         "claim": {"form": "gf", "expr": claim_expr}}
    if definition is not None:
        e["definition"] = definition
    return e


def _society(root: Path, entries, extensions):
    (root / "society" / "frontier").mkdir(parents=True)
    (root / "society" / "systems").mkdir(parents=True)
    (root / "society" / "frontier" / "oeis_conjectures.json").write_text(json.dumps({"entries": entries}))
    (root / "society" / "systems" / "oeis_conjecture_state.json").write_text(
        json.dumps({"scoreboard": {"extensions": extensions}}))
    return root


def test_basis_rules():
    widened = {"entries": {}}
    assert twin.depth_basis(None) == twin.BASIS_PUBLISHED_ONLY
    # g.f. claim with no definition: extended against itself -> range only.
    assert twin.depth_basis(_entry("oc_A1_0"), widened) == twin.BASIS_PUBLISHED_ONLY
    # A menu definition equal to the claim's own expression is not independent.
    same = _entry("oc_A2_0", definition={"kind": "gf", "expr": "1/(1-x-x^2)"})
    assert twin.depth_basis(same, widened) == twin.BASIS_PUBLISHED_ONLY
    other = _entry("oc_A3_0", definition={"kind": "rec", "expr": "a(n)=a(n-1)+a(n-2)"})
    assert twin.depth_basis(other, widened) == twin.BASIS_MENU
    e = _entry("oc_A4_0")
    sha = twin._terms_sha(e)
    for prov, want in (("name", twin.BASIS_NAME), ("formula", twin.BASIS_PUBLISHED_ONLY),
                       ("guessed", twin.BASIS_PUBLISHED_ONLY)):
        w = {"entries": {"oc_A4_0": {"terms_sha": sha, "definition": {"provenance": prov, "expr": "Sum(k)"}}}}
        assert twin.depth_basis(e, w) == want, prov
    # Stale table row (terms changed) does not count.
    w = {"entries": {"oc_A4_0": {"terms_sha": "stale", "definition": {"provenance": "name", "expr": "Sum(k)"}}}}
    assert twin.depth_basis(e, w) == twin.BASIS_PUBLISHED_ONLY


def test_collect_caps_range_only_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(twin, "_WIDENED_DEFS", tmp_path / "none.json")
    entries = [
        _entry("oc_A1_0"),
        _entry("oc_A2_0", definition={"kind": "rec", "expr": "a(n)=a(n-1)+a(n-2)"}),
    ]
    ext = {
        "oc_A1_0": {"anum": "A1", "bfile_hi": 100, "to": 19999, "check": "exact"},
        "oc_A2_0": {"anum": "A2", "bfile_hi": 50, "to": 3000, "check": "exact"},
    }
    m = twin.collect_arm_metrics(_society(tmp_path / "t", entries, ext))
    # Legacy fields unchanged (no history rewrite).
    assert m["verified_depth_sum"] == 19999 + 3000
    assert m["beyond_published_count"] == 2
    # Honest restatement.
    assert m["honest_verified_depth_sum"] == 100 + 3000
    assert m["honest_beyond_published_count"] == 1
    assert m["honest_beyond_depth_sum"] == 3000
    assert m["published_range_only_count"] == 1
    rows = {r["id"]: r for r in m["depths"]}
    assert rows["oc_A1_0"]["depth_basis"] == twin.BASIS_PUBLISHED_ONLY
    assert rows["oc_A1_0"]["credited_depth"] == 100
    assert rows["oc_A2_0"]["credited_depth"] == 3000


def test_history_rows_get_new_fields_old_rows_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(twin, "_WIDENED_DEFS", tmp_path / "none.json")
    board = tmp_path / "board.json"
    old = {"ts": "2026-11-01T00:00:00Z", "treatment": {"verified_depth_sum": 5}, "control": {}}
    board.write_text(json.dumps({"history": [old]}))
    t = {k: 0 for k in twin.NUMERIC_FIELDS}
    t["honest_verified_depth_sum"] = 7
    out = twin.update_scoreboard(path=board, treatment=t, control=dict(t), append=True,
                                 control_root_path=tmp_path / "nope")
    assert out["history"][0] == old
    assert out["history"][-1]["treatment"]["honest_verified_depth_sum"] == 7
    for f in ("honest_verified_depth_sum", "honest_beyond_published_count",
              "honest_beyond_depth_sum", "published_range_only_count"):
        assert f in twin.NUMERIC_FIELDS


def test_restatement_appended_once(tmp_path, monkeypatch):
    board = tmp_path / "board.json"
    board.write_text(json.dumps({"history": []}))
    t = {k: 1 for k in twin.NUMERIC_FIELDS}
    out = twin.update_scoreboard(path=board, treatment=t, control=dict(t), append=True,
                                 control_root_path=tmp_path / "nope")
    assert [r["item"] for r in out["restatements"]] == [113]
    first = out["restatements"][0]
    t2 = dict(t, honest_verified_depth_sum=99)
    out2 = twin.update_scoreboard(path=board, treatment=t2, control=dict(t), append=True,
                                  control_root_path=tmp_path / "nope")
    assert out2["restatements"] == [first]
