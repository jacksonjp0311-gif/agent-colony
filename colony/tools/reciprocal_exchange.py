"""Reciprocal exchange between One Mind and Agent Colony.

Pure Python. Fetches the other system's exchange.jsonl, versions receipts,
and records whether a foreign fingerprint later affected a local decision.
Never inherits the other system's keep/reject verdict.
Fail-open.
"""
from __future__ import annotations
from typing import Any, Dict, List
from pathlib import Path
import json
import urllib.request
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent.parent
LOCAL = ROOT / "data" / "commons" / "exchange.jsonl"
ADOPTION = ROOT / "data" / "commons" / "adoption_feedback.jsonl"

REMOTE = {
    "one-mind": "https://raw.githubusercontent.com/jacksonjp0311-gif/agent-colony/main/data/commons/exchange.jsonl",
    "colony": "https://raw.githubusercontent.com/jacksonjp0311-gif/one-mind/main/data/commons/exchange.jsonl",
}

def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()

def _read_lines(path: Path) -> List[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out

def fetch_remote(my_source: str, timeout: float = 8.0) -> List[dict]:
    """Pull the other system's receipts. Fail-open returns []."""
    url = REMOTE.get(my_source)
    if not url:
        return []
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        out = []
        for line in text.splitlines():
            try:
                rec = json.loads(line)
                rec["_imported"] = True
                rec["_imported_at"] = _utc()
                out.append(rec)
            except Exception:
                continue
        return out
    except Exception:
        return []

def merge_remote(my_source: str) -> int:
    """Append unseen remote receipts to local exchange. Returns count added."""
    remote = fetch_remote(my_source)
    if not remote:
        return 0
    existing = {json.dumps(r, sort_keys=True) for r in _read_lines(LOCAL)}
    added = 0
    LOCAL.parent.mkdir(parents=True, exist_ok=True)
    with LOCAL.open("a", encoding="utf-8") as f:
        for rec in remote:
            key = json.dumps({k: rec[k] for k in rec if not k.startswith("_")}, sort_keys=True)
            if key not in existing:
                f.write(json.dumps(rec) + "\n")
                existing.add(key)
                added += 1
    return added

def record_adoption(fingerprint: str, helped: bool, note: str = "") -> None:
    """Feedback: did this imported fingerprint change a local outcome?"""
    try:
        ADOPTION.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": _utc(),
            "fingerprint": fingerprint,
            "helped": bool(helped),
            "note": note,
        }
        with ADOPTION.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass

def foreign_count(fingerprint: str, my_source: str) -> int:
    """How many remote-origin receipts match this fingerprint."""
    return sum(
        1 for r in _read_lines(LOCAL)
        if r.get("_imported") and r.get("fingerprint") == fingerprint and r.get("source") != my_source
    )
