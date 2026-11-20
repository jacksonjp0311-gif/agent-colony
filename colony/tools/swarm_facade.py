"""Facade so Hive/swarm roles can use the evidence tools adaptively.

Hive never imports colony. The adapter passes plain dicts; this facade
turns those dicts into tool calls and returns plain dicts. Fail-open.
"""
from __future__ import annotations
from typing import Any, Dict, List

def query_tools(request: Dict[str, Any]) -> Dict[str, Any]:
    """Adaptive entry point.

    request keys (all optional):
      action: "record" | "gate" | "novel" | "credit" | "grade" | "compose" | "ablate"
      claim: dict
      delta: float
      ops: list[str]
      historical_keep_rate: float
      with_result / without_result: dicts for ablation
    """
    action = request.get("action", "record")
    out: Dict[str, Any] = {"ok": False, "action": action}
    try:
        if action == "record":
            from colony.tools.evidence_graph import append_node
            nid = append_node("swarm_query", request.get("claim") or request)
            out.update(ok=True, graph_id=nid)
        elif action == "gate":
            from colony.tools.statistical_keep_gate import should_accept, record_outcome
            delta = float(request.get("delta", 0.0))
            accept = should_accept(delta)
            record_outcome(delta, accept)
            out.update(ok=True, accept=accept, delta=delta)
        elif action == "novel":
            from colony.tools.novelty_filter import is_novel, signature
            claim = request.get("claim") or {}
            recent = request.get("recent_signatures") or []
            out.update(ok=True, novel=is_novel(claim, recent), signature=signature(claim))
        elif action == "credit":
            from colony.tools.reward_isolation import can_award_credit
            claim = request.get("claim") or {}
            out.update(ok=True, credit_ok=can_award_credit(claim))
        elif action == "grade":
            from colony.tools.prospective_grading import grade_method
            method = request.get("claim") or request
            rate = float(request.get("historical_keep_rate", 0.3))
            out.update(ok=True, grade=grade_method(method, rate))
        elif action == "compose":
            from colony.tools.method_composition import compose
            ops = request.get("ops") or []
            out.update(ok=True, method=compose(ops, request.get("params")))
        elif action == "ablate":
            from colony.tools.ablation_harness import run_ablation
            wr = request.get("with_result") or {}
            wor = request.get("without_result") or {}
            delta = run_ablation(
                request.get("factor", "unknown"),
                lambda: wr,
                lambda: wor,
            )
            out.update(ok=True, ablation=delta)
        elif action == "sense":
            from colony.tools.connective import route_to_swarm
            out.update(route_to_swarm(request))
        elif action == "recall":
            from colony.tools.connective import route_to_swarm
            out.update(route_to_swarm(request))
        elif action == "pulse":
            from colony.tools.connective import route_to_swarm
            out.update(route_to_swarm(request))
        elif action == "athanor":
            from colony.tools.existing_signals import athanor_h7
            out.update(athanor_h7(request.get("traj")))
        elif action == "residuals":
            from colony.tools.existing_signals import residual_snapshot
            out.update(residual_snapshot(request.get("role")))
        elif action == "failures":
            from colony.tools.existing_signals import recent_failures
            out.update(recent_failures(int(request.get("limit", 5))))
        elif action == "sensors":
            from colony.tools.existing_signals import sensors_snapshot
            out.update(sensors_snapshot())
        else:
            out["error"] = "unknown_action"
    except Exception as exc:
        out["error"] = type(exc).__name__
    return out
