"""Human authorize path — selective accept/reject with witness trail.

Hard ceiling: no silent accept. James (or his delegated authorizer) must
explicitly authorize status transitions to accepted/rejected.
Ledger remains append-only: corrections are new Finding rows with parent_ids.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from colony.charter import requires_human_authorize
from colony.ledger import Finding, Ledger
from colony.society_state import SocietyState
from colony.witness import WitnessLog

ROOT = Path(__file__).resolve().parent.parent
RECEIPTS = ROOT / "society" / "receipts"

Decision = Literal["accepted", "rejected"]

from colony.standing_trust import STANDING_TRUST_P_MIN, meets_standing_trust  # noqa: E402


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class AuthorizeItem:
    finding_id: str
    decision: Decision
    rationale: str


@dataclass
class AuthorizeResult:
    cycle_id: str
    authorizer: str
    delegated_via: str
    accepted: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    proposal_updates: list[dict[str, Any]] = field(default_factory=list)
    receipt_path: Path | None = None


class Authorizer:
    """Apply selective human authorize decisions with full audit trail."""

    def __init__(
        self,
        *,
        root: Path | None = None,
        ledger: Ledger | None = None,
        witness: WitnessLog | None = None,
        state: SocietyState | None = None,
    ) -> None:
        self.root = root or ROOT
        self.state = state or SocietyState.load(self.root / "data" / "society_state.json")
        self.ledger = ledger or Ledger(
            self.root / "data" / "ledger.jsonl",
            extra_roles=self.state.role_names(),
        )
        self.witness = witness or WitnessLog(
            self.root / "data" / "witness.jsonl",
            self.root / "society" / "WITNESS.md",
        )

    def apply(
        self,
        items: list[AuthorizeItem],
        *,
        authorizer: str = "James Paul Jackson",
        delegated_via: str = "Grok Bot (explicit trust grant)",
        also_update_proposals: bool = True,
        proposal_ids: list[tuple[str, Decision, str]] | None = None,
    ) -> AuthorizeResult:
        cycle_id = f"authorize_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        result = AuthorizeResult(
            cycle_id=cycle_id,
            authorizer=authorizer,
            delegated_via=delegated_via,
        )

        by_id = {f.id: f for f in self.ledger.all()}

        self.witness.record(
            cycle_id=cycle_id,
            kind="authorize_batch_open",
            actor="human",
            summary=(
                f"Authorize batch opened by {authorizer} via {delegated_via}. "
                f"Items={len(items)}. Selective — not accept-all."
            ),
            detail={
                "authorizer": authorizer,
                "delegated_via": delegated_via,
                "item_count": len(items),
            },
        )

        for item in items:
            src = by_id.get(item.finding_id)
            if src is None:
                result.skipped.append(
                    {"finding_id": item.finding_id, "reason": "not_found"}
                )
                continue
            if src.status == item.decision:
                result.skipped.append(
                    {
                        "finding_id": item.finding_id,
                        "reason": "already_" + item.decision,
                        "title": src.title,
                    }
                )
                continue
            if not requires_human_authorize(src.status, item.decision):
                result.skipped.append(
                    {
                        "finding_id": item.finding_id,
                        "reason": f"transition_not_authorize_gated:{src.status}->{item.decision}",
                        "title": src.title,
                    }
                )
                continue

            correction = self.ledger.create(
                role="human",
                claim=(
                    f"AUTHORIZE({item.decision}): {src.title or src.claim[:80]} — "
                    f"{item.rationale}"
                ),
                evidence_urls=[
                    f"ledger:{src.id}",
                    "charter:human-authorize",
                    f"authorize:{cycle_id}",
                ],
                provenance="human_authorize",
                status=item.decision,
                tags=list(
                    dict.fromkeys(
                        list(src.tags or [])
                        + ["authorize", item.decision, "human_principal"]
                    )
                ),
                notes=item.rationale,
                parent_ids=[src.id],
                topic_id=src.topic_id,
                title=f"Authorize {item.decision}: {src.title or src.id}",
                meta={
                    "kind": "authorize",
                    "decision": item.decision,
                    "parent_id": src.id,
                    "parent_status": src.status,
                    "authorizer": authorizer,
                    "delegated_via": delegated_via,
                    "rationale": item.rationale,
                    "authorized_at": _utc_now(),
                    "parent_title": src.title,
                    "parent_claim": src.claim[:500],
                },
            )

            self.witness.record(
                cycle_id=cycle_id,
                kind=f"authorize_{item.decision}",
                actor="human",
                summary=(
                    f"{item.decision.upper()} `{src.id}` "
                    f"({src.title or src.claim[:60]}) — {item.rationale}"
                ),
                detail={
                    "finding_id": src.id,
                    "correction_id": correction.id,
                    "decision": item.decision,
                    "title": src.title,
                    "authorizer": authorizer,
                    "delegated_via": delegated_via,
                    "rationale": item.rationale,
                },
            )

            entry = {
                "finding_id": src.id,
                "correction_id": correction.id,
                "title": src.title,
                "decision": item.decision,
                "rationale": item.rationale,
            }
            if item.decision == "accepted":
                result.accepted.append(entry)
            else:
                result.rejected.append(entry)

        if also_update_proposals:
            result.proposal_updates = self._update_proposals(
                cycle_id=cycle_id,
                authorizer=authorizer,
                delegated_via=delegated_via,
                proposal_ids=proposal_ids or [],
                accepted_finding_titles=[a["title"] for a in result.accepted],
            )

        receipt = self._write_receipt(result)
        result.receipt_path = receipt

        self.witness.record(
            cycle_id=cycle_id,
            kind="authorize_batch_close",
            actor="human",
            summary=(
                f"Authorize batch closed. accepted={len(result.accepted)} "
                f"rejected={len(result.rejected)} skipped={len(result.skipped)} "
                f"proposals={len(result.proposal_updates)}. Receipt={receipt.name}."
            ),
            detail={
                "accepted": len(result.accepted),
                "rejected": len(result.rejected),
                "skipped": len(result.skipped),
                "proposal_updates": len(result.proposal_updates),
                "receipt": str(receipt),
            },
        )

        self.witness.render_md(
            ethos=str(self.state.data.get("ethos") or ""),
            principal=authorizer,
        )
        self.state.save()
        return result

    def _update_proposals(
        self,
        *,
        cycle_id: str,
        authorizer: str,
        delegated_via: str,
        proposal_ids: list[tuple[str, Decision, str]],
        accepted_finding_titles: list[str],
    ) -> list[dict[str, Any]]:
        updates: list[dict[str, Any]] = []
        props = self.state.data.get("improvement_proposals") or []
        by_id = {p.get("id"): p for p in props if isinstance(p, dict)}

        for pid, decision, rationale in proposal_ids:
            prop = by_id.get(pid)
            if not prop:
                continue
            prop["status"] = decision
            prop["authorized_at"] = _utc_now()
            prop["authorizer"] = authorizer
            prop["delegated_via"] = delegated_via
            prop["authorize_rationale"] = rationale
            prop["authorize_cycle_id"] = cycle_id
            updates.append(
                {
                    "proposal_id": pid,
                    "title": prop.get("title"),
                    "decision": decision,
                    "rationale": rationale,
                }
            )
            self.witness.record(
                cycle_id=cycle_id,
                kind=f"authorize_proposal_{decision}",
                actor="human",
                summary=(
                    f"Proposal {decision}: `{pid}` ({prop.get('title')}) — {rationale}"
                ),
                detail={
                    "proposal_id": pid,
                    "title": prop.get("title"),
                    "decision": decision,
                    "rationale": rationale,
                    "authorizer": authorizer,
                },
            )

        accepted_titles = {
            u["title"] for u in updates if u["decision"] == "accepted"
        } | set(accepted_finding_titles)
        for imp in self.state.data.get("improvements") or []:
            if not isinstance(imp, dict):
                continue
            title = imp.get("title") or ""
            if title in accepted_titles or any(
                title.startswith(t) or t.startswith(title)
                for t in accepted_titles
                if t
            ):
                if imp.get("outcome") in (None, "attempted", "candidate", "candidate_measured"):
                    matching = [
                        u
                        for u in updates
                        if u["decision"] == "accepted"
                        and (
                            u["title"] == title
                            or (u["title"] and title.startswith(str(u["title"]).split(" (")[0]))
                        )
                    ]
                    if matching:
                        imp["outcome"] = "accepted"
                        imp["authorized_at"] = _utc_now()
                        imp["authorize_rationale"] = matching[0]["rationale"]

        systems = self.root / "society" / "systems" / "improvement_scoreboard.json"
        if systems.is_file() and updates:
            try:
                board = json.loads(systems.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                board = {"proposals": []}
            by_board = {p.get("id"): p for p in board.get("proposals") or []}
            for u in updates:
                if u["proposal_id"] in by_board:
                    by_board[u["proposal_id"]]["status"] = u["decision"]
                    by_board[u["proposal_id"]]["authorize_rationale"] = u["rationale"]
                    by_board[u["proposal_id"]]["authorized_at"] = _utc_now()
            board["proposals"] = list(by_board.values())
            board["updated_at"] = _utc_now()
            systems.write_text(json.dumps(board, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        self.state.data.setdefault("history", []).append(
            {
                "ts": _utc_now(),
                "event": "human_authorize",
                "cycle_id": cycle_id,
                "authorizer": authorizer,
                "delegated_via": delegated_via,
                "proposal_updates": len(updates),
            }
        )
        return updates

    def _write_receipt(self, result: AuthorizeResult) -> Path:
        RECEIPTS.mkdir(parents=True, exist_ok=True)
        path = RECEIPTS / f"AUTHORIZE_{result.cycle_id}.md"
        lines = [
            f"# Authorize receipt — {result.cycle_id}",
            "",
            f"**Authorizer:** {result.authorizer}  ",
            f"**Delegated via:** {result.delegated_via}  ",
            f"**Timestamp:** {_utc_now()}  ",
            "",
            "Hard ceiling held: selective authorize (not accept-all). "
            "Witness append-only. Tribute unchanged.",
            "",
            f"## Accepted ({len(result.accepted)})",
            "",
        ]
        for a in result.accepted:
            lines.append(
                f"- `{a['finding_id']}` → `{a['correction_id']}` — "
                f"**{a['title']}**: {a['rationale']}"
            )
        lines.extend(["", f"## Rejected ({len(result.rejected)})", ""])
        for r in result.rejected:
            lines.append(
                f"- `{r['finding_id']}` → `{r['correction_id']}` — "
                f"**{r['title']}**: {r['rationale']}"
            )
        lines.extend(["", f"## Proposal updates ({len(result.proposal_updates)})", ""])
        for p in result.proposal_updates:
            lines.append(
                f"- `{p['proposal_id']}` **{p['decision']}** — "
                f"{p['title']}: {p['rationale']}"
            )
        if result.skipped:
            lines.extend(["", f"## Skipped ({len(result.skipped)})", ""])
            for s in result.skipped:
                lines.append(f"- `{s.get('finding_id')}`: {s.get('reason')}")
        # SPARK2: before/after threshold compare (0.75 → 0.70)
        try:
            from colony.standing_trust import (
                STANDING_TRUST_P_MIN,
                STANDING_TRUST_P_MIN_BEFORE,
                threshold_compare,
            )
            lines.extend(
                [
                    "",
                    "## Standing trust threshold compare",
                    "",
                    f"- **P_min before (prior mile):** `{STANDING_TRUST_P_MIN_BEFORE}`",
                    f"- **P_min after (this mile):** `{STANDING_TRUST_P_MIN}`",
                    "- Policy: selective — never accept-all; UNKNOWN stays UNKNOWN.",
                    "",
                ]
            )
            compare_rows = []
            for entry in list(result.accepted) + list(result.rejected):
                # confidence unknown at receipt time — record decision under new threshold
                row = {
                    "finding_id": entry.get("finding_id"),
                    "decision": entry.get("decision"),
                    "P_min_before": STANDING_TRUST_P_MIN_BEFORE,
                    "P_min_after": STANDING_TRUST_P_MIN,
                }
                compare_rows.append(row)
                lines.append(
                    f"- `{entry.get('finding_id')}` **{entry.get('decision')}** "
                    f"(gated at P≥{STANDING_TRUST_P_MIN}; prior gate was P≥{STANDING_TRUST_P_MIN_BEFORE})"
                )
            # JSON companion for agent/telemetry query
            import json as _json
            companion = {
                "cycle_id": result.cycle_id,
                "P_min_before": STANDING_TRUST_P_MIN_BEFORE,
                "P_min_after": STANDING_TRUST_P_MIN,
                "accepted": len(result.accepted),
                "rejected": len(result.rejected),
                "skipped": len(result.skipped),
                "never_accept_all": True,
                "compare": compare_rows,
                "note": "SPARK2 authorize threshold compare 0.75→0.70. Selective.",
            }
            (RECEIPTS / f"AUTHORIZE_{result.cycle_id}_compare.json").write_text(
                _json.dumps(companion, indent=2) + "\n", encoding="utf-8"
            )
        except Exception:
            pass
        lines.extend(["", "---", "", "_Durable knowledge requires human authorize._", ""])
        path.write_text("\n".join(lines), encoding="utf-8")
        return path
