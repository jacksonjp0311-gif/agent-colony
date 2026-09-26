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
