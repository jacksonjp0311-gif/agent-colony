#!/usr/bin/env python3
"""Build data/research_cache/papers.jsonl from offline_seeds + ledger arXiv IDs.

Offline-first. Do NOT fetch network in CI unless --live.
Not discovery. Not AGI.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEEDS = ROOT / "data" / "research_cache" / "offline_seeds.json"
LEDGER = ROOT / "data" / "ledger.jsonl"
OUT = ROOT / "data" / "research_cache" / "papers.jsonl"
ARXIV_RE = re.compile(
    r"(?:arxiv(?:\.org/abs/|:)?)\s*([0-9]{4}\.[0-9]{4,5}|[a-z\-]+/[0-9]{7})",
    re.I,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="Reserved; offline-first by default")
    args = ap.parse_args()
    rows: list[dict] = []
    seen: set[str] = set()

    def add(row: dict) -> None:
        aid = str(row.get("arxiv_id") or "").strip()
        key = aid or (row.get("title") or "")[:80]
        if not key or key in seen:
            return
        seen.add(key)
        rows.append(row)

    if SEEDS.exists():
        for s in json.loads(SEEDS.read_text(encoding="utf-8")):
            add({**s, "source": s.get("source") or "offline_seed"})
    if LEDGER.exists():
        for ln in LEDGER.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                e = json.loads(ln)
            except json.JSONDecodeError:
                continue
            meta = e.get("meta") or {}
            aid = str(meta.get("arxiv_id") or "")
            blob = json.dumps(e)
            m = ARXIV_RE.search(blob)
            if m and not aid:
                aid = m.group(1)
            for u in e.get("evidence_urls") or []:
                mm = re.search(r"arxiv\.org/abs/([^\s\"']+)", str(u))
                if mm:
                    aid = mm.group(1)
            if not aid:
                continue
            add(
                {
                    "source": "ledger",
                    "arxiv_id": aid,
                    "title": e.get("title") or (e.get("claim") or "")[:120],
                    "abstract_snippet": (e.get("claim") or "")[:240],
                    "url": f"https://arxiv.org/abs/{aid}",
                    "tags": list(e.get("tags") or [])[:12],
                    "topic_id": e.get("topic_id") or "",
                }
            )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({"rows": len(rows), "path": str(OUT), "live": bool(args.live)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
