"""Society state — emergent civilization under a hard ceiling."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE = ROOT / "data" / "society_state.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class SocietyState:
    path: Path
    data: dict[str, Any]

    @classmethod
    def load(cls, path: Path | None = None) -> SocietyState:
        p = path or DEFAULT_STATE
        with p.open("r", encoding="utf-8") as f:
            return cls(path=p, data=json.load(f))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
            f.write("\n")

    def role_names(self) -> set[str]:
        return set(self.data.get("roles", {}).keys())

    def founding_roles(self) -> set[str]:
        return set(self.data.get("founding_roles") or ["spark", "tribute_keeper"])

    def active_ask(self) -> str:
        return str(self.data.get("tribute_mandate", {}).get("active_ask") or "")

    def standing_topics(self) -> list[str]:
        return list(self.data.get("tribute_mandate", {}).get("standing_ask_topics") or [])

    def record_tribute_compliance(self, cycle_id: str, ok: bool, detail: str) -> None:
        tm = self.data.setdefault("tribute_mandate", {})
        if ok:
            tm["cycles_compliant"] = int(tm.get("cycles_compliant") or 0) + 1
            tm["last_tribute_cycle"] = cycle_id
        self.data.setdefault("history", []).append(
            {"ts": _utc_now(), "cycle_id": cycle_id, "event": "tribute_check", "ok": ok, "detail": detail}
        )

    def add_role(
        self,
        name: str,
        description: str,
        *,
        provisional: bool = True,
        proposed_by: str = "spark",
    ) -> dict[str, Any]:
        key = name.strip().lower().replace(" ", "_")
        entry = {
            "status": "emergent",
            "provisional": provisional,
            "description": description,
            "proposed_by": proposed_by,
            "activated_at": _utc_now(),
        }
        self.data.setdefault("roles", {})[key] = entry
        for t in self.data.get("hierarchy", {}).get("tiers", []):
            if t.get("name") == "emergent" and key not in t.get("roles", []):
                t.setdefault("roles", []).append(key)
        self.data.setdefault("pending_proposals", []).append(
            {
                "type": "new_role",
                "role": key,
                "description": description,
                "provisional": provisional,
                "proposed_by": proposed_by,
                "ts": _utc_now(),
                "enacted": True,
                "needs_human_authorize_for_durable_accepted_knowledge": True,
            }
        )
        self.data.setdefault("history", []).append(
            {"ts": _utc_now(), "event": "role_emerged", "role": key}
        )
        return entry

    def form_council(self, name: str, members: list[str], purpose: str) -> dict[str, Any]:
        council = {
            "name": name,
            "members": members,
            "purpose": purpose,
            "formed_at": _utc_now(),
            "status": "active",
        }
        self.data.setdefault("councils", []).append(council)
        self.data.setdefault("institutions", []).append(
            {"type": "council", "name": name, "ts": _utc_now()}
        )
        self.data.setdefault("history", []).append(
            {"ts": _utc_now(), "event": "council_formed", "name": name}
        )
        return council

    def add_institution(self, name: str, kind: str, description: str) -> dict[str, Any]:
        inst = {"name": name, "kind": kind, "description": description, "ts": _utc_now()}
        self.data.setdefault("institutions", []).append(inst)
        self.data.setdefault("history", []).append(
            {"ts": _utc_now(), "event": "institution_born", "name": name, "kind": kind}
        )
        return inst

    def rename_role(self, old: str, new: str) -> dict[str, Any]:
        roles = self.data.setdefault("roles", {})
        if old not in roles:
            raise KeyError(old)
        roles[new] = {**roles.pop(old), "renamed_from": old, "renamed_at": _utc_now()}
        rec = {"from": old, "to": new, "ts": _utc_now()}
        self.data.setdefault("renames", []).append(rec)
        for t in self.data.get("hierarchy", {}).get("tiers", []):
            rs = t.get("roles") or []
            if old in rs:
                t["roles"] = [new if r == old else r for r in rs]
        return rec

    def add_norm(self, norm: str, source_role: str = "spark") -> dict[str, Any]:
        entry = {"norm": norm, "source_role": source_role, "status": "active_soft", "ts": _utc_now()}
        self.data.setdefault("learned_norms", []).append(entry)
        return entry

    def add_ritual(self, name: str, description: str) -> dict[str, Any]:
        r = {"name": name, "description": description, "ts": _utc_now()}
        self.data.setdefault("rituals", []).append(r)
        return r

    def bump_cycle(self, cycle_id: str) -> None:
        self.data["cycle_count"] = int(self.data.get("cycle_count") or 0) + 1
        self.data.setdefault("history", []).append(
            {"ts": _utc_now(), "event": "cycle_complete", "cycle_id": cycle_id}
        )

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(self.data)
