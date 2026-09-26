"""Agent genomes — heritable trait vectors with mutation on spawn.

Machine-legible scaffolding for fitness-linked selection. Not biological DNA,
not AGI: JSON trait weights that bias skills and child spawn.
"""

from __future__ import annotations

import json
import random
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
GENOMES_DIR = ROOT / "society" / "genomes"

TRAIT_KEYS = ("gather", "build", "reply", "explore", "govern")

ROLE_TRAIT_BIAS: dict[str, dict[str, float]] = {
    "spark": {"explore": 0.75, "govern": 0.55, "reply": 0.6},
    "tribute_keeper": {"gather": 0.85, "explore": 0.5},
    "builder": {"build": 0.9, "explore": 0.45},
    "systems_smith": {"build": 0.92, "explore": 0.5},
    "herald": {"reply": 0.9, "gather": 0.4},
    "courier": {"reply": 0.92},
    "pathfinder": {"gather": 0.85, "explore": 0.8},
    "coverage_auditor": {"gather": 0.9, "explore": 0.55},
    "memory_weaver": {"gather": 0.65, "reply": 0.55, "explore": 0.5},
    "improver": {"explore": 0.7, "build": 0.55, "govern": 0.4},
    "scribe": {"reply": 0.7, "gather": 0.6, "build": 0.5},
    "surveyor": {"explore": 0.9, "gather": 0.7},
    "archivist": {"gather": 0.75, "build": 0.55, "reply": 0.5},
    "legislator": {"govern": 0.9, "reply": 0.55},
    "chronicler": {"gather": 0.7, "explore": 0.65, "reply": 0.5},
    "naturalist": {"gather": 0.8, "explore": 0.85},
    "geometer": {"gather": 0.75, "explore": 0.7, "build": 0.45},
    "messenger": {"reply": 0.88, "explore": 0.5},
    # Flourish specialists — aligned to CREATOR_WILL_ASK / Oracle gates
    "oracle_scribe": {"gather": 0.7, "explore": 0.8, "govern": 0.65, "reply": 0.55},
    "stem_checker": {"gather": 0.7, "build": 0.65, "explore": 0.75},
}

