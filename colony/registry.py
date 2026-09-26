"""Agent registry — enter/leave, inbox, skills, genomes that change from outcomes."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from colony.genomes import ensure_agent_genome

DEFAULT_SKILLS: dict[str, float] = {
    "tribute": 0.5,
    "build": 0.5,
    "communicate": 0.5,
    "gather": 0.5,
    "improve": 0.5,
    "emergence": 0.5,
}

ROLE_SKILL_BIAS: dict[str, dict[str, float]] = {
    "spark": {"emergence": 0.9, "improve": 0.6, "communicate": 0.6},
    "tribute_keeper": {"tribute": 0.95, "gather": 0.7},
    "builder": {"build": 0.9, "improve": 0.55},
    "herald": {"communicate": 0.95},
    "pathfinder": {"gather": 0.9, "communicate": 0.55},
    "improver": {"improve": 0.95, "emergence": 0.6},
    "memory_weaver": {"gather": 0.7, "communicate": 0.6, "improve": 0.55},
    "courier": {"communicate": 0.95, "gather": 0.4},
    "systems_smith": {"build": 0.95, "improve": 0.7},
    "coverage_auditor": {"gather": 0.95, "tribute": 0.6},
    "scribe": {"communicate": 0.85, "gather": 0.65},
    "surveyor": {"gather": 0.8, "emergence": 0.75},
    "archivist": {"gather": 0.8, "build": 0.6},
    "legislator": {"improve": 0.7, "communicate": 0.65, "emergence": 0.55},
    "chronicler": {"gather": 0.8, "communicate": 0.55},
    "naturalist": {"gather": 0.85, "emergence": 0.7},
    "geometer": {"gather": 0.8, "emergence": 0.65},
    "messenger": {"communicate": 0.9, "gather": 0.45},
}

SOFT_POP_CAP = 20  # soft ceiling; retire low fitness before spawn when at/over


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _blank_agent(role: str) -> dict[str, Any]:
    skills = dict(DEFAULT_SKILLS)
    for k, v in ROLE_SKILL_BIAS.get(role, {}).items():
        skills[k] = max(skills.get(k, 0.5), v)
    return {
        "role": role,
        "status": "active",
        "entered_at": _utc_now(),
        "left_at": None,
        "cycles_served": 0,
        "inbox": [],
        "skills": skills,
        "outcomes": {"success": 0, "fail": 0, "neutral": 0},
        "contribution_score": 0.0,
        "last_actions": [],
        "messages_read": 0,
        "replies_sent": 0,
        "systems_used": 0,
        "genome": None,
        "parent_roles": [],
    }


class AgentRegistry:
    """Persistent agent roster inside society_state.data['agents']."""

    def __init__(self, state_data: dict[str, Any]) -> None:
        self.data = state_data
        self.data.setdefault("agents", {})
        self.data.setdefault("population", {"soft_cap": SOFT_POP_CAP, "spawns": 0, "child_spawns": 0})

    def agents(self) -> dict[str, dict[str, Any]]:
        return self.data.setdefault("agents", {})

    def active(self) -> dict[str, dict[str, Any]]:
        return {k: v for k, v in self.agents().items() if v.get("status") == "active"}

    def active_count(self) -> int:
        return len(self.active())

    def soft_cap(self) -> int:
        return int((self.data.get("population") or {}).get("soft_cap") or SOFT_POP_CAP)

    def at_capacity(self) -> bool:
        return self.active_count() >= self.soft_cap()

    def enter(
        self,
        role: str,
        *,
        reason: str = "sync",
        genome: dict[str, Any] | None = None,
        parents: list[str] | None = None,
        cycle_id: str = "",
    ) -> dict[str, Any]:
        agents = self.agents()
        if role in agents and agents[role].get("status") == "active":
            ensure_agent_genome(agents[role], role, cycle_id=cycle_id)
            return agents[role]
        if role in agents and agents[role].get("status") == "retired":
            agents[role]["status"] = "active"
            agents[role]["entered_at"] = _utc_now()
            agents[role]["left_at"] = None
            agents[role]["reentry_reason"] = reason
            if genome:
                agents[role]["genome"] = genome
            ensure_agent_genome(agents[role], role, cycle_id=cycle_id)
            return agents[role]
        agents[role] = _blank_agent(role)
        agents[role]["enter_reason"] = reason
        if parents:
            agents[role]["parent_roles"] = list(parents)
        if genome:
            agents[role]["genome"] = genome
        ensure_agent_genome(agents[role], role, cycle_id=cycle_id)
        self.data.setdefault("history", []).append(
            {"ts": _utc_now(), "event": "agent_enter", "role": role, "reason": reason, "parents": parents or []}
        )
        pop = self.data.setdefault("population", {})
        pop["spawns"] = int(pop.get("spawns") or 0) + 1
        if reason.startswith("child") or parents:
            pop["child_spawns"] = int(pop.get("child_spawns") or 0) + 1
        return agents[role]

    def leave(self, role: str, *, reason: str = "retire") -> dict[str, Any] | None:
        agents = self.agents()
        if role not in agents:
            return None
        founding = set(self.data.get("founding_roles") or ["spark", "tribute_keeper"])
        if role in founding:
            return None  # founding cast cannot leave
        agents[role]["status"] = "retired"
        agents[role]["left_at"] = _utc_now()
        agents[role]["leave_reason"] = reason
        self.data.setdefault("history", []).append(
            {"ts": _utc_now(), "event": "agent_leave", "role": role, "reason": reason}
        )
        return agents[role]

    def sync_from_roles(self, *, cycle_id: str = "") -> list[str]:
        """Ensure every society role has an active agent entry + genome."""
        entered: list[str] = []
        for role in self.data.get("roles", {}).keys():
            before = role in self.agents() and self.agents()[role].get("status") == "active"
            self.enter(role, reason="role_sync", cycle_id=cycle_id)
            if not before:
                entered.append(role)
        # Ensure genomes on all active
        for role, agent in self.active().items():
            ensure_agent_genome(agent, role, cycle_id=cycle_id)
        return entered

    def deliver(self, role: str, message: dict[str, Any]) -> None:
        agent = self.agents().get(role)
        if not agent or agent.get("status") != "active":
            agent = self.enter("spark", reason="fallback_inbox")
            role = "spark"
        inbox = agent.setdefault("inbox", [])
        inbox.append(
            {
                **message,
                "delivered_at": _utc_now(),
                "read": False,
            }
        )
        if len(inbox) > 40:
            agent["inbox"] = inbox[-40:]

    def unread(self, role: str) -> list[dict[str, Any]]:
        agent = self.agents().get(role) or {}
        return [m for m in agent.get("inbox") or [] if not m.get("read")]

    def mark_read(self, role: str, msg_ids: list[str]) -> int:
        agent = self.agents().get(role)
        if not agent:
            return 0
        ids = set(msg_ids)
        n = 0
        for m in agent.get("inbox") or []:
            if m.get("id") in ids and not m.get("read"):
                m["read"] = True
                m["read_at"] = _utc_now()
                n += 1
        agent["messages_read"] = int(agent.get("messages_read") or 0) + n
        return n

    def record_outcome(self, role: str, skill: str, success: float) -> float:
        """Update skill weight from outcome in [0,1]. Returns new weight."""
        agent = self.enter(role, reason="outcome")
        skills = agent.setdefault("skills", dict(DEFAULT_SKILLS))
        old = float(skills.get(skill, 0.5))
        new = max(0.05, min(0.99, old * 0.82 + float(success) * 0.18))
        skills[skill] = round(new, 4)
        outcomes = agent.setdefault("outcomes", {"success": 0, "fail": 0, "neutral": 0})
        if success >= 0.66:
            outcomes["success"] = int(outcomes.get("success") or 0) + 1
        elif success <= 0.33:
            outcomes["fail"] = int(outcomes.get("fail") or 0) + 1
        else:
            outcomes["neutral"] = int(outcomes.get("neutral") or 0) + 1
        prev_c = float(agent.get("contribution_score") or 0.0)
        agent["contribution_score"] = round(prev_c * 0.8 + success * 0.2, 4)
        return new

    def bump_cycle(self, role: str, actions: list[str] | None = None) -> None:
        agent = self.agents().get(role)
        if not agent or agent.get("status") != "active":
            return
        agent["cycles_served"] = int(agent.get("cycles_served") or 0) + 1
        if actions:
            recent = list(agent.get("last_actions") or [])
            recent.extend(actions)
            agent["last_actions"] = recent[-12:]

    def best_for(self, skill: str) -> str:
        active = self.active()
        if not active:
            return "spark"
        ranked = sorted(
            active.items(),
            key=lambda kv: float((kv[1].get("skills") or {}).get(skill, 0.0)),
            reverse=True,
        )
        return ranked[0][0]

    def snapshot_skills(self) -> dict[str, dict[str, float]]:
        return {
            role: {k: float(v) for k, v in (a.get("skills") or {}).items()}
            for role, a in self.active().items()
        }

    def low_contributors(self, *, min_cycles: int = 3, threshold: float = 0.18) -> list[str]:
        founding = set(self.data.get("founding_roles") or ["spark", "tribute_keeper"])
        out = []
        for role, a in self.active().items():
            if role in founding:
                continue
            if int(a.get("cycles_served") or 0) >= min_cycles and float(
                a.get("contribution_score") or 0
            ) < threshold:
                out.append(role)
        return out
