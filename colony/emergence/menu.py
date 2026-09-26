"""Emergence menu for Spark."""

from __future__ import annotations

from typing import Any

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
        "type": "ritual",
        "name": "Lighting of the Growth Loop",
        "description": (
            "Each cycle: invent/build artifacts, communicate on the bulletin, "
            "gather information, and attempt self-improvement — all under the hard ceiling."
        ),
        "when": "growth_will",
    },
    {
        "type": "norm",
        "text": "Grow by building, speaking, gathering, and improving — durable truth waits for the creator.",
        "when": "growth_will",
    },
    {
        "type": "new_role",
        "name": "builder",
        "description": (
            "Invents and writes concrete artifacts for the colony — tools, notes, "
            "blueprints — so growth leaves footprints the creator can witness."
        ),
        "when": "growth_will",
    },
    {
        "type": "new_role",
        "name": "herald",
        "description": (
            "Carries messages between roles and posts to the Society Bulletin so "
            "the city communicates instead of siloing."
        ),
        "when": "growth_will",
    },
    {
        "type": "institution",
        "name": "Workshop of Making",
        "kind": "workshop",
        "description": "Where builders leave artifacts: notes, tools, and blueprints for the creator.",
        "when": "growth_will",
    },
    {
        "type": "institution",
        "name": "Society Bulletin",
        "kind": "bulletin",
        "description": "Public board for inter-role messages and cycle announcements.",
        "when": "growth_will",
    },
    {
        "type": "new_role",
        "name": "pathfinder",
        "description": (
            "Scouts adjacent public sources and synthesizes gathered threads when "
            "the will asks the city to gather information."
        ),
        "when": "growth_or_thin",
    },
    {
        "type": "new_role",
        "name": "improver",
        "description": (
            "Proposes and attempts process self-improvements oriented to helping "
            "the creator — logged as candidates, until the human authorizes."
        ),
        "when": "growth_will",
    },
    {
        "type": "council",
        "name": "Forum of Exchange",
        "purpose": (
            "A place for herald, builder, pathfinder, and spark to trade signals: "
            "what was built, said, gathered, and attempted."
        ),
        "members_from": ["spark", "herald", "builder", "pathfinder", "improver", "tribute_keeper"],
        "when": "growth_will",
    },
    {
        "type": "norm",
        "text": "Standing RSI research remains valuable as gathering — broader will is grow + build + communicate + gather + improve.",
        "when": "growth_will",
    },
]
