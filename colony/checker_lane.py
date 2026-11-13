"""Tighten-only Oracle checker proposal lane.

Mines Oracle, kill, and re-judge logs for checker *candidates*: new
trap or triviality patterns, stricter novelty tests, and wider shifted
windows. Candidates are data. They are never applied to the live Oracle.

A candidate is accepted for human review only if all of these hold:

* it is tighten-only — applying it to the historical verdict set would
  never turn a past FAIL/KILL into a PASS
* it does not touch a fixed invariant (the P ≥ 0.70 gate, the 150
  authored-check cap, Athanor math, human authorize, append-only witness)
* a replay against the full verdict history keeps every still-valid
  PASS passing, and catches at least one known-bad that previously
  slipped through
* any unexplained PASS → FAIL flip rejects it

Accepted candidates show up in telemetry and on the dashboard as
"checker proposals awaiting human review", with their replay evidence.
A helper can write a plain-English proposal file a human can turn into
a PR. Nothing here changes a live check.

Results are recorded append-only. Failures in this lane never break
the evolve cycle. This module does not alter the Oracle, the 0.70
gate, the 150 cap, or Athanor math.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parent.parent
LANE_LOG = ROOT / "data" / "commons" / "checker_lane.jsonl"
STATE_PATH = ROOT / "society" / "systems" / "checker_lane.json"
PROPOSAL_DIR = ROOT / "society" / "systems" / "checker_proposals"
# Committed, auditable receipt. The snapshot, jsonl, and proposal files
# above are gitignored and do not survive a fresh CI checkout.
RECEIPT_PATH = ROOT / "society" / "systems" / "checker_lane_receipt.json"
RECEIPT_KEEP = 80

# Live values, compared against only. This module never writes them.
LIVE_P_MIN = 0.70
LIVE_AUTHORED_CAP = 150
LIVE_TEXTBOOK_REUSE_KILL_AT = 0.34  # mirrors colony.novelty_gate.evaluate
LIVE_MIN_WINDOW = 30  # mirrors colony.trust.shifted_holdout.MIN_WINDOW

CANDIDATE_KINDS = frozenset({
    "trap_pattern",
    "triviality_pattern",
    "stricter_novelty",
    "wider_shifted_window",
})
LOOSENING_ACTIONS = frozenset({
    "allow", "exempt", "loosen", "relax", "whitelist", "permit", "drop", "disable",
})
# Keys a candidate must not carry: touching these is an automatic reject.
_INVARIANT_KEYS = frozenset({
    "p_min", "pmin", "standing_trust_p_min", "authorize_p",
    "authored_cap", "max_authored_total", "max_authored", "authored_check_cap",
    "athanor", "dphi", "delta_phi", "h7", "athanor_math", "coherence_c",
    "authorize", "human_authorize", "authorization",
    "witness", "witness_append_only", "rewrite_witness",
})
# Kill reasons that mean the claim itself was wrong (not just exhausted).
# Conservative: when in doubt, do not invalidate an earlier PASS.
_INVALIDATING_FRAGMENTS = (
    "trivial:",
    "triviality",
    "easy_pad",
    "textbook",
    "known_identity",
    "already_in_lesson",
    "counterexample",
    "false_pass",
    "later_invalid",
    "rejudge_fail",
    "cas:easy_pad",
    "cas:fails",
)
_NOT_INVALIDATING_FRAGMENTS = (
    "already_saturated",
    "no_harder_window",
    "shift_not_applicable",
    "catalog_exhausted",
    "oracle_blocked_no_bus",
    "no_data_headroom",
    "tentative_not_keep",
)

ApplyFn = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# History: load and label verdicts
# ---------------------------------------------------------------------------

def _read_jsonl(path: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    if limit is not None:
        lines = lines[-limit:]
    out: list[dict[str, Any]] = []
    for ln in lines:
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def load_oracle_rows(*, limit: int | None = None) -> list[dict[str, Any]]:
    try:
        from colony.oracle import ORACLE_LOG
        return _read_jsonl(ORACLE_LOG, limit=limit)
    except Exception:
        return []


def load_lesson_rows(*, limit: int | None = None) -> list[dict[str, Any]]:
    try:
        from colony.lessons import LESSONS_JSONL
        path = LESSONS_JSONL
    except Exception:
        path = ROOT / "data" / "commons" / "lessons.jsonl"
    try:
        return _read_jsonl(path, limit=limit)
    except Exception:
        return []


def is_invalidating_kill(verdict: dict[str, Any]) -> bool:
    """True when this FAIL means the claim itself was wrong.

    Saturation, missing windows, and process blocks do not invalidate a
    prior PASS of the same name. An explicit ``invalidates_prior_pass``
    flag on the row always wins (fixtures and future logs).
    """
    flag = verdict.get("invalidates_prior_pass")
    if flag is True:
        return True
    if flag is False:
        return False
    if verdict.get("passed") is True:
        return False
    blob = " ".join(str(k) for k in (verdict.get("kills") or [])).lower()
    blob += " " + str(verdict.get("note") or "").lower()
    if any(frag in blob for frag in _NOT_INVALIDATING_FRAGMENTS):
        # A mixed kill list that also has an invalidating reason still counts
        # as invalidating, unless the only hits are the exclusion list.
        if not any(frag in blob for frag in _INVALIDATING_FRAGMENTS):
            return False
    return any(frag in blob for frag in _INVALIDATING_FRAGMENTS)


def label_history(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy rows and add a ``label`` field, in the given (time) order.

    Labels:
      * ``pass_still_valid`` — a PASS never shown wrong by a later
        invalidating kill; the latest verdict being a PASS also keeps
        earlier passes in this bucket (the claim is currently good).
      * ``pass_later_invalidated`` — a PASS followed later, for the same
        mutation, by an invalidating FAIL, and the latest verdict is not
        a PASS.
      * ``kill`` — a FAIL / KILL (stays a kill; a tighten-only candidate
        must not turn it into a PASS).
    """
    labelled: list[dict[str, Any]] = []
    groups: dict[str, list[int]] = {}
    for i, raw in enumerate(rows):
        row = dict(raw)
        row["_idx"] = i
        labelled.append(row)
        name = str(row.get("mutation") or "").strip()
        if name:
            groups.setdefault(name, []).append(i)
    for _name, idxs in groups.items():
        evs = [labelled[i] for i in idxs]
        last = evs[-1]
        last_is_pass = last.get("passed") is True
        inv_after: dict[int, bool] = {}
        for pos, ev in enumerate(evs):
            inv_after[pos] = any(
                evs[j].get("passed") is False and is_invalidating_kill(evs[j])
                for j in range(pos + 1, len(evs))
            )
        for pos, ev in enumerate(evs):
            if ev.get("passed") is True:
                if last_is_pass:
                    ev["label"] = "pass_still_valid"
                elif inv_after[pos]:
                    ev["label"] = "pass_later_invalidated"
                else:
                    ev["label"] = "pass_still_valid"
            else:
                ev["label"] = "kill"
    for row in labelled:
        if "label" not in row:
            row["label"] = "pass_still_valid" if row.get("passed") is True else "kill"
    return labelled


