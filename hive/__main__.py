"""``python -m hive`` — a short standalone self-check.

Seeds the in-memory library from shipped examples, trains a Bitwork
router, runs held-out replay, and prints a plain report. No host
application is required and no files outside a temp directory are
written. This is not a claim of capability gain; it is a check that
the package runs on its own.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import hive.library as library
import hive.ops as ops
from hive import __version__
from hive.bitwork import WILSON_ACCEPT_PERMILLE, Router, wilson_lower_permille


def main() -> int:
    seeds = library.seed_patterns()
    print(f"Hive {__version__}")
    print(f"shipped seed records: {len(seeds)}")
    print(f"closed ops: {', '.join(sorted(ops.OPS))}")
    print(f"Wilson accept threshold: {WILSON_ACCEPT_PERMILLE} permille")

    with tempfile.TemporaryDirectory() as raw:
        path = Path(raw) / "fix_library.jsonl"
        written = library.seed_into(path=path)
        print(f"wrote {len(written)} seed records to a temp library")
        router = library.train_router(path=path)
        cases = library.held_out_cases(library.load_records(path=path))
        report = router.replay_accuracy(cases, hold_out=True)
        print(
            "held-out replay (uncalibrated gate): "
            f"n={report['n']} correct={report['correct']} "
            f"abstained={report['abstained']} "
            f"accuracy={report['accuracy_permille']} permille "
            f"Wilson lower={report['lower_permille']} permille"
        )
        # Honest calibration from those labeled leave-one-out results.
        import hive.swarm as swarm
        st = swarm._empty_state()
        calib = swarm.calibrate_from_replay(router, st, cases=cases)
        after = router.replay_accuracy(cases, hold_out=True)
        print(
            "replay-seeded calibration: "
            f"n={calib['n']} correct={calib['correct']} source=replay; "
            f"after, abstained={after['abstained']} "
            f"(Wilson gate unchanged at {WILSON_ACCEPT_PERMILLE} permille)"
        )
        # A second, empty router demonstrates abstention before calibration.
        fresh = Router()
        lower = wilson_lower_permille(0, 0)
        print(f"uncalibrated Wilson lower (0/0): {lower} permille (abstain)")
        print("Hive does not write free-form code and does not call an outside model.")
        print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
