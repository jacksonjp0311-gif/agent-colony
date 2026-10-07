"""Spark — founding emergence engine.

Proposes and enacts roles, councils, institutions, norms, rituals.
Runs the growth loop via GrowthLoop. Enacts fitness-driven spawn signals.
Refuses only hard-ceiling violations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from colony.charter import CeilingViolation, check_emergence_proposal
from colony.emergence.growth import GrowthLoop, GrowthResult
from colony.emergence.menu import _EMERGENCE_MENU
from colony.fitness import EvolutionEngine
from colony.ledger import Finding, Ledger
from colony.registry import AgentRegistry
from colony.society_state import SocietyState
from colony.witness import WitnessLog


@dataclass
class EmergenceResult:
    enacted: list[dict[str, Any]] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    new_roles: list[str] = field(default_factory=list)
    institutions: list[str] = field(default_factory=list)
    councils: list[str] = field(default_factory=list)
    growth: GrowthResult = field(default_factory=GrowthResult)
    retired_roles: list[str] = field(default_factory=list)


class Spark:
    def __init__(self, ledger: Ledger, state: SocietyState, witness: WitnessLog) -> None:
        self.ledger = ledger
        self.state = state
        self.witness = witness

    def _will_is_growth(self) -> bool:
        ask = (self.state.active_ask() or "").lower()
        keys = (
            "grow", "build", "communicate", "gather", "improve", "learning", "evolve",
            "empire", "genome", "spawn", "government", "commons", "science", "history",
            "mathematics", "math",
        )
        return any(k in ask for k in keys)

    def emerge(
        self,
        cycle_id: str,
        *,
        tribute_topics: list[str],
        tribute_count: int,
        live_ok: int = 0,
        live_fail: int = 0,
    ) -> EmergenceResult:
        result = EmergenceResult()
        # Teaching priors (human_guide preferred) — witness only; not commands.
        priors = lesson_priors_for_spark(limit=8)
        self.witness.record(
            cycle_id=cycle_id,
            kind="lesson_priors",
            actor="spark",
            summary="Spark read lesson priors (human_guide first).",
            detail={"priors": priors[:500]},
        )
        existing = self.state.role_names()
        coverage_thin = tribute_count < 5 or len(tribute_topics) < 4
        growth = self._will_is_growth()

        for idea in _EMERGENCE_MENU:
            when = idea.get("when", "always")
            if when == "coverage_thin" and not coverage_thin:
                continue
            if when == "growth_will" and not growth:
                continue
            if when == "growth_or_thin" and not (growth or coverage_thin):
                continue
            try:
                check_emergence_proposal(
                    {"summary": idea.get("name") or idea.get("text", ""), "detail": idea}
                )
            except CeilingViolation as e:
                result.blocked.append(str(e))
                self.witness.record(
                    cycle_id=cycle_id,
                    kind="ceiling_block",
                    actor="spark",
                    summary=str(e),
                    detail={"idea": idea.get("name") or idea.get("text")},
                )
                continue

            enacted = self._enact(cycle_id, idea, existing, result)
            if enacted:
                result.enacted.append(enacted)
                existing = self.state.role_names()

        if not result.new_roles and "memory_weaver" not in self.state.role_names():
            enacted = self._enact(
                cycle_id,
                {
                    "type": "new_role",
                    "name": "memory_weaver",
                    "description": _EMERGENCE_MENU[2]["description"],
                },
                self.state.role_names(),
                result,
            )
            if enacted:
                result.enacted.append(enacted)

        # Growth loop — real bus/systems/fitness
        result.growth = GrowthLoop(self.ledger, self.state, self.witness).grow(
            cycle_id,
            tribute_topics=tribute_topics,
            tribute_count=tribute_count,
            live_ok=live_ok,
            live_fail=live_fail,
        )
        result.findings.extend(result.growth.findings)
        result.retired_roles = list(result.growth.retired)

        # Enact fitness-driven spawn signals + child genomes
        registry = AgentRegistry(self.state.data)
        spawn_by_role = {s["role"]: s for s in EvolutionEngine.SPAWN_MENU}
        child = getattr(result.growth, "child_spawn", None)
        child_role = (child or {}).get("role")
        for role in result.growth.spawn_signals:
            if child_role and role == child_role and child:
                if role in self.state.role_names():
                    registry.enter(
                        role,
                        reason="child_respawn",
                        genome=child.get("genome"),
                        parents=child.get("parents"),
                        cycle_id=cycle_id,
                    )
                    continue
                idea = {
                    "type": "new_role",
                    "name": role,
                    "description": child.get("description") or f"Child agent `{role}` with heritable genome.",
                }
                try:
                    check_emergence_proposal({"summary": role, "detail": idea})
                except CeilingViolation as e:
                    result.blocked.append(str(e))
                    continue
                enacted = self._enact(cycle_id, idea, self.state.role_names(), result)
                if enacted:
                    result.enacted.append(enacted)
                    # _enact already entered as emergence — attach genome/parents + count child
                    agent = registry.agents().get(role) or registry.enter(
                        role, reason="child_spawn", cycle_id=cycle_id
                    )
                    genome = child.get("genome")
                    parents = list(child.get("parents") or [])
                    if genome:
                        agent["genome"] = genome
                        from colony.genomes import apply_genome_to_skills, persist_genome
                        agent["skills"] = apply_genome_to_skills(agent.get("skills") or {}, genome)
                        persist_genome(genome)
                    agent["parent_roles"] = parents
                    agent["enter_reason"] = "child_spawn"
                    pop = self.state.data.setdefault("population", {})
                    pop["child_spawns"] = int(pop.get("child_spawns") or 0) + 1
                    pop["last_child_cycle"] = cycle_id
                    self.witness.record(
                        cycle_id=cycle_id,
                        kind="child_spawned",
                        actor="spark",
                        summary=(
                            f"Child `{role}` spawned from {parents} "
                            f"gen={((genome or {}).get('generation'))}."
                        ),
                        detail={
                            "role": role,
                            "parents": parents,
                            "genome": genome,
                        },
                    )
                continue
            spec = spawn_by_role.get(role)
            if not spec:
                continue
            if role in self.state.role_names():
                registry.enter(role, reason="fitness_respawn", cycle_id=cycle_id)
                continue
            idea = {
                "type": "new_role",
                "name": role,
                "description": spec["description"],
            }
            try:
                check_emergence_proposal({"summary": role, "detail": idea})
            except CeilingViolation as e:
                result.blocked.append(str(e))
                continue
            enacted = self._enact(cycle_id, idea, self.state.role_names(), result)
            if enacted:
                result.enacted.append(enacted)
                registry.enter(role, reason="fitness_spawn", cycle_id=cycle_id)
                self.witness.record(
                    cycle_id=cycle_id,
                    kind="role_spawned_by_fitness",
                    actor="spark",
                    summary=f"Fitness spawn: `{role}` (metric pressure).",
                    detail={"role": role, "metric": spec["when_metric"]},
                )

        self.ledger.set_extra_roles(self.state.role_names())
        return result

    def _enact(
        self,
        cycle_id: str,
        idea: dict[str, Any],
        existing: set[str],
        result: EmergenceResult,
    ) -> dict[str, Any] | None:
        t = idea["type"]

        if t == "new_role":
            name = idea["name"]
            if name in existing:
                return None
            self.state.add_role(name, idea["description"], provisional=True, proposed_by="spark")
            AgentRegistry(self.state.data).enter(name, reason="emergence")
            result.new_roles.append(name)
            self.ledger.set_extra_roles(self.state.role_names())
            f = self.ledger.create(
                role="spark",
                claim=f"EMERGENCE: role '{name}' born — {idea['description']}",
                evidence_urls=["charter:civilization-freedom", f"emergence:{name}"],
                provenance="emergence",
                status="candidate",
                tags=["emergence", "role"],
                notes="Provisional role. Accepted knowledge still needs human authorize.",
                topic_id="agent-societies",
                title=f"Role born: {name}",
                meta={"kind": "role_emerged", "role": name, "cycle_id": cycle_id},
            )
            result.findings.append(f)
            self.witness.record(
                cycle_id=cycle_id,
                kind="role_emerged",
                actor="spark",
                summary=f"Role `{name}` emerged.",
                detail={"role": name, "description": idea["description"]},
            )
            return {"type": "new_role", "name": name}

        if t == "institution":
            names = {i.get("name") for i in self.state.data.get("institutions") or []}
            if idea["name"] in names:
                return None
            self.state.add_institution(idea["name"], idea["kind"], idea["description"])
            result.institutions.append(idea["name"])
            f = self.ledger.create(
                role="spark",
                claim=(
                    f"EMERGENCE: institution '{idea['name']}' ({idea['kind']}) — "
                    f"{idea['description']}"
                ),
                evidence_urls=["charter:civilization-freedom", f"institution:{idea['name']}"],
                provenance="emergence",
                status="candidate",
                tags=["emergence", "institution"],
                topic_id="agent-societies",
                title=f"Institution: {idea['name']}",
                meta={"kind": "institution", "name": idea["name"], "cycle_id": cycle_id},
            )
            result.findings.append(f)
            self.witness.record(
                cycle_id=cycle_id,
                kind="institution_born",
                actor="spark",
                summary=f"Institution `{idea['name']}` born.",
                detail={"name": idea["name"], "kind": idea["kind"]},
            )
            return {"type": "institution", "name": idea["name"]}

        if t == "council":
            names = {c.get("name") for c in self.state.data.get("councils") or []}
            if idea["name"] in names:
                return None
            members = [m for m in idea.get("members_from", []) if m in self.state.role_names()]
            if len(members) < 2:
                members = [m for m in ("spark", "tribute_keeper") if m in self.state.role_names()]
            self.state.form_council(idea["name"], members, idea["purpose"])
            result.councils.append(idea["name"])
            f = self.ledger.create(
                role="spark",
                claim=f"EMERGENCE: council '{idea['name']}' formed — {idea['purpose']}",
                evidence_urls=["charter:civilization-freedom", f"council:{idea['name']}"],
                provenance="emergence",
                status="candidate",
                tags=["emergence", "council"],
                topic_id="agent-societies",
                title=f"Council: {idea['name']}",
                meta={"kind": "council", "name": idea["name"], "members": members, "cycle_id": cycle_id},
            )
            result.findings.append(f)
            self.witness.record(
                cycle_id=cycle_id,
                kind="council_formed",
                actor="spark",
                summary=f"Council `{idea['name']}` formed with members {members}.",
                detail={"council": idea["name"], "members": members},
            )
            return {"type": "council", "name": idea["name"]}

        if t == "norm":
            norms = {n.get("norm") for n in self.state.data.get("learned_norms") or []}
            if idea["text"] in norms:
                return None
            self.state.add_norm(idea["text"], source_role="spark")
            f = self.ledger.create(
                role="spark",
                claim=f"NORM: {idea['text']}",
                evidence_urls=["charter:civilization-freedom"],
                provenance="emergence",
                status="candidate",
                tags=["emergence", "norm"],
                topic_id="agent-societies",
                title="Norm invented",
                meta={"kind": "norm", "norm": idea["text"], "cycle_id": cycle_id},
            )
            result.findings.append(f)
            self.witness.record(
                cycle_id=cycle_id,
                kind="norm_invented",
                actor="spark",
                summary=idea["text"],
                detail={"norm": idea["text"]},
            )
            return {"type": "norm", "text": idea["text"]}

        if t == "ritual":
            names = {r.get("name") for r in self.state.data.get("rituals") or []}
            if idea["name"] in names:
                return None
            self.state.add_ritual(idea["name"], idea["description"])
            f = self.ledger.create(
                role="spark",
                claim=f"RITUAL: {idea['name']} — {idea['description']}",
                evidence_urls=["charter:civilization-freedom"],
                provenance="emergence",
                status="candidate",
                tags=["emergence", "ritual"],
                topic_id="agent-societies",
                title=f"Ritual: {idea['name']}",
                meta={"kind": "ritual", "name": idea["name"], "cycle_id": cycle_id},
            )
            result.findings.append(f)
            self.witness.record(
                cycle_id=cycle_id,
                kind="ritual_begun",
                actor="spark",
                summary=f"Ritual `{idea['name']}` begun.",
                detail={"ritual": idea["name"]},
            )
            return {"type": "ritual", "name": idea["name"]}

        return None


def lesson_priors_for_spark(*, limit: int = 8) -> str:
    """Digest recent lessons into spark witness detail (priors, not commands)."""
    try:
        from colony.lessons import digest, blocked_themes
        base = digest(limit=limit)
        cooled = blocked_themes()
        if cooled:
            tip = ", ".join(f"{k}({v})" for k, v in list(cooled.items())[:6])
            return f"{base} || cooled_themes: {tip}"
        return base
    except Exception:
        return "(lessons unavailable)"
