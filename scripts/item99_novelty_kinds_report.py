"""Item 99: which proposal families repeat most in the novelty-gate log (read-only)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from colony.novelty_kind_bias import LOOKBACK, _rows, report  # noqa: E402

if __name__ == "__main__":
    for window in (30, LOOKBACK):
      for desk_only in (False, True):
        print(f"--- last {window} novelty-gate rows ({'desk kinds -> order factor' if desk_only else 'all kinds'})")
        for r in report(_rows(lookback=window), desk_only=desk_only):
            print(f"{r['family']:<28} rows={r['rows']:<4} hits={r['hits']:<4} repeats={r['repeats']:<4} factor={r['factor']}")
