"""Build systems — artifacts that later cycles actually USE."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SYSTEMS_DIR = ROOT / "society" / "systems"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Catalog of systems the colony can build. Each has a concrete on-disk format.
SYSTEM_CATALOG: list[dict[str, Any]] = [
    {
        "name": "coverage_index",
        "kind": "index",
        "filename": "coverage_index.json",
        "description": "Topic coverage counts; gather reads this to prioritize thin topics.",
        "initial": {"topics": {}, "updated_at": None, "version": 1},
    },
    {
        "name": "skill_router",
        "kind": "router",
        "filename": "skill_router.json",
        "description": "Maps skills to best agent; spark/growth consult before acting.",
        "initial": {"routes": {}, "updated_at": None, "version": 1},
    },
    {
        "name": "reply_tracker",
        "kind": "tracker",
        "filename": "reply_tracker.json",
        "description": "Tracks unreplied bus messages so herald/courier can close loops.",
        "initial": {"open": [], "closed": [], "updated_at": None, "version": 1},
    },
    {
        "name": "fitness_ledger",
        "kind": "ledger",
        "filename": "fitness_history.jsonl",
        "description": "Append-only fitness scores per cycle for measurable evolution.",
        "initial_line": None,  # jsonl
    },
    {
        "name": "topic_priority",
        "kind": "priority",
        "filename": "topic_priority.json",
        "description": "Ranked gather targets derived from coverage_index + bus gap alerts.",
        "initial": {"ranked": [], "updated_at": None, "version": 1},
    },
    {
        "name": "improvement_scoreboard",
        "kind": "scoreboard",
        "filename": "improvement_scoreboard.json",
        "description": "Before/after metrics for improvement proposals (candidate until authorize).",
        "initial": {"proposals": [], "updated_at": None, "version": 1},
    },
    {
        "name": "common_knowledge",
        "kind": "commons",
        "filename": "common_knowledge.json",
        "description": "Shared candidate knowledge digests; writers append, readers reuse each cycle.",
        "initial": {"size": 0, "stats": {}, "by_domain": {}, "recent": [], "updated_at": None, "version": 1},
    },
    {
        "name": "rsi_coupling",
        "kind": "coupling",
        "filename": "rsi_coupling.json",
        "description": "Feeds accepted/strong RSI findings into improver/skill_router/genome mutation biases (measured).",
        "initial": {"signal": {}, "updated_at": None, "version": 1},
    },
    {
        "name": "findings_coupling",
        "kind": "coupling",
        "filename": "findings_coupling.json",
        "description": "Accepted math/compute/RSI findings alter gather/debate/build via skill_router, genomes, topic_priority, personas.",
        "initial": {"signal": {}, "updated_at": None, "version": 1},
    },
    {
        "name": "athanor_coherence",
        "kind": "governor",
        "filename": "athanor_coherence.json",
        "description": "Athanor H7 coherence governor (inform-only; no double-gate; no durable accept).",
        "initial": {"latest": {}, "distribution": {}, "updated_at": None, "version": 1},
    },
    {
        "name": "pulsemesh_feeds",
        "kind": "feeds",
        "filename": "pulsemesh_feeds.json",
        "description": "PulseMesh collectors into EXTERNAL ARRAY (debate input only; graceful degrade).",
        "initial": {"feeds": {}, "feed_health": {}, "updated_at": None, "version": 1},
    },
]


class SystemWorkshop:
    """Builds and uses durable systems under society/systems/."""

    def __init__(self, state_data: dict[str, Any], root: Path | None = None) -> None:
        self.data = state_data
        self.root = root or ROOT
        self.dir = self.root / "society" / "systems"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.data.setdefault("systems", [])

    def known(self) -> dict[str, dict[str, Any]]:
        return {s["name"]: s for s in self.data.get("systems") or []}

    def path_for(self, filename: str) -> Path:
        return self.dir / filename

    def ensure(self, name: str, *, built_by: str, cycle_id: str) -> dict[str, Any] | None:
        """Build a catalog system if missing. Returns system record."""
        known = self.known()
        if name in known:
            return known[name]
        catalog = {c["name"]: c for c in SYSTEM_CATALOG}
        if name not in catalog:
            return None
        spec = catalog[name]
        path = self.path_for(spec["filename"])
        if spec["name"] == "fitness_ledger":
            if not path.exists():
                path.write_text("", encoding="utf-8")
        else:
            if not path.exists():
                initial = dict(spec.get("initial") or {})
                initial["updated_at"] = _utc_now()
                initial["built_by"] = built_by
                initial["built_cycle"] = cycle_id
                path.write_text(json.dumps(initial, indent=2) + "\n", encoding="utf-8")
        rel = str(path.relative_to(self.root))
        entry = {
            "name": name,
            "kind": spec["kind"],
            "path": rel,
            "description": spec["description"],
            "built_by": built_by,
            "built_cycle": cycle_id,
            "use_count": 0,
            "last_used_cycle": None,
            "ts": _utc_now(),
        }
        self.data.setdefault("systems", []).append(entry)
        self.data.setdefault("artifacts", []).append(
            {
                "ts": _utc_now(),
                "cycle_id": cycle_id,
                "name": name,
                "kind": f"system:{spec['kind']}",
                "path": rel,
                "description": spec["description"],
                "built_by": built_by,
                "usable": True,
            }
        )
        self.data.setdefault("history", []).append(
            {
                "ts": _utc_now(),
                "event": "system_built",
                "name": name,
                "path": rel,
                "cycle_id": cycle_id,
            }
        )
        return entry

    def next_unbuilt(self) -> dict[str, Any] | None:
        known = self.known()
        for c in SYSTEM_CATALOG:
            if c["name"] not in known:
                return c
        return None

    def use(self, name: str, cycle_id: str) -> dict[str, Any] | None:
        """Load a system and bump use_count. Returns parsed content (dict) or meta."""
        known = self.known()
        if name not in known:
            return None
        rec = known[name]
        path = self.root / rec["path"]
        content: Any = None
        if rec["kind"] == "ledger" or path.suffix == ".jsonl":
            content = {"path": str(path), "lines": sum(1 for _ in path.open()) if path.exists() else 0}
        else:
            if path.exists():
                content = json.loads(path.read_text(encoding="utf-8"))
            else:
                content = {}
        rec["use_count"] = int(rec.get("use_count") or 0) + 1
        rec["last_used_cycle"] = cycle_id
        return {"record": rec, "content": content}

    def write_json(self, name: str, content: dict[str, Any], cycle_id: str) -> Path | None:
        known = self.known()
        if name not in known:
            return None
        path = self.root / known[name]["path"]
        content = dict(content)
        content["updated_at"] = _utc_now()
        content["updated_cycle"] = cycle_id
        path.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def append_fitness(self, row: dict[str, Any]) -> None:
        known = self.known()
        if "fitness_ledger" not in known:
            return
        path = self.root / known["fitness_ledger"]["path"]
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        known["fitness_ledger"]["use_count"] = int(known["fitness_ledger"].get("use_count") or 0) + 1
        known["fitness_ledger"]["last_used_cycle"] = row.get("cycle_id")

    def reuse_ratio(self) -> float:
        systems = self.data.get("systems") or []
        if not systems:
            return 0.0
        used = sum(1 for s in systems if int(s.get("use_count") or 0) > 0)
        return round(used / len(systems), 4)

    def used_this_cycle(self, cycle_id: str) -> list[str]:
        return [
            s["name"]
            for s in (self.data.get("systems") or [])
            if s.get("last_used_cycle") == cycle_id
        ]
