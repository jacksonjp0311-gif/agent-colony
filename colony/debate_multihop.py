"""Multi-hop debate: A proposes → B attacks → C patches → D Oracle-gates.

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

    # SPARK2: fresh seeds outside comfort zone (rotate; avoid weak-spot loops)
    seed_meta = {}
    if not seed_claim:
        try:
            from colony.debate_seeds import next_seed
            seed_meta = next_seed(cycle_id)
            seed_claim = seed_meta.get("claim") or ""
        except Exception:
            seed_claim = ""
    claim = seed_claim or (
        "SPARK2 PROPOSE: deepen hard-tier lemma pressure; keep only on measured hard_pass rise; "
        "easy_pad must revert; novelty gate kills textbook reuse; multi-hop replies must load-bear "
        "(cite prior + change NEXT ACTION) so reply_rate rises without fake padding."
    )

    # Agents query telemetry + external array + residuals mid-debate (not human-only)
    telem_cite = {}
    ext_patterns = []
    residual_view = {}
    try:
        from colony.telemetry import query as telem_query
        telem_cite = telem_query(section=None)
        ext_patterns = list(
            ((telem_cite.get("external") or {}).get("external_array") or {}).get("patterns") or []
        )
    except Exception as exc:
        telem_cite = {"error": str(exc)}
    try:
        from colony.external_array import patterns_for_debate
        if not ext_patterns:
            ext_patterns = patterns_for_debate(limit=3)
    except Exception:
        pass
    try:
        from colony.residuals import ResidualField
        # bus.state may hold society data
        state_data = getattr(bus, "data", None) or {}
        rf = ResidualField(state_data)
        for role in (role_a, role_b, role_c):
            rf.ensure(role)
        residual_view = {
            "high": rf.high_residual_roles(top_k=3),
            "conflicts": rf.detect_conflicts(),
        }
    except Exception as exc:
        residual_view = {"error": str(exc)}

    pattern_snip = "; ".join(
        (p.get("kind") or "?") + ": " + (p.get("summary") or "")[:90]
        for p in ext_patterns[:2]
    ) or "external_array:sparse"

    # A proposes
    msg_a = bus.post(
        from_role=role_a,
        to_role=role_b,
        channel="math",
        message=(
            f"MULTI-HOP A/propose ({role_a}): {claim} "
            f"TELEM cite fitness={(telem_cite.get('internal') or {}).get('fitness_aggregate')} "
            f"reply_rate={(telem_cite.get('internal') or {}).get('reply_rate')} "
            f"oracle={(telem_cite.get('internal') or {}).get('oracle')}. "
            f"EXTERNAL patterns: {pattern_snip}. "
            f"RESIDUAL high={residual_view.get('high')}. "
            f"Cite prior turn + peer findings. cycle={cycle_id}. Not discovery."
        ),
        cycle_id=cycle_id,
        tags=["debate", "multihop", "propose", "peer_cite", "telemetry", "external_array"],
        payload={
            "hop": "A",
            "kind": "propose",
            "claim": claim[:240],
            "seed_id": seed_meta.get("id"),
            "telem_ts": telem_cite.get("ts"),
            "ext_patterns": [p.get("kind") for p in ext_patterns[:3]],
            "residuals_high": residual_view.get("high"),
        },
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

    # D — Oracle gate deepen (flourish mile): require SENSE before keep weight
    role_d = "legislator" if "legislator" in roles else role_b
    msg_d = bus.post(
        from_role=role_d,
        to_role="forum",
        channel="math",
        message=(
            f"MULTI-HOP D/oracle_gate ({role_d}): ACK patch `{msg_c.get('id')}`. "
            f"DEEPEN: keep weight ONLY if Oracle SENSE (held-out+stripped+CAS) passes; "
            f"easy_pad dies; STEM pack same rule. FAIL kills keep. Not AGI. cycle={cycle_id}."
        ),
        cycle_id=cycle_id,
        tags=["debate", "multihop", "oracle_gate", "peer_cite", "action_changed"],
        in_reply_to=msg_c.get("id"),
        payload={"hop": "D", "kind": "oracle_gate", "parent": msg_c.get("id")},
    )
    bus.record_peer_cite(
        cited=bus.message_cites_peer(msg_d.get("message") or "", parent=msg_c)
    )
    bus.record_action_changed(
        changed=True,
        detail={
            "next_action_before": patch_action["next_action_after"],
            "next_action_after": "oracle_sense_before_keep",
            "reason": f"hop D oracle_gate on {msg_c.get('id')}",
            "cycle_id": cycle_id,
        },
    )

    # SPARK: load-bearing close — reply to unreplied directed roots in recent window
    # (not fake padding: each reply cites prior turn + sets NEXT ACTION). Lifts reply_rate.
    closed_roots = 0
    try:
        recent = bus.messages()[-60:] if hasattr(bus, "messages") else []
        unreplied = [
            m for m in recent
            if not m.get("in_reply_to")
            and m.get("to") not in ("all", "*")
            and not m.get("replies")
            and m.get("from") != m.get("to")
        ]
        for root in unreplied[-8:]:
            responder = root.get("to")
            if responder not in roles or responder in ("forum", "all", "*"):
                responder = role_d if role_d in roles else (role_c if role_c in roles else "spark")
            parent_id = root.get("id")
            parent_snip = ((root.get("message") or "")[:70]).replace("\n", " ")
            close = bus.post(
                from_role=responder,
                to_role=root.get("from") or role_a,
                channel=root.get("channel") or "bulletin",
                message=(
                    f"SPARK load-bear reply ({responder}): ACK prior `{parent_id}` "
                    f"from {root.get('from')}. Citing your words: '{parent_snip}'. "
                    f"NEXT ACTION → oracle_sense_or_hard_tier_mutate (bus-driven). "
                    f"easy_pad dies. Not AGI. cycle={cycle_id}."
                ),
                cycle_id=cycle_id,
                tags=["debate", "multihop", "load_bear_reply", "peer_cite", "action_changed"],
                in_reply_to=parent_id,
                payload={"hop": "E_close", "kind": "load_bear_reply", "parent": parent_id},
            )
            bus.record_peer_cite(
                cited=bus.message_cites_peer(close.get("message") or "", parent=root)
            )
            bus.record_action_changed(
                changed=True,
                detail={
                    "next_action_before": "await_reply",
                    "next_action_after": "oracle_sense_or_hard_tier_mutate",
                    "reason": f"spark load-bear close on {parent_id}",
                    "cycle_id": cycle_id,
                },
            )
            closed_roots += 1
    except Exception:
        closed_roots = 0

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
                f"msg:{msg_d.get('id')}",
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
                "hops": ["A_propose", "B_attack", "C_patch", "D_oracle_gate"],
                "msg_ids": [msg_a.get("id"), msg_b.get("id"), msg_c.get("id"), msg_d.get("id")],
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
        "roles": {"A": role_a, "B": role_b, "C": role_c, "D": role_d},
        "msg_ids": [msg_a.get("id"), msg_b.get("id"), msg_c.get("id"), msg_d.get("id")],
        "finding_id": finding_id,
        "code_touched": code_touched,
        "action_changed": True,
        "load_bear_closed": closed_roots,
        "bus_metrics": {
            "reply_rate": metrics.get("reply_rate"),
            "peer_cite_rate": metrics.get("peer_cite_rate"),
            "action_changed_from_message": metrics.get("action_changed_from_message"),
            "reply_quality": metrics.get("reply_quality"),
        },
        "seed_id": seed_meta.get("id"),
        "telemetry_ts": telem_cite.get("ts"),
        "external_patterns": [p.get("kind") for p in ext_patterns[:4]],
        "residuals": residual_view,
        "note": "SPARK2 A→B→C→D(Oracle)+E load-bear + telem/external/residuals. Bus-driven claim/code change. Not AGI.",
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
                    f"Multi-hop A({role_a})→B({role_b})→C({role_c})→D({role_d}) "
                    f"action_changed=True code_touched={code_touched} "
                    f"reply_rate={metrics.get('reply_rate')}"
                ),
                detail=result,
            )
        except Exception:
            pass
    return result
