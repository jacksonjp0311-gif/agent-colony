"""Symbiotic exchange — pure-Python receipts between systems.

Each system appends measured failures/residuals. The other tails the file
and treats foreign fingerprints as additional prior. Fail-open.
No new dependencies. No authority transfer.
"""
from __future__ import annotations
from typing import Any, Dict, List
from pathlib import Path
import json
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent.parent
EXCHANGE = ROOT / "data" / "commons" / "exchange.jsonl"

def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()

def append_receipt(source: str, kind: str, fingerprint: str, outcome: str, extra: Dict[str, Any] | None = None) -> None:
    """Append one receipt. Skip if the same event is already recent.

    Dedup key: source, fingerprint, kind, outcome.
    Fail-open.
    """
    try:
        EXCHANGE.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": _utc(),
            "source": source,
            "lineage": source,
            "kind": kind,
            "fingerprint": str(fingerprint),
            "outcome": outcome,
        }
        if extra:
            rec["extra"] = extra
        key = (source, str(fingerprint), kind, outcome)
        if EXCHANGE.exists():
            for line in EXCHANGE.read_text(encoding="utf-8").splitlines()[-200:]:
                try:
                    old = json.loads(line)
                    if (old.get("source"), str(old.get("fingerprint")), old.get("kind"), old.get("outcome")) == key:
                        return
                except Exception:
                    continue
        with EXCHANGE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass

def foreign_fingerprints(my_source: str, limit: int = 200) -> List[str]:
    """Fingerprints written by any source other than my_source."""
    if not EXCHANGE.exists():
        return []
    out = []
    try:
        for line in EXCHANGE.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                rec = json.loads(line)
                if (rec.get("source") != my_source
                        and rec.get("fingerprint")
                        and rec.get("outcome") in ("reverted", "failed", "failure")):
                    out.append(str(rec["fingerprint"]))
            except Exception:
                continue
    except Exception:
        pass
    return out

def foreign_penalty(fingerprint: str, my_source: str = "colony") -> int:
    """Extra penalty if this fingerprint appears in foreign receipts."""
    fps = foreign_fingerprints(my_source)
    count = sum(1 for fp in fps if fp == fingerprint)
    return -min(count * 30, 120)


def agreed_prior(fingerprint: str) -> int:
    """Small bonus if dream marked this fingerprint agreed. Prior, not a keep."""
    try:
        import json
        from pathlib import Path as P
        store = P(__file__).resolve().parent.parent.parent / "data" / "commons" / "crystallized.jsonl"
        if not store.exists() or not fingerprint:
            return 0
        for line in store.read_text(encoding="utf-8").splitlines()[-64:]:
            try:
                rec = json.loads(line)
                if rec.get("fingerprint") == fingerprint and rec.get("agreed"):
                    return 40
            except Exception:
                continue
        return 0
    except Exception:
        return 0


def kept_prior(fingerprint: str) -> int:
    """Bonus if a kept record matches this fingerprint or its knob.

    A verified adopt is a prior on the next proposal. Not a keep.
    Fail-open returns 0.
    """
    try:
        import json
        from pathlib import Path as P
        if not fingerprint:
            return 0
        store = P(__file__).resolve().parent.parent.parent / "data" / "commons" / "crystallized.jsonl"
        if not store.exists():
            return 0
        knob = str(fingerprint).split(":")[0]
        for line in store.read_text(encoding="utf-8").splitlines()[-128:]:
            try:
                rec = json.loads(line)
                if rec.get("category") != "kept":
                    continue
                fp = str(rec.get("fingerprint") or "")
                if fp == fingerprint or fp.startswith(knob + ":"):
                    return 60
            except Exception:
                continue
        return 0
    except Exception:
        return 0


def foreign_kept_prior(fingerprint: str, my_source: str = "colony") -> int:
    """Capped prior only for a foreign record that is a confirmed keep.

    Exact fingerprint. Outcome must be kept or adopted.
    A proposal, a revert, a dream, or a prefix match is not a reward.
    Fail-open returns 0. Capped at 40.
    """
    try:
        import json
        from pathlib import Path as P
        if not fingerprint:
            return 0
        store = P(__file__).resolve().parent.parent.parent / "data" / "commons" / "evidence_view.jsonl"
        if not store.exists():
            store = P(__file__).resolve().parent.parent.parent / "data" / "commons" / "exchange.jsonl"
        if not store.exists():
            return 0
        for line in store.read_text(encoding="utf-8").splitlines()[-400:]:
            try:
                rec = json.loads(line)
                if rec.get("source") == my_source:
                    continue
                if str(rec.get("fingerprint") or "") != fingerprint:
                    continue
                if rec.get("outcome") not in ("kept", "adopted"):
                    continue
                return 40
            except Exception:
                continue
        return 0
    except Exception:
        return 0
