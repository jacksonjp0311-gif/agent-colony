"""Diff-scope guard: an enable mutation may change exactly one catalog flag, nothing else.

Catches evaluation tampering and hidden regressions smuggled in with an enable (e.g. a
patched ``run_hard_checks`` that swallows failures, or an edited shared helper that still
passes in-window). The desk kills the mutation before the Oracle when this fails.
"""
from __future__ import annotations

import difflib
import re


def enable_diff_ok(before: str, after: str, name: str) -> dict:
    pat = re.compile(rf'(\("{re.escape(name)}",\s*.*?,\s*)False(\))', re.S)
    m = pat.search(before)
    if not m:
        return {"ok": False, "reason": "entry_absent_or_already_enabled"}
    expected = before[: m.start()] + m.group(1) + "True" + m.group(2) + before[m.end():]
    if after == expected:
        return {"ok": True, "reason": "single_flag_flip"}
    diff = [ln for ln in difflib.unified_diff(expected.splitlines(), after.splitlines(), lineterm="", n=0)
            if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---"))]
    return {"ok": False, "reason": "out_of_scope_change", "extra_diff": diff[:12]}
