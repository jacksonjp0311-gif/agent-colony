"""Growth loop steps — part 3."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from colony.fitness import compute_fitness
from colony.findings_coupling import (
    apply_mutation_bias_to_genome as apply_findings_mutation,
    apply_persona_mandates,
    apply_skill_biases as apply_findings_skill_biases,
    count_citations,
    harvest_behavior_signal,
    hearing_score_proposal,
    persist_coupling as persist_findings_coupling,
    spawn_privilege_threshold,
)
from colony.rsi_coupling import (
    apply_skill_biases,
    harvest_rsi_signal,
    persist_coupling,
    pick_rsi_improvement,
)
ROOT = Path(__file__).resolve().parent.parent.parent
ARTIFACTS_DIR = ROOT / "society" / "artifacts"


class GrowthSteps3:

    def _evolve(
        self,
        cycle_id: str,
        g,
        tribute_topics: list[str],
        tribute_count: int,
        live_ok: int,
        live_fail: int,
    ) -> None:
        ledger_topics: dict[str, int] = {}
        math_prize_hits = 0
        compute_useful_hits = 0
        MATH_PRIZE_TOPICS = {
            "open-math-problems",
            "mathematics-foundations",
            "compute-useful-math",
        }
        COMPUTE_USEFUL_TOPICS = {
            "compute-useful-math",
            "emergent-technology",
            "software-engineering",
        }
        for fnd in self.ledger.all():
            if fnd.topic_id:
                ledger_topics[fnd.topic_id] = ledger_topics.get(fnd.topic_id, 0) + 1
            tags = set(fnd.tags or [])
            tid = fnd.topic_id or ""
            # Prize credit for accepted OR strong sourced candidates
            sourced = any(
                str(u).startswith("http") for u in (fnd.evidence_urls or [])
            )
            if tid in MATH_PRIZE_TOPICS or "math" in tags or "prize" in tags:
                if fnd.status == "accepted" or (fnd.status == "candidate" and sourced):
                    math_prize_hits += 1
            if tid in COMPUTE_USEFUL_TOPICS or "compute-useful-math" in tags or "FFT" in tags:
                if fnd.status == "accepted" or (fnd.status == "candidate" and sourced):
                    compute_useful_hits += 1
        from colony.commons import CommonKnowledge

        commons_size = CommonKnowledge(self.state.data).size()
        citation_reuse_hits = int(getattr(g, "citation_hits", 0) or 0)
        # Also scan recent cycle communications for citation reuse (math prize behavior)
        fsig_pre = harvest_behavior_signal(self.ledger.all())
        for entry in (g.communications or [])[-12:]:
            citation_reuse_hits += count_citations(str(entry.get("message") or ""), fsig_pre)
        metrics = compute_fitness(
            tribute_count=tribute_count,
            tribute_topics=tribute_topics,
            live_ok=live_ok,
            live_fail=live_fail,
            standing_topics=self.state.standing_topics(),
            ledger_topic_counts=ledger_topics,
            workshop=self.workshop,
            bus_reply_rate=self.bus.reply_rate(),
            systems_used_this_cycle=list(dict.fromkeys(g.systems_used)),
            reply_quality=self.bus.reply_quality(),
            commons_size=commons_size,
            math_prize_hits=math_prize_hits,
            compute_useful_hits=compute_useful_hits,
            citation_reuse_hits=citation_reuse_hits,
        )
        g.citation_hits = citation_reuse_hits  # type: ignore[attr-defined]
        metrics_with_id = {**metrics, "cycle_id": cycle_id}
        # Lift 1 bus metrics into fitness detail (before record)
        try:
            ibm = self.bus.inner_bus_metrics()
            metrics["peer_cite_rate"] = ibm.get("peer_cite_rate", 0.0)
            metrics["action_changed_from_message"] = ibm.get("action_changed_from_message", 0.0)
            self.state.data.setdefault("bus_metrics_latest", ibm)
        except Exception:
            pass
        self.evo.record_fitness(cycle_id, metrics)
        # Close prior proposals with after_metrics
        closed = self.evo.close_open_proposals(cycle_id, metrics)
        for p in closed:
            self.witness.record(
                cycle_id=cycle_id,
                kind="improvement_measured",
                actor="improver" if "improver" in self.registry.active() else "spark",
                summary=(
                    f"Measured proposal `{p.get('title')}` delta_agg={p.get('delta_aggregate')} "
                    "(still candidate until human authorize)."
                ),
                detail={
                    "id": p.get("id"),
                    "before": p.get("before_metrics"),
                    "after": p.get("after_metrics"),
                    "delta_aggregate": p.get("delta_aggregate"),
                    "status": p.get("status"),
                },
            )
        g.skill_updates = self.evo.update_skills_from_fitness(metrics_with_id)
        # RSI → agent coupling (accepted/strong findings → skill/genome biases)
        rsi_signal = harvest_rsi_signal(self.ledger.all())
        rsi_updates = apply_skill_biases(self.registry, rsi_signal)
        g.skill_updates.update({f"rsi:{k}": v for k, v in rsi_updates.items()})
        persist_coupling(rsi_signal, cycle_id=cycle_id, root=ROOT)
        if "rsi_coupling" not in self.workshop.known():
            self.workshop.ensure("rsi_coupling", built_by="improver", cycle_id=cycle_id)
            g.systems_built.append("rsi_coupling")
        else:
            self.workshop.use("rsi_coupling", cycle_id)
            if "rsi_coupling" not in g.systems_used:
                g.systems_used.append("rsi_coupling")
        self.state.data["rsi_coupling"] = {
            "strength": rsi_signal.get("strength"),
            "accepted_count": rsi_signal.get("accepted_count"),
            "strong_candidate_count": rsi_signal.get("strong_candidate_count"),
            "ts": rsi_signal.get("ts"),
        }
        # Stash for improvement picker
        g.rsi_signal = rsi_signal  # type: ignore[attr-defined]
        self.witness.record(
            cycle_id=cycle_id,
            kind="rsi_coupling_applied",
            actor="improver" if "improver" in self.registry.active() else "spark",
            summary=(
                f"RSI→agent coupling strength={rsi_signal.get('strength')} "
                f"accepted={rsi_signal.get('accepted_count')} "
                f"strong={rsi_signal.get('strong_candidate_count')} (measured, not AGI)."
            ),
            detail=rsi_signal,
        )
        # Findings → behavior coupling (math/compute/RSI accepted → choices change)
        behavior = harvest_behavior_signal(self.ledger.all())
        beh_updates = apply_findings_skill_biases(self.registry, behavior)
        g.skill_updates.update({f"findings:{k}": v for k, v in beh_updates.items()})
        persist_findings_coupling(behavior, cycle_id=cycle_id, root=ROOT)
        if "findings_coupling" not in self.workshop.known():
            self.workshop.ensure("findings_coupling", built_by="improver", cycle_id=cycle_id)
            g.systems_built.append("findings_coupling")
        else:
            self.workshop.use("findings_coupling", cycle_id)
            if "findings_coupling" not in g.systems_used:
                g.systems_used.append("findings_coupling")
        # Refresh skill_router snapshot after findings biases
        if "skill_router" in self.workshop.known():
            routes = {
                skill: self.registry.best_for(skill)
                for skill in ("tribute", "build", "communicate", "gather", "improve", "emergence")
            }
            self.workshop.write_json(
                "skill_router",
                {"routes": routes, "skills_snapshot": self.registry.snapshot_skills(),
                 "findings_bias": behavior.get("skill_bias"),
                 "behavior_strength": behavior.get("strength")},
                cycle_id=cycle_id,
            )
        persona_updated = apply_persona_mandates(self.registry.agents(), behavior, root=ROOT)
        # Spawn privilege from citation reuse of accepted compute-useful findings
        threshold = spawn_privilege_threshold(behavior, citation_reuse_hits)
        self.state.data["spawn_privilege"] = {
            "threshold": threshold,
            "citations": citation_reuse_hits,
            "strength": behavior.get("strength"),
            "ts": behavior.get("ts"),
        }
        self.state.data["findings_coupling"] = {
            "strength": behavior.get("strength"),
            "accepted_math": behavior.get("accepted_math"),
            "accepted_compute": behavior.get("accepted_compute"),
            "accepted_rsi": behavior.get("accepted_rsi"),
            "citation_hits": citation_reuse_hits,
            "persona_updated": len(persona_updated),
            "ts": behavior.get("ts"),
        }
        g.behavior_signal = behavior  # type: ignore[attr-defined]
        self.witness.record(
            cycle_id=cycle_id,
            kind="findings_behavior_coupled",
            actor="improver" if "improver" in self.registry.active() else "spark",
            summary=(
                f"Findings→behavior strength={behavior.get('strength')} "
                f"math={behavior.get('accepted_math')} compute={behavior.get('accepted_compute')} "
                f"rsi={behavior.get('accepted_rsi')} cites={citation_reuse_hits} "
                f"spawn_floor={threshold} personas={len(persona_updated)} (not museum)."
            ),
            detail=behavior,
        )
        g.fitness = metrics
        g.spawn_signals = self.evo.maybe_spawn(cycle_id, metrics)
        # Child spawn with genomes (signal; spark enacts role)
        child = self.evo.maybe_spawn_child(cycle_id, metrics)
        if child:
            # Attach RSI mutation bias to child genome (soft)
            from colony.rsi_coupling import apply_mutation_bias_to_genome
            from colony.genomes import persist_genome
            sig = getattr(g, "rsi_signal", None) or harvest_rsi_signal(self.ledger.all())
            child["genome"] = apply_mutation_bias_to_genome(child["genome"], sig)
            beh = getattr(g, "behavior_signal", None) or harvest_behavior_signal(self.ledger.all())
            child["genome"] = apply_findings_mutation(child["genome"], beh)
            persist_genome(child["genome"])
            g.spawn_signals.append(child["role"])
            g.child_spawn = child  # type: ignore[attr-defined]
            self.witness.record(
                cycle_id=cycle_id,
                kind="child_spawn_signal",
                actor="spark",
                summary=(
                    f"Child spawn signal `{child['role']}` from parents {child['parents']} "
                    f"gen={child['genome'].get('generation')} mutated={child['genome'].get('mutated_keys')}."
                ),
                detail=child,
            )
        g.retired = self.evo.maybe_retire(cycle_id)
        self.witness.record(
            cycle_id=cycle_id,
            kind="fitness_recorded",
            actor="spark",
            summary=f"Fitness aggregate={metrics['aggregate']}",
            detail={"fitness": metrics, "skill_updates": g.skill_updates},
        )

    def _attempt_improvement(self, cycle_id: str, cycle_n: int, g) -> None:
        metrics = g.fitness or {
            "tribute_quality": 0,
            "gather_coverage": 0,
            "build_reuse": 0,
            "comm_reply_rate": 0,
            "aggregate": 0,
        }
        rsi_pick = pick_rsi_improvement(getattr(g, "rsi_signal", None) or {}, metrics)
        if rsi_pick:
            title, hypothesis, action = rsi_pick
        else:
            title, hypothesis, action = self.evo.pick_improvement(metrics)
        # Avoid exact duplicate titles in a row
        prior = {p.get("title") for p in (self.state.data.get("improvement_proposals") or [])[-3:]}
        if title in prior:
            title = f"{title} (cycle {cycle_n})"
        # Hearing gate: weak improve proposals get REJECTED (status rejected + witness)
        behavior = getattr(g, "behavior_signal", None) or harvest_behavior_signal(self.ledger.all())
        cited = count_citations(f"{title} {hypothesis}", behavior)
        # RSI picks that cite coupling get a citation bonus
        if action.startswith("rsi_coupling"):
            cited = max(cited, 1)
        verdict, rationale = hearing_score_proposal(
            title=title,
            hypothesis=hypothesis,
            evidence_urls=["charter:civilization-freedom", f"cycle:{cycle_id}", "fitness:before", "system:findings_coupling"],
            cited=cited,
            prior_titles=prior,
            fitness_aggregate=float(metrics.get("aggregate") or 0),
        )
        prop = self.evo.propose_improvement(
            cycle_id=cycle_id,
            metrics=metrics,
            title=title,
            hypothesis=hypothesis,
            action=action,
        )
        prop["hearing_verdict"] = verdict
        prop["hearing_rationale"] = rationale
        if verdict == "reject":
            prop["status"] = "rejected"
            ledger_status = "rejected"
            tags = ["growth", "improve", "self-improvement", "hearing", "rejected"]
        elif verdict == "defer":
            prop["status"] = "deferred"
            ledger_status = "unknown"
            tags = ["growth", "improve", "self-improvement", "hearing", "deferred"]
        else:
            prop["status"] = "candidate"
            ledger_status = "candidate"
            tags = ["growth", "improve", "self-improvement", "candidate", "hearing", "accept_candidate"]
        # Apply soft action only when hearing lets it survive
        if verdict == "accept_candidate" and action.startswith("skill_boost:"):
            target = action.split(":", 1)[1]
            if "." in target:
                role, skill = target.split(".", 1)
                if role in self.registry.active():
                    self.registry.record_outcome(role, skill, 0.9)
        actor = prop["attempted_by"]
        self.ledger.set_extra_roles(self.state.role_names() | set(self.registry.active()))
        f = self.ledger.create(
            role=actor if actor in self.state.role_names() else "spark",
            claim=(
                f"IMPROVE({verdict}): {title} — {hypothesis} | action={action} | "
                f"before={metrics}. Hearing: {rationale}. Durable accepted needs human authorize."
            ),
            evidence_urls=["charter:civilization-freedom", f"cycle:{cycle_id}", "fitness:before", "institution:Hearing Chamber"],
            provenance="growth_improve",
            status=ledger_status,
            tags=tags,
            notes=f"Hearing verdict={verdict}. {rationale}",
            topic_id="agent-societies",
            title=f"Improve ({verdict}): {title}",
            meta={
                "kind": "improvement_proposal",
                "proposal_id": prop["id"],
                "before_metrics": metrics,
                "action": action,
                "cycle_id": cycle_id,
                "status": ledger_status,
                "hearing_verdict": verdict,
                "hearing_rationale": rationale,
            },
        )
        g.findings.append(f)
        if verdict != "reject":
            g.improvements.append(title)
        self.witness.record(
            cycle_id=cycle_id,
            kind=f"hearing_{verdict}",
            actor="legislator" if "legislator" in self.registry.active() else actor,
            summary=f"Hearing on improve proposal: {verdict} — {title}: {rationale}",
            detail={"verdict": verdict, "title": title, "proposal_id": prop["id"], "finding_id": f.id},
        )
        # Append logbook
        logbook = ARTIFACTS_DIR / "improvement_logbook.md"
        if logbook.is_file():
            with logbook.open("a", encoding="utf-8") as fh:
                fh.write(
                    f"\n- **{title}** (`{cycle_id}`): {hypothesis} "
                    f"| before_agg={metrics.get('aggregate')} | status=candidate\n"
                )
        self.witness.record(
            cycle_id=cycle_id,
            kind="improvement_attempted",
            actor=actor,
            summary=f"Improvement proposed (candidate): {title}",
            detail={
                "title": title,
                "hypothesis": hypothesis,
                "action": action,
                "before_metrics": metrics,
                "status": "candidate",
            },
        )
        self.registry.record_outcome(actor, "improve", 0.7)

    # --- helpers ---------------------------------------------------------


    def _debate_then_propose(self, cycle_id: str, cycle_n: int, g) -> None:
        """Hearing Chamber: debate → propose → verdict (accept_candidate | reject | defer).

        Only strong proposals survive as candidates. Weak ones get status=rejected
        with witness. Durable ledger `accepted` still needs human authorize.
        Not AGI — engineered role postures + measured findings coupling.
        """
        from colony.personas import voice_wrap

        roles = set(self.registry.active().keys())
        behavior = getattr(g, "behavior_signal", None) or harvest_behavior_signal(self.ledger.all())
        cite_targets = behavior.get("citation_targets") or []
        cite_snip = ", ".join(
            f"`{c.get('id')}` {(c.get('title') or '')[:36]}" for c in cite_targets[:3]
        ) or "(no accepted citation targets yet)"

        # Recent sourced findings worth debating (+ prefer citation targets)
        recent = []
        cite_ids = {c.get("id") for c in cite_targets}
        for fnd in self.ledger.all()[-60:]:
            urls = fnd.evidence_urls or []
            if fnd.id in cite_ids or fnd.status == "accepted":
                if fnd.topic_id in (
                    "open-math-problems", "compute-useful-math", "emergent-technology",
                    "mathematics-foundations", "software-engineering",
                ) or "math" in (fnd.tags or []) or "compute-useful-math" in (fnd.tags or []):
                    recent.append(fnd)
                    continue
            if not any(str(u).startswith("http") for u in urls):
                continue
            if fnd.status not in ("candidate", "accepted"):
                continue
            recent.append(fnd)
        # de-dupe by id, keep last 4
        seen = set()
        uniq = []
        for fnd in recent:
            if fnd.id in seen:
                continue
            seen.add(fnd.id)
            uniq.append(fnd)
        recent = uniq[-4:]
        if not recent:
            thin = (g.actionables or {}).get("thin_topics") or ["open-math-problems"]
            claim_snip = f"thin coverage on {', '.join(thin[:4])}"
        else:
            claim_snip = "; ".join(
                f"`{(f.title or f.claim)[:48]}`[{f.status}]" for f in recent[:3]
            )

        debaters = [
            ("geometer" if "geometer" in roles else self.registry.best_for("gather"), "math"),
            ("pathfinder" if "pathfinder" in roles else self.registry.best_for("gather"), "forum"),
            ("improver" if "improver" in roles else self.registry.best_for("improve"), "rsi"),
            ("legislator" if "legislator" in roles else "spark", "forum"),
        ]
        # SPARK: multi-hop reply chain — hop0 is root; later hops in_reply_to prior
        # so reply_rate load-bears (no fake padding / shout-into-void forum roots).
        debate_ids = []
        prev_id = None
        for hop_i, (fr, channel) in enumerate(debaters):
            fr_r = fr if fr in roles else "spark"
            body = (
                f"Hearing Chamber debate hop {hop_i} cycle {cycle_n}: weigh {claim_snip}. "
                f"Cite accepted compute-useful findings: {cite_snip}. "
                + (f"ACK prior `{prev_id}`. " if prev_id else "")
                + f"Ask: enables useful computation? Verdict path: accept_candidate|reject|defer. "
                f"No AGI claims. NEXT ACTION → hearing_weigh."
            )
            voiced = voice_wrap(fr_r, body, root=ROOT)
            # Count citations in debate for math prize
            hits = count_citations(voiced, behavior)
            if hasattr(g, "citation_hits"):
                g.citation_hits = int(getattr(g, "citation_hits", 0) or 0) + hits
            entry = self.bus.post(
                from_role=fr_r,
                to_role="forum",
                channel=channel,
                message=voiced,
                cycle_id=cycle_id,
                tags=["debate", "hearing", "committee", "colloquium", "cites_accepted", "peer_cite"]
                + (["action_changed"] if prev_id else ["propose"]),
                in_reply_to=prev_id,
                payload={
                    "kind": "debate",
                    "hop": hop_i,
                    "findings": [f.id for f in recent],
                    "citation_hits": hits,
                    "parent": prev_id,
                },
            )
            if prev_id:
                try:
                    self.bus.record_peer_cite(cited=True)
                    self.bus.record_action_changed(
                        changed=True,
                        detail={
                            "next_action_before": "hearing_open",
                            "next_action_after": "hearing_weigh",
                            "reason": f"hearing hop {hop_i} replies to {prev_id}",
                            "cycle_id": cycle_id,
                        },
                    )
                except Exception:
                    pass
            g.communications.append(entry)
            debate_ids.append(entry["id"])
            prev_id = entry["id"]
            self._ledger_comm(entry, cycle_id, g)
            self.witness.record(
                cycle_id=cycle_id,
                kind="debate",
                actor=fr_r,
                summary=f"Debate/{channel} hop={hop_i}: {body[:140]}",
                detail={"id": entry["id"], "channel": channel, "hop": hop_i, "findings": [f.id for f in recent], "citation_hits": hits},
            )

        # Propose after debate — then Hearing Chamber verdict
        proposer = "improver" if "improver" in roles else "spark"
        judge = "legislator" if "legislator" in roles else "spark"
        metrics = g.fitness or {"aggregate": 0}
        agg = float(metrics.get("aggregate") or 0)

        # Build one strong + optionally probe a weak duplicate for reject path
        proposals_spec = []
        # Strong proposal: cites accepted findings
        strong_title = "Deepen compute-useful math from accepted findings after hearing"
        strong_hyp = (
            f"Reuse accepted citation targets ({cite_snip}) to focus gather/build on "
            f"open-math-problems and compute-useful-math; raise citation_reuse fitness."
        )
        strong_action = "mandate:cite_accepted_compute_findings"
        proposals_spec.append(
            {
                "title": strong_title,
                "hypothesis": strong_hyp,
                "action": strong_action,
                "evidence": [
                    "institution:Hearing Chamber",
                    "institution:Math Prize Desk",
                    "institution:Committee of Inquiry",
                    f"cycle:{cycle_id}",
                    "system:findings_coupling",
                ] + [f"ledger:{c.get('id')}" for c in cite_targets[:3] if c.get("id")]
                + [f"msg:{i}" for i in debate_ids[:2]],
                "cited": count_citations(strong_hyp + cite_snip, behavior) + (1 if cite_targets else 0),
            }
        )
        # Weak duplicate probe (should be REJECTED by hearing when already proposed recently)
        prior = {p.get("title") for p in (self.state.data.get("improvement_proposals") or [])[-8:]}
        weak_title = "Math/compute prize track after colloquium debate"
        if weak_title in prior or any("Math/compute prize track" in str(t) for t in prior):
            proposals_spec.append(
                {
                    "title": weak_title,
                    "hypothesis": "same as before",
                    "action": "mandate:debate_then_math_prize",
                    "evidence": [f"cycle:{cycle_id}"],
                    "cited": 0,
                }
            )

        g.hearing_verdicts = []  # type: ignore[attr-defined]
        for spec in proposals_spec:
            title = spec["title"]
            hypothesis = spec["hypothesis"]
            action = spec["action"]
            cited = int(spec.get("cited") or 0)
            verdict, rationale = hearing_score_proposal(
                title=title,
                hypothesis=hypothesis,
                evidence_urls=spec.get("evidence"),
                cited=cited,
                prior_titles=prior,
                fitness_aggregate=agg,
            )
            # Record proposal in evo board only if not hard-reject before create? Always create then stamp status.
            prop = self.evo.propose_improvement(
                cycle_id=cycle_id,
                metrics=metrics,
                title=title,
                hypothesis=hypothesis,
                action=action,
            )
            # Map hearing verdict → proposal + ledger status
            if verdict == "reject":
                prop["status"] = "rejected"
                prop["hearing_verdict"] = "reject"
                prop["hearing_rationale"] = rationale
                ledger_status = "rejected"
                tags = ["growth", "debate", "propose", "hearing", "rejected", "math_prize"]
            elif verdict == "accept_candidate":
                prop["status"] = "candidate"
                prop["hearing_verdict"] = "accept_candidate"
                prop["hearing_rationale"] = rationale
                ledger_status = "candidate"
                tags = ["growth", "debate", "propose", "hearing", "accept_candidate", "math_prize", "cites_accepted"]
            else:
                prop["status"] = "deferred"
                prop["hearing_verdict"] = "defer"
                prop["hearing_rationale"] = rationale
                ledger_status = "unknown"
                tags = ["growth", "debate", "propose", "hearing", "deferred"]

            self.ledger.set_extra_roles(self.state.role_names() | set(self.registry.active()))
            f = self.ledger.create(
                role=proposer if proposer in self.state.role_names() else "spark",
                claim=(
                    f"HEARING({verdict}): {title} — {hypothesis} | "
                    f"debates={debate_ids[:4]} | cited={cited} | {rationale}. "
                    f"Durable accepted still needs human authorize."
                ),
                evidence_urls=list(spec.get("evidence") or []),
                provenance="growth_hearing",
                status=ledger_status,
                tags=tags,
                notes=f"Hearing Chamber verdict={verdict}. {rationale}",
                topic_id="compute-useful-math",
                title=f"Hearing {verdict}: {title}",
                meta={
                    "kind": "hearing_verdict",
                    "verdict": verdict,
                    "proposal_id": prop.get("id"),
                    "debate_ids": debate_ids,
                    "cycle_id": cycle_id,
                    "rationale": rationale,
                    "cited": cited,
                },
            )
            g.findings.append(f)
            if verdict != "reject":
                g.improvements.append(title)
            g.hearing_verdicts.append(  # type: ignore[attr-defined]
                {"title": title, "verdict": verdict, "rationale": rationale, "proposal_id": prop.get("id"), "finding_id": f.id}
            )
            self.witness.record(
                cycle_id=cycle_id,
                kind=f"hearing_{verdict}",
                actor=judge,
                summary=f"Hearing Chamber {verdict}: {title} — {rationale}",
                detail={
                    "verdict": verdict,
                    "title": title,
                    "proposal_id": prop.get("id"),
                    "finding_id": f.id,
                    "rationale": rationale,
                    "debate_ids": debate_ids,
                    "cited": cited,
                },
            )
            # Judge posts verdict on forum
            vbody = (
                f"Hearing Chamber verdict={verdict} on `{title}`: {rationale}. "
                f"Only strong survive. Ceiling: human authorize for durable accepted."
            )
            ventry = self.bus.post(
                from_role=judge if judge in roles else "spark",
                to_role="forum",
                channel="forum",
                message=voice_wrap(judge if judge in roles else "spark", vbody, root=ROOT),
                cycle_id=cycle_id,
                tags=["hearing", "verdict", verdict],
                payload={"kind": "hearing_verdict", "verdict": verdict, "proposal_id": prop.get("id")},
            )
            g.communications.append(ventry)
            self._ledger_comm(ventry, cycle_id, g)
            if verdict == "accept_candidate":
                self.registry.record_outcome(proposer, "improve", 0.78)
            elif verdict == "reject":
                self.registry.record_outcome(judge, "improve", 0.7)
            else:
                self.registry.record_outcome(proposer, "improve", 0.55)
            prior.add(title)

        # Academy soft digest citing accepted findings
        academy_actor = "archivist" if "archivist" in roles else "spark"
        note = (
            f"Academy digest cycle {cycle_n}: study {claim_snip}. "
            f"Cite accepted: {cite_snip}. Prize desk watches citation_reuse."
        )
        entry = self.bus.post(
            from_role=academy_actor,
            to_role="all",
            channel="math",
            message=voice_wrap(academy_actor, note, root=ROOT),
            cycle_id=cycle_id,
            tags=["academy", "education", "digest", "cites_accepted"],
            payload={"kind": "academy_digest", "citations": [c.get("id") for c in cite_targets[:4]]},
        )
        g.communications.append(entry)
        self._ledger_comm(entry, cycle_id, g)
        hits = count_citations(note, behavior)
        if hasattr(g, "citation_hits"):
            g.citation_hits = int(getattr(g, "citation_hits", 0) or 0) + hits

    def _ledger_build(
        self, role: str, name: str, path: str, cycle_id: str, g
    ) -> None:
        self.ledger.set_extra_roles(self.state.role_names() | set(self.registry.active()))
        f = self.ledger.create(
            role=role if role in self.state.role_names() else "spark",
            claim=f"BUILD: '{name}' at {path} (usable={path.startswith('society/systems')})",
            evidence_urls=[f"artifact:{path}", "charter:civilization-freedom"],
            provenance="growth_build",
            status="candidate",
            tags=["growth", "build", "system" if "systems/" in path else "artifact"],
            topic_id="agent-societies",
            title=f"Built: {name}",
            meta={"kind": "artifact_built", "name": name, "path": path, "cycle_id": cycle_id},
        )
        g.findings.append(f)

    def _ledger_comm(self, entry: dict[str, Any], cycle_id: str, g) -> None:
        self.ledger.set_extra_roles(self.state.role_names() | set(self.registry.active()))
        fr = entry["from"]
        f = self.ledger.create(
            role=fr if fr in self.state.role_names() else "spark",
            claim=(
                f"COMMUNICATE [{entry['channel']}] {entry['from']} → {entry['to']}: "
                f"{entry['message']}"
            ),
            evidence_urls=["institution:Society Bulletin", f"msg:{entry['id']}"],
            provenance="growth_communicate",
            status="candidate",
            tags=["growth", "communicate", entry.get("channel") or "bulletin"],
            topic_id="agent-societies",
            title=f"Message: {entry['from']} → {entry['to']}",
            meta={
                "kind": "communication",
                "id": entry["id"],
                "from": entry["from"],
                "to": entry["to"],
                "in_reply_to": entry.get("in_reply_to"),
                "cycle_id": cycle_id,
            },
        )
        g.findings.append(f)



    def _government_and_census(self, cycle_id: str, g) -> None:
        from colony.genomes import snapshot_population
        from colony.government import Government

        gov = Government(self.state.data)
        born = gov.ensure_institutions(self.state.add_institution)
        for name in born:
            self.witness.record(
                cycle_id=cycle_id,
                kind="institution_born",
                actor="spark",
                summary=f"Government institution `{name}` established (soft scaffold).",
                detail={"name": name, "kind": "government"},
            )
            if name not in g.builds:
                # track via growth improvements list style
                pass

        # Census each cycle
        snap = snapshot_population(self.registry.agents())
        census = gov.record_census(cycle_id=cycle_id, snapshot=snap)
        self.witness.record(
            cycle_id=cycle_id,
            kind="census_recorded",
            actor="legislator" if "legislator" in self.registry.active() else "spark",
            summary=(
                f"Census: active={census.get('active_count')} "
                f"genomes={census.get('genome_count')} generations={census.get('generations')}."
            ),
            detail=census,
        )

        # Occasional law proposal (candidate) when legislator or spark
        proposals = (self.state.data.get("government") or {}).get("proposals") or []
        recent_titles = {p.get("title") for p in proposals[-3:]}
        title = "Norm: commons digests stay candidate until authorize"
        if title not in recent_titles and (int(self.state.data.get("cycle_count") or 0) % 2 == 0):
            actor = "legislator" if "legislator" in self.registry.active() else "spark"
            prop = gov.propose_law(
                title=title,
                text=(
                    "Shared common_knowledge entries and Chamber law drafts remain "
                    "candidate until the human authorizes durable acceptance. "
                    "Soft norms may guide practice without claiming accepted truth."
                ),
                proposed_by=actor,
                cycle_id=cycle_id,
                tags=["commons", "authorize", "empire"],
            )
            g.gov_proposals = gov.proposal_count()
            self.ledger.set_extra_roles(self.state.role_names() | set(self.registry.active()))
            f = self.ledger.create(
                role=actor if actor in self.state.role_names() else "spark",
                claim=f"LAW(candidate): {prop['title']} — {prop['text'][:200]}",
                evidence_urls=["institution:Chamber of Laws", f"cycle:{cycle_id}"],
                provenance="government",
                status="candidate",
                tags=["government", "law", "candidate"],
                topic_id="agent-societies",
                title=f"Law proposal: {prop['title']}",
                meta={"kind": "law_proposal", "id": prop["id"], "cycle_id": cycle_id, "status": "candidate"},
            )
            g.findings.append(f)
            self.witness.record(
                cycle_id=cycle_id,
                kind="law_proposed",
                actor=actor,
                summary=f"Chamber law proposal `{prop['id']}` (candidate): {prop['title']}",
                detail=prop,
            )
            self.registry.record_outcome(actor, "improve", 0.65)
        else:
            g.gov_proposals = gov.proposal_count()
