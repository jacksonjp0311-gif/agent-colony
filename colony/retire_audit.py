"""Item 70: certified dead-weight retirement (tighten-only, replay-certified).

Why the 11:37 PM ET Nov 14 cap fill freed 0 slots: the three retire rules
(sweep / textbook_pair / trivial_frontier) matched none of the unprotected
authored checks. Of the 150, 50 were disabled checks the Oracle had killed on
every verdict and never passed: generated ``authored_mut_`` claims sent
through the stall-perturb path as kind ``authored_check``. sense_held_out
never lets that kind survive, so they cannot pass, are not in the bench, and
only hold cap slots.

Rule ``dead_weight`` (all must hold; the existing protections run first and
are unchanged):
  * an ``authored_*`` check, disabled in the catalog (not part of the bench);
  * judged by the Oracle at least once, never passed;
  * every verdict is a substantive held-out kill (``held_out:held_out_fail``).
    "Not applicable", blocked or error kills are mechanism failures and have
    turned into passes later, so they never qualify.

Certification: retire only when every replay agrees, otherwise abstain.
  R1 kill replay: each logged verdict's held-out sense is re-run from its own
     logged snapshot. This is only allowed for kinds where that sense is a
     pure function of the snapshot (no shifted window, no theme or pack run).
     Each replay must again give survives=False / held_out_fail.
  R2 verdict-history replay: no other Oracle row, current check or archived
     retired check names or calls the candidate, and the replayed pass count
     over the whole history is unchanged.
  R3 bench replay (in retire.apply): every remaining basic and hard check
     gives the same outcome, name by name, with and without the batch.
Any disagreement or any replay that cannot run means abstain.

On by default on the self-mod arm only (COLONY_RETIRE_DEAD_WEIGHT=off|shadow|live,
default live). On the control arm it is always off. Retirements are new
appended records in retired_checks.json; logs are never edited. Restore with
``python -m colony.retire restore NAME``. Nothing here touches the Oracle, P,
the 0.70 bar, the 150 cap, the Wilson gate or Athanor.
"""
from __future__ import annotations

import ast
import json
import os
import re
from typing import Any

DEAD_KILL = "held_out:held_out_fail"
CATEGORY = "dead_weight"
DEAD_FAMILY_MIN = 3
_IMPURE_KINDS = ("claim_theme", "bench_keep", "hard_check", "hard_enable")
_HASH = re.compile(r"_[0-9a-f]{12}$")


def mode() -> str:
    try:
        from colony.arm import self_mod_enabled
        if not self_mod_enabled():
            return "off"
    except Exception:  # noqa: BLE001
        return "off"
    m = os.environ.get("COLONY_RETIRE_DEAD_WEIGHT", "live").strip().lower()
    return m if m in ("off", "shadow", "live") else "off"


def replay_pure(kind: str) -> bool:
    """True when sense_held_out for ``kind`` depends only on the logged snapshot."""
    k = (kind or "").strip()
    if not k or k.startswith(("hard", "stem")) or k in _IMPURE_KINDS:
        return False
    return True


def _snapshot(row: dict[str, Any]) -> dict[str, Any] | None:
    h = ((row.get("sense") or {}).get("held_out")) or {}
    if "hard_pass" not in h or "hard_n" not in h:
        return None
    return {"n_hard_pass": h.get("hard_pass"), "n_hard": h.get("hard_n"), "ok": h.get("ok"), "score": h.get("score")}


def replay_kill(row: dict[str, Any]) -> tuple[bool, str]:
    """R1 for one verdict row: (agrees, why)."""
    kind = str(row.get("kind") or "")
    if not replay_pure(kind):
        return False, f"kill replay not deterministic for kind {kind or '?'}"
    snap = _snapshot(row)
    if snap is None:
        return False, "no logged held-out snapshot"
    try:
        from colony.oracle import sense_held_out
        r = sense_held_out(str(row.get("mutation") or ""), kind, after_snapshot=snap)
    except Exception as e:  # noqa: BLE001
        return False, f"kill replay error: {type(e).__name__}"
    if r.get("survives") is False and r.get("reason") == "held_out_fail":
        return True, "kill replay agrees"
    return False, f"kill replay disagrees ({r.get('reason')})"


def dead_history(rows: list[dict[str, Any]]) -> str | None:
    """None when a check's verdict history is all substantive held-out kills, else why not."""
    if not rows:
        return "not judged"
    for r in rows:
        if r.get("passed"):
            return "passed the Oracle"
        if DEAD_KILL not in (r.get("kills") or []):
            return "a kill that is not a substantive held-out fail"
    return None


def _refs(text: str, name: str) -> bool:
    return re.search(rf"(?<![a-z0-9_]){re.escape(name)}(?![a-z0-9_])", text) is not None


