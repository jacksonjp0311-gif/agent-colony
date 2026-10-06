"""Measurable fitness, skill updates, role/child spawn/retire, improvement proposals."""

from __future__ import annotations

import hashlib
import math

from datetime import datetime, timezone
from typing import Any

from colony.genomes import (
    child_role_available,
    fitness_score,
    new_genome,
    pick_parents,
    persist_genome,
)
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
    "science-method",
    "history-of-ideas",
    "mathematics-foundations",
    "software-engineering",
    "life-and-death",
    "nature-biology-ecology",
    "cosmology-universe",
    "emergent-technology",
    "open-math-problems",
    "compute-useful-math",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hard_tier_snapshot() -> dict[str, float | int | bool]:
    """Read lemma hard-tier pressure for emergence kill criteria."""
    try:
        from society.benchmarks.lemma_microbench import run as run_lemma
        r = run_lemma()
        return {
            "score": float(r.get("score") or 0),
            "n_hard": int(r.get("n_hard") or 0),
            "n_hard_pass": int(r.get("n_hard_pass") or 0),
            "ok": bool(r.get("ok")),
        }
    except Exception:
        return {"score": 0.0, "n_hard": 0, "n_hard_pass": 0, "ok": False}


def hard_tier_delta(data: dict) -> float:
    """Delta of hard_pass count vs prior recorded snapshot."""
    hist = data.setdefault("hard_tier_history", [])
    cur = hard_tier_snapshot()
    prev = hist[-1] if hist else None
    delta_pass = int(cur["n_hard_pass"]) - int((prev or {}).get("n_hard_pass") or cur["n_hard_pass"])
    delta_score = float(cur["score"]) - float((prev or {}).get("score") or cur["score"])
    cur["delta_pass"] = delta_pass
    cur["delta_score"] = round(delta_score, 4)
    hist.append(cur)
    if len(hist) > 40:
        data["hard_tier_history"] = hist[-40:]
    return float(delta_pass)



def _oracle_kill_rate_term() -> float:
    """Informative sieve scores mid-high; 0 or >0.95 both score mid/low. Easy-pad-only kills → low."""
    try:
        from colony.oracle import counts
        c = counts()
        total = int(c.get("total") or 0)
        kills = int(c.get("kills") or 0)
        easy = int(c.get("easy_pad_kills") or 0)
        if total <= 0:
            return 0.35
        kr = kills / max(1, total)
        if kills == 0 or kr > 0.95:
            return 0.25
        # No credit if all kills are easy_pad only
        if kills > 0 and easy >= kills and (kills / max(1, total)) > 0:
            non_easy = kills - easy
            if non_easy <= 0:
                return 0.30
        # Peak around 0.2–0.8
        if 0.2 <= kr <= 0.8:
            return round(0.55 + 0.45 * (1.0 - abs(kr - 0.5) / 0.5), 4)
        return round(0.35 + 0.2 * (1.0 - abs(kr - 0.5)), 4)
    except Exception:
        return 0.35


def _novelty_term() -> float:
    try:
        from pathlib import Path as _P
        import json as _json
        p = _P(__file__).resolve().parent.parent / "society" / "systems" / "novelty_gate.json"
        if not p.exists():
            return 0.4
        d = _json.loads(p.read_text(encoding="utf-8"))
        hits = float(d.get("hits") or 0)
        kills = float(d.get("kills") or 0)
        total = hits + kills
        if total <= 0:
            return 0.4
        return round(min(1.0, hits / total), 4)
    except Exception:
        return 0.4


