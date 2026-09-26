"""Growth loop steps — part 1."""
from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
ARTIFACTS_DIR = ROOT / "society" / "artifacts"


class GrowthSteps1:

    def _read_all_inboxes(self, cycle_id: str, g) -> dict[str, Any]:
        merged: dict[str, Any] = {
            "thin_topics": [],
            "build_requests": [],
            "improve_hints": [],
            "needs_reply": [],
        }
        total_read = 0
        for role in list(self.registry.active().keys()):
            unread = self.bus.read_inbox(role)
            if not unread:
                continue
            total_read += len(unread)
            act = self.bus.extract_actionables(unread)
            for k in ("thin_topics", "build_requests", "improve_hints", "needs_reply"):
                merged[k].extend(act.get(k) or [])
            self.witness.record(
                cycle_id=cycle_id,
                kind="inbox_read",
                actor=role,
                summary=f"{role} read {len(unread)} unread message(s).",
                detail={"count": len(unread), "ids": [m.get("id") for m in unread[:8]]},
            )
            self.registry.record_outcome(role, "communicate", min(1.0, 0.4 + 0.1 * len(unread)))
        merged["thin_topics"] = sorted(set(merged["thin_topics"]))[:12]
        seen = set()
        uniq = []
        for m in merged["needs_reply"]:
            mid = m.get("id")
            if mid and mid not in seen:
                seen.add(mid)
                uniq.append(m)
        merged["needs_reply"] = uniq[:10]
        g.messages_read = total_read
        return merged

    def _build_and_use_systems(
        self,
        cycle_id: str,
        cycle_n: int,
        g,
        actionables: dict[str, Any],
    ) -> None:
        builder = self.registry.best_for("build")
        for name in ("coverage_index", "skill_router", "topic_priority", "reply_tracker"):
            used = self.workshop.use(name, cycle_id)
            if used:
                g.systems_used.append(name)
                self.registry.agents()[builder]["systems_used"] = int(
                    self.registry.agents()[builder].get("systems_used") or 0
                ) + 1

        unbuilt = self.workshop.next_unbuilt()
        if unbuilt:
            rec = self.workshop.ensure(unbuilt["name"], built_by=builder, cycle_id=cycle_id)
            if rec:
                g.systems_built.append(unbuilt["name"])
                g.builds.append(unbuilt["name"])
                self._ledger_build(builder, unbuilt["name"], rec["path"], cycle_id, g)
                self.witness.record(
                    cycle_id=cycle_id,
                    kind="system_built",
                    actor=builder,
                    summary=f"Built usable system `{unbuilt['name']}` → `{rec['path']}`.",
                    detail={"name": unbuilt["name"], "path": rec["path"]},
                )
                self.registry.record_outcome(builder, "build", 0.85)
        else:
            self._refresh_topic_priority(cycle_id, builder, actionables, g)
            ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
            note_name = f"cycle_{cycle_n}_evolve_note"
            path = ARTIFACTS_DIR / f"cycle_{cycle_n:04d}_evolve_note.md"
            thin = ", ".join(actionables.get("thin_topics") or []) or "(none from inbox)"
            path.write_text(
                f"# Cycle {cycle_n} Evolve Note\n\n"
                f"Cycle: `{cycle_id}`\n\n"
                f"Systems used: {', '.join(g.systems_used) or '—'}\n\n"
                f"Inbox thin topics: {thin}\n\n"
                f"Fitness will be recorded at end of growth loop.\n",
                encoding="utf-8",
            )
            rel = str(path.relative_to(ROOT))
            self.state.record_artifact(
                name=note_name,
                kind="cycle_note",
                path=rel,
                description="Evolve-cycle witness note",
                built_by=builder,
                cycle_id=cycle_id,
            )
            g.builds.append(note_name)
            self._ledger_build(builder, note_name, rel, cycle_id, g)
            self.registry.record_outcome(builder, "build", 0.55)

    def _refresh_topic_priority(
        self,
        cycle_id: str,
        actor: str,
        actionables: dict[str, Any],
        g,
    ) -> None:
        if "topic_priority" not in self.workshop.known():
            self.workshop.ensure("topic_priority", built_by=actor, cycle_id=cycle_id)
            g.systems_built.append("topic_priority")
        cov = self.workshop.use("coverage_index", cycle_id)
        topic_counts: dict[str, int] = {}
        if cov and isinstance(cov.get("content"), dict):
            topic_counts = dict((cov["content"] or {}).get("topics") or {})
            if "coverage_index" not in g.systems_used:
                g.systems_used.append("coverage_index")
        thin = list(actionables.get("thin_topics") or [])
        standing = self.state.standing_topics()
        ranked = []
        for t in thin:
            ranked.append({"topic": t, "priority": 1.0, "reason": "inbox_gap"})
        for t in standing:
            count = topic_counts.get(t, 0)
            if count < 2 and t not in thin:
                ranked.append({"topic": t, "priority": 0.7, "reason": f"coverage={count}"})
        ranked.sort(key=lambda x: -x["priority"])
        self.workshop.write_json(
            "topic_priority",
            {"ranked": ranked[:16], "source": "growth_refresh"},
            cycle_id,
        )
        used = self.workshop.use("topic_priority", cycle_id)
        if used and "topic_priority" not in g.systems_used:
            g.systems_used.append("topic_priority")
        g.builds.append("topic_priority_refresh")
        self.witness.record(
            cycle_id=cycle_id,
            kind="system_used",
            actor=actor,
            summary=f"Refreshed topic_priority with {len(ranked)} ranked targets.",
            detail={"ranked": ranked[:8]},
        )
