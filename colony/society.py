"""Society cycle — light the spark, pay tribute, emerge, witness."""

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
    status_counts: dict[str, int] = field(default_factory=dict)
    witness_path: Path | None = None
    report_path: Path | None = None
    active_ask: str = ""


class Society:
    def __init__(self, root: Path | None = None, live_fetch: bool = True) -> None:
        self.root = root or ROOT
        self.charter = load_charter(self.root / "CHARTER.md")
        self.state = SocietyState.load(self.root / "data" / "society_state.json")
        self.ledger = Ledger(
            self.root / "data" / "ledger.jsonl",
            extra_roles=self.state.role_names(),
        )
        self.witness = WitnessLog(
            self.root / "data" / "witness.jsonl",
            self.root / "society" / "WITNESS.md",
        )
        self.live_fetch = live_fetch

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

        emergence = Spark(self.ledger, self.state, self.witness).emerge(
            cid,
            tribute_topics=result.tribute_topics,
            tribute_count=result.tribute_count,
        )
        result.new_roles = list(emergence.new_roles)
        result.institutions = list(emergence.institutions)
        result.councils = list(emergence.councils)
        result.enacted = list(emergence.enacted)

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
                f"new_roles={result.new_roles}, institutions={result.institutions}, "
                f"councils={result.councils}."
            ),
        )
        result.report_path = self._write_report(result)
        return result

    def status(self) -> dict[str, Any]:
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
            "cycle_count": self.state.data.get("cycle_count"),
            "ledger_count": self.ledger.count(),
            "status_counts": self.ledger.status_counts(),
            "witness_events": len(self.witness.all()),
            "tribute_cycles_compliant": self.state.data.get("tribute_mandate", {}).get(
                "cycles_compliant"
            ),
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
            "## Active Tribute Ask",
            "",
            f"> {result.active_ask}",
            "",
            f"**Paid:** {result.tribute_compliant} — {result.tribute_count} findings "
            f"across topics: {', '.join(result.tribute_topics) or '(none)'}",
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
            f"- Ledger status: `{result.status_counts}`",
            f"- Witness: `{result.witness_path}`",
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
