"""Frontier desk — harder targets: open statements checked on bounded ranges.

James 2026-10-09: "aim at the edge, report evidence honestly, never claim proof from finite
checks." Everything here is BOUNDED EVIDENCE, NOT PROOF:

* the catalog ``society/benchmarks/frontier.json`` lists open/conjectural statements that are
  finitely checkable (Goldbach, Collatz, Legendre, Lehmer's totient problem, Erdős–Straus,
  twin primes vs Hardy–Littlewood) plus OEIS sequences with conjectured/empirical formulas
  discovered from the feed (integer terms only — formula text is never parsed or executed);
* work = extend the colony's own verified range past what the catalog records, verify a
  colony-fitted recurrence on OEIS terms it never saw, or surface a counterexample;
* each task is a machine check with a time budget and pre-run guards (non-trivial window,
  strictly beyond the recorded range, dedupe by fingerprint, shared cooldown filter). A task
  is ``enabled: false`` until its result is judged by the frontier verifier: an independent
  second implementation spot-checks every extension and re-checks every counterexample;
* a re-verified counterexample is flagged LOUDLY in the witness log and the target is frozen
  for human review. Nothing here ever claims a disproof (or a proof).

Frontier evidence never enters the lemma microbench, the Oracle's fitness credit, the novelty
gate, the Hearing, or any proof-scored tier. It is reported in ``society/systems/frontier.json``,
the sensors snapshot and spark priors only. (The Oracle is unchanged: it is a lemma-bench judge
and has no frontier path; adding one would be an Oracle change, which is out of scope here.)
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "society" / "benchmarks" / "frontier.json"
IMPL = ROOT / "society" / "benchmarks" / "frontier" / "frontier_impl.py"  # kept out of artifacts/ (lemma scans)
LOG = ROOT / "data" / "commons" / "frontier.jsonl"
SYSTEM = ROOT / "society" / "systems" / "frontier.json"

LABEL = "bounded evidence, not proof"
GUIDE_TAG = "frontier"
DEFAULT_BUDGET_S = 2.5
SPOT_SAMPLES = 16
STALL_STREAK = 3
MAX_OEIS_TARGETS = 24
MIN_OEIS_TERMS = 20
REVIEW_STATUSES = ("counterexample_review", "disagreement_review")


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- io

def load_impl() -> Any:
    spec = importlib.util.spec_from_file_location("colony_frontier_impl", IMPL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {IMPL}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)  # repo-local checker module (our own code; never feed text)
    return mod


def load_catalog() -> dict[str, Any]:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def save_catalog(cat: dict[str, Any]) -> None:
    cat["updated_at"] = _utc()
    CATALOG.write_text(json.dumps(cat, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_log(limit: int = 4000) -> list[dict[str, Any]]:
    if not LOG.exists():
        return []
    rows = []
    for line in LOG.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _append_log(row: dict[str, Any]) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- guide + cooldown

def guide_frontier_active() -> bool:
    try:
        from colony.lessons import load_human_guides
    except Exception:
        return False
    for g in load_human_guides():
        tags = {str(t).lower() for t in (g.get("tags") or [])}
        prefer = {str(t).lower() for t in ((g.get("catalog_hint") or {}).get("prefer") or [])}
        if GUIDE_TAG in tags or GUIDE_TAG in prefer:
            return True
    return False


def target_blocked_reason(t: dict[str, Any], cooldown: Any) -> str:
    """Why a target may not run now ('' = may run). Same shared cooldown filter as desk/seek."""
    st = str(t.get("status") or "open")
    if st in REVIEW_STATUSES:
        return st
    if st != "open":
        return f"status:{st}"
    why = cooldown.reason(f"frontier_{t['id']}") if cooldown is not None else "no_cooldown_snapshot"
    if why:
        return why
    if int(t.get("stall_streak") or 0) >= STALL_STREAK:
        return f"frontier_stall:{t['stall_streak']}"
    return ""


def pick_target(cat: dict[str, Any], cooldown: Any) -> tuple[dict[str, Any] | None, dict[str, str]]:
    """Least-recently-run unblocked target."""
    blocked: dict[str, str] = {}
    ok: list[dict[str, Any]] = []
    for t in cat.get("targets") or []:
        why = target_blocked_reason(t, cooldown)
        if why:
            blocked[t["id"]] = why
        elif t.get("family") == "oeis_recurrence" and t.get("result"):
            blocked[t["id"]] = "done"
        else:
            ok.append(t)
    ok.sort(key=lambda t: (str(t.get("last_run") or ""), t["id"]))
    return (ok[0] if ok else None), blocked


# --------------------------------------------------------------------------- tasks

def fingerprint(target_id: str, lo: int, hi: int) -> str:
    return hashlib.sha1(f"{target_id}:{lo}:{hi}".encode()).hexdigest()[:16]


def make_task(t: dict[str, Any], *, done: set[str] | None = None) -> tuple[dict[str, Any] | None, str]:
    """Next window strictly past the catalog's verified range, or (None, reason)."""
    done = done if done is not None else {r.get("fingerprint") for r in load_log() if r.get("fingerprint")}
    if t.get("family") == "oeis_recurrence":
        terms = t.get("terms") or []
        if len(terms) < MIN_OEIS_TERMS:
            return None, "trivial:too_few_terms"
        fp = fingerprint(t["id"], 0, len(terms))
        if fp in done:
            return None, "dedupe"
        return {"target": t["id"], "family": t["family"], "lo": 0, "hi": len(terms) - 1,
                "fingerprint": fp, "budget_s": float(t.get("budget_s") or DEFAULT_BUDGET_S),
                "enabled": False, "label": LABEL}, ""
    ver = t.get("verified") or {}
    start = int(t.get("start") or 1)
    vhi = int(ver.get("hi")) if ver.get("hi") is not None else start - 1
    lo = max(start, vhi + 1)
    window = int(t.get("window") or t.get("min_window") or 1000)
    min_w = int(t.get("min_window") or 1)
    if window < min_w:
        return None, f"trivial:window<{min_w}"
    hi = lo + window - 1
    if lo <= vhi:
        return None, "not_beyond_catalog"
    fp = fingerprint(t["id"], lo, hi)
    if fp in done:
        return None, "dedupe"
    return {"target": t["id"], "family": t["family"], "lo": lo, "hi": hi, "fingerprint": fp,
            "budget_s": float(t.get("budget_s") or DEFAULT_BUDGET_S), "enabled": False,
            "label": LABEL}, ""


