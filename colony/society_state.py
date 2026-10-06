"""Society state — emergent civilization under a hard ceiling."""

from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE = ROOT / "data" / "society_state.json"
SHARDS_DIR = ROOT / "data" / "society_shards"
# Feature flag: STATE_SHARDS=1 enables shard flush (default on for relight; fallback keeps full file)
STATE_SHARDS = os.environ.get("STATE_SHARDS", "1") != "0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class SocietyState:
    path: Path
    data: dict[str, Any]
    _last_hash: str | None = field(default=None, repr=False, compare=False)

    @classmethod
    def load(cls, path: Path | None = None) -> SocietyState:
        p = path or DEFAULT_STATE
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        # Merge shard tails if present (full-file remains source of truth for one mile)
        if STATE_SHARDS and SHARDS_DIR.is_dir():
            for key in ("improvement_proposals", "fitness_history", "improvements"):
                shard = SHARDS_DIR / f"{key}.jsonl"
                if not shard.exists():
                    continue
                # Inline state keeps tails; shards are append-only archive — do not re-inflate fully
                data.setdefault("_shards", {})[key] = str(shard.relative_to(ROOT))
        return cls(path=p, data=data)

    def _flush_shard(self, key: str, *, max_inline: int = 50) -> None:
        if not STATE_SHARDS:
            return
        arr = self.data.get(key)
        if not isinstance(arr, list) or len(arr) <= max_inline:
            return
        SHARDS_DIR.mkdir(parents=True, exist_ok=True)
        shard_path = SHARDS_DIR / f"{key}.jsonl"
        overflow = arr[:-max_inline]
        # Append overflow once (track by id/ts to avoid dupes on re-save)
        existing_ids: set[str] = set()
        if shard_path.exists():
            for ln in shard_path.read_text(encoding="utf-8").splitlines()[-5000:]:
                try:
                    e = json.loads(ln)
                    existing_ids.add(str(e.get("id") or e.get("ts") or ""))
                except json.JSONDecodeError:
                    continue
        with shard_path.open("a", encoding="utf-8") as f:
            for e in overflow:
                eid = str((e or {}).get("id") or (e or {}).get("ts") or "")
                if eid and eid in existing_ids:
                    continue
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
                if eid:
                    existing_ids.add(eid)
        self.data[key] = arr[-max_inline:]
        self.data.setdefault("_shards", {})[key] = str(shard_path.relative_to(ROOT))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Shard hot arrays to cut commit churn
        self._flush_shard("improvement_proposals", max_inline=50)
        self._flush_shard("fitness_history", max_inline=30)
        self._flush_shard("improvements", max_inline=50)
        blob = json.dumps(self.data, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(blob.encode()).hexdigest()
        if self._last_hash == digest:
            return
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        self._last_hash = digest

    def role_names(self) -> set[str]:
        return set(self.data.get("roles", {}).keys())

    def founding_roles(self) -> set[str]:
        return set(self.data.get("founding_roles") or ["spark", "tribute_keeper"])

    def active_ask(self) -> str:
        return str(self.data.get("tribute_mandate", {}).get("active_ask") or "")

    def standing_topics(self) -> list[str]:
        return list(self.data.get("tribute_mandate", {}).get("standing_ask_topics") or [])

    def set_active_ask(self, ask: str, *, source: str = "human_principal") -> None:
        tm = self.data.setdefault("tribute_mandate", {})
        prev = tm.get("active_ask")
        tm["active_ask"] = ask
        tm["active"] = True
        tm["repealable_by_agents"] = False
        tm["kind"] = "creator_service"
        tm["ask_updated_at"] = _utc_now()
        tm["ask_source"] = source
        self.data.setdefault("history", []).append(
            {
                "ts": _utc_now(),
                "event": "active_ask_updated",
                "from": prev,
                "to": ask,
                "source": source,
            }
        )

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

    def post_communication(
        self,
        *,
        from_role: str,
        to_role: str,
        channel: str,
        message: str,
        cycle_id: str,
    ) -> dict[str, Any]:
        entry = {
            "ts": _utc_now(),
            "cycle_id": cycle_id,
            "from": from_role,
            "to": to_role,
            "channel": channel,
            "message": message,
        }
        self.data.setdefault("communications", []).append(entry)
        self.data.setdefault("history", []).append(
            {
                "ts": _utc_now(),
                "event": "communication",
                "from": from_role,
                "to": to_role,
                "channel": channel,
                "cycle_id": cycle_id,
            }
        )
        return entry

    def record_artifact(
        self,
        *,
        name: str,
        kind: str,
        path: str,
        description: str,
        built_by: str,
        cycle_id: str,
    ) -> dict[str, Any]:
        entry = {
            "ts": _utc_now(),
            "cycle_id": cycle_id,
            "name": name,
            "kind": kind,
            "path": path,
            "description": description,
            "built_by": built_by,
        }
        self.data.setdefault("artifacts", []).append(entry)
        self.data.setdefault("history", []).append(
            {
                "ts": _utc_now(),
                "event": "artifact_built",
                "name": name,
                "kind": kind,
                "path": path,
                "cycle_id": cycle_id,
            }
        )
        return entry

    def record_improvement(
        self,
        *,
        title: str,
        description: str,
        attempted_by: str,
        cycle_id: str,
        outcome: str = "attempted",
    ) -> dict[str, Any]:
        entry = {
            "ts": _utc_now(),
            "cycle_id": cycle_id,
            "title": title,
            "description": description,
            "attempted_by": attempted_by,
            "outcome": outcome,
        }
        self.data.setdefault("improvements", []).append(entry)
        self.data.setdefault("history", []).append(
            {
                "ts": _utc_now(),
                "event": "improvement_attempted",
                "title": title,
                "outcome": outcome,
                "cycle_id": cycle_id,
            }
        )
        return entry

    def bump_cycle(self, cycle_id: str) -> None:
        self.data["cycle_count"] = int(self.data.get("cycle_count") or 0) + 1
        self.data.setdefault("history", []).append(
            {"ts": _utc_now(), "event": "cycle_complete", "cycle_id": cycle_id}
        )

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(self.data)
