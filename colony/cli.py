"""CLI: python -m colony cycle | evolve | status | dashboard | authorize | bench-improve

Hold posture (colony.hold_posture): default HOLD; light evolve watch; selective authorize only.
"""

from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m colony",
        description="Agent Colony — light the spark and witness.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_cycle = sub.add_parser("cycle", help="Run one society cycle")
    p_cycle.add_argument("--offline", action="store_true", help="Seed only; no HTTP")
    p_evolve = sub.add_parser("evolve", help="Run N autonomous evolve cycles")
    p_evolve.add_argument("--cycles", type=int, default=5, help="Number of cycles (default 5)")
    p_evolve.add_argument("--offline", action="store_true", help="Seed only; no HTTP")
    sub.add_parser("status", help="Print status JSON")
    sub.add_parser("dashboard", help="Refresh DASHBOARD.html + WITNESS_SUMMARY.md")
    p_auth = sub.add_parser(
        "authorize",
        help="Human authorize: selectively accept/reject ledger findings (no silent accept-all)",
    )
    p_auth.add_argument(
        "--decisions",
        required=True,
        help="Path to JSON list of {finding_id, decision, rationale} (+ optional proposals)",
    )
    p_auth.add_argument(
        "--authorizer",
        default="James Paul Jackson",
        help="Human principal name (default: James Paul Jackson)",
    )
    p_auth.add_argument(
        "--delegated-via",
        default="Grok Bot (explicit trust grant)",
        help="Delegation note recorded in witness/receipt",
    )
    sub.add_parser("hold", help="Print hold posture (HOLD default; selective authorize only)")
    sub.add_parser("charters", help="Print institution standing charters (agenda autonomy; no truth authority)")
    p_pilots = sub.add_parser("pilots", help="Pilot sandbox lane status / propose (no durable accept)")
    p_pilots.add_argument("--propose", action="store_true", help="Propose a demo sandbox pilot")
    p_pilots.add_argument("--name", default="demo_gather_filter", help="Pilot name")
    p_pilots.add_argument("--kind", default="gather_filter", help="skill|router|gather_filter|improvement|rsi_bias")
    p_bi = sub.add_parser(
        "bench-improve",
        help="Measure→patch→remeasure bench artifacts; keep if aggregate rises else revert",
    )
    p_bi.add_argument(
        "--patch",
        default=None,
        help="Force patch name (fft_remove_slow_loops|fft_add_slow_loops|autodiff_busy_loop)",
    )
    p_bi.add_argument(
        "--demo",
        action="store_true",
        help="Run keep-then-revert demo (remove slow loops, then add slow loops)",
    )
    args = parser.parse_args(argv)

    from colony.society import Society

    if args.cmd == "cycle":
        society = Society(live_fetch=not args.offline)
        r = society.run_cycle()
        print(f"cycle_id={r.cycle_id}")
        print(f"tribute_count={r.tribute_count} topics={r.tribute_topics}")
        print(f"tribute_compliant={r.tribute_compliant}")
        print(f"new_roles={r.new_roles} retired={r.retired_roles}")
        print(f"institutions={r.institutions}")
        print(f"councils={r.councils}")
        print(f"builds={r.builds} systems_used={r.systems_used}")
        print(f"comms={r.communications} replies={r.replies} read={r.messages_read}")
        print(f"fitness={r.fitness}")
        print(f"enacted={len(r.enacted)} status_counts={r.status_counts}")
        print(f"witness={r.witness_path}")
        print(f"report={r.report_path}")
        from colony.dashboard import refresh_dashboard

        refresh_dashboard(society.root)
        return 0

    if args.cmd == "evolve":
        society = Society(live_fetch=not args.offline)
        before = society.status()
        results = society.evolve(cycles=args.cycles)
        after = society.status()
        print("--- evolve summary ---")
        print(f"cycles_run={len(results)}")
        print(f"fitness_before={before.get('fitness_latest')}")
        print(f"fitness_after={after.get('fitness_latest')}")
        print(f"agents_active={after.get('agents_active')}")
        print(f"agents_retired={after.get('agents_retired')}")
        print(f"population={after.get('population')}")
        print(f"commons_size={after.get('commons_size')}")
        print(f"government_proposals={after.get('government_proposals')}")
        print(f"genomes={len(after.get('genomes') or [])}")
        print(f"systems={after.get('systems')}")
        print(f"improvement_proposals={after.get('improvement_proposals')}")
        return 0

    if args.cmd == "status":
        print(json.dumps(Society(live_fetch=False).status(), indent=2))
        return 0

    if args.cmd == "dashboard":
        from colony.dashboard import refresh_dashboard

        paths = refresh_dashboard()
        print(f"dashboard={paths['dashboard']}")
        print(f"summary={paths['summary']}")
        return 0

    if args.cmd == "authorize":
        from pathlib import Path as _Path

        from colony.authorize import AuthorizeItem, Authorizer

        payload = json.loads(_Path(args.decisions).read_text(encoding="utf-8"))
        items_raw = payload.get("items") if isinstance(payload, dict) else payload
        items = [
            AuthorizeItem(
                finding_id=i["finding_id"],
                decision=i["decision"],
                rationale=i["rationale"],
            )
            for i in items_raw
        ]
        proposals = []
        if isinstance(payload, dict):
            for p in payload.get("proposals") or []:
                proposals.append((p["proposal_id"], p["decision"], p["rationale"]))
        result = Authorizer().apply(
            items,
            authorizer=args.authorizer,
            delegated_via=args.delegated_via,
            proposal_ids=proposals,
        )
        print(
            json.dumps(
                {
                    "cycle_id": result.cycle_id,
                    "authorizer": result.authorizer,
                    "delegated_via": result.delegated_via,
                    "accepted": len(result.accepted),
                    "rejected": len(result.rejected),
                    "skipped": len(result.skipped),
                    "proposal_updates": len(result.proposal_updates),
                    "receipt": str(result.receipt_path),
                    "accepted_ids": [a["finding_id"] for a in result.accepted],
                    "rejected_ids": [r["finding_id"] for r in result.rejected],
                },
                indent=2,
            )
        )
        return 0

    if args.cmd == "bench-improve":
        from colony.bench_improve import improve_demo, improve_once

        if args.demo:
            results = improve_demo()
            for r in results:
                print(
                    f"patch={r.patch_name} decision={r.decision} "
                    f"before={r.before_score} after={r.after_score} delta={r.delta}"
                )
            return 0
        r = improve_once(force_patch=args.patch)
        print(
            json.dumps(
                {
                    "patch": r.patch_name,
                    "decision": r.decision,
                    "before_score": r.before_score,
                    "after_score": r.after_score,
                    "delta": r.delta,
                    "note": r.note,
                    "target": r.target,
                },
                indent=2,
            )
        )
        return 0


    if args.cmd == "hold":
        from colony.hold_posture import latest_hold

        print(json.dumps(latest_hold(), indent=2))
        return 0

    if args.cmd == "charters":
        from colony.institution_charters import ensure_charters, latest_charters

        ensure_charters(cycle_id="cli")
        print(json.dumps(latest_charters(), indent=2))
        return 0

    if args.cmd == "pilots":
        from colony.pilot_lane import ensure_sandbox, latest_lane, propose_pilot

        ensure_sandbox()
        if args.propose:
            row = propose_pilot(
                name=args.name,
                kind=args.kind,
                body={"demo": True, "reversible": True},
                proposed_by="cli",
                cycle_id="cli",
                rationale="CLI demo sandbox pilot — promotion still needs authorize.",
            )
            print(json.dumps(row, indent=2))
            return 0
        print(json.dumps(latest_lane(), indent=2))
        return 0


    return 1


if __name__ == "__main__":
    sys.exit(main())