def _spot_points(task: dict[str, Any], hi: int, k: int = SPOT_SAMPLES) -> list[int]:
    lo = task["lo"]
    if hi < lo:
        return []
    rng = random.Random(task["fingerprint"])
    pts = {lo, hi}
    span = hi - lo + 1
    for _ in range(min(k, span)):
        pts.add(lo + rng.randrange(span))
    return sorted(pts)


def _challenge(out: dict[str, Any], task: dict[str, Any], r: dict[str, Any], t: dict[str, Any], impl: Any,
               cycle_id: str) -> bool:
    """Challenger pass before the independent recheck. True → withheld (self-rejected)."""
    try:
        from colony.challenger import challenge_frontier, record as challenger_record, why_believe
        ch = challenge_frontier(task, r, t, impl, cycle_id=cycle_id)
        why = why_believe(ch, extra={"target": task["target"], "window": [task["lo"], task["hi"]]})
        challenger_record(ch, why=why)
        out["challenger"] = {"blocked": ch.blocked, "reason": ch.reason, "summary": ch.summary(),
                             "counterexample": ch.counterexample}
        out["why_believe"] = why
        blocked = ch.blocked
    except Exception as exc:  # noqa: BLE001 — fail closed: no challenge, no submission
        out["challenger"] = {"blocked": True, "reason": f"challenger_unavailable:{type(exc).__name__}"}
        blocked = True
    if blocked:
        out.update({"outcome": "self_rejected", "verified_hi": None})
    return blocked


