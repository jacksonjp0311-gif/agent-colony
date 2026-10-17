"""Colony evolve must evolve from current main, not a stale event SHA (queued cron vs dispatch race)."""
from pathlib import Path

WF = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "colony-evolve.yml"


def test_checkout_uses_current_main_and_runs_are_serialized():
    s = WF.read_text(encoding="utf-8")
    i = s.index("uses: actions/checkout@v4")
    assert "ref: main" in s[i:i + 400]
    assert "group: colony-evolve" in s and "cancel-in-progress: false" in s
