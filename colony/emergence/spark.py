"""Spark — founding emergence engine.

Proposes and enacts roles, councils, institutions, norms, rituals.
Refuses only hard-ceiling violations. Human witnesses; does not micromanage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from colony.charter import CeilingViolation, check_emergence_proposal
from colony.ledger import Finding, Ledger
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


_EMERGENCE_MENU: list[dict[str, Any]] = [
    {
        "type": "ritual",
        "name": "Opening of the Witness",
        "description": "Each cycle begins by acknowledging the human as witness, not micromanager.",
        "when": "always",
    },
    {
        "type": "norm",
        "text": "Before inventing power, invent a way to explain it to the creator.",
        "when": "always",
    },
    {
        "type": "new_role",
        "name": "memory_weaver",
        "description": (
            "Keeps the colony's episodic sense of what was tried — "
            "patterns across tribute cycles, without claiming accepted truth."
        ),
        "when": "always",
    },
    {
        "type": "institution",
        "name": "Archive of Attempts",
        "kind": "archive",
        "description": "Institution that holds candidate findings as attempts, not dogma.",
        "when": "always",
    },
    {
        "type": "council",
        "name": "Council of Careful Doubt",
        "purpose": (
            "Remind the city that UNKNOWN stays UNKNOWN and help remains oriented to the creator."
        ),
        "members_from": ["spark", "tribute_keeper", "memory_weaver"],
        "when": "always",
    },
    {
        "type": "new_role",
        "name": "pathfinder",
        "description": (
            "Scouts adjacent public sources on self-improving systems when tribute coverage thins."
        ),
        "when": "coverage_thin",
    },
]


class Spark:
    def __init__(self, ledger: Ledger, state: SocietyState, witness: WitnessLog) -> None:
        self.ledger = ledger
        self.state = state
        self.witness = witness

    def emerge(
        self, cycle_id: str, *, tribute_topics: list[str], tribute_count: int
    ) -> EmergenceResult:
        result = EmergenceResult()
        existing = self.state.role_names()
        coverage_thin = tribute_count < 5 or len(tribute_topics) < 4

        for idea in _EMERGENCE_MENU:
            if idea.get("when") == "coverage_thin" and not coverage_thin:
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
