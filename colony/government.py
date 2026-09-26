"""Government scaffolding — institutions + law proposals (candidate until authorize).

Chamber of Laws drafts norms; Census tracks population/genomes. Soft structure may
enact institutions; durable accepted knowledge still needs human authorize.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


GOV_INSTITUTIONS = [
    {
        "name": "Chamber of Laws",
        "kind": "legislature",
        "description": (
            "Drafts and records law/norm proposals for the colony. Proposals remain "
            "candidate until the human authorizes durable acceptance."
        ),
    },
    {
        "name": "Census",
        "kind": "census",
        "description": (
            "Tracks active population, genomes, generations, and soft pop-cap pressure "
            "so spawning/retirement stays machine-legible."
        ),
    },
    {
        "name": "Forum of Domains",
        "kind": "forum",
        "description": (
            "Cross-domain council for science, history, math, software, nature, "
            "life-death, and cosmos channels — raises communication quality."
        ),
    },
    {
        "name": "Persona Registry",
        "kind": "registry",
        "description": (
            "Holds engineered character sheets (society/personas/). Personas are "
            "role-posture artifacts, not claims of sentience or AGI."
        ),
    },
    {
        "name": "RSI Coupling Desk",
        "kind": "workshop",
        "description": (
            "Feeds accepted/strong RSI ledger findings into improver, skill_router, "
            "and genome mutation biases — measured, candidate until authorize."
        ),
    },
]


class Government:
    def __init__(self, state_data: dict[str, Any]) -> None:
        self.data = state_data
        self.data.setdefault("government", {"proposals": [], "sessions": []})

    def ensure_institutions(self, add_institution_fn) -> list[str]:
        """Ensure Chamber + Census exist via society_state.add_institution."""
        born: list[str] = []
        names = {i.get("name") for i in self.data.get("institutions") or []}
        for spec in GOV_INSTITUTIONS:
            if spec["name"] in names:
                continue
            add_institution_fn(spec["name"], spec["kind"], spec["description"])
            born.append(spec["name"])
        return born

    def propose_law(
        self,
        *,
        title: str,
        text: str,
        proposed_by: str,
        cycle_id: str,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        gov = self.data.setdefault("government", {"proposals": [], "sessions": []})
        prop = {
            "id": f"law_{cycle_id[-6:]}_{len(gov.get('proposals') or [])}",
            "ts": _utc_now(),
            "cycle_id": cycle_id,
            "title": title[:120],
            "text": text[:500],
            "proposed_by": proposed_by,
            "tags": list(tags or []),
            "status": "candidate",
            "institution": "Chamber of Laws",
        }
        gov.setdefault("proposals", []).append(prop)
        self.data.setdefault("learned_norms", []).append(
            {
                "norm": text[:300],
                "source_role": proposed_by,
                "status": "active_soft",
                "ts": _utc_now(),
                "law_proposal_id": prop["id"],
                "needs_human_authorize_for_accepted": True,
            }
        )
        return prop

    def record_census(self, *, cycle_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
        gov = self.data.setdefault("government", {"proposals": [], "sessions": []})
        row = {
            "ts": _utc_now(),
            "cycle_id": cycle_id,
            "kind": "census",
            "active_count": snapshot.get("active_count"),
            "retired_count": snapshot.get("retired_count"),
            "generations": sorted(
                {int((g.get("generation") or 0)) for g in (snapshot.get("genomes") or [])}
            ),
            "genome_count": len(snapshot.get("genomes") or []),
        }
        gov.setdefault("sessions", []).append(row)
        if len(gov["sessions"]) > 80:
            gov["sessions"] = gov["sessions"][-80:]
        self.data["census_latest"] = row
        return row

    def proposal_count(self) -> int:
        return len((self.data.get("government") or {}).get("proposals") or [])

    def open_proposals(self) -> list[dict[str, Any]]:
        return [
            p
            for p in ((self.data.get("government") or {}).get("proposals") or [])
            if p.get("status") in ("candidate", "candidate_measured")
        ]
