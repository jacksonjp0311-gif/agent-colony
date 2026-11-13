"""Society-state split: identical logical state, no rewrite of history."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from colony import state_segments as SS
from colony.society_state import SocietyState, load_data


def _entry(i: int, kind: str = "communications") -> dict:
    return {
        "ts": f"2026-01-01T00:00:{i:02d}Z",
        "cycle_id": f"c{i}",
        "from": "spark",
        "to": "all",
        "channel": "bus",
        "message": f"{kind} message {i} " + ("x" * 20),
    }


def _full_state(n_comm: int = 40, n_hist: int = 12, n_diag: int = 5) -> dict:
    return {
        "version": 1,
        "colony": "agent-colony",
        "cycle_count": n_comm,
        "communications": [_entry(i) for i in range(n_comm)],
        "history": [
            {"ts": f"2026-01-01T00:00:{i:02d}Z", "event": "cycle_complete", "cycle_id": f"c{i}"}
            for i in range(n_hist)
        ],
        "evolution_log": [
            {"ts": f"2026-01-01T00:00:{i:02d}Z", "cycle_id": f"c{i}", "event": "evolve"}
            for i in range(3)
        ],
        "artifacts": [
            {"ts": f"2026-01-01T00:00:{i:02d}Z", "name": f"a{i}", "kind": "report", "cycle_id": f"c{i}"}
            for i in range(3)
        ],
        "cycle_diagnostics": {
            f"c{i}": {"cycle_id": f"c{i}", "ok": True} for i in range(n_diag)
        },
        "agents": {"spark": {"status": "active", "note": "founder"}},
        "fitness_history": [
            {"ts": "2026-01-01T00:00:00Z", "cycle_id": "c0", "aggregate": 0.85}
        ],
        "bus": {"stats": {"posted": 4}},
    }


def _write_full(path: Path, data: dict, *, pad: int = 0) -> bytes:
    """Write a single-file state. Optional pad to exceed a size threshold."""
    payload = dict(data)
    if pad:
        payload["communications"] = list(payload.get("communications") or [])
        # Inflate one message so the file crosses the test threshold
        # without inventing extra logical items after the fact.
        if payload["communications"]:
            payload["communications"][-1] = {
                **payload["communications"][-1],
                "message": payload["communications"][-1]["message"] + ("P" * pad),
            }
        else:
            payload["communications"] = [_entry(0) | {"message": "P" * pad}]
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    return path.read_bytes()


def test_unmigrated_load_data_equals_json_load(tmp_path):
    path = tmp_path / "society_state.json"
    data = _full_state()
    _write_full(path, data)
    raw = json.loads(path.read_text(encoding="utf-8"))
    logical = load_data(path)
    ok, reason = SS.logical_keys_equal(raw, logical)
    assert ok, reason
    assert not SS.is_split(path)


def test_migrate_leaves_original_bytes_untouched_and_readers_agree(tmp_path):
    path = tmp_path / "society_state.json"
    data = _full_state(n_comm=25, n_hist=10, n_diag=4)
    original = _write_full(path, data, pad=200)
    original_sha = hashlib.sha256(original).hexdigest()
    raw = json.loads(original)

    # Load, append two communications, save with a low threshold so
    # the (already padded) file migrates.
    state = SocietyState.load(path)
    state.data["communications"].append(_entry(25))
    state.data["communications"].append(_entry(26))
    state.data["cycle_count"] = 27
    state.data["history"].append({"ts": "2026-01-01T00:01:00Z", "event": "cycle_complete", "cycle_id": "c25"})
    state.data["cycle_diagnostics"]["c25"] = {"cycle_id": "c25", "ok": True}
    state.save(segment_threshold=len(original) // 2)

    # Original file is bitwise identical: frozen as segment 1.
    assert path.is_file()
    assert path.read_bytes() == original
    assert hashlib.sha256(path.read_bytes()).hexdigest() == original_sha
    assert SS.is_split(path)
    man = SS.load_manifest(path)
    assert man is not None
    assert man["frozen"]["sha256"] == original_sha
    assert man["frozen"]["kind"] == "frozen_snapshot"
    assert man["frozen"]["status"] == "closed"
    assert SS.file_sha256(path) == original_sha

    # Logical state is the frozen snapshot plus the new items.
    expected = dict(raw)
    expected["communications"] = list(raw["communications"]) + [_entry(25), _entry(26)]
    expected["cycle_count"] = 27
    expected["history"] = list(raw["history"]) + [
        {"ts": "2026-01-01T00:01:00Z", "event": "cycle_complete", "cycle_id": "c25"}
    ]
    expected["cycle_diagnostics"] = dict(raw["cycle_diagnostics"])
    expected["cycle_diagnostics"]["c25"] = {"cycle_id": "c25", "ok": True}

    loaded = load_data(path)
    ok, reason = SS.logical_keys_equal(expected, loaded)
    assert ok, reason
    # SocietyState.load sees the same.
    again = SocietyState.load(path)
    ok, reason = SS.logical_keys_equal(expected, again.data)
    assert ok, reason

    # New items live in JSONL segments, not in the frozen file.
    comm_primary = SS.key_primary(path, "communications")
    new_lines = [json.loads(l) for l in __import__("colony.log_segments", fromlist=["iter_lines"]).iter_lines(comm_primary) if l.strip()]
    assert [e["cycle_id"] for e in new_lines] == ["c25", "c26"]

    # A second save does not rewrite the frozen file and does not
    # duplicate the already-stored appends.
    again.data["agents"]["spark"]["note"] = "still founder"
    again.save(segment_threshold=1)
    assert path.read_bytes() == original
    new_lines2 = [json.loads(l) for l in __import__("colony.log_segments", fromlist=["iter_lines"]).iter_lines(comm_primary) if l.strip()]
    assert [e["cycle_id"] for e in new_lines2] == ["c25", "c26"]
    loaded2 = load_data(path)
    assert loaded2["agents"]["spark"]["note"] == "still founder"
    assert [e["cycle_id"] for e in loaded2["communications"][-2:]] == ["c25", "c26"]
    assert len(loaded2["communications"]) == len(expected["communications"])


def test_small_file_is_not_split_by_default(tmp_path):
    path = tmp_path / "society_state.json"
    data = _full_state(n_comm=3)
    _write_full(path, data)
    state = SocietyState.load(path)
    state.data["cycle_count"] = 4
    state.save()
    assert not SS.is_split(path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["cycle_count"] == 4
    assert len(saved["communications"]) == 3


def test_control_shared_snapshot_does_not_copy_and_stays_equivalent(tmp_path):
    treat = tmp_path / "treatment" / "data" / "society_state.json"
    data = _full_state(n_comm=20, n_hist=8)
    original = _write_full(treat, data, pad=400)
    original_sha = hashlib.sha256(original).hexdigest()

    # Migrate treatment first (as a real first save would).
    st = SocietyState.load(treat)
    st.data["communications"].append(_entry(20))
    st.save(segment_threshold=len(original) // 2)
    assert treat.read_bytes() == original
    treat_logical = load_data(treat)

    ctrl = tmp_path / "control" / "data" / "society_state.json"
    man = SS.attach_shared_state(ctrl, treat)
    assert man["frozen"]["kind"] == "shared_snapshot"
    assert man["frozen"]["sha256"] == original_sha
    # Control has no copy of the large frozen file.
    assert (not ctrl.is_file()) or ctrl.stat().st_size == 0
    assert SS.live_path(ctrl, man).is_file()

    # At seed, control's logical append-only keys match treatment.
    control_logical = load_data(ctrl)
    for key in SS.APPEND_LIST_KEYS:
        assert control_logical[key] == treat_logical[key], key
    for key in SS.APPEND_DICT_KEYS:
        assert control_logical[key] == treat_logical[key], key
    # Mutable keys were snapshotted.
    assert control_logical["cycle_count"] == treat_logical["cycle_count"]
    assert control_logical["agents"] == treat_logical["agents"]

    # Treatment keeps growing; the shared snapshot and the shared
    # JSONL prefix must not pick up later treatment appends.
    treat_st = SocietyState.load(treat)
    treat_st.data["communications"].append(_entry(21))
    treat_st.data["cycle_count"] = 99
    treat_st.save(segment_threshold=1)
    # Frozen treatment file still original.
    assert treat.read_bytes() == original

    control_after = load_data(ctrl)
    assert [e["cycle_id"] for e in control_after["communications"]] == (
        [e["cycle_id"] for e in treat_logical["communications"]]
    )
    assert all(e["cycle_id"] != "c21" for e in control_after["communications"])
    # Control's mutable snapshot is unchanged by treatment's later save.
    assert control_after["cycle_count"] == treat_logical["cycle_count"]

    # New control appends go to a control-owned segment, not treatment.
    ctrl_st = SocietyState.load(ctrl)
    ctrl_st.data["communications"].append(_entry(50) | {"message": "control only"})
    ctrl_st.data["cycle_count"] = 50
    ctrl_st.save(segment_threshold=1)
    assert treat.read_bytes() == original
    treat_now = load_data(treat)
    assert all(e.get("message") != "control only" for e in treat_now["communications"])
    ctrl_now = load_data(ctrl)
    assert ctrl_now["communications"][-1]["message"] == "control only"
    assert ctrl_now["cycle_count"] == 50
    # Prefix up to seed is still identical to treatment-at-seed.
    seed_n = len(treat_logical["communications"])
    assert ctrl_now["communications"][:seed_n] == treat_logical["communications"]
    assert len(ctrl_now["communications"]) == seed_n + 1


def test_real_committed_state_load_equivalence():
    """If the 44 MiB committed file is present, raw json == load_data.

    This does not migrate it (the next evolve save will). It only
    checks that the reader sees the same logical state before a split.
    """
    root = Path(__file__).resolve().parent.parent
    path = root / "data" / "society_state.json"
    if not path.is_file() or path.stat().st_size < 1024 * 1024:
        pytest.skip("committed society_state.json is not present or is tiny")
    if SS.is_split(path):
        # After this PR lands and a run migrates, compare through the
        # reader only (the frozen file is no longer the whole state).
        logical = load_data(path)
        assert isinstance(logical.get("communications"), list)
        assert len(logical["communications"]) > 0
        return
    raw = json.loads(path.read_text(encoding="utf-8"))
    logical = load_data(path)
    ok, reason = SS.logical_keys_equal(raw, logical)
    assert ok, reason
    # communications is the key that grew 127 KB last run.
    assert len(logical["communications"]) == len(raw["communications"])


def test_control_committed_copy_also_equivalent():
    root = Path(__file__).resolve().parent.parent
    path = root / "control" / "data" / "society_state.json"
    if not path.is_file() or path.stat().st_size < 1024 * 1024:
        pytest.skip("committed control society_state.json is not present")
    if SS.is_split(path):
        logical = load_data(path)
        assert isinstance(logical.get("communications"), list)
        return
    raw = json.loads(path.read_text(encoding="utf-8"))
    logical = load_data(path)
    ok, reason = SS.logical_keys_equal(raw, logical)
    assert ok, reason
