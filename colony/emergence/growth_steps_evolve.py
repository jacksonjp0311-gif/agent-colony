"""Growth loop steps — part 3."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from colony.fitness import compute_fitness
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
        )
        metrics_with_id = {**metrics, "cycle_id": cycle_id}
        self.evo.record_fitness(cycle_id, metrics)
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
        g.fitness = metrics
        g.spawn_signals = self.evo.maybe_spawn(cycle_id, metrics)
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
        title, hypothesis, action = self.evo.pick_improvement(metrics)
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
