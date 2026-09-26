"""Common knowledge — shared candidate notes the society reuses each cycle.

Writers append candidates; readers load digests. Durable `accepted` still needs
human authorize. Stored as society/systems/common_knowledge.json + data/commons/.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
COMMONS_DIR = ROOT / "data" / "commons"
COMMONS_JSONL = COMMONS_DIR / "entries.jsonl"
SYSTEM_NAME = "common_knowledge"

DOMAINS = ("science", "history", "math", "rsi", "empire", "general")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CommonKnowledge:
    def __init__(self, state_data: dict[str, Any], root: Path | None = None) -> None:
        self.data = state_data
        self.root = root or ROOT
        self.dir = self.root / "data" / "commons"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.jsonl = self.dir / "entries.jsonl"
        self.system_path = self.root / "society" / "systems" / "common_knowledge.json"
        self.data.setdefault("commons", {"entries": [], "stats": {"appended": 0, "reused": 0}})

    def size(self) -> int:
        entries = (self.data.get("commons") or {}).get("entries") or []
        return len(entries)

    def append(
        self,
        *,
        domain: str,
        title: str,
        summary: str,
        source_role: str,
        cycle_id: str,
        tags: list[str] | None = None,
        evidence: list[str] | None = None,
    ) -> dict[str, Any]:
        domain = domain if domain in DOMAINS else "general"
        entry = {
            "id": f"ck_{cycle_id[-6:]}_{self.size():04d}",
            "ts": _utc_now(),
            "cycle_id": cycle_id,
            "domain": domain,
            "title": title[:160],
            "summary": summary[:600],
            "source_role": source_role,
            "tags": list(tags or []),
            "evidence": list(evidence or []),
            "status": "candidate",  # hard ceiling
            "reuse_count": 0,
        }
        commons = self.data.setdefault("commons", {"entries": [], "stats": {}})
        commons.setdefault("entries", []).append(entry)
        if len(commons["entries"]) > 200:
            commons["entries"] = commons["entries"][-200:]
        stats = commons.setdefault("stats", {})
        stats["appended"] = int(stats.get("appended") or 0) + 1
        # Append-only mirror
        with self.jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._persist_system(cycle_id)
        return entry

    def reuse(self, *, domain: str | None = None, limit: int = 8) -> list[dict[str, Any]]:
        entries = list((self.data.get("commons") or {}).get("entries") or [])
        if domain:
            entries = [e for e in entries if e.get("domain") == domain]
        # Prefer least-reused then newest
        entries.sort(key=lambda e: (int(e.get("reuse_count") or 0), e.get("ts") or ""))
        picked = list(reversed(entries[-limit:])) if not domain else entries[:limit]
        # Actually take last N by time among filtered
        filtered = [
            e
            for e in ((self.data.get("commons") or {}).get("entries") or [])
            if (domain is None or e.get("domain") == domain)
        ]
        picked = filtered[-limit:]
        for e in picked:
            e["reuse_count"] = int(e.get("reuse_count") or 0) + 1
        stats = self.data.setdefault("commons", {}).setdefault("stats", {})
        stats["reused"] = int(stats.get("reused") or 0) + len(picked)
        return picked

    def digest(self, *, limit: int = 6) -> str:
        entries = ((self.data.get("commons") or {}).get("entries") or [])[-limit:]
        if not entries:
            return "(commons empty)"
        parts = []
        for e in entries:
            parts.append(f"[{e.get('domain')}] {e.get('title')}: {(e.get('summary') or '')[:80]}")
        return " | ".join(parts)

    def by_domain_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in (self.data.get("commons") or {}).get("entries") or []:
            d = e.get("domain") or "general"
            counts[d] = counts.get(d, 0) + 1
        return counts

    def _persist_system(self, cycle_id: str) -> None:
        commons = self.data.get("commons") or {}
        payload = {
            "version": 1,
            "updated_at": _utc_now(),
            "updated_cycle": cycle_id,
            "size": len(commons.get("entries") or []),
            "stats": commons.get("stats") or {},
            "by_domain": self.by_domain_counts(),
            "recent": (commons.get("entries") or [])[-12:],
            "note": "Candidates only. Human authorize required for accepted knowledge.",
        }
        self.system_path.parent.mkdir(parents=True, exist_ok=True)
        self.system_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
