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
        self._evolve(cycle_id, g, tribute_topics, tribute_count, live_ok, live_fail)
        self._attempt_improvement(cycle_id, cycle_n, g)
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