def _lesson_uptake_term() -> float:
    """Fraction of recent keep/enable decisions that cite a prior lesson id."""
    try:
        from colony.lessons import load_lessons, LESSONS_JSONL
        lessons = load_lessons(limit=80)
        ids = {e.get("id") for e in lessons if e.get("id")}
        if not ids:
            return 0.0
        keeps = [e for e in lessons if e.get("decision") == "keep"][-10:]
        if not keeps:
            return 0.0
        cited = 0
        for e in keeps:
            ev = " ".join(str(x) for x in (e.get("evidence") or []))
            what = e.get("what") or ""
            blob = ev + " " + what
            if any(i and i in blob for i in ids if i != e.get("id")):
                cited += 1
            elif any(t.startswith("lesson:") for t in (e.get("tags") or [])):
                cited += 1
        return round(cited / max(1, len(keeps)), 4)
    except Exception:
        return 0.0


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
    reply_quality: float = 0.0,
    commons_size: int = 0,
    math_prize_hits: int = 0,
    compute_useful_hits: int = 0,
    citation_reuse_hits: int = 0,
) -> dict[str, float]:
    standing = standing_topics or STANDING_FALLBACK
    breadth = min(1.0, len(set(tribute_topics)) / max(4, 1))
    live_total = live_ok + live_fail
    live_ratio = (live_ok / live_total) if live_total else 0.5
    paid = 1.0 if tribute_count > 0 else 0.0
    tribute_quality = round(0.45 * paid + 0.35 * breadth + 0.20 * live_ratio, 4)

    covered = sum(1 for t in standing if ledger_topic_counts.get(t, 0) >= 1)
    gather_coverage = round(covered / max(len(standing), 1), 4)

    systems = workshop.data.get("systems") or []
    if not systems:
        build_reuse = 0.0
    else:
        used_now = len(systems_used_this_cycle) / len(systems)
        historic = workshop.reuse_ratio()
        build_reuse = round(0.6 * used_now + 0.4 * historic, 4)

    comm_reply_rate = round(float(bus_reply_rate), 4)
    reply_q = round(float(reply_quality), 4)
    # Soft commons signal (does not dominate)
    commons_signal = round(min(1.0, commons_size / 24.0), 4)

    # Prize framing: PRIMARY signal is measured benchmark scores (society/benchmarks/latest.json).
    # Institution existence / gather hits alone must NOT saturate math_prize.
    from colony.benchmarks_fit import bench_prize_components

    bench = bench_prize_components()
    hit_math = round(min(1.0, math_prize_hits / 12.0), 4)  # soft, hard to saturate
    hit_compute = round(min(1.0, compute_useful_hits / 12.0), 4)
    math_prize = round(0.75 * bench["math_prize"] + 0.25 * hit_math, 4)
    compute_usefulness = round(0.75 * bench["compute_usefulness"] + 0.25 * hit_compute, 4)
    # Behavior prize: citing/reusing accepted compute-useful findings (not museum)
    citation_reuse = round(min(1.0, citation_reuse_hits / 3.0), 4)
    prize_boost = round(
        0.45 * math_prize + 0.35 * compute_usefulness + 0.20 * citation_reuse, 4
    )

    kill_rate_term = _oracle_kill_rate_term()
    novelty = _novelty_term()
    lesson_uptake = _lesson_uptake_term()
    aggregate = round(
        0.18 * tribute_quality
        + 0.14 * gather_coverage
        + 0.14 * build_reuse
        + 0.11 * comm_reply_rate
        + 0.06 * reply_q
        + 0.04 * commons_signal
        + 0.16 * prize_boost
        + 0.07 * kill_rate_term
        + 0.05 * novelty
        + 0.05 * lesson_uptake,
        4,
    )
    return {
        "tribute_quality": tribute_quality,
        "gather_coverage": gather_coverage,
        "build_reuse": build_reuse,
        "comm_reply_rate": comm_reply_rate,
        "reply_quality": reply_q,
        "commons_signal": commons_signal,
        "math_prize": math_prize,
        "compute_usefulness": compute_usefulness,
        "citation_reuse": citation_reuse,
        "prize_boost": prize_boost,
        "kill_rate": kill_rate_term,
        "novelty": novelty,
        "lesson_uptake": lesson_uptake,
        "aggregate": aggregate,
    }


