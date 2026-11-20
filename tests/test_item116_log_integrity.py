"""Item 116: one writer per exchange file, crystallized.jsonl never rewritten, union merge."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from colony.tools import symbiotic_exchange as SX
from colony.tools import watch as W

ROOT = Path(__file__).resolve().parent.parent


def test_watch_downscale_keeps_store_append_only(tmp_path, monkeypatch):
    store = tmp_path / "crystallized.jsonl"
    compact = tmp_path / "crystallized_compact.jsonl"
    rows = [{"fingerprint": f"f{i}", "source": "colony"} for i in range(5)]
    store.write_text("".join(json.dumps(r) + "\n" for r in rows))
    before = store.read_bytes()
    monkeypatch.setattr(W, "STORE", store)
    monkeypatch.setattr(W, "COMPACT", compact)
    kept = W.downscale([dict(r, reactivated=True) for r in rows[:2]])
    assert kept == 2
    assert store.read_bytes() == before
    assert [json.loads(l)["fingerprint"] for l in compact.read_text().splitlines()] == ["f0", "f1"]


def test_exchange_write_path_override(tmp_path, monkeypatch):
    main = tmp_path / "data" / "commons" / "exchange.jsonl"
    monkeypatch.setattr(SX, "ROOT", tmp_path)
    monkeypatch.setattr(SX, "EXCHANGE", main)
    monkeypatch.setenv("COLONY_EXCHANGE_FILE", "data/commons/exchange_watch.jsonl")
    SX.append_receipt("colony", "dream", "fp1", "observed")
    assert not main.exists()
    assert (tmp_path / "data" / "commons" / "exchange_watch.jsonl").exists()
    monkeypatch.delenv("COLONY_EXCHANGE_FILE")
    assert SX.write_path() == main


def test_fold_is_append_only_and_idempotent(tmp_path):
    src = tmp_path / "exchange_watch.jsonl"
    dest = tmp_path / "exchange.jsonl"
    dest.write_text(json.dumps({"event_id": "a", "fingerprint": "x"}) + "\n")
    before = dest.read_text()
    src.write_text("".join(json.dumps(r) + "\n" for r in (
        {"event_id": "a", "fingerprint": "x"}, {"event_id": "b", "fingerprint": "y"},
        {"source": "one-mind", "fingerprint": "z", "kind": "k", "outcome": "o"})))
    assert W.fold_watch_receipts(src, dest) == 2
    assert dest.read_text().startswith(before)
    assert W.fold_watch_receipts(src, dest) == 0
    assert len(dest.read_text().splitlines()) == 3


def test_union_attributes_cover_exchange_not_compact():
    def attr(path):
        out = subprocess.run(["git", "check-attr", "merge", "--", path], cwd=ROOT, capture_output=True, text=True)
        return out.stdout.strip().rsplit(": ", 1)[-1]
    assert attr("data/commons/exchange.jsonl") == "union"
    assert attr("data/commons/crystallized.jsonl") == "union"
    assert attr("data/commons/crystallized_compact.jsonl") in ("unspecified", "unset")
    assert attr("data/commons/lessons.jsonl") == "unspecified"  # rewritten by lessons.expire; not union


def test_watch_workflow_writes_only_its_own_files():
    wf = (ROOT / ".github" / "workflows" / "colony-watch.yml").read_text()
    assert "COLONY_EXCHANGE_FILE: data/commons/exchange_watch.jsonl" in wf
    assert "git add -A" not in wf
    ev = (ROOT / ".github" / "workflows" / "colony-evolve.yml").read_text()
    assert "colony.tools.watch --fold" in ev
    assert ev.count("git rebase --abort") >= 4
