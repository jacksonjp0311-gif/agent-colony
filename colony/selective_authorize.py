"""Fail-closed machine selection. Explicit human decisions use Authorizer separately."""
from __future__ import annotations

from typing import Any

from colony.standing_trust import meets_standing_trust
from colony.trust.provenance import oracle_backed


def select_candidates(ledger: Any, state: Any, *, event_name: str,
                      requested: str, cap: int = 8) -> list[dict[str, Any]]:
    """Select only explicit manual requests backed by confidence and Oracle evidence.

    Metadata labels (keep, bus_driven, hard_checked) are not machine evidence.
    Missing cycle diagnostics also fail closed; a legacy cycle must be revalidated.
    This function never applies decisions or grants human authority.
    """
    if event_name != "workflow_dispatch" or requested != "true":
        return []
    data = state.data if hasattr(state, "data") else state
    health = data.get("cycle_diagnostics") or {}
    findings = ledger.all()
    decided = {str((f.meta or {}).get("parent_id")) for f in findings
               if (f.meta or {}).get("kind") == "authorize"
               and f.status in ("accepted", "rejected")}
    selected = []
    seen = set(decided)
    for finding in findings[-200:]:
        if finding.id in seen or finding.status != "candidate" or str(finding.id).startswith("imp_"):
            continue
        meta = finding.meta or {}
        if "easy_pad" in (finding.tags or []) or meta.get("decision") == "revert":
            continue
        confidence = meta["P"] if "P" in meta else meta.get("confidence")
        if not meets_standing_trust(confidence, machine_checked=True):
            continue
        cycle = str(meta.get("cycle_id") or "")
        diagnostic = health.get(cycle) or {}
        if diagnostic.get("promotion_allowed") is not True:
            continue
        target = str(meta.get("mutation") or meta.get("theme_id") or "")
        if not oracle_backed(target, cycle)["ok"]:
            continue
        selected.append({"finding_id": finding.id, "confidence": confidence,
                         "rationale": "Finite machine checks and healthy cycle; explicit manual selection. Not a universal proof."})
        seen.add(finding.id)
        if len(selected) >= max(0, cap):
            break
    return selected if cap > 0 else []
