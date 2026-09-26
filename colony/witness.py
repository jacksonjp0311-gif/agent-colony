"""Append-only witness log — the human (and logs) observe civilization forming."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
WITNESS_JSONL = ROOT / "data" / "witness.jsonl"
WITNESS_MD = ROOT / "society" / "WITNESS.md"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _eid() -> str:
    return f"wit_{uuid.uuid4().hex[:10]}"


@dataclass
class WitnessEvent:
    id: str
    timestamp: str
    cycle_id: str
    kind: str
    actor: str
    summary: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WitnessLog:
    def __init__(self, path: Path | None = None, md_path: Path | None = None) -> None:
        self.path = path or WITNESS_JSONL
        self.md_path = md_path or WITNESS_MD
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def record(
        self,
        *,
        cycle_id: str,
        kind: str,
        actor: str,
        summary: str,
        detail: dict[str, Any] | None = None,
    ) -> WitnessEvent:
        ev = WitnessEvent(
            id=_eid(),
            timestamp=_utc_now(),
            cycle_id=cycle_id,
            kind=kind,
            actor=actor,
            summary=summary,
            detail=dict(detail or {}),
        )
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev.to_dict(), ensure_ascii=False) + "\n")
        return ev

    def all(self) -> list[WitnessEvent]:
        out: list[WitnessEvent] = []
        if not self.path.is_file():
            return out
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                out.append(WitnessEvent(**d))
        return out

    def render_md(self, *, ethos: str, principal: str, extra_preamble: str = "") -> Path:
        events = self.all()
        lines = [
            "# WITNESS",
            "",
            f"> {ethos}",
            "",
            f"**Human Principal / Witness:** {principal}  ",
            f"**Events recorded:** {len(events)}  ",
            f"**Log:** `data/witness.jsonl` (append-only)",
            "",
        ]
        if extra_preamble:
            lines.extend([extra_preamble, ""])
        lines.append("## Chronology")
        lines.append("")
        if not events:
            lines.append("_Nothing witnessed yet._")
        else:
            for ev in events:
                lines.append(f"### {ev.timestamp} — `{ev.kind}` ({ev.actor})")
                lines.append("")
                lines.append(f"- **id:** `{ev.id}` | **cycle:** `{ev.cycle_id}`")
                lines.append(f"- {ev.summary}")
                if ev.detail:
                    interesting = {
                        k: v
                        for k, v in ev.detail.items()
                        if k in {"role", "roles", "council", "institution", "norm", "ritual",
                                 "from_role", "to_role", "from", "to", "channel", "message",
                                 "topics", "count", "title", "status", "proposal_type", "name",
                                 "path", "kind", "builds", "gathered", "improvements",
                                 "communications", "outcome", "description"}
                        or not isinstance(v, (dict, list))
                    }
                    if interesting:
                        lines.append(f"- detail: `{json.dumps(interesting, ensure_ascii=False)[:300]}`")
                lines.append("")
        lines.extend(
            [
                "---",
                "",
                "_The human does not micromanage the city. The human witnesses._",
                "",
            ]
        )
        self.md_path.parent.mkdir(parents=True, exist_ok=True)
        self.md_path.write_text("\n".join(lines), encoding="utf-8")
        return self.md_path
