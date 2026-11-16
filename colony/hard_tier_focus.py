"""Item 103: steer hard-tier (OEIS conjecture desk) time toward targets with the best historical
chance of a counterexample or a non-routine proof. Ordering only, same Oracle / checkers.

Measured (society/systems/oeis_attempt_log.json, 210 attempts): every proof so far is a routine
relation (24 proved_checked, all form ``relation``); counterexamples 0. The only near-misses are
``proof_rejected`` rows: 16 of 35 ``gf`` attempts, on exactly the targets the colony extended
past the published b-file (A165064, A094213, A308215, ...); every gf attempt was tested past the
b-file (35/35 near-miss by the rule below), relations 48 of 174 (holds beyond the b-file).

Factor on the desk's existing score inside ``oeis_conjectures.choose`` (bands untouched):
  * form near-miss rate: 0.75 + 1.5 * (near_misses + 1) / (attempts + 2), clamped [0.75, 1.75];
    near-miss = proof_rejected, or a hold that was tested beyond the published range;
  * counterexample window: x1.25 when the target can be searched past its b-file and has not been
    tested past it yet (a published conjecture can only fail beyond the published data);
  * target near-miss: x1.2 for a target with a proof_rejected attempt and < 10 attempts;
  * stated conjecture: x1.5 when the OEIS entry itself labels the claim a conjecture (e.g.
    "Conjectures from ..." blocks): a proven formula can never yield a counterexample, and only an
    open claim can yield a non-routine proof. 16 of the 164 menu entries are labelled so.
Finding at the time of writing: the menu had 0 open targets (94 held on the published range
with no way past it, 29 already attempted at their depth, 26 closed, 15 cannot progress), so this
steers the refills target_supply adds each cycle; it cannot create targets.
Total clamped to [0.5, 2.5]. Nothing is removed, no check or threshold changes.

Switch ``COLONY_HARD_TIER_FOCUS`` = live (default) | off; off on the control arm.
"""
from __future__ import annotations

import os
from typing import Any, Mapping

NEAR_MISS_STATUSES = ("proof_rejected",)
MIN_F, MAX_F = 0.5, 2.5


def enabled() -> bool:
    try:
        from colony.arm import self_mod_enabled
        if not self_mod_enabled():
            return False
    except Exception:  # noqa: BLE001
        return False
    return (os.environ.get("COLONY_HARD_TIER_FOCUS") or "live").strip().lower() == "live"


def _near_miss(row: Mapping[str, Any]) -> bool:
    if row.get("status") in NEAR_MISS_STATUSES:
        return True
    return row.get("status") == "holds_on_range" and bool(row.get("beyond"))


def stats(log: Mapping[str, Any] | None) -> dict[str, Any]:
    forms: dict[str, dict[str, int]] = {}
    targets: dict[str, dict[str, int]] = {}
    for r in (log or {}).get("attempts") or []:
        f = str(r.get("form") or "")
        s = forms.setdefault(f, {"attempts": 0, "near_misses": 0})
        s["attempts"] += 1
        nm = _near_miss(r)
        s["near_misses"] += int(nm)
        t = targets.setdefault(str(r.get("id") or ""), {"proof_rejected": 0})
        t["proof_rejected"] += int(r.get("status") == "proof_rejected")
    return {"forms": forms, "targets": targets}


def stated_conjecture(e: Mapping[str, Any]) -> bool:
    for k in ("block_header", "section"):
        if "conjectur" in str(e.get(k) or "").lower():
            return True
    return False


def form_factor(form: str, st: Mapping[str, Any]) -> float:
    s = (st.get("forms") or {}).get(form) or {}
    n, nm = int(s.get("attempts") or 0), int(s.get("near_misses") or 0)
    return max(0.75, min(1.75, 0.75 + 1.5 * (nm + 1) / (n + 2)))


def factor(e: Mapping[str, Any], target_state: Mapping[str, Any] | None, st: Mapping[str, Any], *,
           past: bool, bfile_hi: int) -> float:
    form = str((e.get("claim") or {}).get("form") or "")
    f = form_factor(form, st)
    tested = int((target_state or {}).get("tested_hi") or 0)
    if past and tested <= int(bfile_hi):
        f *= 1.25
    t = (st.get("targets") or {}).get(str(e.get("id") or "")) or {}
    if int(t.get("proof_rejected") or 0) > 0 and int((target_state or {}).get("attempts") or 0) < 10:
        f *= 1.2
    if stated_conjecture(e):
        f *= 1.5
    return max(MIN_F, min(MAX_F, f))
