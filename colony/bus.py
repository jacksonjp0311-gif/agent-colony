"""Communication bus — bulletin/forum that agents actually read next cycle."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from colony.registry import AgentRegistry

ROOT = Path(__file__).resolve().parent.parent
BULLETIN_PATH = ROOT / "society" / "BULLETIN.md"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mid() -> str:
    return f"msg_{uuid.uuid4().hex[:10]}"


class CommBus:
    """Shared message bus backed by society_state + per-agent inboxes."""

    def __init__(self, state_data: dict[str, Any], registry: AgentRegistry) -> None:
        self.data = state_data
        self.registry = registry
        self.data.setdefault("bus", {"messages": [], "stats": {}})
        bus = self.data["bus"]
        bus.setdefault("messages", [])
        bus.setdefault("stats", {"posted": 0, "read": 0, "replied": 0})

    def messages(self) -> list[dict[str, Any]]:
        return self.data["bus"].setdefault("messages", [])

    def post(
        self,
        *,
        from_role: str,
        to_role: str,
        channel: str,
        message: str,
        cycle_id: str,
        tags: list[str] | None = None,
        in_reply_to: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = {
            "id": _mid(),
            "ts": _utc_now(),
            "cycle_id": cycle_id,
            "from": from_role,
            "to": to_role,
            "channel": channel,
            "message": message,
            "tags": list(tags or []),
            "in_reply_to": in_reply_to,
            "payload": dict(payload or {}),
            "replies": [],
        }
        self.messages().append(entry)
        # Keep last 200 on the bus
        if len(self.messages()) > 200:
            self.data["bus"]["messages"] = self.messages()[-200:]

        # Also mirror into legacy communications list for dashboard continuity
        self.data.setdefault("communications", []).append(
            {
                "ts": entry["ts"],
                "cycle_id": cycle_id,
                "from": from_role,
                "to": to_role,
                "channel": channel,
                "message": message,
                "id": entry["id"],
                "in_reply_to": in_reply_to,
                "tags": entry["tags"],
            }
        )
        stats = self.data["bus"].setdefault("stats", {})
        stats["posted"] = int(stats.get("posted") or 0) + 1
        if in_reply_to:
            stats["replied"] = int(stats.get("replied") or 0) + 1
            # Link reply on parent
            for m in self.messages():
                if m.get("id") == in_reply_to:
                    m.setdefault("replies", []).append(entry["id"])
                    break

        # Deliver into recipient inbox (and broadcast targets)
        targets = [to_role]
        if to_role in ("all", "forum", "*"):
            targets = list(self.registry.active().keys())
        for t in targets:
            if t == from_role and to_role not in ("all", "forum", "*"):
                continue
            self.registry.deliver(
                t,
                {
                    "id": entry["id"],
                    "from": from_role,
                    "to": to_role,
                    "channel": channel,
                    "message": message,
                    "tags": entry["tags"],
                    "cycle_id": cycle_id,
                    "in_reply_to": in_reply_to,
                    "payload": entry["payload"],
                },
            )
        return entry

    def read_inbox(self, role: str) -> list[dict[str, Any]]:
        """Return unread messages and mark them read. Real next-cycle consumption."""
        unread = self.registry.unread(role)
        if unread:
            self.registry.mark_read(role, [m["id"] for m in unread if m.get("id")])
            stats = self.data["bus"].setdefault("stats", {})
            stats["read"] = int(stats.get("read") or 0) + len(unread)
        return unread

    def reply_rate(self, *, lookback_cycles: int = 3) -> float:
        """Fraction of non-reply messages that received at least one reply."""
        msgs = self.messages()
        if not msgs:
            return 0.0
        # Consider recent messages only
        recent = msgs[-80:]
        roots = [m for m in recent if not m.get("in_reply_to") and m.get("to") not in ("all",)]
        if not roots:
            return 0.0
        replied = sum(1 for m in roots if m.get("replies"))
        return round(replied / len(roots), 4)

    def extract_actionables(self, unread: list[dict[str, Any]]) -> dict[str, Any]:
        """Parse unread messages into actionable signals agents can USE."""
        gaps: list[str] = []
        build_requests: list[str] = []
        improve_hints: list[str] = []
        needs_reply: list[dict[str, Any]] = []
        for m in unread:
            tags = set(m.get("tags") or [])
            payload = m.get("payload") or {}
            if "gap_alert" in tags or payload.get("thin_topics"):
                gaps.extend(list(payload.get("thin_topics") or []))
            if "build_request" in tags:
                build_requests.append(m.get("message") or "")
            if "improve_hint" in tags:
                improve_hints.append(m.get("message") or "")
            if not m.get("in_reply_to") and m.get("from") != m.get("to"):
                needs_reply.append(m)
            # Heuristic: message text mentioning thin/gap
            text = (m.get("message") or "").lower()
            if "thin" in text or "gap" in text:
                for part in text.replace(",", " ").split():
                    if "-" in part and len(part) > 4:
                        gaps.append(part.strip(".:;"))
        # dedupe
        return {
            "thin_topics": sorted(set(gaps))[:12],
            "build_requests": build_requests[:5],
            "improve_hints": improve_hints[:5],
            "needs_reply": needs_reply[:8],
        }

    def render_bulletin(self) -> Path:
        msgs = self.messages()
        legacy = self.data.get("communications") or []
        # Prefer bus messages; fall back to legacy
        source = msgs if msgs else legacy
        lines = [
            "# Society Bulletin",
            "",
            "> We light the spark and witness. We do not micromanage the city.",
            "",
            f"**Bus messages:** {len(msgs)}  ",
            f"**Legacy communications:** {len(legacy)}  ",
            f"**Stats:** `{self.data.get('bus', {}).get('stats', {})}`  ",
            f"**Reply rate (recent):** {self.reply_rate():.0%}",
            "",
            "## Chronology (latest 50)",
            "",
        ]
        if not source:
            lines.append("_No messages yet._")
        else:
            for c in source[-50:]:
                reply = f" (reply to `{c.get('in_reply_to')}`)" if c.get("in_reply_to") else ""
                tags = ",".join(c.get("tags") or []) or "-"
                lines.append(
                    f"- **{c.get('ts')}** [`{c.get('channel')}`/{tags}] "
                    f"**{c.get('from')}** → **{c.get('to')}**: {c.get('message')}{reply}"
                )
            lines.append("")
        lines.extend(
            [
                "---",
                "",
                "_Messages are delivered to agent inboxes and read on the next cycle._",
                "",
            ]
        )
        BULLETIN_PATH.parent.mkdir(parents=True, exist_ok=True)
        BULLETIN_PATH.write_text("\n".join(lines), encoding="utf-8")
        return BULLETIN_PATH
