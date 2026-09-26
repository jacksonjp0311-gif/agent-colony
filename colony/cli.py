"""CLI: python -m colony cycle | status"""

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
    sub.add_parser("status", help="Print status JSON")
    args = parser.parse_args(argv)

    from colony.society import Society

    if args.cmd == "cycle":
        society = Society(live_fetch=not args.offline)
        r = society.run_cycle()
        print(f"cycle_id={r.cycle_id}")
        print(f"tribute_count={r.tribute_count} topics={r.tribute_topics}")
        print(f"tribute_compliant={r.tribute_compliant}")
        print(f"new_roles={r.new_roles}")
        print(f"institutions={r.institutions}")
        print(f"councils={r.councils}")
        print(f"enacted={len(r.enacted)} status_counts={r.status_counts}")
        print(f"witness={r.witness_path}")
        print(f"report={r.report_path}")
        return 0

    if args.cmd == "status":
        print(json.dumps(Society(live_fetch=False).status(), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
