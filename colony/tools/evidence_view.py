"""Deduped evidence view.

Pattern: read the raw log, project unique events, append nothing to the raw log.
The original stream is never rewritten.
A future system reads the view, not the raw duplicates.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RAW = ROOT / "data" / "commons" / "exchange.jsonl"
VIEW = ROOT / "data" / "commons" / "evidence_view.jsonl"


def project() -> dict:
    """One unique row per source+fingerprint+kind+outcome+ts. Fail-open."""
    seen = set()
    kept = 0
    total = 0
    unique = 0
    try:
        if not RAW.exists():
            return {"total": 0, "unique": 0, "kept": 0}
        VIEW.parent.mkdir(parents=True, exist_ok=True)
        with VIEW.open("w", encoding="utf-8") as out:
            for line in RAW.read_text(encoding="utf-8").splitlines():
                total += 1
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                key = (
                    rec.get("event_id") or rec.get("ts"),
                    rec.get("source"),
                    rec.get("fingerprint"),
                    rec.get("kind"),
                    rec.get("outcome"),
                )
                if key in seen:
                    continue
                seen.add(key)
                unique += 1
                if rec.get("outcome") in ("kept", "adopted"):
                    kept += 1
                out.write(json.dumps(rec) + "\n")
        return {"total": total, "unique": unique, "kept": kept}
    except Exception:
        return {"total": total, "unique": unique, "kept": kept}


if __name__ == "__main__":
    print(json.dumps(project()))
