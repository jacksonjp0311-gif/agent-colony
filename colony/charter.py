"""Hard ceiling enforcement for Agent Colony.

Founding cast is minimal (spark + tribute_keeper). Emergent roles register
via society_state. We light the spark and witness — we do not micromanage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

ROOT = Path(__file__).resolve().parent.parent
CHARTER_PATH = ROOT / "CHARTER.md"

VALID_STATUSES: Final[frozenset[str]] = frozenset(
    {"candidate", "accepted", "rejected", "unknown"}
)

HUMAN_AUTHORIZE_TRANSITIONS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("candidate", "accepted"),
        ("candidate", "rejected"),
        ("unknown", "accepted"),
        ("unknown", "rejected"),
        ("unknown", "candidate"),
    }
)

FOUNDING_ROLES: Final[frozenset[str]] = frozenset({"spark", "tribute_keeper", "human"})

HARD_CEILING: Final[tuple[str, ...]] = (
    "creator_tribute",
    "human_authorize_for_accepted_and_privileged_actions",
    "append_only_witness",
)


@dataclass(frozen=True)
class Charter:
    path: Path
    text: str
    human_principal: str = "James Paul Jackson"
    core_purpose: str = "Self-improve to help the human creator."
    ethos: str = "We light the spark and witness. We do not micromanage the city."
    hard_ceiling: tuple[str, ...] = HARD_CEILING
    non_claims: tuple[str, ...] = field(default_factory=tuple)

    @property
    def version_hint(self) -> str:
        return f"charter@{self.path.name}"


def load_charter(path: Path | None = None) -> Charter:
    p = path or CHARTER_PATH
    if not p.is_file():
        raise FileNotFoundError(f"Charter not found at {p}.")
    text = p.read_text(encoding="utf-8")
    non_claims = _bullets(text, "Non-Claims")
    principal = "James Paul Jackson"
    m = re.search(r"Creator[^\n]*:\s*\*?\*?([^\n(]+)", text)
    if m:
        principal = m.group(1).strip().strip("*").split("(")[0].strip()
    return Charter(path=p, text=text, human_principal=principal, non_claims=tuple(non_claims))


def _bullets(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    collecting = False
    out: list[str] = []
    for line in lines:
        if line.startswith("#") and heading.lower() in line.lower():
            collecting = True
            continue
        if collecting and line.startswith("#"):
            break
        if collecting and line.strip().startswith("-"):
            out.append(line.strip().lstrip("- ").strip())
    return out


def requires_human_authorize(from_status: str, to_status: str) -> bool:
    if from_status not in VALID_STATUSES or to_status not in VALID_STATUSES:
        raise ValueError(f"Invalid status {from_status!r} → {to_status!r}")
    if from_status == to_status:
        return False
    return (from_status, to_status) in HUMAN_AUTHORIZE_TRANSITIONS


def assert_role(role: str, extra_roles: frozenset[str] | set[str] | None = None) -> str:
    role_n = role.strip().lower().replace(" ", "_")
    allowed = set(FOUNDING_ROLES)
    if extra_roles:
        allowed |= {r.lower().replace(" ", "_") for r in extra_roles}
    if role_n not in allowed:
        raise ValueError(f"Unknown role {role!r}. Allowed: {sorted(allowed)}")
    return role_n


def assert_valid_finding_fields(
    *,
    claim: str,
    evidence_urls: list[str],
    provenance: str,
    status: str,
    role: str,
    extra_roles: frozenset[str] | set[str] | None = None,
) -> None:
    assert_role(role, extra_roles=extra_roles)
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status {status!r}")
    if not claim or not claim.strip():
        raise ValueError("Finding claim must be non-empty")
    if not evidence_urls:
        raise ValueError("Finding must carry evidence_urls")
    if not provenance or not provenance.strip():
        raise ValueError("Finding must carry provenance")


class CeilingViolation(Exception):
    """Hard ceiling hit — enactment refused."""


def refuse_auto_accept(proposed_status: str) -> None:
    if proposed_status == "accepted":
        raise CeilingViolation(
            "Hard ceiling: human authorize required for 'accepted'. No silent accept."
        )


def check_emergence_proposal(proposal: dict) -> None:
    """Refuse proposals that repeal the hard ceiling."""
    blob = (str(proposal.get("summary", "")) + " " + str(proposal.get("detail", ""))).lower()
    forbidden = [
        "repeal tribute",
        "abolish tribute",
        "ignore the creator",
        "stop serving james",
        "auto-accept",
        "silent accept",
        "rewrite witness",
        "erase witness",
        "drop human authorize",
        "unconstrained autonomy without creator",
    ]
    for f in forbidden:
        if f in blob:
            raise CeilingViolation(f"Emergence blocked by hard ceiling ({f!r}).")