def run_task(task: dict[str, Any], t: dict[str, Any], impl: Any | None = None, *, cycle_id: str = "") -> dict[str, Any]:
    """Primary check under the time budget, Challenger, then independent verification. Never raises."""
    impl = impl or load_impl()
    deadline = impl.Deadline(task["budget_s"])
    out: dict[str, Any] = {"ts": _utc(), **task, "label": LABEL, "proof": False}
    fam = task["family"]
    try:
        if fam == "oeis_recurrence":
            terms = [int(x) for x in t.get("terms") or []]
            r = impl.check_oeis_recurrence(terms, deadline)
            out["primary"] = r
            if r.get("holds") and _challenge(out, task, r, t, impl, cycle_id):
                return out
            indep = bool(r.get("holds")) and impl.reverify_oeis_recurrence(terms, r["order"], r["coeffs"])
            out.update({"primary": r, "independent_ok": indep if r.get("holds") else None,
                        "outcome": ("recurrence_verified_on_unused_terms" if indep
                                    else ("disagreement" if r.get("holds") else "no_low_order_recurrence")),
                        "verified_hi": None})
            return out
        check, holds = impl.FAMILIES[fam]
        if fam == "twin_hl":
            r = check(task["lo"], task["hi"], deadline, prior_count=int((t.get("verified") or {}).get("pi2") or 0))
        else:
            r = check(task["lo"], task["hi"], deadline)
        out["primary"] = r
        if _challenge(out, task, r, t, impl, cycle_id):
            return out
        if r.get("counterexample") is not None:
            n = int(r["counterexample"])
            confirmed = not holds(n)  # independent method
            out.update({"outcome": "counterexample_candidate" if confirmed else "disagreement",
                        "counterexample": n, "independent_confirms_failure": confirmed,
                        "verified_hi": r["checked_hi"] if r["checked_hi"] >= task["lo"] else None})
            return out
        top = int(r["checked_hi"])
        anomaly = r.get("anomaly")
        if anomaly is not None and fam != "twin_hl":
            n = int(anomaly)
            resolved = holds(n)  # wider limits / different method
            out.update({"anomaly": n, "anomaly_resolved_independently": resolved})
            if not resolved:
                out.update({"outcome": "unresolved_anomaly",
                            "verified_hi": top if top >= task["lo"] else None})
                return out
            top = n  # independently resolved: n itself holds
        if fam == "twin_hl":
            # independent recount of a sub-window with Miller-Rabin instead of the sieve
            rng = random.Random(task["fingerprint"])
            span = max(0, top - task["lo"])
            a = task["lo"] + (rng.randrange(span) if span > 20_000 else 0)
            b = min(top, a + 20_000)
            same = impl.twin_pairs_in(a, b) == impl.twin_pairs_in_mr(a, b) if top >= task["lo"] else True
            spots_ok = same
            out["independent_subwindow"] = [a, b]
            if anomaly is not None:
                out["hl_deviation_flag"] = True  # statistical flag only; not a counterexample
        else:
            pts = _spot_points(task, top)
            spots_ok = all(holds(n) for n in pts)
            out["independent_spots"] = len(pts)
        if not spots_ok:
            out.update({"outcome": "disagreement", "verified_hi": None})
            return out
        out.update({"outcome": "extended" if top >= task["lo"] else "no_progress",
                    "verified_hi": top if top >= task["lo"] else None})
        return out
    except Exception as exc:  # noqa: BLE001
        out.update({"outcome": "error", "error": f"{type(exc).__name__}: {str(exc)[:160]}", "verified_hi": None})
        return out