def build_history(
    oracle_rows: list[dict[str, Any]] | None = None,
    *,
    lessons: list[dict[str, Any]] | None = None,
    extra_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Assemble a labelled verdict history.

    ``extra_rows`` lets tests (and a future re-judge log) inject verdicts
    without touching live files. Lesson rows with
    ``invalidates_prior_pass`` or type ``oracle_false_pass`` mark the
    matching mutation's later kills as invalidating; they are not
    themselves Oracle verdicts.
    """
    rows = list(oracle_rows if oracle_rows is not None else load_oracle_rows())
    if extra_rows:
        rows.extend(extra_rows)
    # Lessons may flag a mutation as later-invalidated.
    flagged: set[str] = set()
    lesson_rows = lessons if lessons is not None else []
    for les in lesson_rows:
        ltype = str(les.get("lesson_type") or les.get("type") or "")
        if les.get("invalidates_prior_pass") or ltype in {"oracle_false_pass", "false_pass"}:
            name = str(les.get("mutation") or "").strip()
            if name:
                flagged.add(name)
    if flagged:
        for row in rows:
            if (
                str(row.get("mutation") or "").strip() in flagged
                and row.get("passed") is False
                and "invalidates_prior_pass" not in row
            ):
                row = row  # already a distinct dict if from extra; live rows stay
                # Do not mutate the caller's live dicts in place if we can avoid it.
        rows = [dict(r) for r in rows]
        for row in rows:
            if (
                str(row.get("mutation") or "").strip() in flagged
                and row.get("passed") is False
                and "invalidates_prior_pass" not in row
            ):
                row["invalidates_prior_pass"] = True
    return label_history(rows)


# ---------------------------------------------------------------------------
# Candidate identity and application (simulation only)
# ---------------------------------------------------------------------------

def fingerprint(candidate: dict[str, Any]) -> str:
    key = {
        "kind": candidate.get("kind"),
        "pattern": candidate.get("pattern"),
        "pattern_type": candidate.get("pattern_type"),
        "add_identities": candidate.get("add_identities"),
        "textbook_reuse_kill_at": candidate.get("textbook_reuse_kill_at"),
        "min_window": candidate.get("min_window"),
    }
    raw = json.dumps(key, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _blob(verdict: dict[str, Any]) -> str:
    return " ".join(
        str(verdict.get(k) or "")
        for k in ("mutation", "kind", "claim_text", "note")
    ).lower()


def _textbook_score(verdict: dict[str, Any]) -> float | None:
    if verdict.get("textbook_reuse") is not None:
        try:
            return float(verdict["textbook_reuse"])
        except (TypeError, ValueError):
            return None
    try:
        from colony.novelty_gate import textbook_reuse_score
        return float(textbook_reuse_score(
            str(verdict.get("mutation") or ""),
            str(verdict.get("claim_text") or ""),
        ))
    except Exception:
        return None


def candidate_fires(candidate: dict[str, Any], verdict: dict[str, Any]) -> bool:
    """Whether this candidate would add a kill on ``verdict`` (simulation)."""
    kind = str(candidate.get("kind") or "")
    if kind in ("trap_pattern", "triviality_pattern"):
        pat = str(candidate.get("pattern") or "").strip()
        if not pat:
            return False
        blob = _blob(verdict)
        if str(candidate.get("pattern_type") or "literal") == "regex":
            try:
                return bool(re.search(pat, blob, re.IGNORECASE))
            except re.error:
                return False
        return pat.lower() in blob

    if kind == "stricter_novelty":
        blob = _blob(verdict)
        for ident in candidate.get("add_identities") or []:
            token = str(ident).strip().lower()
            if token and (token in blob or token.replace("_", " ") in blob):
                return True
        thresh = candidate.get("textbook_reuse_kill_at")
        if thresh is not None:
            try:
                t = float(thresh)
            except (TypeError, ValueError):
                return False
            score = _textbook_score(verdict)
            if score is not None and score >= t:
                return True
        return False

    if kind == "wider_shifted_window":
        proposed = candidate.get("min_window")
        if proposed is None:
            return False
        try:
            proposed_i = int(proposed)
        except (TypeError, ValueError):
            return False
        evidence = verdict.get("window_evidence") or {}
        if not isinstance(evidence, dict):
            evidence = {}
        fails_at = evidence.get("fails_at") or evidence.get("would_fail_at_window")
        if fails_at is None:
            return False
        try:
            return proposed_i >= int(fails_at)
        except (TypeError, ValueError):
            return False

    return False


def simulate(candidate: dict[str, Any], verdict: dict[str, Any]) -> dict[str, Any]:
    """Apply a candidate in memory. May only add a kill, never remove one."""
    fired = candidate_fires(candidate, verdict)
    kills = list(verdict.get("kills") or [])
    if not fired:
        return {
            "passed": bool(verdict.get("passed")),
            "kills": kills,
            "fired": False,
        }
    cid = candidate.get("id") or fingerprint(candidate)
    reason = f"checker_candidate:{cid}"
    if reason not in kills:
        kills.append(reason)
    return {"passed": False, "kills": kills, "fired": True}


# ---------------------------------------------------------------------------
# Tighten-only guard
# ---------------------------------------------------------------------------

def _walk(obj: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k), v
            yield from _walk(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from _walk(x)


def invariant_hits(candidate: dict[str, Any]) -> list[str]:
    """Return invariant keys the candidate tries to set or change.

    A mention in ``rationale`` or ``source`` (values, not keys) is not a
    hit: proposals may say the invariants are unchanged.
    """
    hits: list[str] = []
    skip_value_only = {"rationale", "source", "note", "evidence", "id"}
    for k, _v in _walk(candidate):
        if k.lower() in skip_value_only:
            continue
        kl = k.lower().replace("-", "_")
        if kl in _INVARIANT_KEYS or kl in {x.replace("_", "") for x in _INVARIANT_KEYS}:
            hits.append(k)
            continue
        # Compound keys like "new_P_min" or "raise_authored_cap".
        compact = kl.replace("_", "")
        for inv in ("pmin", "authoredcap", "maxauthored", "athanor", "dphi",
                    "humanauthorize", "witnessappend"):
            if inv in compact:
                hits.append(k)
                break
    return sorted(set(hits))


def tighten_only_guard(
    candidate: dict[str, Any],
    history: list[dict[str, Any]],
    *,
    apply_fn: ApplyFn | None = None,
) -> dict[str, Any]:
    """Reject loosening, invariant-touching, or unknown candidates.

    ``apply_fn`` is for tests: a malicious applicator that would turn a
    FAIL into a PASS is still rejected here.
    """
    reasons: list[str] = []
    kind = str(candidate.get("kind") or "")
    if kind not in CANDIDATE_KINDS:
        reasons.append(f"unknown_kind:{kind or 'missing'}")
    direction = str(candidate.get("direction") or "").strip().lower()
    if direction != "tighten":
        reasons.append(f"direction_not_tighten:{direction or 'missing'}")
    action = str(candidate.get("action") or "").strip().lower()
    if action in LOOSENING_ACTIONS:
        reasons.append(f"loosening_action:{action}")
    if candidate.get("exempt_mutations") or candidate.get("whitelist"):
        reasons.append("loosening_exemption_field")

    inv = invariant_hits(candidate)
    if inv:
        reasons.append("touches_invariant:" + ",".join(inv))

    thresh = candidate.get("textbook_reuse_kill_at")
    if thresh is not None:
        try:
            t = float(thresh)
            if t > LIVE_TEXTBOOK_REUSE_KILL_AT + 1e-12:
                reasons.append(
                    f"novelty_looser_than_live:{t}>{LIVE_TEXTBOOK_REUSE_KILL_AT}"
                )
            if t <= 0:
                reasons.append("novelty_threshold_not_positive")
        except (TypeError, ValueError):
            reasons.append("novelty_threshold_unreadable")

    window = candidate.get("min_window")
    if window is not None:
        try:
            w = int(window)
            if w < LIVE_MIN_WINDOW:
                reasons.append(f"window_narrower_than_live:{w}<{LIVE_MIN_WINDOW}")
            if w == LIVE_MIN_WINDOW and kind == "wider_shifted_window":
                reasons.append("window_not_wider_than_live")
        except (TypeError, ValueError):
            reasons.append("window_unreadable")

    if kind in ("trap_pattern", "triviality_pattern"):
        if not str(candidate.get("pattern") or "").strip():
            reasons.append("empty_pattern")

    applicator = apply_fn or simulate
    fail_to_pass: list[str] = []
    for row in history:
        if row.get("passed") is True:
            continue
        try:
            nxt = applicator(candidate, row)
        except Exception as exc:  # noqa: BLE001
            reasons.append(f"apply_error:{type(exc).__name__}")
            break
        if nxt.get("passed") is True:
            fail_to_pass.append(str(row.get("mutation") or row.get("_idx") or "?"))
    if fail_to_pass:
        reasons.append(
            "would_turn_fail_into_pass:" + ",".join(fail_to_pass[:8])
        )

    ok = not reasons
    return {
        "ok": ok,
        "accepted": ok,
        "reasons": reasons,
        "fingerprint": fingerprint(candidate),
        "note": (
            "tighten-only guard passed"
            if ok
            else "tighten-only guard rejected: " + "; ".join(reasons)
        ),
    }


# ---------------------------------------------------------------------------
# Replay harness
# ---------------------------------------------------------------------------

def replay_candidate(
    candidate: dict[str, Any],
    history: list[dict[str, Any]],
    *,
    apply_fn: ApplyFn | None = None,
) -> dict[str, Any]:
    """Replay ``candidate`` against a labelled verdict history.

    Accepts for human review only when the guard passes, every
    still-valid PASS still passes, at least one slipped known-bad is
    caught, and there is no unexplained PASS → FAIL flip and no
    FAIL → PASS flip.
    """
    labelled = history if all("label" in r for r in history) else label_history(history)
    guard = tighten_only_guard(candidate, labelled, apply_fn=apply_fn)
    record: dict[str, Any] = {
        "ts": _utc(),
        "candidate_id": candidate.get("id") or f"chk_{fingerprint(candidate)}",
        "fingerprint": fingerprint(candidate),
        "kind": candidate.get("kind"),
        "guard": guard,
        "accepted": False,
        "reasons": list(guard.get("reasons") or []),
        "known_good_kept": 0,
        "known_good_total": 0,
        "known_bad_caught": [],
        "known_bad_total": 0,
        "unexplained_pass_to_fail": [],
        "fail_to_pass": [],
        "applied_to_live_oracle": False,
    }
    if not guard.get("ok"):
        record["reasons"].append("guard_rejected")
        record["note"] = guard.get("note")
        return record

    applicator = apply_fn or simulate
    known_bad_caught: list[str] = []
    unexplained: list[str] = []
    fail_to_pass: list[str] = []
    good_kept = 0
    good_total = 0
    bad_total = 0

    for row in labelled:
        label = str(row.get("label") or "")
        name = str(row.get("mutation") or "")
        try:
            nxt = applicator(candidate, row)
        except Exception as exc:  # noqa: BLE001
            record["reasons"].append(f"apply_error:{type(exc).__name__}")
            record["note"] = "replay aborted on apply error"
            return record
        was_pass = row.get("passed") is True
        now_pass = nxt.get("passed") is True

        if not was_pass and now_pass:
            fail_to_pass.append(name or str(row.get("_idx")))
        if label == "pass_still_valid":
            good_total += 1
            if now_pass:
                good_kept += 1
            else:
                unexplained.append(name or str(row.get("_idx")))
        elif label == "pass_later_invalidated":
            bad_total += 1
            if not now_pass and nxt.get("fired"):
                if name not in known_bad_caught:
                    known_bad_caught.append(name)

    record["known_good_kept"] = good_kept
    record["known_good_total"] = good_total
    record["known_bad_caught"] = known_bad_caught
    record["known_bad_total"] = bad_total
    record["unexplained_pass_to_fail"] = unexplained
    record["fail_to_pass"] = fail_to_pass

    reasons = record["reasons"]
    if fail_to_pass:
        reasons.append("fail_to_pass:" + ",".join(fail_to_pass[:8]))
    if unexplained:
        reasons.append("unexplained_pass_to_fail:" + ",".join(unexplained[:8]))
    if good_total and good_kept < good_total:
        reasons.append(f"lost_known_good:{good_kept}/{good_total}")
    if not known_bad_caught:
        reasons.append("no_known_bad_caught")

    accepted = not reasons
    record["accepted"] = accepted
    record["note"] = (
        "accepted for human review; not applied to the live Oracle"
        if accepted
        else "replay rejected: " + "; ".join(reasons)
    )
    return record


# ---------------------------------------------------------------------------
# Mining
# ---------------------------------------------------------------------------

def _unique(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for c in candidates:
        fp = fingerprint(c)
        if fp in seen:
            continue
        seen.add(fp)
        c = dict(c)
        c.setdefault("id", f"chk_{fp}")
        c.setdefault("direction", "tighten")
        c["fingerprint"] = fp
        out.append(c)
    return out


def mine(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Propose tighten-only candidates from a labelled history.

    The main signal is a PASS later invalidated by a real kill. Patterns
    taken from already-caught trivial kills are also proposed; they only
    pass replay if they also catch a slipped known-bad and leave
    still-valid passes alone.
    """
    labelled = history if all("label" in r for r in history) else label_history(history)
    slipped = [r for r in labelled if r.get("label") == "pass_later_invalidated"]
    candidates: list[dict[str, Any]] = []

    seen_names: set[str] = set()
    for row in slipped:
        name = str(row.get("mutation") or "").strip()
        if not name or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())
        if len(name) >= 4:
            candidates.append({
                "kind": "trap_pattern",
                "direction": "tighten",
                "pattern": name,
                "pattern_type": "literal",
                "source": f"mined_from_later_invalidated:{name}",
                "rationale": (
                    f"Claim `{name}` passed and was later killed for an "
                    f"invalidating reason. A trap on this name would have "
                    f"caught the earlier pass. Not applied to the live Oracle."
                ),
            })
        # If the slipped claim looks textbook-ish, also propose a stricter
        # novelty identity (still subject to replay).
        score = _textbook_score(row)
        if score is not None and score > 0:
            candidates.append({
                "kind": "stricter_novelty",
                "direction": "tighten",
                "add_identities": [name],
                "source": f"mined_novelty_identity:{name}",
                "rationale": (
                    f"Claim `{name}` had a textbook-reuse signal and later "
                    f"failed an invalidating check. Adding this identity to "
                    f"the novelty kill list would be a tightening. Not applied."
                ),
            })
        evidence = row.get("window_evidence") or {}
        fails_at = None
        if isinstance(evidence, dict):
            fails_at = evidence.get("fails_at") or evidence.get("would_fail_at_window")
        if fails_at is not None:
            try:
                w = int(fails_at)
            except (TypeError, ValueError):
                w = None
            if w is not None and w > LIVE_MIN_WINDOW:
                candidates.append({
                    "kind": "wider_shifted_window",
                    "direction": "tighten",
                    "min_window": w,
                    "source": f"mined_wider_window:{name}:{w}",
                    "rationale": (
                        f"Claim `{name}` has evidence it would fail a shifted "
                        f"window of {w} (live minimum is {LIVE_MIN_WINDOW}). "
                        f"A wider window is a tightening. Not applied."
                    ),
                })

    # Frequent already-caught trivial / easy_pad kills: propose a pattern.
    # Replay will reject these unless they also catch a slipped known-bad.
    trivial_names: list[str] = []
    for row in labelled:
        if row.get("label") != "kill":
            continue
        kills = " ".join(str(k) for k in (row.get("kills") or [])).lower()
        if "trivial" in kills or "easy_pad" in kills:
            n = str(row.get("mutation") or "").strip()
            if n and n.lower() not in seen_names:
                trivial_names.append(n)
    # A shared prefix of length >= 8 across two or more trivial kills.
    if len(trivial_names) >= 2:
        first, second = trivial_names[0], trivial_names[1]
        i = 0
        while i < min(len(first), len(second)) and first[i].lower() == second[i].lower():
            i += 1
        prefix = first[:i].rstrip("_-:")
        if len(prefix) >= 8:
            candidates.append({
                "kind": "triviality_pattern",
                "direction": "tighten",
                "pattern": prefix,
                "pattern_type": "literal",
                "source": "mined_from_trivial_kill_prefix",
                "rationale": (
                    f"Several already-killed claims share the prefix `{prefix}`. "
                    f"A triviality trap on that prefix is a tightening only if "
                    f"replay shows it catches a slipped known-bad and keeps "
                    f"still-valid passes. Not applied to the live Oracle."
                ),
            })

    return _unique(candidates)


