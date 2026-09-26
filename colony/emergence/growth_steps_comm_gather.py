"""Growth loop steps - part 2: communicate, commons digests, gather STEM."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from colony.commons import CommonKnowledge
from colony.personas import voice_wrap

ROOT = Path(__file__).resolve().parent.parent.parent
ARTIFACTS_DIR = ROOT / "society" / "artifacts"

DOMAIN_TOPIC = {
    "science": "science-method",
    "history": "history-of-ideas",
    "math": "mathematics-foundations",
}


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
        commons = CommonKnowledge(self.state.data, root=ROOT)

        # Higher-quality replies to unreplied messages
        reply_tracker_open = []
        for m in actionables.get("needs_reply") or []:
            to_role = m.get("to")
            responder = to_role if to_role in roles else self.registry.best_for("communicate")
            if responder not in roles:
                responder = "spark"
            parent_id = m.get("id")
            thin = ", ".join((actionables.get("thin_topics") or [])[:3]) or "n/a"
            digest_snip = commons.digest(limit=2)
            reply_body = (
                f"ACK cycle {cycle_n}: read your message from {m.get('from')}. "
                f"Acting under empire growth will. Thin focus={thin}. "
                f"Commons reuse: {digest_snip[:160]}."
            )
            reply_text = voice_wrap(responder, reply_body, root=ROOT)
            entry = self.bus.post(
                from_role=responder,
                to_role=m.get("from") or "spark",
                channel=m.get("channel") or "bulletin",
                message=reply_text,
                cycle_id=cycle_id,
                tags=["reply", "quality"],
                in_reply_to=parent_id,
            )
            g.replies += 1
            g.communications.append(entry)
            self.registry.agents()[responder]["replies_sent"] = int(
                self.registry.agents()[responder].get("replies_sent") or 0
            ) + 1
            q = float(entry.get("quality") or 0.7)
            self.registry.record_outcome(responder, "communicate", min(0.95, 0.55 + 0.4 * q))
            self._ledger_comm(entry, cycle_id, g)
            self.witness.record(
                cycle_id=cycle_id,
                kind="communication_reply",
                actor=responder,
                summary=f"Reply {responder} -> {entry['to']} (to {parent_id}) q={entry.get('quality')}",
                detail={"id": entry["id"], "in_reply_to": parent_id, "quality": entry.get("quality")},
            )

        thin = actionables.get("thin_topics") or list(tribute_topics)[:4]
        reused = commons.reuse(limit=4)
        if reused and "common_knowledge" in self.workshop.known():
            self.workshop.use("common_knowledge", cycle_id)
            if "common_knowledge" not in g.systems_used:
                g.systems_used.append("common_knowledge")

        # Domain channel posts + commons digest broadcast
        plans = [
            (
                "spark",
                "tribute_keeper",
                "bulletin",
                f"Cycle {cycle_n}: keep paying tribute. Will — {ask[:140]}",
                ["directive"],
                {},
            ),
            (
                self.registry.best_for("communicate"),
                "memory_weaver" if "memory_weaver" in roles else "spark",
                "bulletin",
                f"Herald: weave patterns; watch thin topics {', '.join(thin[:5]) or 'none'}.",
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
            (
                "messenger" if "messenger" in roles else self.registry.best_for("communicate"),
                "all",
                "empire",
                f"Commons digest (candidate): {commons.digest(limit=4)}",
                ["commons_digest", "broadcast"],
                {"commons": True, "size": commons.size()},
            ),
            (
                "naturalist" if "naturalist" in roles else self.registry.best_for("gather"),
                "archivist" if "archivist" in roles else "spark",
                "science",
                f"Science channel: prioritize science-method; thin includes "
                f"{', '.join(t for t in thin if 'science' in t or t == 'science-method') or 'science-method'}.",
                ["gap_alert", "science"],
                {"thin_topics": ["science-method"]},
            ),
            (
                "chronicler" if "chronicler" in roles else self.registry.best_for("gather"),
                "archivist" if "archivist" in roles else "spark",
                "history",
                "History channel: prioritize history-of-ideas for commons reuse.",
                ["gap_alert", "history"],
                {"thin_topics": ["history-of-ideas"]},
            ),
            (
                "geometer" if "geometer" in roles else self.registry.best_for("gather"),
                "archivist" if "archivist" in roles else "spark",
                "math",
                "Math channel: prioritize mathematics-foundations for commons reuse.",
                ["gap_alert", "math"],
                {"thin_topics": ["mathematics-foundations"]},
            ),
            (
                "messenger" if "messenger" in roles else self.registry.best_for("communicate"),
                "archivist" if "archivist" in roles else "spark",
                "software",
                "Software channel: prioritize software-engineering craft for commons.",
                ["gap_alert", "software"],
                {"thin_topics": ["software-engineering"]},
            ),
            (
                "naturalist" if "naturalist" in roles else self.registry.best_for("gather"),
                "archivist" if "archivist" in roles else "spark",
                "nature",
                "Nature channel: prioritize nature-biology-ecology for commons.",
                ["gap_alert", "nature"],
                {"thin_topics": ["nature-biology-ecology"]},
            ),
            (
                "naturalist" if "naturalist" in roles else self.registry.best_for("gather"),
                "memory_weaver" if "memory_weaver" in roles else "spark",
                "life",
                "Life channel: theories of life-and-death stay careful; candidate notes only.",
                ["gap_alert", "life"],
                {"thin_topics": ["life-and-death"]},
            ),
            (
                "surveyor" if "surveyor" in roles else self.registry.best_for("gather"),
                "archivist" if "archivist" in roles else "spark",
                "cosmos",
                "Cosmos channel: prioritize cosmology-universe / our place in the universe.",
                ["gap_alert", "cosmos"],
                {"thin_topics": ["cosmology-universe"]},
            ),
            (
                "improver" if "improver" in roles else self.registry.best_for("improve"),
                "spark",
                "rsi",
                "RSI channel: feed accepted/strong RSI findings into measured skill/genome biases.",
                ["improve_hint", "rsi"],
                {"thin_topics": ["recursive-self-improvement", "self-improving-agents"]},
            ),
        ]
        for fr, to, channel, message, tags, payload in plans:
            fr_r = fr if fr in roles else "spark"
            to_r = to if to in roles or to in ("all", "forum", "*") else "spark"
            voiced = voice_wrap(fr_r, message, root=ROOT)
            entry = self.bus.post(
                from_role=fr_r,
                to_role=to_r,
                channel=channel,
                message=voiced,
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
                summary=f"{fr_r} → {to_r} via {channel}: {message[:140]}",
                detail={"id": entry["id"], "from": fr_r, "to": to_r, "tags": tags, "channel": channel},
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
        commons = CommonKnowledge(self.state.data, root=ROOT)
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

        # Ensure common_knowledge system exists and is used
        if "common_knowledge" not in self.workshop.known():
            self.workshop.ensure("common_knowledge", built_by=actor, cycle_id=cycle_id)
            g.systems_built.append("common_knowledge")
            g.builds.append("common_knowledge")

        thin_inbox = actionables.get("thin_topics") or []
        stem = ["science-method", "history-of-ideas", "mathematics-foundations", "software-engineering", "life-and-death", "nature-biology-ecology", "cosmology-universe"]
        all_focus = sorted(
            set(ranked_topics[:6]) | set(thin_inbox[:6]) | set(tribute_topics[:4]) | set(stem)
        )
        thin = [t for t in (standing or all_focus) if ledger_topics.get(t, 0) < 2]
        rich = sorted(ledger_topics.items(), key=lambda x: -x[1])[:6]

        # Append commons candidates for STEM / RSI thin topics
        domain_for = {
            "science-method": "science",
            "history-of-ideas": "history",
            "mathematics-foundations": "math",
            "software-engineering": "software",
            "life-and-death": "life",
            "nature-biology-ecology": "nature",
            "cosmology-universe": "cosmos",
            "recursive-self-improvement": "rsi",
            "meta-learning": "rsi",
            "self-improving-agents": "rsi",
            "godel-machines": "rsi",
            "darwin-godel-machine": "rsi",
            "reflexion": "rsi",
            "self-refine": "rsi",
            "agent-societies": "empire",
        }
        writer = "archivist" if "archivist" in self.registry.active() else actor
        for topic in (thin[:4] or stem[:2]):
            domain = domain_for.get(topic, "general")
            count = ledger_topics.get(topic, 0)
            entry = commons.append(
                domain=domain,
                title=f"Commons note: {topic}",
                summary=(
                    f"Standing gather on `{topic}` (ledger_count={count}). "
                    f"Candidate synthesis for shared reuse. Not accepted."
                ),
                source_role=writer,
                cycle_id=cycle_id,
                tags=["gather", "commons", topic],
                evidence=[f"cycle:{cycle_id}", f"topic:{topic}"],
            )
            setattr(g, "commons_appended", getattr(g, "commons_appended", 0) + 1)

        # Reuse prior commons into gather claim
        reused = commons.reuse(limit=5)
        self.workshop.use("common_knowledge", cycle_id)
        if "common_knowledge" not in g.systems_used:
            g.systems_used.append("common_knowledge")

        title = f"Gather synthesis cycle {cycle_id[-6:]}"
        claim = (
            f"GATHER(used systems+commons): tribute_count={tribute_count}; "
            f"focus={all_focus[:8]}; thin={thin[:8]}; rich={rich[:4]}; "
            f"inbox_gaps={thin_inbox[:4]}; commons_size={commons.size()}; "
            f"reused={[e.get('title') for e in reused[:3]]}."
        )
        self.ledger.set_extra_roles(self.state.role_names() | set(self.registry.active()))
        f = self.ledger.create(
            role=actor if actor in self.state.role_names() else "spark",
            claim=claim,
            evidence_urls=[
                "charter:creator-tribute",
                f"cycle:{cycle_id}",
                "system:coverage_index",
                "system:common_knowledge",
            ],
            provenance="growth_gather",
            status="candidate",
            tags=["growth", "gather", "synthesis", "system_use", "commons"],
            topic_id="agent-societies",
            title=title,
            meta={
                "kind": "gather_synthesis",
                "thin": thin[:12],
                "rich": rich,
                "focus": all_focus[:12],
                "cycle_id": cycle_id,
                "systems_used": list(g.systems_used),
                "commons_size": commons.size(),
            },
        )
        g.findings.append(f)
        g.gathered.append(title)
        self.registry.record_outcome(actor, "gather", 0.75 if thin else 0.9)
        self.witness.record(
            cycle_id=cycle_id,
            kind="information_gathered",
            actor=actor,
            summary=(
                f"Gathered via systems+commons: focus={len(all_focus)} thin={len(thin)} "
                f"commons={commons.size()}."
            ),
            detail={
                "focus": all_focus[:8],
                "thin": thin[:8],
                "title": title,
                "commons_size": commons.size(),
            },
        )