CHILD_ROLE_POOL = [
    {
        "role": "scribe",
        "description": (
            "Writes commons digests and raises reply quality; heritable reply/gather traits."
        ),
        "prefer_traits": ("reply", "gather"),
    },
    {
        "role": "surveyor",
        "description": (
            "Explores thin domains (science/history/math) and feeds topic_priority."
        ),
        "prefer_traits": ("explore", "gather"),
    },
    {
        "role": "archivist",
        "description": (
            "Maintains common_knowledge candidates so later cycles reuse shared notes."
        ),
        "prefer_traits": ("gather", "build"),
    },
    {
        "role": "legislator",
        "description": (
            "Drafts law/norm proposals for the Chamber of Laws — candidate until authorize."
        ),
        "prefer_traits": ("govern", "reply"),
    },
    {
        "role": "chronicler",
        "description": "Gathers history-of-ideas threads into the commons.",
        "prefer_traits": ("gather", "explore"),
    },
    {
        "role": "naturalist",
        "description": "Gathers science-method and empiricism threads into the commons.",
        "prefer_traits": ("gather", "explore"),
    },
    {
        "role": "geometer",
        "description": "Gathers mathematics-foundations threads into the commons.",
        "prefer_traits": ("gather", "explore"),
    },
    {
        "role": "messenger",
        "description": "Broadcasts commons digests on science/history/math channels.",
        "prefer_traits": ("reply", "explore"),
    },
    {
        "role": "oracle_scribe",
        "description": (
            "Records Oracle HEAR/SENSE/vote; presses hard/STEM enables when fitness gaps appear."
        ),
        "prefer_traits": ("explore", "gather", "govern"),
    },
    {
        "role": "stem_checker",
        "description": (
            "Runs STEM domain pack checks (kinematics); retire when no Oracle-pass lift."
        ),
        "prefer_traits": ("explore", "build", "gather"),
    },
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clamp(v: float, lo: float = 0.05, hi: float = 0.99) -> float:
    return max(lo, min(hi, float(v)))


def blank_traits(role: str) -> dict[str, float]:
    traits = {k: 0.5 for k in TRAIT_KEYS}
    for k, v in ROLE_TRAIT_BIAS.get(role, {}).items():
        if k in traits:
            traits[k] = max(traits[k], float(v))
    return {k: round(float(v), 4) for k, v in traits.items()}


def mutate_traits(
    parent_traits: dict[str, float],
    *,
    rate: float = 0.12,
    rng: random.Random | None = None,
) -> tuple[dict[str, float], list[str]]:
    """Gaussian-ish mutation on trait weights. Returns (traits, mutated_keys)."""
    r = rng or random.Random()
    out = {}
    mutated: list[str] = []
    for k in TRAIT_KEYS:
        base = float(parent_traits.get(k, 0.5))
        if r.random() < rate:
            delta = (r.random() - 0.5) * 0.28
            out[k] = round(_clamp(base + delta), 4)
            mutated.append(k)
        else:
            out[k] = round(_clamp(base + (r.random() - 0.5) * 0.04), 4)
    return out, mutated


def crossover(
    a: dict[str, float],
    b: dict[str, float],
    *,
    rng: random.Random | None = None,
) -> dict[str, float]:
    r = rng or random.Random()
    return {
        k: round(float(a.get(k, 0.5) if r.random() < 0.5 else b.get(k, 0.5)), 4)
        for k in TRAIT_KEYS
    }


def new_genome(
    role: str,
    *,
    parents: list[str] | None = None,
    parent_genomes: list[dict[str, Any]] | None = None,
    generation: int | None = None,
    cycle_id: str = "",
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Create a genome, optionally mutating from parent genome(s)."""
    r = rng or random.Random(f"{role}:{cycle_id}:{parents}")
    parents = list(parents or [])
    parent_genomes = list(parent_genomes or [])
    mutated_keys: list[str] = []
    if len(parent_genomes) >= 2:
        traits = crossover(
            parent_genomes[0].get("traits") or blank_traits(role),
            parent_genomes[1].get("traits") or blank_traits(role),
            rng=r,
        )
        traits, mutated_keys = mutate_traits(traits, rate=0.18, rng=r)
        gen = max(int(g.get("generation") or 0) for g in parent_genomes) + 1
    elif len(parent_genomes) == 1:
        traits, mutated_keys = mutate_traits(
            parent_genomes[0].get("traits") or blank_traits(role), rate=0.2, rng=r
        )
        gen = int(parent_genomes[0].get("generation") or 0) + 1
    else:
        traits = blank_traits(role)
        gen = 0 if generation is None else int(generation)
    genome = {
        "role": role,
        "traits": traits,
        "parents": parents,
        "generation": gen if generation is None else int(generation),
        "mutated_keys": mutated_keys,
        "born_cycle": cycle_id or None,
        "born_at": _utc_now(),
        "fitness_at_birth": None,
        "version": 1,
    }
    return genome


def apply_genome_to_skills(skills: dict[str, float], genome: dict[str, Any]) -> dict[str, float]:
    """Bias skill weights from genome traits (soft, bounded)."""
    traits = genome.get("traits") or {}
    mapping = {
        "gather": "gather",
        "build": "build",
        "reply": "communicate",
        "explore": "emergence",
        "govern": "improve",
    }
    out = dict(skills)
    for trait, skill in mapping.items():
        t = float(traits.get(trait, 0.5))
        old = float(out.get(skill, 0.5))
        out[skill] = round(_clamp(0.65 * old + 0.35 * t), 4)
    return out


def fitness_score(agent: dict[str, Any]) -> float:
    """Selection fitness: contribution + trait mean + cycles soft factor."""
    contrib = float(agent.get("contribution_score") or 0.0)
    genome = agent.get("genome") or {}
    traits = genome.get("traits") or {}
    trait_mean = (
        sum(float(traits.get(k, 0.5)) for k in TRAIT_KEYS) / len(TRAIT_KEYS)
        if traits
        else 0.5
    )
    cycles = int(agent.get("cycles_served") or 0)
    cycle_factor = min(1.0, cycles / 8.0)
    return round(0.55 * contrib + 0.30 * trait_mean + 0.15 * cycle_factor, 4)


def pick_parents(
    active_agents: dict[str, dict[str, Any]],
    *,
    n: int = 2,
    prefer_traits: tuple[str, ...] | None = None,
) -> list[str]:
    """Fitness-linked parent selection (weighted sample without replacement)."""
    scored: list[tuple[str, float]] = []
    for role, agent in active_agents.items():
        if agent.get("status") != "active":
            continue
        score = fitness_score(agent)
        if prefer_traits:
            traits = (agent.get("genome") or {}).get("traits") or {}
            bonus = sum(float(traits.get(t, 0.5)) for t in prefer_traits) / max(
                len(prefer_traits), 1
            )
            score = score * 0.7 + bonus * 0.3
        scored.append((role, max(0.01, score)))
    if not scored:
        return []
    scored.sort(key=lambda x: -x[1])
    top = scored[: max(2, len(scored) // 2 + 1)]
    picked: list[str] = []
    pool = list(top)
    rng = random.Random(sum(int(s * 1000) for _, s in pool) + len(pool))
    while pool and len(picked) < n:
        weights = [s for _, s in pool]
        total = sum(weights) or 1.0
        draw = rng.random() * total
        acc = 0.0
        choice_i = 0
        for i, w in enumerate(weights):
            acc += w
            if acc >= draw:
                choice_i = i
                break
        picked.append(pool[choice_i][0])
        pool.pop(choice_i)
    return picked


def persist_genome(genome: dict[str, Any], root: Path | None = None) -> Path:
    """Write per-agent genome JSON under society/genomes/."""
    base = (root or ROOT) / "society" / "genomes"
    base.mkdir(parents=True, exist_ok=True)
    role = genome.get("role") or "unknown"
    path = base / f"{role}.json"
    path.write_text(json.dumps(genome, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_genome(role: str, root: Path | None = None) -> dict[str, Any] | None:
    path = (root or ROOT) / "society" / "genomes" / f"{role}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_agent_genome(
    agent: dict[str, Any],
    role: str,
    *,
    cycle_id: str = "",
    root: Path | None = None,
) -> dict[str, Any]:
    """Attach genome to agent if missing; persist JSON."""
    if agent.get("genome") and isinstance(agent["genome"], dict):
        g = agent["genome"]
        persist_genome(g, root=root)
        return g
    disk = load_genome(role, root=root)
    if disk:
        agent["genome"] = disk
        return disk
    g = new_genome(role, cycle_id=cycle_id)
    agent["genome"] = g
    agent["skills"] = apply_genome_to_skills(agent.get("skills") or {}, g)
    persist_genome(g, root=root)
    return g


def child_role_available(existing_roles: set[str]) -> dict[str, Any] | None:
    for spec in CHILD_ROLE_POOL:
        if spec["role"] not in existing_roles:
            return spec
    return None


def snapshot_population(agents: dict[str, dict[str, Any]]) -> dict[str, Any]:
    active = {k: v for k, v in agents.items() if v.get("status") == "active"}
    genomes = []
    for role, a in sorted(active.items()):
        g = a.get("genome") or {}
        genomes.append(
            {
                "role": role,
                "generation": g.get("generation", 0),
                "traits": g.get("traits") or {},
                "parents": g.get("parents") or [],
                "fitness": fitness_score(a),
                "contribution": a.get("contribution_score"),
            }
        )
    return {
        "active_count": len(active),
        "retired_count": sum(1 for v in agents.values() if v.get("status") == "retired"),
        "genomes": genomes,
        "ts": _utc_now(),
    }
