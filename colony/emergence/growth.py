"""Growth loop — invent/build usable systems, communicate (bus), gather, improve."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from colony.bus import CommBus
from colony.fitness import EvolutionEngine
from colony.ledger import Finding, Ledger
from colony.registry import AgentRegistry
from colony.society_state import SocietyState
from colony.systems import SystemWorkshop
from colony.witness import WitnessLog
from colony.emergence.growth_steps_inbox_build import GrowthSteps1
from colony.emergence.growth_steps_comm_gather import GrowthSteps2
from colony.emergence.growth_steps_evolve import GrowthSteps3

ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass
class GrowthResult:
    builds: list[str] = field(default_factory=list)
    communications: list[dict[str, Any]] = field(default_factory=list)
    gathered: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    systems_used: list[str] = field(default_factory=list)
    systems_built: list[str] = field(default_factory=list)
    replies: int = 0
    messages_read: int = 0
    fitness: dict[str, float] = field(default_factory=dict)
    skill_updates: dict[str, float] = field(default_factory=dict)
    spawn_signals: list[str] = field(default_factory=list)
    retired: list[str] = field(default_factory=list)
    actionables: dict[str, Any] = field(default_factory=dict)
    child_spawn: dict[str, Any] | None = None
    commons_size: int = 0
    gov_proposals: int = 0


class GrowthLoop(GrowthSteps1, GrowthSteps2, GrowthSteps3):
    def __init__(self, ledger: Ledger, state: SocietyState, witness: WitnessLog) -> None:
        self.ledger = ledger
        self.state = state
        self.witness = witness
        self.registry = AgentRegistry(state.data)
        self.bus = CommBus(state.data, self.registry)
        self.workshop = SystemWorkshop(state.data, root=ROOT)
        self.evo = EvolutionEngine(state.data, self.registry, self.workshop)

    def grow(
        self,
        cycle_id: str,
        *,
        tribute_topics: list[str],
        tribute_count: int,
        live_ok: int = 0,
        live_fail: int = 0,
    ) -> GrowthResult:
        g = GrowthResult()
        cycle_n = int(self.state.data.get("cycle_count") or 0) + 1

        entered = self.registry.sync_from_roles(cycle_id=cycle_id)
        if entered:
            self.witness.record(
                cycle_id=cycle_id,
                kind="agents_entered",
                actor="spark",
                summary=f"Agents entered: {entered}",
                detail={"entered": entered},
            )

        # Durable engineered personas (role posture — not sentience)
        from colony.personas import ensure_all_active

        persona_roles = ensure_all_active(self.registry.agents(), root=ROOT)
        if persona_roles:
            self.witness.record(
                cycle_id=cycle_id,
                kind="personas_ensured",
                actor="spark",
                summary=f"Personas ensured for {len(persona_roles)} agents (engineered character, not sentience).",
                detail={"roles": persona_roles, "engineered_character": True, "not_sentience": True},
            )

        self.witness.record(
            cycle_id=cycle_id,
            kind="growth_loop_open",
            actor="spark",
            summary="Growth loop lit: read-bus → build/use-systems → communicate/reply → gather → evolve.",
            detail={"active_ask": self.state.active_ask(), "cycle_n": cycle_n},
        )

        actionables = self._read_all_inboxes(cycle_id, g)
        g.actionables = actionables
        self._build_and_use_systems(cycle_id, cycle_n, g, actionables)
        self._communicate_and_reply(cycle_id, cycle_n, g, tribute_topics, actionables)
        self._gather(cycle_id, g, tribute_topics, tribute_count, actionables)
        # Pre-load findings→behavior so debate/hearing voices + mandates are live
        from colony.findings_coupling import (
            apply_persona_mandates,
            harvest_behavior_signal,
        )
        from colony.rsi_coupling import harvest_rsi_signal
        g.behavior_signal = harvest_behavior_signal(self.ledger.all())  # type: ignore[attr-defined]
        g.rsi_signal = harvest_rsi_signal(self.ledger.all())  # type: ignore[attr-defined]
        apply_persona_mandates(self.registry.agents(), g.behavior_signal, root=ROOT)
        # Seed fitness from last cycle for hearing scoring
        hist = self.state.data.get("fitness_history") or []
        if hist:
            g.fitness = {k: v for k, v in hist[-1].items() if isinstance(v, (int, float))}
        # Research-lab: debate → propose → hearing verdict, then evolve/fitness
        self._debate_then_propose(cycle_id, cycle_n, g)
        self._attempt_improvement(cycle_id, cycle_n, g)
        # Measured bench improve: one measure→keep/revert attempt per cycle
        try:
            from colony.bench_improve import run_from_growth

            bi = run_from_growth(cycle_id)
            g.improvements.append(f"bench_improve:{bi.patch_name}:{bi.decision}")
            self.witness.record(
                cycle_id=cycle_id,
                kind="bench_improve",
                actor="improver" if "improver" in self.registry.active() else "spark",
                summary=(
                    f"Bench improve `{bi.patch_name}` → {bi.decision} "
                    f"({bi.before_score}→{bi.after_score}, delta={bi.delta})"
                ),
                detail={
                    "patch": bi.patch_name,
                    "decision": bi.decision,
                    "before_score": bi.before_score,
                    "after_score": bi.after_score,
                    "delta": bi.delta,
                    "note": bi.note,
                },
            )
        except Exception as exc:  # noqa: BLE001
            self.witness.record(
                cycle_id=cycle_id,
                kind="bench_improve_error",
                actor="improver",
                summary=f"Bench improve skipped: {exc}",
                detail={"error": str(exc)},
            )
        # Conjecture desk: paper themes → lemma mutations; keep only on score rise
        try:
            from colony.conjecture_desk import run_from_growth as conjecture_run

            cj = conjecture_run(cycle_id, ledger=self.ledger)
            g.improvements.append(f"conjecture:{cj.mutation or 'none'}:{cj.decision}")
            self.witness.record(
                cycle_id=cycle_id,
                kind="conjecture_desk",
                actor="geometer" if "geometer" in self.registry.active() else "spark",
                summary=(
                    f"Conjecture desk `{cj.mutation or 'none'}` → {cj.decision} "
                    f"({cj.before_score}→{cj.after_score}, delta={cj.delta})"
                ),
                detail={
                    "mutation": cj.mutation,
                    "decision": cj.decision,
                    "before_score": cj.before_score,
                    "after_score": cj.after_score,
                    "delta": cj.delta,
                    "note": cj.note,
                    "n_proposals": len(cj.proposals),
                },
            )
        except Exception as exc:  # noqa: BLE001
            self.witness.record(
                cycle_id=cycle_id,
                kind="conjecture_desk_error",
                actor="geometer",
                summary=f"Conjecture desk skipped: {exc}",
                detail={"error": str(exc)},
            )
        # Lift 3: scrape→analyze→claim (raw scrape ≠ discovery)
        try:
            from colony.claim_pipeline import run_pipeline
            pipe = run_pipeline(live_gather=False, ledger=self.ledger, cycle_id=cycle_id)
            g.improvements.append(
                f"claim_pipeline:extracted={pipe.get('n_extracted')}:proposed={pipe.get('n_proposed')}"
            )
            self.witness.record(
                cycle_id=cycle_id,
                kind="claim_pipeline",
                actor="geometer" if "geometer" in self.registry.active() else "spark",
                summary=(
                    f"Claim pipeline: extracted={pipe.get('n_extracted')} "
                    f"hard_checked={pipe.get('n_hard_checked')} "
                    f"proposed={pipe.get('n_proposed')} (raw scrape ≠ discovery)."
                ),
                detail=pipe,
            )
        except Exception as exc:  # noqa: BLE001
            self.witness.record(
                cycle_id=cycle_id,
                kind="claim_pipeline_error",
                actor="geometer",
                summary=f"Claim pipeline skipped: {exc}",
                detail={"error": str(exc)},
            )
        # Lift 2: bias skills/genomes from lesson ledger (kept outcomes only)
        try:
            from colony.lessons import apply_lesson_bias_to_agents, apply_lesson_bias_to_genomes, digest
            bias = apply_lesson_bias_to_agents(self.registry.agents())
            n_gen = apply_lesson_bias_to_genomes(ROOT)
            if bias or n_gen:
                self.witness.record(
                    cycle_id=cycle_id,
                    kind="lesson_bias_applied",
                    actor="improver" if "improver" in self.registry.active() else "spark",
                    summary=f"Lesson bias applied keys={list(bias)} genomes_touched={n_gen}. Digest: {digest(limit=3)}",
                    detail={"skill_bias": bias, "genomes_touched": n_gen},
                )
        except Exception as exc:  # noqa: BLE001
            self.witness.record(
                cycle_id=cycle_id,
                kind="lesson_bias_error",
                actor="improver",
                summary=f"Lesson bias skipped: {exc}",
                detail={"error": str(exc)},
            )
        # Lift 5: external_mind proposals under hard-tier (cross-agent debate already in evolve)
        try:
            from colony.external_mind import propose as em_propose
            batch = em_propose(n=4, ledger=self.ledger, cycle_id=cycle_id, state_data=self.state.data)
            self.witness.record(
                cycle_id=cycle_id,
                kind="external_mind_propose",
                actor="spark",
                summary=(
                    f"External mind proposed {len(batch.proposals)} candidates "
                    f"(keep only on hard-tier rise; dissent stays in witness)."
                ),
                detail={
                    "n": len(batch.proposals),
                    "ids": [p.get("id") for p in batch.proposals],
                    "commons_prior": (batch.commons_digest or "")[:160],
                    "not_consciousness": True,
                },
            )
        except Exception as exc:  # noqa: BLE001
            self.witness.record(
                cycle_id=cycle_id,
                kind="external_mind_error",
                actor="spark",
                summary=f"External mind skipped: {exc}",
                detail={"error": str(exc)},
            )
        self._evolve(cycle_id, g, tribute_topics, tribute_count, live_ok, live_fail)
        self._government_and_census(cycle_id, g)

        for role in self.registry.active():
            self.registry.bump_cycle(role)

        from colony.commons import CommonKnowledge
        g.commons_size = CommonKnowledge(self.state.data).size()
        self.bus.render_bulletin()

        self.witness.record(
            cycle_id=cycle_id,
            kind="growth_loop_close",
            actor="spark",
            summary=(
                f"Growth closed: built={g.builds} systems_used={g.systems_used} "
                f"comms={len(g.communications)} replies={g.replies} "
                f"gathered={g.gathered} fitness={g.fitness.get('aggregate')} "
                f"spawn={g.spawn_signals} retired={g.retired}."
            ),
            detail={
                "builds": g.builds,
                "systems_used": g.systems_used,
                "systems_built": g.systems_built,
                "communications": len(g.communications),
                "replies": g.replies,
                "messages_read": g.messages_read,
                "gathered": g.gathered,
                "improvements": g.improvements,
                "fitness": g.fitness,
                "spawn_signals": g.spawn_signals,
                "retired": g.retired,
            },
        )
        return g