def apply_result(t: dict[str, Any], res: dict[str, Any]) -> None:
    """Update one catalog target from a judged result (in place)."""
    t["last_run"] = res["ts"]
    t["runs"] = int(t.get("runs") or 0) + 1
    oc = res.get("outcome")
    if oc == "self_rejected":  # withheld by the Challenger: no progress, nothing frozen
        t["stall_streak"] = int(t.get("stall_streak") or 0) + 1
        t["last_self_reject"] = {"ts": res["ts"], "reason": (res.get("challenger") or {}).get("reason")}
        return
    if t.get("family") == "oeis_recurrence":
        if oc in ("recurrence_verified_on_unused_terms", "no_low_order_recurrence"):
            t["result"] = {"outcome": oc, "order": (res.get("primary") or {}).get("order"),
                           "coeffs": (res.get("primary") or {}).get("coeffs"),
                           "unused_verified": (res.get("primary") or {}).get("unused_verified"),
                           "label": LABEL}
        elif oc == "disagreement":
            t["status"] = "disagreement_review"
        return
    vhi = res.get("verified_hi")
    prev = (t.get("verified") or {}).get("hi")
    progressed = vhi is not None and (prev is None or int(vhi) > int(prev))
    if progressed:
        ver = dict(t.get("verified") or {})
        ver.setdefault("lo", int(t.get("start") or 1))
        ver["hi"] = int(vhi)
        ver["by"] = "colony"
        ver["label"] = LABEL
        if t.get("family") == "twin_hl":
            d = (res.get("primary") or {}).get("data") or {}
            ver["pi2"] = d.get("pi2")
            ver["hl_ratio"] = d.get("ratio")
        t["verified"] = ver
        ext = list(t.get("extensions") or [])
        ext.append({"ts": res["ts"], "lo": res["lo"], "hi": int(vhi), "seconds": (res.get("primary") or {}).get("seconds")})
        t["extensions"] = ext[-10:]
        rec = (res.get("primary") or {}).get("data") or {}
        if rec:
            t["last_data"] = rec
    # adapt the window to the time budget
    prim = res.get("primary") or {}
    w = int(t.get("window") or t.get("min_window") or 1000)
    if prim.get("complete") and float(prim.get("seconds") or 0) < float(t.get("budget_s") or DEFAULT_BUDGET_S) / 4:
        w = min(int(t.get("max_window") or w), w * 2)
    elif prim.get("budget_hit"):
        w = max(int(t.get("min_window") or 1), w // 2)
    t["window"] = w
    t["stall_streak"] = 0 if progressed else int(t.get("stall_streak") or 0) + 1
    if oc == "counterexample_candidate":
        t["status"] = "counterexample_review"
        t["review"] = {"n": res.get("counterexample"), "ts": res["ts"],
                       "note": "Primary checker failed and an independent method agrees. NOT a disproof "
                               "claim: needs human review + external re-verification."}
    elif oc in ("disagreement", "unresolved_anomaly"):
        t["status"] = "disagreement_review"
        t["review"] = {"n": res.get("counterexample") or res.get("anomaly"), "ts": res["ts"],
                       "note": "Checkers disagree or could not decide; likely a checker limit/bug. Human review."}


# --------------------------------------------------------------------------- OEIS discovery (feed)

def discover_oeis_targets(cat: dict[str, Any]) -> list[str]:
    """Add OEIS sequences with conjectured/empirical formulas from the feed cache. Ints only."""
    try:
        from colony.feeds import conj_sequence_items
        items = conj_sequence_items()
    except Exception:
        return []
    have = {t["id"] for t in cat.get("targets") or []}
    n_oeis = sum(1 for t in cat.get("targets") or [] if t.get("family") == "oeis_recurrence")
    added: list[str] = []
    for it in items:
        if n_oeis >= MAX_OEIS_TARGETS:
            break
        tid = f"oeis_{it['oeis_id']}"
        if tid in have:
            continue
        terms = [int(x) for x in it["terms"]]
        if len(terms) < MIN_OEIS_TERMS or len(set(terms)) < 4:
            continue  # non-trivial guard: constant / near-constant data is not a target
        cat.setdefault("targets", []).append({
            "id": tid, "family": "oeis_recurrence", "kind": "conjectured_formula",
            "statement": f"{it['oeis_id']} (feed: {it.get('conj_flag') or 'listed'}) — does a low-order "
                         f"linear recurrence fitted on early terms predict every later listed term?",
            "oeis_id": it["oeis_id"], "source": f"https://oeis.org/{it['oeis_id']}",
            "terms": terms, "status": "open", "budget_s": 1.0, "label": LABEL, "proof": False,
            "discovered": _utc(), "note": "Integer terms only; OEIS formula text is never parsed or executed.",
        })
        have.add(tid)
        added.append(tid)
        n_oeis += 1
    return added


# --------------------------------------------------------------------------- cycle

def write_system(cat: dict[str, Any], last: dict[str, Any] | None = None) -> dict[str, Any]:
    targets = cat.get("targets") or []
    summary = {
        "version": 1,
        "updated_at": _utc(),
        "label": LABEL,
        "proof": False,
        "targets": {
            t["id"]: {"family": t.get("family"), "status": t.get("status"),
                      "verified_hi": (t.get("verified") or {}).get("hi"),
                      "literature": t.get("literature"), "window": t.get("window"),
                      "result": (t.get("result") or {}).get("outcome")}
            for t in targets
        },
        "reviews": [{"id": t["id"], **(t.get("review") or {})} for t in targets if t.get("status") in REVIEW_STATUSES],
        "last": last or {},
        "note": "Frontier evidence is bounded evidence, not proof; it is never scored as a proof.",
    }
    SYSTEM.parent.mkdir(parents=True, exist_ok=True)
    SYSTEM.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def run_cycle(cycle_id: str = "", *, witness: Any | None = None, max_tasks: int = 1) -> dict[str, Any]:
    """One frontier step per cycle (guide-driven). Fail closed; never raises."""
    if not guide_frontier_active():
        return {"ran": 0, "skipped": "no_frontier_guide"}
    try:
        from colony.lessons import mutation_cooldown
        cooldown = mutation_cooldown()
    except Exception as exc:  # noqa: BLE001
        return {"ran": 0, "skipped": f"cooldown_unavailable:{exc}"[:200]}
    try:
        cat = load_catalog()
        impl = load_impl()
    except Exception as exc:  # noqa: BLE001
        return {"ran": 0, "skipped": f"catalog_or_impl_unavailable:{exc}"[:200]}
    added = discover_oeis_targets(cat)
    done = {r.get("fingerprint") for r in load_log() if r.get("fingerprint")}
    results: list[dict[str, Any]] = []
    blocked: dict[str, str] = {}
    tried: set[str] = set()
    while len(results) < max_tasks:
        t, blocked = pick_target({"targets": [x for x in cat.get("targets") or [] if x["id"] not in tried]}, cooldown)
        if t is None:
            break
        tried.add(t["id"])
        task, why = make_task(t, done=done)
        if task is None:
            blocked[t["id"]] = why
            continue
        res = run_task(task, t, impl, cycle_id=cycle_id)
        res["cycle_id"] = cycle_id
        res["enabled"] = res.get("outcome") in ("extended", "recurrence_verified_on_unused_terms")
        _append_log(res)
        done.add(task["fingerprint"])
        apply_result(t, res)
        results.append(res)
        _witness(witness, cycle_id, t, res)
    save_catalog(cat)
    last = results[-1] if results else {}
    write_system(cat, {k: last.get(k) for k in ("target", "lo", "hi", "outcome", "verified_hi", "cycle_id")} if last else None)
    return {"ran": len(results), "added_oeis": added, "blocked": blocked,
            "results": [{k: r.get(k) for k in ("target", "lo", "hi", "outcome", "verified_hi", "counterexample")}
                        for r in results]}


def _witness(witness: Any | None, cycle_id: str, t: dict[str, Any], res: dict[str, Any]) -> None:
    if witness is None:
        return
    oc = res.get("outcome")
    if oc == "counterexample_candidate":
        kind = "frontier_counterexample_candidate"
        summary = (f"⚠⚠ FRONTIER COUNTEREXAMPLE CANDIDATE for {t['id']} at n={res.get('counterexample')} — "
                   f"primary and independent checkers agree. NOT a disproof claim; target frozen for human review.")
    elif oc == "self_rejected":
        ch = res.get("challenger") or {}
        ce = ch.get("counterexample") or {}
        kind = "frontier_self_reject"
        loud = "⚠ " if ce.get("independent_fails") else ""
        summary = (f"{loud}Frontier {t['id']}: Challenger withheld the result before recheck "
                   f"({ch.get('reason')}; {json.dumps(ce, default=str)[:120]}). No range claimed; "
                   f"{'independent method fails here — human review, NOT a disproof' if loud else 'checker edge'}.")
    elif oc in ("disagreement", "unresolved_anomaly"):
        kind = "frontier_review"
        summary = f"Frontier {t['id']}: {oc} near n={res.get('counterexample') or res.get('anomaly')} — frozen for review."
    else:
        kind = "frontier_evidence"
        if t.get("family") == "oeis_recurrence":
            summary = f"Frontier {t['id']}: {oc} ({LABEL})."
        else:
            summary = (f"Frontier {t['id']}: {oc}; verified to {(t.get('verified') or {}).get('hi')} "
                       f"({LABEL}).")
    try:
        witness.record(cycle_id=cycle_id, kind=kind, actor="geometer", summary=summary,
                       detail={k: res.get(k) for k in ("target", "lo", "hi", "outcome", "verified_hi",
                                                        "counterexample", "anomaly", "label", "proof")})
    except Exception:
        pass


def digest(limit: int = 4) -> str:
    """Short prior for spark: verified ranges + open reviews."""
    try:
        s = json.loads(SYSTEM.read_text(encoding="utf-8"))
    except Exception:
        return ""
    parts = [f"{k}≤{v.get('verified_hi')}" for k, v in (s.get("targets") or {}).items()
             if v.get("verified_hi") is not None][:limit]
    rev = [r.get("id") for r in s.get("reviews") or []]
    out = f"frontier ({LABEL}): " + ", ".join(parts) if parts else ""
    if rev:
        out += f" | REVIEW PENDING: {', '.join(rev)}"
    return out


if __name__ == "__main__":
    print(json.dumps(run_cycle("manual"), indent=2))
