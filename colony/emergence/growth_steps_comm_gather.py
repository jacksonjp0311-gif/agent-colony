"""Growth loop steps - part 2."""
from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
ARTIFACTS_DIR = ROOT / "society" / "artifacts"


class GrowthSteps2:

    def _communicate_and_reply(
        self,
        cycle_id: str,
        cycle_n: int,
        g,
        tribute_topics: list[str],
        actionables: dict[str, Any],
    ) -> None:
        roles = set(self.registry.active().keys())
        ask = self.state.active_ask()

        # Reply to unreplied messages (REAL loop closure)
        reply_tracker_open = []
        for m in actionables.get("needs_reply") or []:
            to_role = m.get("to")
            responder = to_role if to_role in roles else self.registry.best_for("communicate")
            if responder not in roles:
                responder = "spark"
            parent_id = m.get("id")
            reply_text = (
                f"ACK cycle {cycle_n}: read your message from {m.get('from')}. "
                f"Acting under growth will. Thin focus={', '.join((actionables.get('thin_topics') or [])[:3]) or 'n/a'}."
            )
            entry = self.bus.post(
                from_role=responder,
                to_role=m.get("from") or "spark",
                channel=m.get("channel") or "bulletin",
                message=reply_text,
                cycle_id=cycle_id,
                tags=["reply"],
                in_reply_to=parent_id,
            )
            g.replies += 1
            g.communications.append(entry)
            self.registry.agents()[responder]["replies_sent"] = int(
                self.registry.agents()[responder].get("replies_sent") or 0
            ) + 1
            self.registry.record_outcome(responder, "communicate", 0.8)
            self._ledger_comm(entry, cycle_id, g)
            self.witness.record(
                cycle_id=cycle_id,
                kind="communication_reply",
                actor=responder,
                summary=f"Reply {responder} -> {entry['to']} (to {parent_id})",
                detail={"id": entry["id"], "in_reply_to": parent_id},
            )

        # Fresh posts (land in inboxes for NEXT cycle)
        thin = actionables.get("thin_topics") or list(tribute_topics)[:4]
        plans = [
            (
                "spark",
                "tribute_keeper",
                "bulletin",
                f"Cycle {cycle_n}: keep paying tribute. Will - {ask[:120]}",
                ["directive"],
                {},
            ),
            (
                self.registry.best_for("communicate"),
                "memory_weaver" if "memory_weaver" in roles else "spark",
                "bulletin",
                f"Herald/courier: weave patterns; watch thin topics {', '.join(thin[:5]) or 'none'}.",
                ["gap_alert"],
                {"thin_topics": thin[:8]},
            ),
            (
                self.registry.best_for("build"),
                self.registry.best_for("improve"),
                "forum",
                f"Builder: systems_used={g.systems_used}; propose reuse upgrades.",
                ["build_request"],
                {"systems_used": g.systems_used},
            ),
            (
                self.registry.best_for("gather"),
                "spark",
                "bulletin",
                f"Gather signal: coverage targets ranked; thin={', '.join(thin[:4]) or 'none'}.",
                ["gap_alert", "gather"],
                {"thin_topics": thin[:8]},
            ),
        ]
        for fr, to, channel, message, tags, payload in plans:
            fr_r = fr if fr in roles else "spark"
            to_r = to if to in roles else "spark"
            entry = self.bus.post(
                from_role=fr_r,
                to_role=to_r,
                channel=channel,
                message=message,
                cycle_id=cycle_id,
                tags=tags,
                payload=payload,
            )
            g.communications.append(entry)
            self._ledger_comm(entry, cycle_id, g)
            self.witness.record(
                cycle_id=cycle_id,
                kind="communication",
                actor=fr_r,
                summary=f"{fr_r} -> {to_r} via {channel}: {message[:140]}",
                detail={"id": entry["id"], "from": fr_r, "to": to_r, "tags": tags},
            )
            if "gap_alert" in tags:
                reply_tracker_open.append(entry["id"])

        if "reply_tracker" in self.workshop.known():
            prev = self.workshop.use("reply_tracker", cycle_id)
            content = (prev or {}).get("content") or {"open": [], "closed": []}
            replied_parents = {c.get("in_reply_to") for c in g.communications if c.get("in_reply_to")}
            still_open = [x for x in (content.get("open") or []) if x not in replied_parents]
            still_open.extend(reply_tracker_open)
            closed = list(content.get("closed") or []) + [x for x in replied_parents if x]
            self.workshop.write_json(
                "reply_tracker",
                {"open": still_open[-40:], "closed": closed[-80:]},
                cycle_id,
            )
            if "reply_tracker" not in g.systems_used:
                g.systems_used.append("reply_tracker")

    def _gather(
        self,
        cycle_id: str,
        g,
        tribute_topics: list[str],
        tribute_count: int,
        actionables: dict[str, Any],
    ) -> None:
        actor = self.registry.best_for("gather")
        standing = self.state.standing_topics()
        ranked_topics: list[str] = []
        pri = self.workshop.use("topic_priority", cycle_id)
        if pri and isinstance(pri.get("content"), dict):
            ranked_topics = [
                r.get("topic")
                for r in (pri["content"].get("ranked") or [])
                if r.get("topic")
            ]
            if "topic_priority" not in g.systems_used:
                g.systems_used.append("topic_priority")

        ledger_topics: dict[str, int] = {}
        for fnd in self.ledger.all():
            if fnd.topic_id:
                ledger_topics[fnd.topic_id] = ledger_topics.get(fnd.topic_id, 0) + 1

        if "coverage_index" not in self.workshop.known():
            self.workshop.ensure("coverage_index", built_by=actor, cycle_id=cycle_id)
            g.systems_built.append("coverage_index")
        self.workshop.write_json(
            "coverage_index",
            {"topics": ledger_topics, "source": "gather_pass"},
            cycle_id,
        )
        self.workshop.use("coverage_index", cycle_id)
        if "coverage_index" not in g.systems_used:
            g.systems_used.append("coverage_index")

        thin_inbox = actionables.get("thin_topics") or []
        all_focus = sorted(set(ranked_topics[:6]) | set(thin_inbox[:6]) | set(tribute_topics[:4]))
        thin = [t for t in (standing or all_focus) if ledger_topics.get(t, 0) < 2]
        rich = sorted(ledger_topics.items(), key=lambda x: -x[1])[:6]
        title = f"Gather synthesis cycle {cycle_id[-6:]}"
        claim = (
            f"GATHER(used systems): tribute_count={tribute_count}; "
            f"focus={all_focus[:8]}; thin={thin[:8]}; rich={rich[:4]}; "
            f"inbox_gaps={thin_inbox[:4]}."
        )
        self.ledger.set_extra_roles(self.state.role_names() | set(self.registry.active()))
        f = self.ledger.create(
            role=actor if actor in self.state.role_names() else "spark",
            claim=claim,
            evidence_urls=["charter:creator-tribute", f"cycle:{cycle_id}", "system:coverage_index"],
            provenance="growth_gather",
            status="candidate",
            tags=["growth", "gather", "synthesis", "system_use"],
            topic_id="agent-societies",
            title=title,
            meta={
                "kind": "gather_synthesis",
                "thin": thin[:12],
                "rich": rich,
                "focus": all_focus[:12],
                "cycle_id": cycle_id,
                "systems_used": list(g.systems_used),
            },
        )
        g.findings.append(f)
        g.gathered.append(title)
        self.registry.record_outcome(actor, "gather", 0.75 if thin else 0.9)
        self.witness.record(
            cycle_id=cycle_id,
            kind="information_gathered",
            actor=actor,
            summary=f"Gathered via systems: focus={len(all_focus)} thin={len(thin)}.",
            detail={"focus": all_focus[:8], "thin": thin[:8], "title": title},
        )
