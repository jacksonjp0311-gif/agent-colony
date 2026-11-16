"""Item 83: local pre-screen before an Oracle submission (strictly a pre-filter).

It runs the Oracle's OWN held-out check (``colony.oracle.sense_held_out``, called
directly, so it follows any future Oracle change) with a best-case bench snapshot:
everything enabled and green. In sense_held_out a green bench is necessary for
survival, never sufficient. So if the candidate fails even with the best-case
bench, the real Oracle run (same code, same lemma file, a moment later) fails
held-out too. A held-out failure means no sense_pass, and the collective vote's
absolute rule means no sense_pass is a kill. The candidate is dropped before it
uses an Oracle attempt.

What gets dropped:
  * kinds whose held-out cannot survive at all (process titles such as the
    ``Chain`` / ``Chain+seek`` wrappers, authored_check, oeis_conjecture,
    claim_shape, easy_pad): 0 passes in the whole Oracle history;
  * claim_theme claims whose theme window is missing, not in the catalog, or
    disabled (``held_out:already_saturated_no_harder_window``): this depends
    only on the lemma catalog, not on the bench.

Item 96: a ``stem_enable`` whose check is a symbolic tautology of its own definitions is
dropped (``trivial:stem_symbolic_tautology``): the novelty gate's own item-95 triviality kill,
so it would be killed regardless of the Oracle. Its held-out is still never pre-screened.

What is never pre-screened by held-out: kinds whose held-out runs real work (hard_enable /
hard_check shifted window, stem packs), the empty kind, and easy_pad (the Oracle's
sieve self-test, whose kill is the point). Those always go to
the Oracle. Everything that is submitted is judged by the unchanged Oracle.

A drop is not an Oracle row and is never counted as an Oracle verdict. It is
appended to data/commons/oracle_prescreen.jsonl and written as an
``oracle_prescreen`` lesson. The lesson carries the same catalog_hint the
Oracle kill lesson would have, and it counts toward the kill cooldown like
that kill, so a dropped wrapper is not re-proposed forever.

COLONY_ORACLE_PRESCREEN = live | shadow | off (default live). Shadow logs what
would be dropped and drops nothing. Off on the control arm.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PRESCREEN_LOG = ROOT / "data" / "commons" / "oracle_prescreen.jsonl"
BEST_SNAPSHOT = {"ok": True, "n_hard_pass": 1, "n_hard": 1, "score": 1.0}
# easy_pad is the Oracle's own sieve self-test (its kill is the point); never pre-screened
_NOT_SCREENED = ("hard_enable", "hard_check", "easy_pad", "stem_easy_pad")


def mode() -> str:
    try:
        from colony.arm import self_mod_enabled
        if not self_mod_enabled():
            return "off"
    except Exception:  # noqa: BLE001
        return "off"
    m = os.environ.get("COLONY_ORACLE_PRESCREEN", "live").strip().lower()
    return m if m in ("live", "shadow", "off") else "off"


def screened_kind(kind: str) -> bool:
    k = (kind or "").strip()
    return bool(k) and k not in _NOT_SCREENED and not k.startswith("stem")


def held_out_best_case(mutation: str, kind: str) -> dict[str, Any] | None:
    """The Oracle's held-out result with a best-case bench; None when not screened."""
    if not screened_kind(kind):
        return None
    from colony.oracle import sense_held_out
    return sense_held_out((mutation or "").strip(), kind, after_snapshot=dict(BEST_SNAPSHOT))


def stem_trivial_drop(mutation: str, kind: str) -> dict[str, Any] | None:
    """Item 96: a ``stem_enable`` the novelty gate kills as a symbolic tautology anyway.

    This calls the novelty gate's OWN triviality kill (``stem_triviality_kill``, item 95), so it
    can only drop what the gate would kill as trivial regardless of the Oracle's verdict.
    The check reads only the check function's body, which an enable does not change.
    Treatment only (the gate function returns None when self-mod is off)."""
    if (kind or "").strip() != "stem_enable":
        return None
    from colony.novelty_gate import stem_triviality_kill
    t = stem_triviality_kill((mutation or "").strip(), "stem_enable")
    if not (t and t.get("trivial")):
        return None
    return {"mutation": (mutation or "").strip(), "kind": kind, "would_kill": f"trivial:{t.get('reason')}",
            "rule": "novelty_gate.stem_triviality_kill (the gate's own kill; not an Oracle verdict)",
            "catalog_hint": None}