# ---------------------------------------------------------------------------
# Persistence (append-only log + runtime snapshot)
# ---------------------------------------------------------------------------

def _empty_state() -> dict[str, Any]:
    return {
        "version": 1,
        "awaiting_review": [],
        "rejected": [],
        "runs": 0,
    }


def load_receipt() -> dict[str, Any]:
    """Committed cycle receipts and rejected-fingerprint memory."""
    if not RECEIPT_PATH.exists():
        return {"version": 1, "cycles": [], "rejected": []}
    try:
        data = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("cycles", [])
            data.setdefault("rejected", [])
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"version": 1, "cycles": [], "rejected": []}


def save_receipt(receipt: dict[str, Any]) -> None:
    RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(receipt)
    payload["version"] = 1
    payload["updated_at"] = _utc()
    cycles = list(payload.get("cycles") or [])
    payload["cycles"] = cycles[-RECEIPT_KEEP:]
    rejected = list(payload.get("rejected") or [])
    payload["rejected"] = rejected[-80:]
    tmp = RECEIPT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(RECEIPT_PATH)


def _receipt_item(item: dict[str, Any]) -> dict[str, Any]:
    """Slim, commitable summary of one accept/reject."""
    replay = item.get("replay") or {}
    return {
        "fingerprint": item.get("fingerprint"),
        "kind": item.get("kind") or (item.get("candidate") or {}).get("kind"),
        "status": item.get("status"),
        "reasons": list(replay.get("reasons") or item.get("reasons") or []),
        "id": item.get("id"),
    }