def certify(name: str, oracle_rows: list[dict[str, Any]], *, fns: dict[str, ast.FunctionDef],
            archived_src: list[str] | None = None) -> dict[str, Any]:
    """R1 + R2 for one candidate whose history is dead. {'ok': bool, 'replay': {...}, 'why': str}."""
    own = [r for r in oracle_rows if r.get("mutation") == name]
    why = dead_history(own)
    if why:
        return {"ok": False, "why": why}
    for r in own:
        ok, w = replay_kill(r)
        if not ok:
            return {"ok": False, "why": w}
    for r in oracle_rows:
        if r.get("mutation") != name and _refs(json.dumps(r), name):
            return {"ok": False, "why": f"named in the Oracle verdict for {r.get('mutation')}"}
    for fn_name, fn in fns.items():
        if fn_name != f"check_{name}" and any(isinstance(x, ast.Name) and x.id == f"check_{name}" for x in ast.walk(fn)):
            return {"ok": False, "why": f"called by {fn_name}"}
    for s in archived_src or []:
        if _refs(s, f"check_{name}"):
            return {"ok": False, "why": "called by an archived retired check"}
    before = sum(1 for r in oracle_rows if r.get("passed"))
    after = sum(1 for r in oracle_rows if r.get("passed") and r.get("mutation") != name)
    if before != after:
        return {"ok": False, "why": "replayed pass count would change"}
    return {"ok": True, "why": "every replay agrees",
            "replay": {"verdicts": len(own), "kill_replays_agree": len(own), "kind": own[-1].get("kind"),
                       "history_refs": 0, "passes_before": before, "passes_after": after}}


def candidates(authored: list[str], flags: dict[str, bool | None], protected: dict[str, str],
               oracle_rows: list[dict[str, Any]], fns: dict[str, ast.FunctionDef], *,
               archived_src: list[str] | None = None, skip: set[str] | None = None) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """(certified candidate dicts, {name: abstain reason}) for disabled, never-passed checks."""
    if mode() == "off":
        return [], {}
    judged = {r.get("mutation") for r in oracle_rows}
    out: list[dict[str, Any]] = []
    abstain: dict[str, str] = {}
    for n in authored:
        if n in protected or (skip and n in skip) or flags.get(n) is not False or n not in judged:
            continue
        c = certify(n, oracle_rows, fns=fns, archived_src=archived_src)
        if not c["ok"]:
            if c["why"] not in ("passed the Oracle",):
                abstain[n] = c["why"]
            continue
        rp = c["replay"]
        out.append({"name": n, "category": CATEGORY, "replay": rp,
                    "reason": (f"disabled, Oracle-killed on all {rp['verdicts']} verdict(s) (held_out_fail, kind "
                               f"{rp['kind']}), never passed; kill replay agrees, no verdict or check depends on it, "
                               f"passes {rp['passes_before']} -> {rp['passes_after']}")})
    return out, abstain


def family(name: str) -> str:
    return _HASH.sub("", name)


def dead_families(oracle_rows: list[dict[str, Any]]) -> set[str]:
    """Generated families (``authored_mut_<kind>``) with >= DEAD_FAMILY_MIN members whose whole
    history is replay-certified held-out kills, and no member that ever passed."""
    by: dict[str, list[dict[str, Any]]] = {}
    for r in oracle_rows:
        m = str(r.get("mutation") or "")
        if m.startswith("authored_mut_"):
            by.setdefault(m, []).append(r)
    fams: dict[str, list[bool]] = {}
    for m, rows in by.items():
        dead = dead_history(rows) is None and all(replay_kill(r)[0] for r in rows)
        fams.setdefault(family(m), []).append(dead)
    return {f for f, v in fams.items() if all(v) and len(v) >= DEAD_FAMILY_MIN}


def bench_agrees(before: dict[str, Any], after: dict[str, Any]) -> tuple[bool, str]:
    """R3: identical per-check outcomes on every remaining check."""
    if before.get("error") or after.get("error"):
        return False, "bench replay could not run"
    for tier in ("basic", "hard"):
        b, a = before.get(tier) or {}, after.get(tier) or {}
        if set(b) != set(a):
            return False, f"{tier} check set changed"
        diff = sorted(k for k in b if bool(b[k]) != bool(a[k]))
        if diff:
            return False, f"{tier} outcome changed: {diff[:5]}"
    return True, "bench replay agrees"


def stall_audit(st: dict[str, Any], cycle_id: str = "", *, plan_fn=None) -> dict[str, Any] | None:
    """Item 70 (b): when self-heal has no proposal, spend the stall on a retirement audit.

    Read-only: runs the retire plan, records what certified retirement would
    free (and why others abstain) in trial_skip and, once per change, in
    ``retirement_audits`` (last 20). Retiring itself stays in the retire
    stage. Self-mod arm only.
    """
    if mode() == "off":
        return None
    try:
        from colony import retire as R
        p = (plan_fn or R.plan)()
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}
    dead = [c["name"] for c in p.get("candidates") or [] if c.get("category") == CATEGORY]
    abst = p.get("dead_weight_abstained") or {}
    why: dict[str, int] = {}
    for v in abst.values():
        why[v] = why.get(v, 0) + 1
    audit = {"cycle_id": cycle_id, "n_authored": p.get("n_authored"), "would_free": p.get("n_candidates", 0),
             "by_category": p.get("by_category") or {}, "dead_weight": len(dead),
             "abstained": len(abst), "abstain_reasons": why, "n_protected": len(p.get("protected") or {}),
             "dead_families": p.get("dead_families") or [], "mode": mode()}
    if isinstance(st.get("trial_skip"), dict):
        st["trial_skip"]["retirement_audit"] = audit
    sig = [audit["would_free"], sorted(dead)]
    if st.get("retirement_audit_sig") != sig:
        st["retirement_audit_sig"] = sig
        # kept beside (not in) trial evidence, so evidence[-1] stays the last trial event
        log = st.setdefault("retirement_audits", [])
        del log[:-19]
        log.append({
            "event": "retirement_audit", "cycle_id": cycle_id,
            **{k: audit[k] for k in ("would_free", "by_category", "dead_weight", "abstained", "abstain_reasons")},
            "names": sorted(dead)[:60], "authorized": False})
    return audit
