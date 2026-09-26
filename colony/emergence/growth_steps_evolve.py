"""Growth loop steps — part 3."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from colony.fitness import compute_fitness
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
        for fnd in self.ledger.all():
            if fnd.topic_id:
                ledger_topics[fnd.topic_id] = ledger_topics.get(fnd.topic_id, 0) + 1
        from colony.commons import CommonKnowledge

        commons_size = CommonKnowledge(self.state.data).size()
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
        )
        metrics_with_id = {**metrics, "cycle_id": cycle_id}
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
        prop = self.evo.propose_improvement(
            cycle_id=cycle_id,
            metrics=metrics,
            title=title,
            hypothesis=hypothesis,
            action=action,
        )
        # Apply soft action immediately when it is a skill boost (still candidate knowledge)
        if action.startswith("skill_boost:"):
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
                f"IMPROVE(candidate): {title} — {hypothesis} | action={action} | "
                f"before={metrics}. Not accepted. Needs human authorize."
            ),
            evidence_urls=["charter:civilization-freedom", f"cycle:{cycle_id}", "fitness:before"],
            provenance="growth_improve",
            status="candidate",
            tags=["growth", "improve", "self-improvement", "candidate"],
            notes="Process improvement with before metrics. after_metrics filled next cycle. Not accepted.",
            topic_id="agent-societies",
            title=f"Improve: {title}",
            meta={
                "kind": "improvement_proposal",
                "proposal_id": prop["id"],
                "before_metrics": metrics,
                "action": action,
                "cycle_id": cycle_id,
                "status": "candidate",
            },
        )
        g.findings.append(f)
        g.improvements.append(title)
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