def record_cycle_receipt(result: dict[str, Any], *, state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Append this cycle's mine/accept/reject counts to the committed receipt.

    Also keeps a bounded rejected-fingerprint list so the next CI run does
    not rediscover the same reject on its first cycle.
    """
    receipt = load_receipt()
    reasons = []
    st = state or {}
    for item in (result.get("receipt_items") or []):
        reasons.append(_receipt_item(item))
    # Fall back to state rejected / accepted if the result did not carry items.
    if not reasons:
        for item in list(st.get("rejected") or [])[-12:]:
            if str(item.get("cycle_id") or "") == str(result.get("cycle_id") or "") or not item.get("cycle_id"):
                reasons.append(_receipt_item(item))
        for item in list(st.get("awaiting_review") or [])[-12:]:
            reasons.append(_receipt_item(item))
    row = {
        "cycle_id": result.get("cycle_id"),
        "ok": bool(result.get("ok")),
        "error": result.get("error"),
        "candidates_mined": int(result.get("candidates_mined") or 0),
        "new_accepted": int(result.get("new_accepted") or 0),
        "new_rejected": int(result.get("new_rejected") or 0),
        "reasons": reasons,
        "awaiting_review": int(result.get("awaiting_review") or 0),
        "applied_to_live_oracle": False,
        "ts": _utc(),
    }
    cycles = list(receipt.get("cycles") or [])
    cycles.append(row)
    receipt["cycles"] = cycles[-RECEIPT_KEEP:]
    # Merge rejected fingerprints (durable memory).
    by_fp = {str(r.get("fingerprint")): r for r in (receipt.get("rejected") or []) if r.get("fingerprint")}
    for item in (st.get("rejected") or []):
        fp = item.get("fingerprint")
        if fp:
            by_fp[str(fp)] = _receipt_item(item)
    for item in reasons:
        fp = item.get("fingerprint")
        if fp and item.get("status") in ("rejected", "withdrawn"):
            by_fp[str(fp)] = item
    receipt["rejected"] = list(by_fp.values())[-80:]
    receipt["last"] = row
    try:
        save_receipt(receipt)
    except Exception:
        pass
    return row


def load_state() -> dict[str, Any]:
    data: dict[str, Any] | None = None
    if STATE_PATH.exists():
        try:
            loaded = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                loaded.setdefault("awaiting_review", [])
                loaded.setdefault("rejected", [])
                data = loaded
        except (json.JSONDecodeError, OSError):
            data = None
    if data is None:
        data = _empty_state()
    # Seed rejected-fingerprint memory from the committed receipt when
    # this is a fresh checkout (gitignore hides the runtime snapshot).
    if not data.get("rejected"):
        try:
            receipt = load_receipt()
            seeded = [r for r in (receipt.get("rejected") or []) if r.get("fingerprint")]
            if seeded:
                data["rejected"] = seeded[-80:]
                data["rejected_seeded_from_receipt"] = True
        except Exception:
            pass
    return data


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(state)
    payload["version"] = 1
    payload["updated_at"] = _utc()
    STATE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def append_log(record: dict[str, Any]) -> None:
    """Append one replay/guard record. Never rewrites earlier lines."""
    LANE_LOG.parent.mkdir(parents=True, exist_ok=True)
    row = dict(record)
    row.setdefault("ts", _utc())
    with LANE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def write_proposal_file(
    candidate: dict[str, Any],
    replay: dict[str, Any],
    *,
    directory: Path | None = None,
) -> Path:
    """Write a human-readable proposal a person can turn into a PR."""
    dest = directory or PROPOSAL_DIR
    dest.mkdir(parents=True, exist_ok=True)
    cid = str(candidate.get("id") or replay.get("candidate_id") or f"chk_{fingerprint(candidate)}")
    path = dest / f"{cid}.md"
    caught = replay.get("known_bad_caught") or []
    unexplained = replay.get("unexplained_pass_to_fail") or []
    fail_to_pass = replay.get("fail_to_pass") or []
    lines = [
        f"# Checker proposal `{cid}` — awaiting human review",
        "",
        "This is a **candidate only**. It has not been applied to the live Oracle.",
        "The P ≥ 0.70 gate, the 150 authored-check cap, Athanor math, human",
        "authorization, and the append-only witness log are unchanged.",
        "",
        "## What it would tighten",
        "",
        f"- kind: `{candidate.get('kind')}`",
        f"- direction: `{candidate.get('direction') or 'tighten'}`",
    ]
    if candidate.get("pattern"):
        lines.append(
            f"- pattern ({candidate.get('pattern_type') or 'literal'}): "
            f"`{candidate.get('pattern')}`"
        )
    if candidate.get("add_identities"):
        lines.append("- added novelty identities: " + ", ".join(
            f"`{x}`" for x in candidate["add_identities"]
        ))
    if candidate.get("textbook_reuse_kill_at") is not None:
        lines.append(
            f"- textbook-reuse kill threshold: "
            f"{candidate['textbook_reuse_kill_at']} "
            f"(live is {LIVE_TEXTBOOK_REUSE_KILL_AT}; lower is stricter)"
        )
    if candidate.get("min_window") is not None:
        lines.append(
            f"- proposed minimum shifted window: {candidate['min_window']} "
            f"(live is {LIVE_MIN_WINDOW}; wider is stricter)"
        )
    lines += [
        "",
        f"- source: {candidate.get('source') or '—'}",
        "",
        str(candidate.get("rationale") or ""),
        "",
        "## Replay evidence",
        "",
        f"- known-good passes still passing: "
        f"{replay.get('known_good_kept')}/{replay.get('known_good_total')}",
        f"- known-bad that previously slipped, now caught: "
        f"{', '.join(f'`{c}`' for c in caught) or 'none'}",
        f"- FAIL → PASS flips: {len(fail_to_pass)}",
        f"- unexplained PASS → FAIL flips: "
        f"{', '.join(f'`{u}`' for u in unexplained) or 'none'}",
        f"- accepted for review: {bool(replay.get('accepted'))}",
        f"- applied to the live Oracle: **false**",
        "",
        "## What a follow-up PR would do",
        "",
        "A human would implement this check in the Oracle or novelty path,",
        "add tests, and open a pull request. This file is not that PR, and",
        "merging this lane does not turn the candidate on.",
        "",
        "## What it does not do",
        "",
        "- Does not loosen any existing check.",
        "- Does not change the P ≥ 0.70 gate, the 150 cap, Athanor, authorize, or the witness log.",
        "- Does not apply itself.",
        "",
        f"Recorded at {replay.get('ts') or _utc()}.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Cycle hook and visibility
# ---------------------------------------------------------------------------

def run_lane(
    history: list[dict[str, Any]] | None = None,
    *,
    cycle_id: str = "",
    write_proposals: bool = True,
    mine_fn: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Mine, guard, and replay. Never applies a candidate. Safe to call often."""
    hist = history if history is not None else build_history()
    miner = mine_fn or mine
    try:
        candidates = miner(hist)
    except Exception as exc:  # noqa: BLE001
        fail = {
            "ok": False,
            "error": f"mine:{type(exc).__name__}:{exc}",
            "awaiting_review": 0,
            "candidates_mined": 0,
            "new_accepted": 0,
            "new_rejected": 0,
            "applied_to_live_oracle": False,
            "cycle_id": cycle_id,
            "receipt_items": [],
        }
        try:
            record_cycle_receipt(fail, state=load_state())
        except Exception:
            pass
        return fail

    state = load_state()
    pending = {str(p.get("fingerprint")): p for p in (state.get("awaiting_review") or [])}
    rejected = {str(p.get("fingerprint")): p for p in (state.get("rejected") or [])}
    already_logged: set[str] = set()
    for item in list(pending.values()) + list(rejected.values()):
        if item.get("fingerprint"):
            already_logged.add(str(item["fingerprint"]) + ":" + str(item.get("status") or ""))

    new_accepted: list[dict[str, Any]] = []
    new_rejected: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []

    # Re-replay pending items against the current history. If new evidence
    # would flip a still-valid pass, withdraw them from review.
    for fp, item in list(pending.items()):
        cand = item.get("candidate") or item
        try:
            replay = replay_candidate(cand, hist)
        except Exception as exc:  # noqa: BLE001
            replay = {"accepted": False, "reasons": [f"replay_error:{type(exc).__name__}"], "fingerprint": fp}
        if not replay.get("accepted"):
            pending.pop(fp, None)
            item = dict(item)
            item["status"] = "withdrawn"
            item["withdrawn_reason"] = replay.get("note") or replay.get("reasons")
            item["replay"] = {k: replay.get(k) for k in (
                "accepted", "reasons", "known_good_kept", "known_good_total",
                "known_bad_caught", "unexplained_pass_to_fail", "fail_to_pass", "note",
            )}
            rejected[fp] = item
            new_rejected.append(item)
            append_log({
                "event": "withdrawn",
                "cycle_id": cycle_id,
                "fingerprint": fp,
                "replay": item["replay"],
                "applied_to_live_oracle": False,
            })

    for cand in candidates:
        fp = fingerprint(cand)
        cand.setdefault("id", f"chk_{fp}")
        try:
            replay = replay_candidate(cand, hist)
        except Exception as exc:  # noqa: BLE001
            replay = {
                "accepted": False,
                "reasons": [f"replay_error:{type(exc).__name__}"],
                "fingerprint": fp,
                "note": f"replay error: {exc}",
                "applied_to_live_oracle": False,
            }
        records.append(replay)
        summary = {
            "id": cand["id"],
            "fingerprint": fp,
            "kind": cand.get("kind"),
            "candidate": {k: cand.get(k) for k in (
                "id", "kind", "direction", "pattern", "pattern_type",
                "add_identities", "textbook_reuse_kill_at", "min_window",
                "source", "rationale",
            ) if cand.get(k) is not None},
            "replay": {k: replay.get(k) for k in (
                "accepted", "reasons", "known_good_kept", "known_good_total",
                "known_bad_caught", "known_bad_total",
                "unexplained_pass_to_fail", "fail_to_pass", "note", "ts",
            )},
            "applied_to_live_oracle": False,
        }
        if replay.get("accepted"):
            summary["status"] = "awaiting_review"
            if fp not in pending:
                pending[fp] = summary
                new_accepted.append(summary)
                append_log({
                    "event": "accepted_for_review",
                    "cycle_id": cycle_id,
                    "fingerprint": fp,
                    "candidate": summary["candidate"],
                    "replay": summary["replay"],
                    "applied_to_live_oracle": False,
                })
                if write_proposals:
                    try:
                        path = write_proposal_file(cand, replay)
                        summary["proposal_file"] = str(path)
                        pending[fp]["proposal_file"] = str(path)
                    except Exception:
                        pass
        else:
            summary["status"] = "rejected"
            # Log a rejection the first time we see this fingerprint, or when
            # the reason set changes. Do not append the same reject every cycle.
            reason_key = fp + ":rejected:" + ",".join(replay.get("reasons") or [])
            if fp not in pending and reason_key not in already_logged:
                rejected[fp] = summary
                new_rejected.append(summary)
                append_log({
                    "event": "rejected",
                    "cycle_id": cycle_id,
                    "fingerprint": fp,
                    "candidate": summary["candidate"],
                    "replay": summary["replay"],
                    "applied_to_live_oracle": False,
                })
                already_logged.add(reason_key)

    state["awaiting_review"] = list(pending.values())
    # Keep a bounded rejected list (most recent first); the log is the full record.
    rejected_list = list(rejected.values())
    state["rejected"] = rejected_list[-80:]
    state["runs"] = int(state.get("runs") or 0) + 1
    state["last_cycle_id"] = cycle_id
    state["last_history_rows"] = len(hist)
    state["last_new_accepted"] = len(new_accepted)
    state["last_new_rejected"] = len(new_rejected)
    try:
        save_state(state)
    except Exception:
        pass

    result = {
        "ok": True,
        "cycle_id": cycle_id,
        "history_rows": len(hist),
        "candidates_mined": len(candidates),
        "new_accepted": len(new_accepted),
        "new_rejected": len(new_rejected),
        "awaiting_review": len(state["awaiting_review"]),
        "receipt_items": [
            {**_receipt_item(x), "cycle_id": cycle_id}
            for x in list(new_accepted) + list(new_rejected)
        ],
        "proposals": [
            {
                "id": p.get("id"),
                "kind": p.get("kind"),
                "status": "awaiting_review",
                "known_bad_caught": (p.get("replay") or {}).get("known_bad_caught") or [],
                "known_good_kept": (p.get("replay") or {}).get("known_good_kept"),
                "known_good_total": (p.get("replay") or {}).get("known_good_total"),
                "proposal_file": p.get("proposal_file"),
                "applied_to_live_oracle": False,
            }
            for p in state["awaiting_review"]
        ],
        "applied_to_live_oracle": False,
        "records": records,
    }
    try:
        receipt_row = record_cycle_receipt(result, state=state)
        result["receipt"] = {
            k: receipt_row.get(k)
            for k in (
                "ok", "error", "candidates_mined", "new_accepted", "new_rejected",
                "reasons", "cycle_id", "ts",
            )
        }
    except Exception:
        result["receipt"] = None
    return result


def on_cycle(cycle_id: str = "", *, history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Evolve-cycle entry point. Exceptions are swallowed and returned."""
    try:
        return run_lane(history, cycle_id=cycle_id)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"{type(exc).__name__}:{exc}",
            "awaiting_review": 0,
            "applied_to_live_oracle": False,
            "cycle_id": cycle_id,
        }


def visibility() -> dict[str, Any]:
    """Fields for telemetry and the dashboard. Not scored, not the Oracle."""
    try:
        state = load_state()
        proposals = []
        for p in state.get("awaiting_review") or []:
            replay = p.get("replay") or {}
            proposals.append({
                "id": p.get("id"),
                "kind": p.get("kind"),
                "status": "awaiting_review",
                "known_bad_caught": replay.get("known_bad_caught") or [],
                "known_good_kept": replay.get("known_good_kept"),
                "known_good_total": replay.get("known_good_total"),
                "note": replay.get("note"),
                "proposal_file": p.get("proposal_file"),
                "applied_to_live_oracle": False,
            })
        last = {}
        try:
            receipt = load_receipt()
            last = receipt.get("last") or (receipt.get("cycles") or [None])[-1] or {}
        except Exception:
            last = {}
        reasons = list((last or {}).get("reasons") or [])
        return {
            "checker_proposals_awaiting_review": len(proposals),
            "checker_proposals": proposals,
            "checker_lane_ok": last.get("ok") if last else None,
            "checker_lane_error": last.get("error"),
            "checker_candidates_mined": last.get("candidates_mined"),
            "checker_new_accepted": last.get("new_accepted"),
            "checker_new_rejected": last.get("new_rejected"),
            "checker_reject_reasons": reasons,
            "checker_lane_cycle_id": last.get("cycle_id"),
        }
    except Exception:
        return {
            "checker_proposals_awaiting_review": 0,
            "checker_proposals": [],
            "checker_lane_ok": None,
            "checker_lane_error": None,
            "checker_candidates_mined": None,
            "checker_new_accepted": None,
            "checker_new_rejected": None,
            "checker_reject_reasons": [],
            "checker_lane_cycle_id": None,
        }


def format_visibility(vis: dict[str, Any] | None = None) -> str:
    v = vis if vis is not None else visibility()
    n = int(v.get("checker_proposals_awaiting_review") or 0)
    proposals = v.get("checker_proposals") or []
    mined = v.get("checker_candidates_mined")
    cycle_bit = ""
    if mined is not None:
        cycle_bit = (
            f" last cycle mined {mined}, "
            f"accepted {v.get('checker_new_accepted')}, "
            f"rejected {v.get('checker_new_rejected')}"
            + (f", error {v.get('checker_lane_error')}" if v.get("checker_lane_error") else "")
            + ("" if v.get("checker_lane_ok") is not False else ", ok=false")
        )
    if not n:
        return "checker proposals awaiting human review: 0" + (";" + cycle_bit if cycle_bit else "")
    parts = []
    for p in proposals[:6]:
        caught = p.get("known_bad_caught") or []
        catch_s = f", caught {', '.join(str(c) for c in caught)}" if caught else ""
        parts.append(f"{p.get('id')} ({p.get('kind')}{catch_s})")
    more = f" +{n - 6} more" if n > 6 else ""
    return (
        f"checker proposals awaiting human review: {n} "
        f"({'; '.join(parts)}{more}). Not applied to the live Oracle."
        + (";" + cycle_bit if cycle_bit else "")
    )
