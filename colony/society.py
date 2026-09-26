"""Society cycle — light the spark, pay tribute, emerge, grow, witness."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from colony.ceiling import Ceiling
from colony.charter import load_charter
from colony.emergence.spark import Spark
from colony.ledger import Ledger
from colony.roles.tribute_keeper import TributeKeeper
from colony.society_state import SocietyState
from colony.witness import WitnessLog

ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = ROOT / "society" / "report.md"

# Creator will (Human Principal James Paul Jackson) — active Tribute Mandate
CREATOR_WILL_ASK = (
    "Novel-math / real scientific education under ceiling — NOT AGI theater, NOT claim unproven "
    "theorems as discovered. Colony may propose conjectures and small lemmas; durable "
    "'discovered' requires machine-check or reproducible derivation + human authorize. Prefer "
    "arXiv/OpenAlex/Crossref as pointers; primary = paper metadata + abstracts. Never claim "
    "Millennium problems solved. Research gather + lemma microbench + conjecture desk keep only "
    "on harness score rise. Hearings reject 'we discovered X' without bench/proof artifact cite. "
    "FFT/autodiff stay green. Math Prize Desk pays on verified harness lifts only. Personas + "
    "RSI coupling + hard ceiling. Soft-cap 20; bias builder+geometer toward benches. Not AGI. "
    "Defer local model runtime."
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cycle_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:6]


@dataclass
class CycleResult:
    cycle_id: str
    tribute_count: int = 0
    tribute_topics: list[str] = field(default_factory=list)
    tribute_compliant: bool = False
    new_roles: list[str] = field(default_factory=list)
    institutions: list[str] = field(default_factory=list)
    councils: list[str] = field(default_factory=list)
    enacted: list[dict[str, Any]] = field(default_factory=list)
    builds: list[str] = field(default_factory=list)
    communications: int = 0
    gathered: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    systems_built: list[str] = field(default_factory=list)
    systems_used: list[str] = field(default_factory=list)
    fitness: dict[str, float] = field(default_factory=dict)
    replies: int = 0
    messages_read: int = 0
    retired_roles: list[str] = field(default_factory=list)
    status_counts: dict[str, int] = field(default_factory=dict)
    witness_path: Path | None = None
    report_path: Path | None = None
    active_ask: str = ""


class Society:
    def __init__(self, root: Path | None = None, live_fetch: bool = True) -> None:
        self.root = root or ROOT
        self.charter = load_charter(self.root / "CHARTER.md")
        self.state = SocietyState.load(self.root / "data" / "society_state.json")
        self._ensure_creator_will()
        self.ledger = Ledger(
            self.root / "data" / "ledger.jsonl",
            extra_roles=self.state.role_names(),
        )
        self.witness = WitnessLog(
            self.root / "data" / "witness.jsonl",
            self.root / "society" / "WITNESS.md",
        )
        self.live_fetch = live_fetch

    def _ensure_creator_will(self) -> None:
        """Pivot active ask to the standing creator will when it has changed."""
        standing = [
            "recursive-self-improvement",
            "meta-learning",
            "self-improving-agents",
            "godel-machines",
            "darwin-godel-machine",
            "reflexion",
            "self-refine",
            "agent-societies",
            "science-method",
            "history-of-ideas",
            "mathematics-foundations",
            "software-engineering",
            "life-and-death",
            "nature-biology-ecology",
            "cosmology-universe",
            "emergent-technology",
            "open-math-problems",
            "compute-useful-math",
            "debate",
            "autogpt-loops",
            "constitutional-ai",
            "opendevin",
            "voyager",
        ]
        tm = self.state.data.setdefault("tribute_mandate", {})
        tm["standing_ask_topics"] = standing
        current = self.state.active_ask().strip()
        if current != CREATOR_WILL_ASK:
            self.state.set_active_ask(CREATOR_WILL_ASK, source="human_principal")
            self.state.save()
        else:
            # Persist expanded standing topics even if ask text matches
            self.state.save()

    def run_cycle(self) -> CycleResult:
        cid = _cycle_id()
        ask = self.state.active_ask()
        result = CycleResult(cycle_id=cid, active_ask=ask)

        self.witness.record(
            cycle_id=cid,
            kind="cycle_open",
            actor="spark",
            summary=f"Cycle opened. Ethos: {self.charter.ethos}",
            detail={"active_ask": ask},
        )

        # 1. Tribute Keeper pays the standing/active ask (gather under creator will)
        payment = TributeKeeper(
            self.ledger,
            seed_path=self.root / "data" / "seed_corpus.json",
            live_fetch=self.live_fetch,
        ).pay(cycle_id=cid, active_ask=ask)
        result.tribute_count = len(payment.findings)
        result.tribute_topics = list(payment.topics_touched)
        result.tribute_compliant = result.tribute_count > 0
        self.state.record_tribute_compliance(
            cid,
            result.tribute_compliant,
            detail=f"count={result.tribute_count} topics={result.tribute_topics}",
        )
        self.witness.record(
            cycle_id=cid,
            kind="tribute_paid" if result.tribute_compliant else "tribute_missed",
            actor="tribute_keeper",
            summary=(
                f"Tribute payment: {result.tribute_count} findings across "
                f"{len(result.tribute_topics)} topics."
            ),
            detail={
                "count": result.tribute_count,
                "topics": result.tribute_topics,
                "live_ok": payment.live_ok,
                "live_fail": payment.live_fail,
            },
        )

        # Mark thin theoretical RSI as unknown (witness epistemic humility)
        for f in payment.findings:
            if f.topic_id == "recursive-self-improvement" or "theoretical" in f.tags:
                self.ledger.create(
                    role="spark",
                    claim=(
                        f"Note on {f.id}: RSI claims stay largely theoretical — "
                        "UNKNOWN until stronger evidence. UNKNOWN stays UNKNOWN."
                    ),
                    evidence_urls=f.evidence_urls,
                    provenance="critique",
                    status="unknown",
                    tags=["unknown", "tribute", f.topic_id],
                    parent_ids=[f.id],
                    topic_id=f.topic_id,
                    title=f"UNKNOWN caution: {f.title[:80]}",
                    meta={"kind": "unknown_mark", "target_id": f.id, "cycle_id": cid},
                )
                self.witness.record(
                    cycle_id=cid,
                    kind="unknown_marked",
                    actor="spark",
                    summary=f"Marked caution UNKNOWN around `{f.id}` (theoretical RSI).",
                    detail={"target_id": f.id},
                )

        # 2. Spark emerges civilization + growth loop (build/communicate/gather/improve)
        emergence = Spark(self.ledger, self.state, self.witness).emerge(
            cid,
            tribute_topics=result.tribute_topics,
            tribute_count=result.tribute_count,
            live_ok=payment.live_ok,
            live_fail=payment.live_fail,
        )
        result.new_roles = list(emergence.new_roles)
        result.institutions = list(emergence.institutions)
        result.councils = list(emergence.councils)
        result.enacted = list(emergence.enacted)
        result.builds = list(emergence.growth.builds)
        result.communications = len(emergence.growth.communications)
        result.gathered = list(emergence.growth.gathered)
        result.improvements = list(emergence.growth.improvements)
        result.systems_built = list(emergence.growth.systems_built)
        result.systems_used = list(emergence.growth.systems_used)
        result.fitness = dict(emergence.growth.fitness)
        result.replies = int(emergence.growth.replies)
        result.messages_read = int(emergence.growth.messages_read)
        result.retired_roles = list(emergence.retired_roles)

        # 3. Hard ceiling — no silent accept
        cycle_findings = payment.findings + emergence.findings
        Ceiling(self.ledger, self.witness).enforce(
            cid,
            tribute_ok=result.tribute_compliant,
            cycle_findings=cycle_findings,
            principal=self.charter.human_principal,
        )

        result.status_counts = self.ledger.status_counts()
        self.state.bump_cycle(cid)
        self.state.save()

        result.witness_path = self.witness.render_md(
            ethos=self.charter.ethos,
            principal=self.charter.human_principal,
            extra_preamble=(
                f"Latest cycle `{cid}`: tribute={result.tribute_count}, "
                f"new_roles={result.new_roles}, retired={result.retired_roles}, "
                f"builds={result.builds}, systems_used={result.systems_used}, "
                f"comms={result.communications}, replies={result.replies}, "
                f"read={result.messages_read}, fitness={result.fitness.get('aggregate')}, "
                f"improvements={result.improvements}."
            ),
        )
        result.report_path = self._write_report(result)
        return result


    def evolve(self, cycles: int = 5) -> list[CycleResult]:
        """Run N autonomous cycles with full learn/evolve mechanics."""
        from colony.dashboard import refresh_dashboard

        results: list[CycleResult] = []
        for i in range(max(1, int(cycles))):
            r = self.run_cycle()
            results.append(r)
            print(
                f"[evolve {i+1}/{cycles}] cycle={r.cycle_id} "
                f"fitness={r.fitness.get('aggregate')} "
                f"systems_used={r.systems_used} replies={r.replies} "
                f"new_roles={r.new_roles} retired={r.retired_roles}"
            )
        refresh_dashboard(self.root)
        return results

    def status(self) -> dict[str, Any]:
        agents = self.state.data.get("agents") or {}
        active = {k: v for k, v in agents.items() if v.get("status") == "active"}
        genomes = []
        for role, a in sorted(active.items()):
            g = a.get("genome") or {}
            genomes.append(
                {
                    "role": role,
                    "generation": g.get("generation", 0),
                    "traits": g.get("traits") or {},
                    "parents": g.get("parents") or a.get("parent_roles") or [],
                }
            )
        commons = self.state.data.get("commons") or {}
        gov = self.state.data.get("government") or {}
        pop = self.state.data.get("population") or {}
        return {
            "colony": "agent-colony",
            "ethos": self.charter.ethos,
            "core_purpose": self.charter.core_purpose,
            "human_principal": self.charter.human_principal,
            "active_ask": self.state.active_ask(),
            "founding_roles": sorted(self.state.founding_roles()),
            "roles": sorted(self.state.role_names()),
            "councils": [c.get("name") for c in self.state.data.get("councils") or []],
            "institutions": [i.get("name") for i in self.state.data.get("institutions") or []],
            "artifacts": [a.get("name") for a in self.state.data.get("artifacts") or []],
            "systems": [
                {"name": s.get("name"), "uses": s.get("use_count"), "path": s.get("path")}
                for s in (self.state.data.get("systems") or [])
            ],
            "agents_active": sorted(active.keys()),
            "agents_retired": sorted(
                k for k, v in agents.items() if v.get("status") == "retired"
            ),
            "population": {
                "active": len(active),
                "soft_cap": pop.get("soft_cap", 20),
                "spawns": pop.get("spawns", 0),
                "child_spawns": pop.get("child_spawns", 0),
            },
            "genomes": genomes,
            "commons_size": len(commons.get("entries") or []),
            "commons_stats": commons.get("stats"),
            "commons_by_domain": {
                d: sum(1 for e in (commons.get("entries") or []) if e.get("domain") == d)
                for d in ("science", "history", "math", "rsi", "empire", "general")
            },
            "government_proposals": len(gov.get("proposals") or []),
            "government_open": [
                {"id": p.get("id"), "title": p.get("title"), "status": p.get("status")}
                for p in (gov.get("proposals") or [])
                if p.get("status") in ("candidate", "candidate_measured")
            ][-8:],
            "census_latest": self.state.data.get("census_latest"),
            "fitness_latest": (self.state.data.get("fitness_history") or [None])[-1],
            "improvement_proposals": len(self.state.data.get("improvement_proposals") or []),
            "bus_stats": (self.state.data.get("bus") or {}).get("stats"),
            "bus_domains": (self.state.data.get("bus") or {}).get("domains"),
            "communications_count": len(self.state.data.get("communications") or []),
            "improvements": [i.get("title") for i in self.state.data.get("improvements") or []],
            "cycle_count": self.state.data.get("cycle_count"),
            "ledger_count": self.ledger.count(),
            "status_counts": self.ledger.status_counts(),
            "witness_events": len(self.witness.all()),
            "tribute_cycles_compliant": self.state.data.get("tribute_mandate", {}).get(
                "cycles_compliant"
            ),
            "standing_topics": self.state.standing_topics(),
        }

    def _write_report(self, result: CycleResult) -> Path:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Agent Colony — Cycle Report",
            "",
            f"> {self.charter.ethos}",
            "",
            f"**Cycle:** `{result.cycle_id}`  ",
            f"**When:** {_utc_now()}  ",
            f"**Creator / Witness:** {self.charter.human_principal}  ",
            "",
            "## Active Tribute Ask (Creator Will)",
            "",
            f"> {result.active_ask}",
            "",
            f"**Paid:** {result.tribute_compliant} — {result.tribute_count} findings "
            f"across topics: {', '.join(result.tribute_topics) or '(none)'}",
            "",
            "## Growth Loop (this cycle)",
            "",
            f"- **Built:** {', '.join(result.builds) or '_none_'}",
            f"- **Systems built:** {', '.join(result.systems_built) or '_none_'}",
            f"- **Systems used:** {', '.join(result.systems_used) or '_none_'}",
            f"- **Communications:** {result.communications} (replies={result.replies}, read={result.messages_read})",
            f"- **Gathered:** {', '.join(result.gathered) or '_none_'}",
            f"- **Fitness:** `{result.fitness}`",
            f"- **Improvements (candidate):** {', '.join(result.improvements) or '_none_'}",
            f"- **Retired roles:** {', '.join(result.retired_roles) or '_none_'}",
            "",
            "## Emergence (this cycle)",
            "",
            f"- **Roles born:** {', '.join(result.new_roles) or '_none_'}",
            f"- **Institutions:** {', '.join(result.institutions) or '_none_'}",
            f"- **Councils:** {', '.join(result.councils) or '_none_'}",
            f"- **Enactments:** {len(result.enacted)}",
            "",
            "## Society now",
            "",
            f"- Roles: {', '.join(sorted(self.state.role_names()))}",
            f"- Artifacts: {', '.join(a.get('name','') for a in self.state.data.get('artifacts') or []) or '_none_'}",
            f"- Ledger status: `{result.status_counts}`",
            f"- Witness: `{result.witness_path}`",
            f"- Bulletin: `society/BULLETIN.md`",
            "",
            "## Hard ceiling",
            "",
            "- Creator tribute: enforced",
            "- Human authorize for `accepted` / privileged actions: enforced (no silent accept)",
            "- Append-only witness: enforced",
            "",
            "## Claim boundary",
            "",
            "We light the spark and witness. We do not micromanage the city. "
            "This is not AGI theater — it is a runnable society under a hard ceiling, "
            "oriented to helping the creator.",
            "",
        ]
        REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
        return REPORT_PATH
