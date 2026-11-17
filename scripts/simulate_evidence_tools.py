#!/usr/bin/env python3
"""Time-stepped simulation of the full evidence-tool set.

Demonstrates static agency (discrete cycles) with cybernetic feedback
(outcomes update gates, novelty, and persistence).
"""
from colony.tools.evidence_graph import append_node, query_by_type
from colony.tools.statistical_keep_gate import should_accept, record_outcome
from colony.tools.method_composition import compose
from colony.tools.prospective_grading import grade_method
from colony.tools.novelty_filter import is_novel, signature
from colony.tools.hunter_persistence import persist_hit
from colony.tools.reward_isolation import can_award_credit
from colony.tools.ablation_harness import run_ablation

def simulate(cycles: int = 6) -> None:
    print(f"=== Full Evidence Tools Simulation ({cycles} cycles) ===")
    recent_sigs = []
    for c in range(1, cycles + 1):
        method = compose(["modular_search", "residue_check"], {"window": 50 + c * 10})
        grade = grade_method(method)
        claim = {
            "id": f"claim-{c}",
            "delta": 0.03 + c * 0.008,
            "independent_path_recorded": True,
            "ops": method["ops"],
        }
        nid = append_node("claim", claim)
        novel = is_novel(claim, recent_sigs)
        if novel:
            recent_sigs.append(signature(claim))
        credit_ok = can_award_credit(claim)
        accept = should_accept(claim["delta"]) and credit_ok and novel and grade > 0.4
        record_outcome(claim["delta"], accept)
        if c % 3 == 0:
            persist_hit(claim["id"], {"n": 10**c, "fails": True})
        print(f"Cycle {c}: node={nid} grade={grade:.2f} novel={novel} credit={credit_ok} accept={accept}")

    def with_bus():
        return {"oracle_passes": 4, "verified_depth": 9}
    def without_bus():
        return {"oracle_passes": 2, "verified_depth": 6}
    ab = run_ablation("bus", with_bus, without_bus)
    print(f"\nAblation delta_passes={ab['delta_passes']}")
    print(f"Final claim nodes: {len(query_by_type('claim'))}")
    print("Simulation complete — tools close attributable feedback loops.")

if __name__ == "__main__":
    simulate()
