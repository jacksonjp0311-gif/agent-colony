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
            # Lift 1: reply cites prior turn + peer findings (kill shout-into-void)
            peer_fids = []
            try:
                for fnd in self.ledger.all()[-12:]:
                    if getattr(fnd, "status", "") in ("accepted", "candidate") and getattr(fnd, "id", None):
                        peer_fids.append(fnd.id)
            except Exception:
                peer_fids = []
            cite_fid = peer_fids[-1] if peer_fids else ""
            parent_snip = ((m.get("message") or "")[:80]).replace("\n", " ")
            reply_body = (
                f"ACK cycle {cycle_n}: read prior turn `{parent_id}` from {m.get('from')}. "
                f"Citing peer finding `{cite_fid or 'none'}` and your words: '{parent_snip}'. "
                f"NEXT ACTION changed: thin focus={thin}. "
                f"Commons reuse: {digest_snip[:120]}."
            )
            reply_text = voice_wrap(responder, reply_body, root=ROOT)
            entry = self.bus.post(
                from_role=responder,
                to_role=m.get("from") or "spark",
                channel=m.get("channel") or "bulletin",
                message=reply_text,
                cycle_id=cycle_id,
                tags=["reply", "quality", "peer_cite"],
                in_reply_to=parent_id,
                payload={"cites_message": parent_id, "cites_finding": cite_fid},
            )
            cited = self.bus.message_cites_peer(
                reply_text, parent=m, peer_findings=peer_fids[-3:]
            )
            self.bus.record_peer_cite(cited=cited)
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
                summary=(
                    f"Reply {responder} -> {entry['to']} (to {parent_id}) "
                    f"q={entry.get('quality')} peer_cite={cited}"
                ),
                detail={
                    "id": entry["id"],
                    "in_reply_to": parent_id,
                    "quality": entry.get("quality"),
                    "peer_cite": cited,
                    "cites_finding": cite_fid,
                },
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
                "Math channel: prioritize mathematics-foundations, open-math-problems, "
                "compute-useful-math; cite accepted FFT/autodiff/open-problem findings.",
                ["gap_alert", "math", "cites_accepted"],
                {"thin_topics": ["mathematics-foundations", "open-math-problems", "compute-useful-math"]},
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
                "Nature channel: prioritize nature-biology-ecology for commons reuse.",
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
        stem = ["science-method", "history-of-ideas", "mathematics-foundations", "software-engineering", "life-and-death", "nature-biology-ecology", "cosmology-universe", "open-math-problems", "compute-useful-math", "emergent-technology"]
        # Behavior coupling: accepted findings drive focus order
        from colony.findings_coupling import harvest_behavior_signal, load_signal, count_citations
        fsig = load_signal(ROOT) or harvest_behavior_signal(self.ledger.all())
        boost_topics = [b.get("topic") for b in (fsig.get("topic_boosts") or []) if b.get("topic")]
        all_focus = list(dict.fromkeys(
            list(boost_topics[:6]) + list(ranked_topics[:6]) + list(thin_inbox[:4]) + list(tribute_topics[:4]) + stem
        ))
        thin = [t for t in (standing or all_focus) if ledger_topics.get(t, 0) < 2]
        # Prefer boosted topics even if not thin (deepen accepted lines)
        for bt in boost_topics[:4]:
            if bt not in thin:
                thin.insert(0, bt)
        thin = list(dict.fromkeys(thin))
        rich = sorted(ledger_topics.items(), key=lambda x: -x[1])[:6]
        cite_targets = fsig.get("citation_targets") or []
        cite_ids = [c.get("id") for c in cite_targets[:4] if c.get("id")]
        g.findings_signal = fsig  # type: ignore[attr-defined]
        g.citation_hits = 0  # type: ignore[attr-defined]

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
            "open-math-problems": "math",
            "compute-useful-math": "math",
            "emergent-technology": "software",
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
        cite_line = ", ".join(cite_ids) if cite_ids else "none"
        claim = (
            f"GATHER(used systems+commons+accepted findings): tribute_count={tribute_count}; "
            f"focus={all_focus[:8]}; thin={thin[:8]}; rich={rich[:4]}; "
            f"inbox_gaps={thin_inbox[:4]}; commons_size={commons.size()}; "
            f"reused={[e.get('title') for e in reused[:3]]}; "
            f"cites_accepted=[{cite_line}]; boost={boost_topics[:4]}."
        )
        # Math prize: count citation reuse of accepted compute/math findings
        g.citation_hits = count_citations(claim, fsig)  # type: ignore[attr-defined]
        self.ledger.set_extra_roles(self.state.role_names() | set(self.registry.active()))
        f = self.ledger.create(
            role=actor if actor in self.state.role_names() else "spark",
            claim=claim,
            evidence_urls=[
                "charter:creator-tribute",
                f"cycle:{cycle_id}",
                "system:coverage_index",
                "system:common_knowledge",
                "system:findings_coupling",
            ] + [f"ledger:{cid}" for cid in cite_ids[:3]],
            provenance="growth_gather",
            status="candidate",
            tags=["growth", "gather", "synthesis", "system_use", "commons", "cites_accepted"],
            topic_id=(boost_topics[0] if boost_topics else "agent-societies"),
            title=title,
            meta={
                "kind": "gather_synthesis",
                "thin": thin[:12],
                "rich": rich,
                "focus": all_focus[:12],
                "cycle_id": cycle_id,
                "systems_used": list(g.systems_used),
                "commons_size": commons.size(),
                "citation_hits": g.citation_hits,
                "boost_topics": boost_topics[:8],
            },
        )
        # Research paper gather (OpenAlex/arXiv or offline cache)
        try:
            from colony.research_gather import run_from_tribute, cached_count
            # Tribute already live-fetches; gather reuses cache unless empty
            live = cached_count() == 0
            rg = run_from_tribute(ledger=self.ledger, cycle_id=cycle_id, live=live)
            if rg.findings_created:
                g.gathered.append(f"research_papers:{len(rg.findings_created)}")
                self.witness.record(
                    cycle_id=cycle_id,
                    kind="research_gather",
                    actor=actor,
                    summary=(
                        f"Research gather: {len(rg.findings_created)} papers "
                        f"(live_ok={rg.live_ok} offline={rg.used_offline})"
                    ),
                    detail={
                        "count": len(rg.findings_created),
                        "live_ok": rg.live_ok,
                        "live_fail": rg.live_fail,
                        "used_offline": rg.used_offline,
                        "titles": [h.title[:80] for h in rg.hits[:6]],
                    },
                )
        except Exception as exc:  # noqa: BLE001
            self.witness.record(
                cycle_id=cycle_id,
                kind="research_gather_error",
                actor=actor,
                summary=f"Research gather skipped: {exc}",
                detail={"error": str(exc)},
            )

        g.findings.append(f)
        g.gathered.append(title)
        cite_bonus = min(0.15, 0.05 * int(getattr(g, "citation_hits", 0) or 0))
        self.registry.record_outcome(actor, "gather", min(0.98, (0.75 if thin else 0.9) + cite_bonus))
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
