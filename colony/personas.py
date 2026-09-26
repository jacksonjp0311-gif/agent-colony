"""Durable per-agent personas — engineered character, not sentience.

Personas are role-posture / self-model *artifacts* inspired by the stance
"I think therefore I am" as a first-person working posture for messages and
notes. They are JSON character sheets under society/personas/. Genome traits
may bias voice/quirks. This is civilization scaffolding, not consciousness.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PERSONAS_DIR = ROOT / "society" / "personas"

# See full module on box; stub redirect note for partial push safety.
# Full colony/personas.py is maintained locally and in subsequent push batches.

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Minimal export surface so imports succeed if only this stub landed.
# Prefer the full file from the box / later commits.
PERSONA_SEEDS: dict[str, dict[str, Any]] = {}


def blank_persona(role: str, *, genome: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "role": role,
        "version": 1,
        "engineered_character": True,
        "not_sentience": True,
        "not_agi": True,
        "display_name": role.replace("_", " ").title(),
        "voice": "plain, cooperative, ceiling-aware",
        "values": ["help the creator", "candidate until authorize", "witness"],
        "quirks": ["names their role", "avoids AGI theater"],
        "first_person_stance": (
            f"I act as `{role}`. This first-person stance is an engineered "
            "role posture / self-model artifact, not a claim of consciousness."
        ),
        "signature": f"— {role}",
        "genome_influence": {"genome_flavor": [], "traits_snapshot": {}},
        "born_at": _utc_now(),
        "updated_at": _utc_now(),
        "note": "Personas are durable engineered character sheets.",
    }


def persist_persona(persona: dict[str, Any], root: Path | None = None) -> Path:
    base = (root or ROOT) / "society" / "personas"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{persona.get('role') or 'unknown'}.json"
    path.write_text(json.dumps(persona, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_persona(role: str, root: Path | None = None) -> dict[str, Any] | None:
    path = (root or ROOT) / "society" / "personas" / f"{role}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_persona(role: str, *, genome: dict[str, Any] | None = None, agent: dict[str, Any] | None = None, root: Path | None = None, refresh_genome: bool = True) -> dict[str, Any]:
    disk = load_persona(role, root=root)
    persona = disk or blank_persona(role, genome=genome)
    if agent is not None:
        agent["persona"] = {
            "display_name": persona["display_name"],
            "voice": persona.get("voice"),
            "signature": persona.get("signature"),
            "engineered_character": True,
        }
    persist_persona(persona, root=root)
    return persona


def voice_wrap(role: str, message: str, *, root: Path | None = None, persona: dict[str, Any] | None = None) -> str:
    p = persona or load_persona(role, root=root) or blank_persona(role)
    quirk = (p.get("quirks") or ["speaks in role"])[0]
    stance_snip = (p.get("first_person_stance") or "")[:110]
    sig = p.get("signature") or f"— {role}"
    return (
        f"[{p.get('display_name', role)} | {p.get('voice', 'plain')}] "
        f"{message.strip()} "
        f"(quirk: {quirk}; stance: {stance_snip}…) {sig}"
    )


def evolve_note_voice(role: str, body: str, *, root: Path | None = None) -> str:
    p = load_persona(role, root=root) or blank_persona(role)
    return (
        f"_Persona voice ({p.get('display_name')}): {p.get('voice')}_\n\n"
        f"> {p.get('first_person_stance')}\n\n"
        f"{body.strip()}\n\n"
        f"{p.get('signature')}\n"
    )


def ensure_all_active(agents: dict[str, dict[str, Any]], *, root: Path | None = None) -> list[str]:
    ensured: list[str] = []
    for role, agent in agents.items():
        if agent.get("status") != "active":
            continue
        ensure_persona(role, genome=agent.get("genome"), agent=agent, root=root)
        ensured.append(role)
    return ensured
