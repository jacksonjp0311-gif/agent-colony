"""CLI: python -m colony cycle | evolve | status | dashboard"""

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

    return 1


if __name__ == "__main__":
    sys.exit(main())
