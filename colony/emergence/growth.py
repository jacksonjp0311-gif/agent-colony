"""Growth loop — invent/build, communicate, gather, improve."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from colony.ledger import Finding, Ledger
from colony.society_state import SocietyState
from colony.witness import WitnessLog

ROOT = Path(__file__).resolve().parent.parent.parent
ARTIFACTS_DIR = ROOT / "society" / "artifacts"
BULLETIN_PATH = ROOT / "society" / "BULLETIN.md"


@dataclass
class GrowthResult:
    builds: list[str] = field(default_factory=list)
    communications: list[dict[str, Any]] = field(default_factory=list)
    gathered: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


_ARTIFACT_BLUEPRINTS: list[dict[str, str]] = json.loads(
    (ROOT / "data" / "artifact_blueprints.json").read_text(encoding="utf-8")
)
_IMPROVEMENT_ATTEMPTS: list[dict[str, str]] = json.loads(
    (ROOT / "data" / "improvement_attempts.json").read_text(encoding="utf-8")
)


class GrowthLoop:
    def __init__(self, ledger: Ledger, state: SocietyState, witness: WitnessLog) -> None:
        self.ledger = ledger
        self.state = state
        self.witness = witness

    def grow(
        self,
        cycle_id: str,
        *,
        tribute_topics: list[str],
        tribute_count: int,
    ) -> GrowthResult:
        """Visible growth cycle: build → communicate → gather → improve."""
        g = GrowthResult()
        cycle_n = int(self.state.data.get("cycle_count") or 0) + 1

        self.witness.record(
            cycle_id=cycle_id,
            kind="growth_loop_open",
            actor="spark",
            summary="Growth loop lit: build → communicate → gather → improve.",
            detail={"active_ask": self.state.active_ask(), "cycle_n": cycle_n},
        )

        # 1. BUILD
        build = self._build_artifact(cycle_id, cycle_n)
        if build:
            g.builds.append(build["name"])
            g.findings.append(build["finding"])

        # 2. COMMUNICATE
        msgs = self._communicate(cycle_id, cycle_n, tribute_topics=tribute_topics)
        g.communications.extend(msgs)
        for m in msgs:
            if m.get("finding"):
                g.findings.append(m["finding"])

        # 3. GATHER (synthesize beyond tribute payment)
        gathered = self._gather(cycle_id, tribute_topics=tribute_topics, tribute_count=tribute_count)
        if gathered:
            g.gathered.append(gathered["title"])
            g.findings.append(gathered["finding"])

        # 4. IMPROVE
        imp = self._attempt_improvement(cycle_id, cycle_n)
        if imp:
            g.improvements.append(imp["title"])
            g.findings.append(imp["finding"])

        self.witness.record(
            cycle_id=cycle_id,
            kind="growth_loop_close",
            actor="spark",
            summary=(
                f"Growth loop closed: builds={g.builds}, "
                f"comms={len(g.communications)}, gathered={g.gathered}, "
                f"improvements={g.improvements}."
            ),
            detail={
                "builds": g.builds,
                "communications": len(g.communications),
                "gathered": g.gathered,
                "improvements": g.improvements,
            },
        )
        return g

    def _build_artifact(self, cycle_id: str, cycle_n: int) -> dict[str, Any] | None:
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        existing_names = {a.get("name") for a in self.state.data.get("artifacts") or []}
        blueprint = None
        for bp in _ARTIFACT_BLUEPRINTS:
            if bp["name"] not in existing_names:
                blueprint = bp
                break
        if blueprint is None:
            blueprint = {
                "name": f"cycle_{cycle_n}_note",
                "kind": "cycle_note",
                "filename": f"cycle_{cycle_n:04d}_note.md",
                "body": (
                    f"# Cycle {cycle_n} Build Note\n\n"
                    f"Cycle id: `{cycle_id}`\n\n"
                    f"Active ask: {self.state.active_ask()}\n\n"
                    "The colony continues to build under the growth will.\n"
                ),
            }

        path = ARTIFACTS_DIR / blueprint["filename"]
        body = blueprint["body"]
        if blueprint["name"] == "improvement_logbook":
            prior = self.state.data.get("improvements") or []
            if prior:
                extra = "\n".join(
                    f"- **{p.get('title')}** ({p.get('ts')}): {p.get('description', '')[:120]}"
                    for p in prior[-8:]
                )
                body = body + "\n" + extra + "\n"
        path.write_text(body, encoding="utf-8")
        rel = str(path.relative_to(ROOT))

        builder = "builder" if "builder" in self.state.role_names() else "spark"
        self.state.record_artifact(
            name=blueprint["name"],
            kind=blueprint["kind"],
            path=rel,
            description=f"Artifact built in growth loop cycle {cycle_n}.",
            built_by=builder,
            cycle_id=cycle_id,
        )
        self.ledger.set_extra_roles(self.state.role_names())
        f = self.ledger.create(
            role=builder if builder in self.state.role_names() else "spark",
            claim=f"BUILD: artifact '{blueprint['name']}' written to {rel}",
            evidence_urls=[f"artifact:{rel}", "charter:civilization-freedom"],
            provenance="growth_build",
            status="candidate",
            tags=["growth", "build", "artifact"],
            topic_id="agent-societies",
            title=f"Built: {blueprint['name']}",
            meta={"kind": "artifact_built", "name": blueprint["name"], "path": rel, "cycle_id": cycle_id},
        )
        self.witness.record(
            cycle_id=cycle_id,
            kind="artifact_built",
            actor=builder,
            summary=f"Built artifact `{blueprint['name']}` → `{rel}`.",
            detail={"name": blueprint["name"], "path": rel, "kind": blueprint["kind"]},
        )
        return {"name": blueprint["name"], "path": rel, "finding": f}

    def _communicate(
        self, cycle_id: str, cycle_n: int, *, tribute_topics: list[str]
    ) -> list[dict[str, Any]]:
        roles = sorted(self.state.role_names())
        msgs: list[dict[str, Any]] = []
        ask = self.state.active_ask()

        plans = [
            (
                "spark",
                "tribute_keeper",
                "bulletin",
                f"Cycle {cycle_n}: keep paying tribute. Active will — {ask[:140]}",
            ),
            (
                "herald" if "herald" in roles else "spark",
                "memory_weaver" if "memory_weaver" in roles else "spark",
                "bulletin",
                (
                    f"Herald call: weave patterns from topics "
                    f"{', '.join(tribute_topics[:6]) or 'standing RSI corpus'}."
                ),
            ),
            (
                "builder" if "builder" in roles else "spark",
                "improver" if "improver" in roles else "spark",
                "forum",
                "Builder → Improver: footprints exist in society/artifacts; propose the next process upgrade.",
            ),
            (
                "pathfinder" if "pathfinder" in roles else "spark",
                "spark",
                "bulletin",
                "Gather signal: pathfinder/scout ready to synthesize coverage gaps for the creator.",
            ),
        ]

        seen: set[tuple[str, str, str]] = set()
        for fr, to, channel, message in plans:
            fr_r = fr if fr in roles else "spark"
            to_r = to if to in roles else "spark"
            key = (fr_r, to_r, message)
            if key in seen:
                continue
            seen.add(key)
            entry = self.state.post_communication(
                from_role=fr_r,
                to_role=to_r,
                channel=channel,
                message=message,
                cycle_id=cycle_id,
            )
            self.ledger.set_extra_roles(self.state.role_names())
            actor = fr_r if fr_r in self.state.role_names() else "spark"
            f = self.ledger.create(
                role=actor,
                claim=f"COMMUNICATE [{channel}] {fr_r} → {to_r}: {message}",
                evidence_urls=["institution:Society Bulletin", f"cycle:{cycle_id}"],
                provenance="growth_communicate",
                status="candidate",
                tags=["growth", "communicate", channel],
                topic_id="agent-societies",
                title=f"Message: {fr_r} → {to_r}",
                meta={
                    "kind": "communication",
                    "from": fr_r,
                    "to": to_r,
                    "channel": channel,
                    "cycle_id": cycle_id,
                },
            )
            self.witness.record(
                cycle_id=cycle_id,
                kind="communication",
                actor=actor,
                summary=f"{fr_r} → {to_r} via {channel}: {message[:160]}",
                detail={"from": fr_r, "to": to_r, "channel": channel, "message": message},
            )
            msgs.append({**entry, "finding": f})

        self._render_bulletin()
        return msgs

    def _render_bulletin(self) -> None:
        comms = self.state.data.get("communications") or []
        lines = [
            "# Society Bulletin",
            "",
            "> We light the spark and witness. We do not micromanage the city.",
            "",
            f"**Messages:** {len(comms)}",
            "",
            "## Chronology",
            "",
        ]
        if not comms:
            lines.append("_No messages yet._")
        else:
            for c in comms[-40:]:
                lines.append(
                    f"- **{c.get('ts')}** [`{c.get('channel')}`] "
                    f"**{c.get('from')}** → **{c.get('to')}**: {c.get('message')}"
                )
            lines.append("")
        lines.extend(["---", "", "_Inter-role speech is civilization._", ""])
        BULLETIN_PATH.parent.mkdir(parents=True, exist_ok=True)
        BULLETIN_PATH.write_text("\n".join(lines), encoding="utf-8")

    def _gather(
        self,
        cycle_id: str,
        *,
        tribute_topics: list[str],
        tribute_count: int,
    ) -> dict[str, Any] | None:
        standing = self.state.standing_topics()
        all_topics = sorted(set(tribute_topics) | set(standing))
        ledger_topics: dict[str, int] = {}
        for fnd in self.ledger.all():
            if fnd.topic_id:
                ledger_topics[fnd.topic_id] = ledger_topics.get(fnd.topic_id, 0) + 1
        thin = [t for t in all_topics if ledger_topics.get(t, 0) < 2]
        rich = sorted(ledger_topics.items(), key=lambda x: -x[1])[:6]
        actor = (
            "pathfinder"
            if "pathfinder" in self.state.role_names()
            else ("memory_weaver" if "memory_weaver" in self.state.role_names() else "spark")
        )
        title = f"Gather synthesis cycle {cycle_id[-6:]}"
        claim = (
            f"GATHER: tribute_count={tribute_count}; "
            f"coverage_rich={rich}; thin_or_missing={thin[:8] or 'none'}; "
            "RSI/self-improving research remains valuable standing gather. "
            "Broader will: grow + build + communicate + gather + improve."
        )
        self.ledger.set_extra_roles(self.state.role_names())
        f = self.ledger.create(
            role=actor if actor in self.state.role_names() else "spark",
            claim=claim,
            evidence_urls=["charter:creator-tribute", f"cycle:{cycle_id}", "growth:gather"],
            provenance="growth_gather",
            status="candidate",
            tags=["growth", "gather", "synthesis"],
            topic_id="agent-societies",
            title=title,
            meta={
                "kind": "gather_synthesis",
                "thin": thin[:12],
                "rich": rich,
                "cycle_id": cycle_id,
            },
        )
        self.witness.record(
            cycle_id=cycle_id,
            kind="information_gathered",
            actor=actor,
            summary=f"Gathered synthesis: rich={len(rich)} thin={len(thin)} tribute={tribute_count}.",
            detail={"thin": thin[:8], "rich": rich, "title": title},
        )
        return {"title": title, "finding": f}

    def _attempt_improvement(self, cycle_id: str, cycle_n: int) -> dict[str, Any] | None:
        done = {i.get("title") for i in self.state.data.get("improvements") or []}
        attempt = None
        for a in _IMPROVEMENT_ATTEMPTS:
            if a["title"] not in done:
                attempt = a
                break
        if attempt is None:
            attempt = {
                "title": f"Cycle {cycle_n} reflection pass",
                "description": (
                    "Re-read witness + bulletin; tighten next-cycle communication "
                    "clarity without touching the hard ceiling."
                ),
            }
        actor = "improver" if "improver" in self.state.role_names() else "spark"
        self.state.record_improvement(
            title=attempt["title"],
            description=attempt["description"],
            attempted_by=actor,
            cycle_id=cycle_id,
            outcome="attempted",
        )
        logbook = ARTIFACTS_DIR / "improvement_logbook.md"
        if logbook.is_file():
            with logbook.open("a", encoding="utf-8") as fh:
                fh.write(
                    f"\n- **{attempt['title']}** (`{cycle_id}`): {attempt['description']}\n"
                )

        self.ledger.set_extra_roles(self.state.role_names())
        f = self.ledger.create(
            role=actor if actor in self.state.role_names() else "spark",
            claim=f"IMPROVE (attempted): {attempt['title']} — {attempt['description']}",
            evidence_urls=["charter:civilization-freedom", f"cycle:{cycle_id}"],
            provenance="growth_improve",
            status="candidate",
            tags=["growth", "improve", "self-improvement"],
            notes="Process improvement attempt. Not accepted. Needs human authorize for durable acceptance.",
            topic_id="agent-societies",
            title=f"Improve attempt: {attempt['title']}",
            meta={
                "kind": "improvement_attempted",
                "title": attempt["title"],
                "cycle_id": cycle_id,
                "outcome": "attempted",
            },
        )
        self.witness.record(
            cycle_id=cycle_id,
            kind="improvement_attempted",
            actor=actor,
            summary=f"Improvement attempted: {attempt['title']}",
            detail={"title": attempt["title"], "description": attempt["description"]},
        )
        return {"title": attempt["title"], "finding": f}
