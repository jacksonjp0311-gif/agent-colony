"""Communication bus — bulletin/forum that agents actually read next cycle."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from colony.registry import AgentRegistry

ROOT = Path(__file__).resolve().parent.parent
BULLETIN_PATH = ROOT / "society" / "BULLETIN.md"

# Domain channels for empire gather/comms upgrade
DOMAIN_CHANNELS = ("science", "history", "math", "empire", "bulletin", "forum", "software", "nature", "life", "cosmos", "rsi")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mid() -> str:
    return f"msg_{uuid.uuid4().hex[:10]}"


def score_reply_quality(text: str, *, parent_message: str | None = None) -> float:
    """Heuristic reply quality in [0,1]: length, ACK, actionable cues, non-empty."""
    t = (text or "").strip()
    if not t:
        return 0.0
    score = 0.15
    n = len(t)
    if n >= 40:
        score += 0.2
    if n >= 100:
        score += 0.15
    low = t.lower()
    if any(k in low for k in ("ack", "read", "acting", "will")):
        score += 0.15
    if any(k in low for k in ("thin", "focus", "commons", "propose", "gather", "build")):
        score += 0.15
    if any(k in low for k in ("science", "history", "math", "genome", "census", "law")):
        score += 0.1
    if parent_message and any(
        w in low for w in (parent_message.lower().split()[:6]) if len(w) > 4
    ):
        score += 0.1
    return round(min(1.0, score), 4)


class CommBus:
    """Shared message bus backed by society_state + per-agent inboxes."""

    def __init__(self, state_data: dict[str, Any], registry: AgentRegistry) -> None:
        self.data = state_data
        self.registry = registry
        self.data.setdefault("bus", {"messages": [], "stats": {}})
        bus = self.data["bus"]
        bus.setdefault("messages", [])
        bus.setdefault(
            "stats",
            {
                "posted": 0,
                "read": 0,
                "replied": 0,
                "reply_quality_sum": 0.0,
                "reply_quality_n": 0,
                "peer_cites": 0,
                "peer_cite_opportunities": 0,
                "actions_changed_from_message": 0,
                "actions_planned": 0,
            },
        )
        bus.setdefault("domains", {d: 0 for d in DOMAIN_CHANNELS})

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
            "quality": None,
        }
        if in_reply_to:
            parent_text = None
            for m in self.messages():
                if m.get("id") == in_reply_to:
                    parent_text = m.get("message")
                    break
            q = score_reply_quality(message, parent_message=parent_text)
            entry["quality"] = q
            stats = self.data["bus"].setdefault("stats", {})
            stats["reply_quality_sum"] = float(stats.get("reply_quality_sum") or 0) + q
            stats["reply_quality_n"] = int(stats.get("reply_quality_n") or 0) + 1

        self.messages().append(entry)
        if len(self.messages()) > 200:
            self.data["bus"]["messages"] = self.messages()[-200:]

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
                "quality": entry.get("quality"),
            }
        )
        stats = self.data["bus"].setdefault("stats", {})
        stats["posted"] = int(stats.get("posted") or 0) + 1
        if in_reply_to:
            stats["replied"] = int(stats.get("replied") or 0) + 1
            for m in self.messages():
                if m.get("id") == in_reply_to:
                    m.setdefault("replies", []).append(entry["id"])
                    break

        domains = self.data["bus"].setdefault("domains", {})
        ch = channel if channel in DOMAIN_CHANNELS else "bulletin"
        domains[ch] = int(domains.get(ch) or 0) + 1

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
        unread = self.registry.unread(role)
        if unread:
            self.registry.mark_read(role, [m["id"] for m in unread if m.get("id")])
            stats = self.data["bus"].setdefault("stats", {})
            stats["read"] = int(stats.get("read") or 0) + len(unread)
        return unread

    def reply_rate(self, *, lookback_cycles: int = 3) -> float:
        msgs = self.messages()
        if not msgs:
            return 0.0
        recent = msgs[-80:]
        roots = [m for m in recent if not m.get("in_reply_to") and m.get("to") not in ("all",)]
        if not roots:
            return 0.0
        replied = sum(1 for m in roots if m.get("replies"))
        return round(replied / len(roots), 4)

    def reply_quality(self) -> float:
        stats = (self.data.get("bus") or {}).get("stats") or {}
        n = int(stats.get("reply_quality_n") or 0)
        if n <= 0:
            return 0.0
        return round(float(stats.get("reply_quality_sum") or 0) / n, 4)

    def record_peer_cite(self, *, cited: bool) -> None:
        """Count replies that cite prior turns / peer findings (kill shout-into-void)."""
        stats = self.data["bus"].setdefault("stats", {})
        stats["peer_cite_opportunities"] = int(stats.get("peer_cite_opportunities") or 0) + 1
        if cited:
            stats["peer_cites"] = int(stats.get("peer_cites") or 0) + 1

    def peer_cite_rate(self) -> float:
        stats = (self.data.get("bus") or {}).get("stats") or {}
        n = int(stats.get("peer_cite_opportunities") or 0)
        if n <= 0:
            return 0.0
        return round(int(stats.get("peer_cites") or 0) / n, 4)

    def record_action_changed(self, *, changed: bool, detail: dict | None = None) -> None:
        """NEXT ACTION must change because of a message — measure it."""
        stats = self.data["bus"].setdefault("stats", {})
        stats["actions_planned"] = int(stats.get("actions_planned") or 0) + 1
        if changed:
            stats["actions_changed_from_message"] = int(
                stats.get("actions_changed_from_message") or 0
            ) + 1
        if detail:
            log = self.data["bus"].setdefault("action_change_log", [])
            log.append(detail)
            if len(log) > 40:
                self.data["bus"]["action_change_log"] = log[-40:]

    def action_changed_rate(self) -> float:
        stats = (self.data.get("bus") or {}).get("stats") or {}
        n = int(stats.get("actions_planned") or 0)
        if n <= 0:
            return 0.0
        return round(int(stats.get("actions_changed_from_message") or 0) / n, 4)

    def inner_bus_metrics(self) -> dict:
        return {
            "reply_rate": self.reply_rate(),
            "reply_quality": self.reply_quality(),
            "peer_cite_rate": self.peer_cite_rate(),
            "action_changed_from_message": self.action_changed_rate(),
            "stats": dict((self.data.get("bus") or {}).get("stats") or {}),
        }

    def message_cites_peer(self, text: str, *, parent: dict | None = None, peer_findings: list | None = None) -> bool:
        """Heuristic: reply cites prior msg id, peer role finding, or parent tokens."""
        t = (text or "").lower()
        if not t:
            return False
        if parent:
            pid = str(parent.get("id") or "")
            if pid and pid.lower() in t:
                return True
            # cite prior turn fragment
            parent_words = [w for w in (parent.get("message") or "").lower().split() if len(w) > 5][:6]
            if parent_words and sum(1 for w in parent_words if w in t) >= 2:
                return True
            fr = (parent.get("from") or "").lower()
            if fr and f"from {fr}" in t or (fr and f"@{fr}" in t):
                return True
        for fid in peer_findings or []:
            if fid and str(fid).lower() in t:
                return True
        if any(k in t for k in ("finding ", "fnd_", "peer:", "prior turn", "citing ", "cite ")):
            return True
        return False

    def extract_actionables(self, unread: list[dict[str, Any]]) -> dict[str, Any]:
        gaps: list[str] = []
        build_requests: list[str] = []
        improve_hints: list[str] = []
        needs_reply: list[dict[str, Any]] = []
        domain_notes: list[str] = []
        for m in unread:
            tags = set(m.get("tags") or [])
            payload = m.get("payload") or {}
            if "gap_alert" in tags or payload.get("thin_topics"):
                gaps.extend(list(payload.get("thin_topics") or []))
            if "build_request" in tags:
                build_requests.append(m.get("message") or "")
            if "improve_hint" in tags:
                improve_hints.append(m.get("message") or "")
            if "commons_digest" in tags or payload.get("commons"):
                domain_notes.append(m.get("message") or "")
            if not m.get("in_reply_to") and m.get("from") != m.get("to"):
                needs_reply.append(m)
            text = (m.get("message") or "").lower()
            if "thin" in text or "gap" in text:
                for part in text.replace(",", " ").split():
                    if "-" in part and len(part) > 4:
                        gaps.append(part.strip(".:;"))
            ch = m.get("channel") or ""
            if ch in ("science", "history", "math") and ch not in gaps:
                gaps.append(
                    {
                        "science": "science-method",
                        "history": "history-of-ideas",
                        "math": "mathematics-foundations",
                    }.get(ch, ch)
                )
        return {
            "thin_topics": sorted(set(str(g) for g in gaps if isinstance(g, str)))[:12],
            "build_requests": build_requests[:5],
            "improve_hints": improve_hints[:5],
            "needs_reply": needs_reply[:14],
            "commons_notes": domain_notes[:5],
        }

    def render_bulletin(self) -> Path:
        msgs = self.messages()
        legacy = self.data.get("communications") or []
        source = msgs if msgs else legacy
        lines = [
            "# Society Bulletin",
            "",
            "> We light the spark and witness. We do not micromanage the city.",
            "",
            f"**Bus messages:** {len(msgs)}  ",
            f"**Legacy communications:** {len(legacy)}  ",
            f"**Stats:** `{self.data.get('bus', {}).get('stats', {})}`  ",
            f"**Domains:** `{self.data.get('bus', {}).get('domains', {})}`  ",
            f"**Reply rate (recent):** {self.reply_rate():.0%}  ",
            f"**Reply quality (avg):** {self.reply_quality():.0%}  ",
            f"**Peer cite rate:** {self.peer_cite_rate():.0%}  ",
            f"**Action changed from message:** {self.action_changed_rate():.0%}",
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
                q = c.get("quality")
                q_s = f" q={q}" if q is not None else ""
                lines.append(
                    f"- **{c.get('ts')}** [`{c.get('channel')}`/{tags}] "
                    f"**{c.get('from')}** → **{c.get('to')}**: {c.get('message')}{reply}{q_s}"
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
