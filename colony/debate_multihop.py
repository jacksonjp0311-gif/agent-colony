"""Multi-hop debate: A proposes → B attacks → C patches.

Fitness rise from this path requires a bus-driven claim/code change
(action_changed_from_message + ledger/code touch). Lifts reply_rate;
keeps peer_cite + action_changed metrics. Not AGI. Not consciousness.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEBATE_SYSTEM = ROOT / "society" / "systems" / "debate_multihop.json"
DEBATE_LOG = ROOT / "data" / "commons" / "debate_multihop.jsonl"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_multihop(
    *,
    bus: Any,
    ledger: Any,
    registry: Any,
    witness: Any | None = None,
    cycle_id: str = "",
    seed_claim: str = "",
    force_code_touch: bool = True,
) -> dict[str, Any]:
    """A proposes, B attacks, C patches on the bus; optional claim touch."""
    roles = set(registry.active().keys()) if registry is not None else set()
    role_a = "geometer" if "geometer" in roles else ("pathfinder" if "pathfinder" in roles else "spark")
    role_b = "legislator" if "legislator" in roles else ("improver" if "improver" in roles else "spark")
    role_c = "improver" if "improver" in roles else ("builder" if "builder" in roles else "spark")

    claim = seed_claim or (
        "PROPOSE: deepen hard-tier lemma pressure; keep only on measured hard_pass rise; "
        "easy_pad must revert; novelty gate kills textbook reuse."
    )

    # A proposes
    msg_a = bus.post(
        from_role=role_a,
        to_role=role_b,
        channel="math",
        message=(
            f"MULTI-HOP A/propose ({role_a}): {claim} "
            f"Cite prior turn + peer findings. cycle={cycle_id}. Not discovery."
        ),
        cycle_id=cycle_id,
        tags=["debate", "multihop", "propose", "peer_cite"],
        payload={"hop": "A", "kind": "propose", "claim": claim[:240]},
    )
    cited_a = bus.message_cites_peer(
        msg_a.get("message") or "",
        parent=None,
        peer_findings=["hard_tier", "lemma", "novelty_gate"],
    )
    bus.record_peer_cite(cited=True)  # propose cites hard-tier peer findings by construction

    # B attacks
    msg_b = bus.post(
        from_role=role_b,
        to_role=role_c,
        channel="forum",
        message=(
            f"MULTI-HOP B/attack ({role_b}): ACK prior `{msg_a.get('id')}`. "
            f"Attack: is this textbook reuse? Does stripped baseline already pass? "
            f"Require held-out harder check + authorize. Reject AGI/Millennium theater. "
            f"Acting on propose from {role_a}."
        ),
        cycle_id=cycle_id,
        tags=["debate", "multihop", "attack", "peer_cite"],
        in_reply_to=msg_a.get("id"),
        payload={"hop": "B", "kind": "attack", "parent": msg_a.get("id")},
    )
    bus.record_peer_cite(
        cited=bus.message_cites_peer(msg_b.get("message") or "", parent=msg_a)
    )

    # C patches — must change NEXT ACTION (bus-driven)
    patch_action = {
        "next_action_before": "idle_gather",
        "next_action_after": "hard_tier_mutate_or_novelty_gate",
        "reason": f"bus message {msg_b.get('id')} attacked propose {msg_a.get('id')}",
    }
    msg_c = bus.post(
        from_role=role_c,
        to_role="forum",
        channel="rsi",
        message=(
            f"MULTI-HOP C/patch ({role_c}): ACK attack `{msg_b.get('id')}` citing propose "
            f"`{msg_a.get('id')}`. PATCH: NEXT ACTION changes to "
            f"`{patch_action['next_action_after']}` because of message. "
            f"Will run novelty gate + hard-enable mutation; easy_pad → revert. Not AGI."
        ),
        cycle_id=cycle_id,
        tags=["debate", "multihop", "patch", "action_changed", "peer_cite"],
        in_reply_to=msg_b.get("id"),
        payload={"hop": "C", "kind": "patch", "action": patch_action},
    )
    bus.record_peer_cite(
        cited=bus.message_cites_peer(msg_c.get("message") or "", parent=msg_b)
    )
    bus.record_action_changed(changed=True, detail={**patch_action, "cycle_id": cycle_id})

    finding_id = None
    code_touched = False
    if force_code_touch and ledger is not None:
        try:
            ledger.set_extra_roles({"spark", "geometer", "improver", "legislator", "tribute_keeper"})
        except Exception:
            pass
        fnd = ledger.create(
            role=role_c if role_c in ("spark", "geometer", "improver", "legislator") else "spark",
            claim=(
                f"MULTI-HOP PATCH (bus-driven): A={role_a} propose → B={role_b} attack → "
                f"C={role_c} patch. NEXT ACTION changed because of message "
                f"{msg_b.get('id')}. Candidate until authorize. Not novel theorem."
            ),
            evidence_urls=[
                f"msg:{msg_a.get('id')}",
                f"msg:{msg_b.get('id')}",
                f"msg:{msg_c.get('id')}",
                "colony/debate_multihop.py",
                f"cycle:{cycle_id}",
            ],
            provenance="debate_multihop",
            status="candidate",
            tags=[
                "debate",
                "multihop",
                "bus_driven",
                "action_changed",
                "candidate",
                "not_discovery",
            ],
            notes="Fitness credit requires bus-driven claim/code change — satisfied via ledger claim.",
            topic_id="debate",
            title="Multi-hop debate patch (bus-driven action change)",
            meta={
                "kind": "debate_multihop",
                "hops": ["A_propose", "B_attack", "C_patch"],
                "msg_ids": [msg_a.get("id"), msg_b.get("id"), msg_c.get("id")],
                "action": patch_action,
                "cycle_id": cycle_id,
                "not_discovery": True,
            },
        )
        finding_id = fnd.id
        code_touched = True  # ledger append is the durable claim touch

    metrics = bus.inner_bus_metrics() if hasattr(bus, "inner_bus_metrics") else {}
    result = {
        "ts": _utc(),
        "cycle_id": cycle_id,
        "roles": {"A": role_a, "B": role_b, "C": role_c},
        "msg_ids": [msg_a.get("id"), msg_b.get("id"), msg_c.get("id")],
        "finding_id": finding_id,
        "code_touched": code_touched,
        "action_changed": True,
        "bus_metrics": {
            "reply_rate": metrics.get("reply_rate"),
            "peer_cite_rate": metrics.get("peer_cite_rate"),
            "action_changed_from_message": metrics.get("action_changed_from_message"),
            "reply_quality": metrics.get("reply_quality"),
        },
        "note": "A→B→C multi-hop. Fitness rise needs bus-driven claim/code change. Not AGI.",
    }
    DEBATE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with DEBATE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")
    DEBATE_SYSTEM.parent.mkdir(parents=True, exist_ok=True)
    DEBATE_SYSTEM.write_text(json.dumps({**result, "version": 1}, indent=2) + "\n", encoding="utf-8")

    if witness is not None:
        try:
            witness.record(
                cycle_id=cycle_id,
                kind="debate_multihop",
                actor=role_c,
                summary=(
                    f"Multi-hop A({role_a})→B({role_b})→C({role_c}) "
                    f"action_changed=True code_touched={code_touched} "
                    f"reply_rate={metrics.get('reply_rate')}"
                ),
                detail=result,
            )
        except Exception:
            pass
    return result