def check(mutation: str, kind: str) -> dict[str, Any] | None:
    """A drop record when the candidate cannot pass the Oracle's held-out, else None."""
    if (kind or "").strip() == "stem_enable":
        try:
            return stem_trivial_drop(mutation, kind)
        except Exception:  # noqa: BLE001
            return None  # cannot tell: submit (the Oracle decides)
    try:
        held = held_out_best_case(mutation, kind)
    except Exception:  # noqa: BLE001
        return None  # cannot tell: submit (the Oracle decides)
    if held is None or held.get("survives") is not False:
        return None
    reason = str(held.get("reason") or "")
    if not reason or reason.startswith(("error:", "held_out_theme_error", "stem_pack_err")):
        return None
    return {"mutation": (mutation or "").strip(), "kind": kind, "would_kill": f"held_out:{reason}",
            "rule": "oracle.sense_held_out with best-case bench", "catalog_hint": held.get("catalog_hint")}


def screen(mutation: str, kind: str, *, source: str = "", cycle_id: str = "",
           claim_text: str = "") -> dict[str, Any] | None:
    """Return the drop record if the submission should be dropped (live), else None.

    In shadow mode the would-drop is logged and None is returned (submit as before)."""
    m = mode()
    if m == "off":
        return None
    drop = check(mutation, kind)
    if drop is None:
        return None
    drop = {**drop, "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "source": source,
            "cycle_id": cycle_id, "mode": m, "dropped": m == "live", "not_an_oracle_verdict": True}
    _append(drop)
    if m != "live":
        return None
    _lesson(drop, claim_text)
    return drop


def _append(row: dict[str, Any]) -> None:
    if os.environ.get("PYTEST_CURRENT_TEST") and PRESCREEN_LOG == ROOT / "data" / "commons" / "oracle_prescreen.jsonl":
        return
    try:
        PRESCREEN_LOG.parent.mkdir(parents=True, exist_ok=True)
        with PRESCREEN_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _lesson(drop: dict[str, Any], claim_text: str) -> None:
    try:
        from colony.lessons import write_lesson
        hint = drop.get("catalog_hint")
        write_lesson(
            decision="revert",
            check="oracle_prescreen",
            what=(f"Pre-screen drop (not an Oracle verdict): the Oracle's held-out would kill "
                  f"`{drop['mutation'][:120]}` kind={drop['kind']} ({drop['would_kill']}). {claim_text[:200]}")[:500],
            source=drop.get("source") or "oracle_prescreen",
            cycle_id=drop.get("cycle_id") or "",
            mutation=drop["mutation"],
            family=drop["kind"] or "oracle",
            lesson_type="oracle_prescreen",
            tags=["oracle_prescreen", drop["would_kill"]],
            evidence=[f"would_kill:{drop['would_kill']}"],
            catalog_hint=hint if isinstance(hint, dict) else None,
        )
    except Exception:  # noqa: BLE001
        pass


def replay_drop(row: dict[str, Any]) -> bool:
    """Replay on a logged Oracle row: would the pre-screen have dropped it at the time?

    Screened kinds whose held-out does not read the catalog are re-run on the
    current Oracle code (their outcome does not depend on state). Theme claims
    use the row's own logged held-out (rules and catalog as of that verdict):
    under a best-case bench they survive iff the logged reason was a green-bench
    or theme-window outcome.
    """
    kind = str(row.get("kind") or "")
    if not screened_kind(kind):
        return False
    if kind in ("claim_theme", "bench_keep"):
        held = ((row.get("sense") or {}).get("held_out")) or {}
        reason = str(held.get("reason") or "")
        if held.get("survives") or reason in ("held_out_hard_green", "held_out_theme_window_green",
                                               "held_out_theme_window_fail"):
            return False
        return "already_saturated_no_harder_window" in reason or reason == "no_theme_held_out_window"
    return check(str(row.get("mutation") or ""), kind) is not None
