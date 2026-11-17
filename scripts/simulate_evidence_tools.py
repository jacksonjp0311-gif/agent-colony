#!/usr/bin/env python3
"""Minimal simulation of the evidence tools in a time-stepped cybernetic loop.

Demonstrates:
- Static time-based steps (cycles)
- Feedback: outcomes update history, which gates future keeps
- Evidence graph records findings
"""
from colony.tools.evidence_graph import append_node, query_by_type
from colony.tools.statistical_keep_gate import should_accept, record_outcome
from colony.tools.invariant_contracts import check_verified_depth_contract

def simulate(cycles: int = 5) -> None:
    print(f"=== Evidence Tools Simulation ({cycles} cycles) ===")
    for c in range(1, cycles + 1):
        # propose a finding
        claim = {"id": f"claim-{c}", "delta": 0.03 + c * 0.01, "independent_path_recorded": True}
        nid = append_node("claim", claim)
        print(f"Cycle {c}: recorded {nid}")

        # check invariants
        ok = check_verified_depth_contract(claim)
        print(f"  invariant: {ok}")

        # statistical gate
        accept = should_accept(claim["delta"])
        record_outcome(claim["delta"], accept)
        print(f"  gate accept={accept} delta={claim['delta']:.3f}")

    print("\nFinal graph nodes:", len(query_by_type("claim")))
    print("Simulation complete — tools close a feedback loop without altering the colony core.")

if __name__ == "__main__":
    simulate()