class EvolutionEngine:
    """Apply fitness → skill weights, spawn/retire, child genomes, improvement proposals."""

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
        {
            "when_metric": "math_prize",
            "below": 0.55,
            "role": "oracle_scribe",
            "description": (
                "Specialist: records Oracle HEAR/SENSE kills and passes; "
                "pressures hard/STEM enables when fitness gaps appear."
            ),
            "skill": "improve",
        },
        {
            "when_metric": "compute_useful",
            "below": 0.45,
            "role": "stem_checker",
            "description": (
                "Specialist: runs STEM kinematics domain pack; "
                "retire when no Oracle-pass lift across recent cycles."
            ),
            "skill": "gather",
        },
        {
            "when_metric": "reply_quality",
            "below": 0.35,
            "role": "debate_deepener",
            "description": (
                "Specialist: deepens multi-hop debate A→B→C→D(Oracle gate) on the bus."
            ),
            "skill": "communicate",
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
        self.workshop = workshop
        self.data.setdefault("fitness_history", [])
        self.data.setdefault("improvement_proposals", [])
        self.data.setdefault("evolution_log", [])
        self.data.setdefault("population", {"soft_cap": 20, "spawns": 0, "child_spawns": 0})

    def record_fitness(self, cycle_id: str, metrics: dict[str, float]) -> dict[str, Any]:
        row = {"ts": _utc_now(), "cycle_id": cycle_id, **metrics}
        self.data.setdefault("fitness_history", []).append(row)
        if len(self.data["fitness_history"]) > 100:
            self.data["fitness_history"] = self.data["fitness_history"][-100:]
        if self.workshop is not None:
            self.workshop.append_fitness(row)
        return row

    def update_skills_from_fitness(self, metrics: dict[str, float]) -> dict[str, float]:
        mapping = [
            ("tribute_keeper", "tribute", metrics["tribute_quality"]),
            ("pathfinder", "gather", metrics["gather_coverage"]),
            ("memory_weaver", "gather", metrics["gather_coverage"]),
            ("coverage_auditor", "gather", metrics["gather_coverage"]),
            ("surveyor", "gather", metrics["gather_coverage"]),
            ("naturalist", "gather", metrics["gather_coverage"]),
            ("chronicler", "gather", metrics["gather_coverage"]),
            ("geometer", "gather", metrics["gather_coverage"]),
            ("archivist", "gather", metrics.get("commons_signal", metrics["gather_coverage"])),
            ("builder", "build", metrics["build_reuse"]),
            ("systems_smith", "build", metrics["build_reuse"]),
            ("herald", "communicate", metrics["comm_reply_rate"]),
            ("courier", "communicate", metrics["comm_reply_rate"]),
            ("scribe", "communicate", metrics.get("reply_quality", metrics["comm_reply_rate"])),
            ("messenger", "communicate", metrics.get("reply_quality", metrics["comm_reply_rate"])),
            ("legislator", "improve", metrics["aggregate"]),
            ("improver", "improve", metrics["aggregate"]),
            ("spark", "emergence", metrics["aggregate"]),
        ]
        updated: dict[str, float] = {}
        active = self.registry.active()
        for role, skill, success in mapping:
            if role in active:
                updated[f"{role}.{skill}"] = self.registry.record_outcome(role, skill, success)
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

    
    def hard_tier_emergence(self, cycle_id: str) -> dict[str, Any]:
        """Lift 4: spawn on measured hard-tier fitness gaps; retire when no lift."""
        delta = hard_tier_delta(self.data)
        hist = self.data.get("hard_tier_history") or []
        cur = hist[-1] if hist else {}
        gap = int(cur.get("n_hard") or 0) > int(cur.get("n_hard_pass") or 0)
        # Also treat flat hard_pass across last 3 cycles as gap to fill via new role pressure
        recent = hist[-3:]
        flat = len(recent) >= 3 and len({r.get("n_hard_pass") for r in recent}) == 1
        spawn_roles: list[str] = []
        retire_roles: list[str] = []
        # SPARK: Oracle-pass lift gate for specialist spawn (no theater spawn)
        oracle_lift_now = 0
        try:
            from colony.oracle import counts as _oracle_counts
            _oc = _oracle_counts()
            oracle_lift_now = int(_oc.get("passes") or 0)
        except Exception:
            oracle_lift_now = int(self.data.get("oracle_pass_total") or 0)
        prev_oracle = int(self.data.get("oracle_pass_total_prev") or oracle_lift_now)
        oracle_pass_lift = oracle_lift_now - prev_oracle
        metrics_agg = float((self.data.get("fitness_history") or [{}])[-1].get("aggregate") or 0)
        if gap or (flat and metrics_agg < 0.95):
            # Prefer geometer/improver pressure — signal only (spark enacts)
            for role in ("geometer", "improver"):
                if role not in self.registry.active():
                    spawn_roles.append(role)
            # SPARK: oracle_scribe/stem_checker spawn ONLY on Oracle-pass fitness lift
            if oracle_pass_lift > 0 or gap:
                for role in ("oracle_scribe", "stem_checker"):
                    if role not in self.registry.active() and role not in spawn_roles:
                        spawn_roles.append(role)
        # Kill criteria: decorative roles that never lift hard tier
        ht_log = self.data.setdefault("hard_tier_role_credit", {})
        if delta > 0:
            # credit active math roles
            for role in ("geometer", "improver", "spark"):
                if role in self.registry.active():
                    ht_log[role] = int(ht_log.get(role) or 0) + int(delta)
        else:
            founding = set(self.data.get("founding_roles") or ["spark", "tribute_keeper"])
            # Flourish: Oracle-pass lift credit — retire specialists with no lift
            oracle_lift = 0
            try:
                from colony.oracle import counts as oracle_counts
                oc = oracle_counts()
                oracle_lift = int(oc.get("passes") or 0)
                self.data["oracle_pass_total"] = oracle_lift
            except Exception:
                oracle_lift = int(self.data.get("oracle_pass_total") or 0)
            prev_lift = int(self.data.get("oracle_pass_total_prev") or oracle_lift)
            lift_delta = oracle_lift - prev_lift
            self.data["oracle_pass_total_prev"] = oracle_lift
            for role, agent in list(self.registry.active().items()):
                if role in founding:
                    continue
                if int(agent.get("cycles_served") or 0) < 6:
                    continue
                credit = int(ht_log.get(role) or 0)
                # Retire if many cycles and zero hard-tier credit and low contribution
                if credit <= 0 and float(agent.get("contribution_score") or 0) < 0.25:
                    # only mark candidates; maybe_retire still executes leave
                    agent["hard_tier_kill_candidate"] = True
                    retire_roles.append(role)
                # Flourish specialists: retire when no Oracle-pass lift
                if role in ("oracle_scribe", "stem_checker", "debate_deepener", "systems_smith", "coverage_auditor"):
                    if lift_delta <= 0 and int(agent.get("cycles_served") or 0) >= 4:
                        if float(agent.get("contribution_score") or 0) < 0.40:
                            agent["oracle_no_lift_retire"] = True
                            agent["hard_tier_kill_candidate"] = True
                            if role not in retire_roles:
                                retire_roles.append(role)
        self.data.setdefault("evolution_log", []).append(
            {
                "ts": _utc_now(),
                "cycle_id": cycle_id,
                "event": "hard_tier_emergence",
                "delta_pass": delta,
                "gap": gap,
                "flat": flat,
                "spawn_signals": spawn_roles,
                "kill_candidates": retire_roles[:3],
                "snapshot": cur,
            }
        )
        out = {
            "delta_pass": delta,
            "gap": gap,
            "spawn_signals": spawn_roles,
            "kill_candidates": retire_roles[:3],
            "snapshot": cur,
        }
        try:
            from colony.exploration_budget import apply_hard_tier_spawn_retire
            apply_hard_tier_spawn_retire(evo=self, cycle_id=cycle_id, delta_pass=delta)
        except Exception:
            pass
        return out

    def maybe_spawn(self, cycle_id: str, metrics: dict[str, float]) -> list[str]:
        """Spawn pressure roles when a metric stays weak. Hard-tier gaps also signal."""
        ht = self.hard_tier_emergence(cycle_id)
        spawned: list[str] = list(ht.get("spawn_signals") or [])
        if self.registry.at_capacity():
            return spawned
        history = self.data.get("fitness_history") or []
        for idea in self.SPAWN_MENU:
            role = idea["role"]
            if role in self.registry.agents() and self.registry.agents()[role].get("status") == "active":
                continue
            if role in (self.data.get("roles") or {}):
                self.registry.enter(role, reason="respawn", cycle_id=cycle_id)
                continue
            metric = idea["when_metric"]
            recent = [h.get(metric, 1.0) for h in history[-3:]]
            if not recent:
                continue
            weak = sum(1 for v in recent if float(v) < float(idea["below"]))
            if weak >= min(2, len(recent)) or (
                len(recent) == 1 and float(recent[0]) < float(idea["below"]) * 0.8
            ):
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

    def maybe_spawn_child(self, cycle_id: str, metrics: dict[str, float]) -> dict[str, Any] | None:
        """Spawn a child agent from high-fitness parents with mutated genome.

        Soft pop cap enforced. Returns spawn spec or None.
        """
        if self.registry.at_capacity():
            return None
        # Need decent aggregate (spawn privilege lowers threshold when citations reuse accepted findings)
        spawn_floor = float((self.data.get("spawn_privilege") or {}).get("threshold") or 0.45)
        if float(metrics.get("aggregate") or 0) < spawn_floor:
            return None
        active = self.registry.active()
        if len(active) < 3:
            return None
        # Limit child spawn frequency: at most one every other cycle when pop high
        pop = self.data.setdefault("population", {})
        last_child = pop.get("last_child_cycle")
        history = self.data.get("fitness_history") or []
        if last_child and len(history) >= 1 and self.registry.active_count() > 12:
            # allow but don't spam — skip if last cycle already spawned child
            if last_child == (history[-1].get("cycle_id") if history else None):
                return None
        # Also skip if we already spawned a child this exact cycle via log
        for ev in (self.data.get("evolution_log") or [])[-5:]:
            if ev.get("cycle_id") == cycle_id and ev.get("event") == "child_spawn_signal":
                return None

        existing = set(self.data.get("roles") or {}) | set(active.keys())
        spec = child_role_available(existing)
        if not spec:
            return None
        parents = pick_parents(
            active, n=2, prefer_traits=tuple(spec.get("prefer_traits") or ())
        )
        if not parents:
            return None
        parent_genomes = []
        for p in parents:
            g = (active.get(p) or {}).get("genome")
            if g:
                parent_genomes.append(g)
        genome = new_genome(
            spec["role"],
            parents=parents,
            parent_genomes=parent_genomes,
            cycle_id=cycle_id,
        )
        genome["fitness_at_birth"] = metrics.get("aggregate")
        persist_genome(genome)
        signal = {
            "role": spec["role"],
            "description": spec["description"],
            "parents": parents,
            "genome": genome,
            "prefer_traits": list(spec.get("prefer_traits") or []),
        }
        pop["last_child_cycle"] = cycle_id
        self.data.setdefault("evolution_log", []).append(
            {
                "ts": _utc_now(),
                "cycle_id": cycle_id,
                "event": "child_spawn_signal",
                "role": spec["role"],
                "parents": parents,
                "generation": genome.get("generation"),
                "mutated_keys": genome.get("mutated_keys"),
                "fitness": metrics.get("aggregate"),
            }
        )
        return signal

    def spawn_spec(self, role: str) -> dict[str, Any] | None:
        for idea in self.SPAWN_MENU:
            if idea["role"] == role:
                return idea
        return None

    def maybe_retire(self, cycle_id: str) -> list[str]:
        retired: list[str] = []
        # Prefer retire when at/over soft cap
        force = self.registry.active_count() >= self.registry.soft_cap()
        threshold = 0.22 if force else 0.15
        min_cycles = 3 if force else 4
        candidates = self.registry.low_contributors(min_cycles=min_cycles, threshold=threshold)
        if force and not candidates:
            # Retire lowest non-founding by fitness_score
            founding = set(self.data.get("founding_roles") or ["spark", "tribute_keeper"])
            scored = []
            for role, a in self.registry.active().items():
                if role in founding:
                    continue
                if int(a.get("cycles_served") or 0) < 3:
                    continue
                scored.append((role, fitness_score(a)))
            scored.sort(key=lambda x: x[1])
            candidates = [r for r, _ in scored[:2]]
        # Prefer hard-tier kill candidates (Lift 4)
        kill_pref = [
            r for r, a in self.registry.active().items()
            if a.get("hard_tier_kill_candidate") and r not in (self.data.get("founding_roles") or ["spark", "tribute_keeper"])
        ]
        if kill_pref:
            candidates = list(dict.fromkeys(kill_pref + candidates))
        for role in candidates:
            agent = self.registry.agents().get(role) or {}
            if int(agent.get("cycles_served") or 0) < min_cycles and not force and not agent.get("hard_tier_kill_candidate"):
                continue
            reason = (
                "hard_tier_no_lift"
                if agent.get("hard_tier_kill_candidate")
                else ("low_contribution" if not force else "pop_cap")
            )
            self.registry.leave(role, reason=reason)
            roles = self.data.get("roles") or {}
            if role in roles:
                roles[role]["status"] = "retired"
                roles[role]["retired_at"] = _utc_now()
                roles[role]["retire_reason"] = reason
            retired.append(role)
            self.data.setdefault("evolution_log", []).append(
                {
                    "ts": _utc_now(),
                    "cycle_id": cycle_id,
                    "event": "role_retired",
                    "role": role,
                    "contribution": agent.get("contribution_score"),
                    "fitness": fitness_score(agent) if agent else None,
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
        import re as _re
        def _canon(s: str) -> str:
            return _re.sub(r"\s+", " ", (s or "").strip().lower())
        fp = hashlib.sha1(f"{_canon(title)}|{_canon(action)}".encode()).hexdigest()[:12]
        # Phase 4 / 1: block repeats (≥3 identical in recent proposals / lessons)
        try:
            from colony.lessons import write_lesson, proposal_fingerprint_counts
            counts = proposal_fingerprint_counts(days=14)
            recent = self.data.get("improvement_proposals") or []
            recent_fp_n = sum(1 for p in recent[-80:] if p.get("fingerprint") == fp)
            if counts.get(fp, 0) >= 3 or recent_fp_n >= 3:
                write_lesson(
                    decision="block",
                    check="dedupe",
                    what=f"blocked repeat: {title[:80]}",
                    source="growth_hearing",
                    cycle_id=cycle_id,
                    lesson_type="repeat_proposal",
                    family="process",
                    proposal_fingerprint=fp,
                    tags=["repeat_proposal"],
                )
                # Archive older duplicates (witness — do not delete)
                archive = self.data.setdefault("improvement_proposals_archived", [])
                kept = []
                for p in recent:
                    if p.get("fingerprint") == fp and p.get("status") in ("rejected", "deferred", "candidate"):
                        archive.append(p)
                    else:
                        kept.append(p)
                # Keep last 2 of this fp inline max
                same = [p for p in kept if p.get("fingerprint") == fp]
                other = [p for p in kept if p.get("fingerprint") != fp]
                self.data["improvement_proposals"] = other + same[-2:]
                return {
                    "id": f"imp_blocked_{fp}",
                    "ts": _utc_now(),
                    "cycle_id": cycle_id,
                    "title": title,
                    "hypothesis": hypothesis,
                    "action": action,
                    "status": "blocked_repeat",
                    "fingerprint": fp,
                    "P": 0.0,
                    "note": "repeat_proposal blocked",
                }
        except Exception:
            pass
        # Compute standing-trust P (Phase 3)
        P = None
        P_terms = {}
        try:
            from colony.standing_trust import compute_proposal_P
            P, P_terms = compute_proposal_P(
                mutation=title,
                action=action,
                fingerprint=fp,
                bench_delta=None,
            )
        except Exception:
            pass
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
            "status": "candidate",
            "attempted_by": self.registry.best_for("improve"),
            "fingerprint": fp,
            "P": P,
            "P_terms": P_terms,
            "confidence": P,
            "machine_checked": P is not None,
        }
        self.data.setdefault("improvement_proposals", []).append(prop)
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
        closed: list[dict[str, Any]] = []
        for prop in self.data.get("improvement_proposals") or []:
            if prop.get("after_metrics") is None and prop.get("cycle_id") != cycle_id:
                prop["after_metrics"] = dict(metrics)
                prop["measured_cycle"] = cycle_id
                before = float((prop.get("before_metrics") or {}).get("aggregate") or 0)
                after = float(metrics.get("aggregate") or 0)
                prop["delta_aggregate"] = round(after - before, 4)
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
                "Using coverage_index + topic_priority so gather targets thin standing topics incl. STEM.",
                "system_use:topic_priority",
            ),
            "build_reuse": (
                "Raise system reuse",
                "Forcing growth loop to load existing systems (incl. common_knowledge) before writing new notes.",
                "mandate:use_systems_each_cycle",
            ),
            "comm_reply_rate": (
                "Close communication loops",
                "Herald/courier/messenger reply with higher-quality ACKs; broadcast commons digests.",
                "mandate:reply_unread",
            ),
        }
        return plans[weakest]
