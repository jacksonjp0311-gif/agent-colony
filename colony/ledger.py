"""Append-only JSONL ledger of colony findings.

Corrections are new entries; history is not rewritten.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal

from colony.charter import assert_valid_finding_fields

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LEDGER = ROOT / "data" / "ledger.jsonl"

Status = Literal["candidate", "accepted", "rejected", "unknown"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id() -> str:
    return f"fnd_{uuid.uuid4().hex[:12]}"


@dataclass
class Finding:
    id: str
    timestamp: str
    role: str
    claim: str
    evidence_urls: list[str]
    provenance: str
    status: Status
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    parent_ids: list[str] = field(default_factory=list)
    topic_id: str = ""
    title: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Finding:
        return cls(
            id=d["id"],
            timestamp=d["timestamp"],
            role=d["role"],
            claim=d["claim"],
            evidence_urls=list(d.get("evidence_urls") or []),
            provenance=d["provenance"],
            status=d["status"],
            tags=list(d.get("tags") or []),
            notes=d.get("notes") or "",
            parent_ids=list(d.get("parent_ids") or []),
            topic_id=d.get("topic_id") or "",
            title=d.get("title") or "",
            meta=dict(d.get("meta") or {}),
        )


class Ledger:
    """Append-only JSONL store."""

    def __init__(
        self,
        path: Path | None = None,
        extra_roles: set[str] | None = None,
    ) -> None:
        self.path = path or DEFAULT_LEDGER
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        self.extra_roles: set[str] = set(extra_roles or [])

    def set_extra_roles(self, roles: set[str]) -> None:
        self.extra_roles = set(roles)

    def append(self, finding: Finding) -> Finding:
        assert_valid_finding_fields(
            claim=finding.claim,
            evidence_urls=finding.evidence_urls,
            provenance=finding.provenance,
            status=finding.status,
            role=finding.role,
            extra_roles=self.extra_roles,
        )
        line = json.dumps(finding.to_dict(), ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        return finding

    def create(
        self,
        *,
        role: str,
        claim: str,
        evidence_urls: list[str],
        provenance: str,
        status: Status = "candidate",
        tags: list[str] | None = None,
        notes: str = "",
        parent_ids: list[str] | None = None,
        topic_id: str = "",
        title: str = "",
        meta: dict[str, Any] | None = None,
    ) -> Finding:
        finding = Finding(
            id=_new_id(),
            timestamp=_utc_now(),
            role=role,
            claim=claim,
            evidence_urls=list(evidence_urls),
            provenance=provenance,
            status=status,
            tags=list(tags or []),
            notes=notes,
            parent_ids=list(parent_ids or []),
            topic_id=topic_id,
            title=title,
            meta=dict(meta or {}),
        )
        return self.append(finding)

    def iter_all(self) -> Iterator[Finding]:
        if not self.path.is_file():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield Finding.from_dict(json.loads(line))

    def all(self) -> list[Finding]:
        return list(self.iter_all())

    def by_status(self, status: Status) -> list[Finding]:
        return [f for f in self.all() if f.status == status]

    def by_topic(self, topic_id: str) -> list[Finding]:
        return [f for f in self.all() if f.topic_id == topic_id]

    def count(self) -> int:
        return sum(1 for _ in self.iter_all())

    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {s: 0 for s in ("candidate", "accepted", "rejected", "unknown")}
        for f in self.all():
            counts[f.status] = counts.get(f.status, 0) + 1
        return counts

    def tribute_findings(self, tribute_topics: list[str]) -> list[Finding]:
        tset = set(tribute_topics)
        return [
            f
            for f in self.all()
            if f.topic_id in tset or any(t in (f.tags or []) for t in tset)
        ]
