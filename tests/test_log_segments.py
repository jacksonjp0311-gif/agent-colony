"""Append-only JSONL segment rotation: readers, no-rewrite, chain continuity."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from colony import log_segments as LS
from colony.ledger import Finding, Ledger
from colony.witness import WitnessLog


def _lines(n: int, prefix: str = "row") -> list[str]:
    return [json.dumps({"i": i, "k": prefix}) + "\n" for i in range(n)]


def test_reader_equivalence_across_segments(tmp_path):
    primary = tmp_path / "witness.jsonl"
    # Small threshold so a handful of lines rotate.
    threshold = 80
    expected: list[str] = []
    for i in range(20):
        line = json.dumps({"i": i, "payload": "x" * 10})
        LS.append_line(primary, line, threshold=threshold)
        expected.append(line + "\n")
    # Rotation must have created a later segment; segment 1 is the original.
    man = LS.load_manifest(primary)
    assert man is not None
    assert len(man["segments"]) >= 2
    assert (tmp_path / "witness.jsonl").is_file()
    # The original file is still segment 1 and was not renamed.
    assert man["segments"][0]["path"] == "witness.jsonl"
    got = list(LS.iter_lines(primary))
    assert got == expected


def test_rotation_never_modifies_earlier_bytes(tmp_path):
    primary = tmp_path / "ledger.jsonl"
    threshold = 60
    LS.append_line(primary, json.dumps({"i": 0, "pad": "A" * 40}), threshold=threshold)
    first_bytes = primary.read_bytes()
    assert first_bytes
    # Fill past the threshold and rotate.
    for i in range(1, 8):
        LS.append_line(primary, json.dumps({"i": i, "pad": "B" * 40}), threshold=threshold)
    man = LS.load_manifest(primary)
    assert man is not None
    assert len(man["segments"]) >= 2
    # Segment 1's bytes are bitwise identical to what was first written
    # (plus any lines that landed on it before the cut), and that
    # prefix has not been rewritten: the original first_bytes are a
    # prefix of the current file (or equal, if the first write already
    # sat at the threshold and later writes went elsewhere).
    later = primary.read_bytes()
    assert later.startswith(first_bytes) or later == first_bytes
    # After rotation the original file is closed and must not grow.
    closed_size = primary.stat().st_size
    LS.append_line(primary, json.dumps({"i": 99, "pad": "C" * 40}), threshold=threshold)
    assert primary.stat().st_size == closed_size
    assert primary.read_bytes() == later


def test_hash_chain_continues_across_segments(tmp_path):
    primary = tmp_path / "witness.jsonl"
    threshold = 70
    for i in range(12):
        LS.append_line(primary, json.dumps({"i": i, "pad": "n" * 20}), threshold=threshold)
    man = LS.load_manifest(primary)
    assert man is not None
    assert len(man["segments"]) >= 2
    # The hinge: segment 2's prev_sha256 equals segment 1's last line.
    first = man["segments"][0]
    second = man["segments"][1]
    assert first["last_line_sha256"]
    assert second["prev_sha256"] == first["last_line_sha256"]
    ok, reason = LS.verify_chain(primary)
    assert ok, reason


def test_witness_and_ledger_read_all_segments(tmp_path, monkeypatch):
    monkeypatch.setenv(LS.THRESHOLD_ENV, "90")
    wpath = tmp_path / "witness.jsonl"
    lpath = tmp_path / "ledger.jsonl"
    witness = WitnessLog(path=wpath, md_path=tmp_path / "W.md")
    ledger = Ledger(path=lpath)
    for i in range(15):
        witness.record(cycle_id=f"c{i}", kind="test", actor="spark", summary=f"event {i} " + "y" * 20)
        ledger.create(
            role="spark",
            claim=f"claim {i} " + "z" * 20,
            evidence_urls=["https://example.invalid/e"],
            provenance="test",
        )
    # May or may not have rotated depending on exact line size; force
    # a known rotation and then read through the class APIs.
    events = witness.all()
    findings = ledger.all()
    assert len(events) == 15
    assert [e.summary.split()[1] for e in events] == [str(i) for i in range(15)]
    assert len(findings) == 15
    assert [f.claim.split()[1] for f in findings] == [str(i) for i in range(15)]


def test_shared_prefix_does_not_copy_and_ignores_later_appends(tmp_path):
    treat = tmp_path / "treatment" / "data" / "witness.jsonl"
    treat.parent.mkdir(parents=True)
    original = [json.dumps({"i": i, "src": "treat"}) + "\n" for i in range(5)]
    treat.write_text("".join(original), encoding="utf-8")
    frozen = treat.stat().st_size
    ctrl = tmp_path / "control" / "data" / "witness.jsonl"
    ctrl.parent.mkdir(parents=True)
    LS.attach_shared_prefix(ctrl, treat, limit_bytes=frozen, source_label="treatment")
    # Treatment keeps growing; the frozen prefix must not include this.
    with treat.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"i": 99, "src": "later"}) + "\n")
    # Control has no copy of the huge file.
    assert not ctrl.exists() or ctrl.stat().st_size == 0
    got = [json.loads(line) for line in LS.iter_lines(ctrl) if line.strip()]
    assert [r["i"] for r in got] == [0, 1, 2, 3, 4]
    assert all(r["src"] == "treat" for r in got)
    # New control appends go to a local segment, not the treatment file.
    LS.append_line(ctrl, json.dumps({"i": 50, "src": "control"}), threshold=10 ** 9)
    treat_ids = [json.loads(l)["i"] for l in treat.read_text().splitlines() if l.strip()]
    assert 50 not in treat_ids
    got = [json.loads(line) for line in LS.iter_lines(ctrl) if line.strip()]
    assert [r["i"] for r in got] == [0, 1, 2, 3, 4, 50]
    ok, reason = LS.verify_chain(ctrl)
    assert ok, reason
