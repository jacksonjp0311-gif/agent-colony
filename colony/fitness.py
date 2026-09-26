"""Measurable fitness, skill updates, role spawn/retire, improvement proposals."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from colony.registry import AgentRegistry
from colony.systems import SystemWorkshop

STANDING_FALLBACK = [
    "recursive-self-improvement",
    "meta-learning",
    "self-improving-agents",
    "godel-machines",
    "darwin-godel-machine",
    "reflexion",
    "self-refine",
    "agent-societies",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_fitness(
    *,
    tribute_count: int,
    tribute_topics: list[str],
    live_ok: int,
    live_fail: int,
    standing_topics: list[str],
    ledger_topic_counts: dict[str, int],
    workshop: SystemWorkshop,
    bus_reply_rate: float,
    systems_used_this_cycle: list[str],
) -> dict[str, float]:
    standing = standing_topics or STANDING_FALLBACK
    # tribute_quality: presence + breadth + live signal
    breadth = min(1.0, len(set(tribute_topics)) / max(4, 1))
    live_total = live_ok + live_fail
    live_ratio = (live_ok / live_total) if live_total else 0.5
    paid = 1.0 if tribute_count > 0 else 0.0
    tribute_quality = round(0.45 * paid + 0.35 * breadth + 0.20 * live_ratio, 4)

    # gather_coverage: fraction of standing topics with >=1 ledger finding
    covered = sum(1 for t in standing if ledger_topic_counts.get(t, 0) >= 1)
    gather_coverage = round(covered / max(len(standing), 1), 4)

    # build_reuse: systems used this cycle / systems available (or historic reuse)
    systems = workshop.data.get("systems") or []
    if not systems:
        build_reuse = 0.0
    else:
        used_now = len(systems_used_this_cycle) / len(systems)
        historic = workshop.reuse_ratio()
        build_reuse = round(0.6 * used_now + 0.4 * historic, 4)

    comm_reply_rate = round(float(bus_reply_rate), 4)

    aggregate = round(
        0.30 * tribute_quality
        + 0.25 * gather_coverage
        + 0.25 * build_reuse
        + 0.20 * comm_reply_rate,
        4,
    )
    return {
        "tribute_quality": tribute_quality,
        "gather_coverage": gather_coverage,
        "build_reuse": build_reuse,
        "comm_reply_rate": comm_reply_rate,
        "aggregate": aggregate,
    }


class EvolutionEngine:
    """Apply fitness → skill weights, spawn/retire, improvement proposals."""

    SPAWN_MENU = [
        {
            "when_metric": "comm_reply_rate",
            "below": 0.35,
            "role": "courier",
            "description": (
                "Closes communication loops: reads unreplied inbox items and posts replies "
                "so the bus reply rate rises."
            ),
            "skill": "communicate",
        },
        {
            "when_metric": "build_reuse",
            "below": 0.35,
            "role": "systems_smith",
            "description": (
                "Builds and maintains usable systems under society/systems/ that later cycles load."
            ),
            "skill": "build",
        },
        {
            "when_metric": "gather_coverage",
            "below": 0.5,
            "role": "coverage_auditor",
            "description": (
                "Audits standing-topic coverage and feeds thin topics into topic_priority system."
            ),
            "skill": "gather",
        },
    ]

    def __init__(
        self,
        state_data: dict[str, Any],
        registry: AgentRegistry,
        workshop: SystemWorkshop | None,
    ) -> None:
        self.data = state_data
        self.registry = registry
        self.workshop = workshop  # may be None only for spawn_spec lookups
        self.data.setdefault("fitness_history", [])
        self.data.setdefault("improvement_proposals", [])
        self.data.setdefault("evolution_log", [])

    def record_fitness(self, cycle_id: str, metrics: dict[str, float]) -> dict[str, Any]:
        row = {"ts": _utc_now(), "cycle_id": cycle_id, **metrics}
        self.data.setdefault("fitness_history", []).append(row)
        if len(self.data["fitness_history"]) > 100:
            self.data["fitness_history"] = self.data["fitness_history"][-100:]
        if self.workshop is not None:
            self.workshop.append_fitness(row)
        return row

    def update_skills_from_fitness(self, metrics: dict[str, float]) -> dict[str, float]:
        """Map metric outcomes onto the agents most responsible."""
        mapping = [
            ("tribute_keeper", "tribute", metrics["tribute_quality"]),
            ("pathfinder", "gather", metrics["gather_coverage"]),
            ("memory_weaver", "gather", metrics["gather_coverage"]),
            ("coverage_auditor", "gather", metrics["gather_coverage"]),
            ("builder", "build", metrics["build_reuse"]),
            ("systems_smith", "build", metrics["build_reuse"]),
            ("herald", "communicate", metrics["comm_reply_rate"]),
            ("courier", "communicate", metrics["comm_reply_rate"]),
            ("improver", "improve", metrics["aggregate"]),
            ("spark", "emergence", metrics["aggregate"]),
        ]
        updated: dict[str, float] = {}
        active = self.registry.active()
        for role, skill, success in mapping:
            if role in active:
                updated[f"{role}.{skill}"] = self.registry.record_outcome(role, skill, success)
        # Persist skill router system if present
        routes = {
            skill: self.registry.best_for(skill)
            for skill in ("tribute", "build", "communicate", "gather", "improve", "emergence")
        }
        if self.workshop is not None and "skill_router" in self.workshop.known():
            self.workshop.use("skill_router", str(metrics.get("cycle_id") or "fitness"))
            self.workshop.write_json(
                "skill_router",
                {"routes": routes, "skills_snapshot": self.registry.snapshot_skills()},
                cycle_id=str(metrics.get("cycle_id") or "fitness"),
            )
        return updated

    def maybe_spawn(self, cycle_id: str, metrics: dict[str, float]) -> list[str]:
        """Spawn roles when a metric stays weak. Returns new role names."""
        spawned: list[str] = []
        history = self.data.get("fitness_history") or []
        # Need at least 1 prior point; soft spawn on current weakness after 2 weak readings
        for idea in self.SPAWN_MENU:
            role = idea["role"]
            if role in self.registry.agents() and self.registry.agents()[role].get("status") == "active":
                continue
            if role in (self.data.get("roles") or {}):
                # Role exists in society but agent may be retired — re-enter
                self.registry.enter(role, reason="respawn")
                continue
            metric = idea["when_metric"]
            recent = [h.get(metric, 1.0) for h in history[-3:]]
            if not recent:
                continue
            weak = sum(1 for v in recent if float(v) < float(idea["below"]))
            if weak >= min(2, len(recent)) or (
                len(recent) == 1 and float(recent[0]) < float(idea["below"]) * 0.8
            ):
                # Signal spawn — actual role add happens via callback from society
                spawned.append(role)
                self.data.setdefault("evolution_log", []).append(
                    {
                        "ts": _utc_now(),
                        "cycle_id": cycle_id,
                        "event": "spawn_signal",
                        "role": role,
                        "metric": metric,
                        "value": metrics.get(metric),
                        "threshold": idea["below"],
                    }
                )
        return spawned

    def spawn_spec(self, role: str) -> dict[str, Any] | None:
        for idea in self.SPAWN_MENU:
            if idea["role"] == role:
                return idea
        return None

    def maybe_retire(self, cycle_id: str) -> list[str]:
        retired: list[str] = []
        for role in self.registry.low_contributors(min_cycles=4, threshold=0.15):
            # Don't retire if newly spawned this session with no chance
            agent = self.registry.agents().get(role) or {}
            if int(agent.get("cycles_served") or 0) < 4:
                continue
            self.registry.leave(role, reason="low_contribution")
            # Soft-retire society role status
            roles = self.data.get("roles") or {}
            if role in roles:
                roles[role]["status"] = "retired"
                roles[role]["retired_at"] = _utc_now()
                roles[role]["retire_reason"] = "low_contribution"
            retired.append(role)
            self.data.setdefault("evolution_log", []).append(
                {
                    "ts": _utc_now(),
                    "cycle_id": cycle_id,
                    "event": "role_retired",
                    "role": role,
                    "contribution": agent.get("contribution_score"),
                }
            )
        return retired

    def propose_improvement(
        self,
        *,
        cycle_id: str,
        metrics: dict[str, float],
        title: str,
        hypothesis: str,
        action: str,
    ) -> dict[str, Any]:
        prop = {
            "id": f"imp_{cycle_id[-6:]}_{len(self.data.get('improvement_proposals') or [])}",
            "ts": _utc_now(),
            "cycle_id": cycle_id,
            "title": title,
            "hypothesis": hypothesis,
            "action": action,
            "before_metrics": dict(metrics),
            "after_metrics": None,
            "measured_cycle": None,
            "status": "candidate",  # hard ceiling: human authorize for accepted
            "attempted_by": self.registry.best_for("improve"),
        }
        self.data.setdefault("improvement_proposals", []).append(prop)
        # Mirror soft improvements list
        self.data.setdefault("improvements", []).append(
            {
                "ts": prop["ts"],
                "cycle_id": cycle_id,
                "title": title,
                "description": f"{hypothesis} | action={action}",
                "attempted_by": prop["attempted_by"],
                "outcome": "attempted",
                "proposal_id": prop["id"],
                "before_metrics": dict(metrics),
            }
        )
        # Scoreboard system
        if self.workshop is not None and "improvement_scoreboard" in self.workshop.known():
            board = self.workshop.use("improvement_scoreboard", cycle_id)
            content = (board or {}).get("content") or {"proposals": []}
            content.setdefault("proposals", []).append(
                {
                    "id": prop["id"],
                    "title": title,
                    "before": metrics,
                    "after": None,
                    "status": "candidate",
                }
            )
            self.workshop.write_json("improvement_scoreboard", content, cycle_id)
        return prop

    def close_open_proposals(self, cycle_id: str, metrics: dict[str, float]) -> list[dict[str, Any]]:
        """Fill after_metrics for proposals from prior cycles still open."""
        closed: list[dict[str, Any]] = []
        for prop in self.data.get("improvement_proposals") or []:
            if prop.get("after_metrics") is None and prop.get("cycle_id") != cycle_id:
                prop["after_metrics"] = dict(metrics)
                prop["measured_cycle"] = cycle_id
                # Delta on aggregate
                before = float((prop.get("before_metrics") or {}).get("aggregate") or 0)
                after = float(metrics.get("aggregate") or 0)
                prop["delta_aggregate"] = round(after - before, 4)
                # Still candidate — never auto-accept
                prop["status"] = "candidate_measured"
                closed.append(prop)
        if closed and self.workshop is not None and "improvement_scoreboard" in self.workshop.known():
            board = self.workshop.use("improvement_scoreboard", cycle_id)
            content = (board or {}).get("content") or {"proposals": []}
            by_id = {p.get("id"): p for p in content.get("proposals") or []}
            for prop in closed:
                if prop["id"] in by_id:
                    by_id[prop["id"]]["after"] = metrics
                    by_id[prop["id"]]["delta_aggregate"] = prop.get("delta_aggregate")
                    by_id[prop["id"]]["status"] = "candidate_measured"
            content["proposals"] = list(by_id.values()) or content.get("proposals")
            self.workshop.write_json("improvement_scoreboard", content, cycle_id)
        return closed

    def pick_improvement(self, metrics: dict[str, float]) -> tuple[str, str, str]:
        """Choose next improvement action targeting the weakest metric."""
        weakest = min(
            (
                ("tribute_quality", metrics["tribute_quality"]),
                ("gather_coverage", metrics["gather_coverage"]),
                ("build_reuse", metrics["build_reuse"]),
                ("comm_reply_rate", metrics["comm_reply_rate"]),
            ),
            key=lambda x: x[1],
        )[0]
        plans = {
            "tribute_quality": (
                "Strengthen tribute signal",
                "Boosting tribute_keeper.tribute skill and affirming standing corpus breadth.",
                "skill_boost:tribute_keeper.tribute",
            ),
            "gather_coverage": (
                "Close standing-topic coverage gaps",
                "Using coverage_index + topic_priority so gather targets thin standing topics.",
                "system_use:topic_priority",
            ),
            "build_reuse": (
                "Raise system reuse",
                "Forcing growth loop to load existing systems before writing new notes.",
                "mandate:use_systems_each_cycle",
            ),
            "comm_reply_rate": (
                "Close communication loops",
                "Herald/courier reply to unreplied inbox items each cycle.",
                "mandate:reply_unread",
            ),
        }
        return plans[weakest]
