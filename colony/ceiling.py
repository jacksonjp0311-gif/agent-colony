"""Hard ceiling gate — tribute, human authorize, witness integrity."""

from __future__ import annotations

from dataclasses import dataclass, field

from colony.charter import CeilingViolation, refuse_auto_accept, requires_human_authorize
from colony.ledger import Finding, Ledger
from colony.witness import WitnessLog


@dataclass
class CeilingReport:
    tribute_ok: bool
    auto_accepts_refused: int = 0
    pending_human_authorize: int = 0
    messages: list[str] = field(default_factory=list)


class Ceiling:
    """Not a role aristocracy — just the three hard limits."""

    def __init__(self, ledger: Ledger, witness: WitnessLog) -> None:
        self.ledger = ledger
        self.witness = witness

    def enforce(
        self,
        cycle_id: str,
        *,
        tribute_ok: bool,
        cycle_findings: list[Finding],
        principal: str,
    ) -> CeilingReport:
        report = CeilingReport(tribute_ok=tribute_ok)
        if not tribute_ok:
            report.messages.append("Ceiling warning: tribute not paid this cycle.")
            self.witness.record(
                cycle_id=cycle_id,
                kind="ceiling_warning",
                actor="ceiling",
                summary="Tribute mandate not satisfied this cycle.",
            )

        for f in cycle_findings:
            if f.status == "candidate" and requires_human_authorize("candidate", "accepted"):
                report.pending_human_authorize += 1
                try:
                    refuse_auto_accept("accepted")
                except CeilingViolation:
                    report.auto_accepts_refused += 1

        msg = (
            f"Hard ceiling held. Tribute_ok={tribute_ok}. "
            f"Refused silent accepts={report.auto_accepts_refused}. "
            f"Pending human authorize ({principal})={report.pending_human_authorize}. "
            "Witness log append-only."
        )
        report.messages.append(msg)
        self.witness.record(
            cycle_id=cycle_id,
            kind="ceiling_held",
            actor="ceiling",
            summary=msg,
            detail={
                "tribute_ok": tribute_ok,
                "auto_accepts_refused": report.auto_accepts_refused,
                "pending_human_authorize": report.pending_human_authorize,
            },
        )

        # Ledger trace from spark-adjacent governance (use spark as actor — ceiling is not a role)
        self.ledger.create(
            role="spark",
            claim=msg,
            evidence_urls=["charter:hard-ceiling", f"cycle:{cycle_id}"],
            provenance="governance",
            status="candidate",
            tags=["ceiling"],
            title="Hard ceiling held",
            meta={"kind": "ceiling_report", "cycle_id": cycle_id},
        )
        return report
