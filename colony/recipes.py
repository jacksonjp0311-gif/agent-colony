"""Success recipes — the colony learns from verified successes, not only from failures.

A *recipe* is distilled automatically from the recorded frontier log of a target that succeeded
under strong verification. Nothing here is hand-written per target: every field is read from
the run rows (family, engines, window sizes, seconds, which checks fired, outcomes).

Strong verification (ALL required, else no recipe):
  * the target reached a terminal success (status ``done``, or a ``new_term_candidate``/
    ``recurrence_verified_on_unused_terms`` outcome);
  * every run row is a clean pass (no disagreement / self-reject / error / review status);
  * the Challenger ran on every row and blocked none;
  * an independent re-check is recorded on every row (MR sub-window recount, spot checks or
    recurrence re-verify);
  * if the target lists published terms, every one was reproduced and none mismatched;
  * label stays "bounded evidence, not proof" and ``proof`` is False.

Retrieval is by structural features derived from target fields (e.g. ``counting_over_primes``,
``falsifiable_search_over_n``, ``known_terms_available``). Applying a recipe proposes a
verification ladder and a batching plan; it never relaxes any check. Each use is recorded and,
when the target first verifies (or fails), the outcome is recorded: time-to-verified, windows,
disagreements/self-rejects (kills avoided or not). Recipes are advisory evidence, not proof.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "data" / "commons" / "recipes.jsonl"
USES = ROOT / "data" / "commons" / "recipe_uses.jsonl"
LABEL = "bounded evidence, not proof"
SUCCESS_OUTCOMES = ("new_term_candidate", "recurrence_verified_on_unused_terms")
CLEAN_OUTCOMES = ("extended", "new_term_candidate", "recurrence_verified_on_unused_terms", "no_low_order_recurrence")
COUNTING_FAMILIES = ("prime_run_count", "twin_hl")


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


# --------------------------------------------------------------------------- features

def features(t: dict[str, Any]) -> list[str]:
    """Structural features of a target, derived from its fields (no per-target lists)."""
    fam = str(t.get("family") or "")
    f: set[str] = {f"family:{fam}"} if fam else set()
    if fam in COUNTING_FAMILIES or t.get("index_thresholds"):
        f.add("counting_over_primes_to_bound")
    if str(t.get("kind") or "") == "universal" or fam in ("goldbach", "collatz", "legendre", "lehmer_totient", "erdos_straus"):
        f.add("falsifiable_search_over_n")
    if t.get("known_terms") or t.get("terms"):
        f.add("known_terms_available")
    if t.get("oeis_id"):
        f.add("oeis_sequence")
    if t.get("beyond_record") or t.get("published_record"):
        f.add("past_published_record")
    if t.get("index_thresholds") or t.get("start") is not None:
        f.add("monotone_range_windows")
    return sorted(f)


# --------------------------------------------------------------------------- extraction

def _independent_method(row: dict[str, Any]) -> str:
    if row.get("independent_subwindow"):
        return "sub_window_recount_by_second_prime_test"
    if row.get("independent_spots"):
        return "spot_points_by_independent_holds"
    if row.get("independent_ok") is not None:
        return "recurrence_reverify_exact_arithmetic"
    return ""


def verification_failures(t: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    """Why this target's record is NOT a strongly verified success ([] = it is)."""
    why: list[str] = []
    if not rows:
        return ["no_recorded_runs"]
    if str(t.get("status") or "") in ("counterexample_review", "disagreement_review"):
        why.append(f"status:{t.get('status')}")
    terminal = str(t.get("status") or "") == "done" or any(r.get("outcome") in SUCCESS_OUTCOMES for r in rows)
    if not terminal:
        why.append("no_terminal_success")
    for r in rows:
        if r.get("outcome") not in CLEAN_OUTCOMES:
            why.append(f"unclean_outcome:{r.get('outcome')}")
            break
    for r in rows:
        ch = r.get("challenger")
        if not isinstance(ch, dict) or ch.get("blocked") is not False:
            why.append("challenger_missing_or_blocked")
            break
    if any(not _independent_method(r) for r in rows):
        why.append("independent_check_missing")
    known = {str(k) for k in (t.get("known_terms") or {})}
    if known:
        reproduced = {str(x) for r in rows for x in (r.get("published_reproduced") or [])}
        if not known <= reproduced:
            why.append(f"published_terms_not_all_reproduced:{sorted(known - reproduced)[:3]}")
        if any(r.get("published_mismatch") for r in rows):
            why.append("published_mismatch")
    if any(r.get("proof") is not False or r.get("label") != LABEL for r in rows):
        why.append("label_or_proof_flag")
    return why


def extract(t: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Distill a recipe from the target's actual recorded rows, or None if not strongly verified."""
    rows = [r for r in rows if r.get("target") == t.get("id")]
    if verification_failures(t, rows):
        return None
    prim = [r.get("primary") or {} for r in rows]
    secs = [float(p.get("seconds") or 0) for p in prim]
    spans = [int(r["hi"]) - int(r["lo"]) + 1 for r in rows if r.get("hi") is not None and r.get("lo") is not None]
    engines = sorted({str((p.get("data") or {}).get("engine")) for p in prim if (p.get("data") or {}).get("engine")})
    batched = sorted({str(r.get("cycle_id") or "").split("_")[0] for r in rows if str(r.get("cycle_id") or "").startswith("burst")})
    reproduced = sorted({str(x) for r in rows for x in (r.get("published_reproduced") or [])}, key=lambda s: int(s) if s.isdigit() else 0)
    ladder = ["challenger_block_only"]
    if reproduced:
        ladder.insert(0, "reproduce_published_terms_first_or_freeze")
    ladder += sorted({_independent_method(r) for r in rows})
    ladder += ["candidate_only_label_bounded_evidence_not_proof"]
    total_span = sum(spans)
    rate = total_span / sum(secs) if sum(secs) > 0 else None
    body = {
        "source_target": t["id"],
        "target_type": str(t.get("family") or ""),
        "features": features(t),
        "verification_ladder": ladder,
        "independent_check_method": sorted({_independent_method(r) for r in rows}),
        "reproduce_known_first": bool(reproduced),
        "published_terms_reproduced": reproduced,
        "speedups": {"engines": engines, "batched_windows": bool(batched),
                     "max_window": max(spans) if spans else None,
                     "median_window_seconds": sorted(secs)[len(secs) // 2] if secs else None,
                     "throughput_per_s": round(rate, 1) if rate else None},
        "run_stats": {"windows": len(rows), "seconds_total": round(sum(secs), 3), "range_covered": total_span,
                      "first_ts": rows[0].get("ts"), "last_ts": rows[-1].get("ts")},
        "outcome": {"status": t.get("status"),
                    "terminal_outcomes": sorted({r.get("outcome") for r in rows if r.get("outcome") in SUCCESS_OUTCOMES}),
                    "new_terms": {k: (v or {}).get("count") for k, v in (t.get("new_term_review") or {}).items()}},
    }
    fp = hashlib.sha1(json.dumps({k: body[k] for k in ("source_target", "verification_ladder", "run_stats")},
                                 sort_keys=True, default=str).encode()).hexdigest()[:12]
    return {"id": f"rcp_{fp}", "ts": _utc(), "kind": "success_recipe", **body, "label": LABEL, "proof": False}


def signature(r: dict[str, Any]) -> str:
    return json.dumps([r.get("target_type"), r.get("verification_ladder"), r.get("features")], sort_keys=True)


def load() -> list[dict[str, Any]]:
    return [r for r in _read(LEDGER) if r.get("kind") == "success_recipe"]


def distill(cat: dict[str, Any], log_rows: list[dict[str, Any]]) -> list[str]:
    """Extract recipes for every strongly verified target not yet distilled. Returns new ids."""
    have = {r.get("source_target") for r in load()}
    sigs = {signature(r) for r in load()}
    new = []
    for t in cat.get("targets") or []:
        if t.get("id") in have:
            continue
        rec = extract(t, log_rows)
        if rec and signature(rec) not in sigs:  # one recipe per (type, ladder, features); no duplicates
            sigs.add(signature(rec))
            _append(LEDGER, rec)
            new.append(rec["id"])
    return new


# --------------------------------------------------------------------------- retrieval + application

def retrieve(t: dict[str, Any], recipes: list[dict[str, Any]] | None = None, *, k: int = 3) -> list[tuple[float, dict[str, Any]]]:
    """Recipes ranked by Jaccard overlap of structural features (excluding the target's own)."""
    ft = set(features(t))
    out = []
    for r in recipes if recipes is not None else load():
        if r.get("source_target") == t.get("id"):
            continue
        fr = set(r.get("features") or [])
        if not ft or not fr:
            continue
        j = len(ft & fr) / len(ft | fr)
        if j > 0:
            out.append((round(j, 3), r))
    out.sort(key=lambda x: (-x[0], x[1].get("id", "")))
    return out[:k]


def plan_for(t: dict[str, Any], recipe: dict[str, Any], score: float) -> dict[str, Any]:
    """Adapt a recipe into a proposed plan. Advisory: adds checks/batching, never removes one."""
    same_type = recipe.get("target_type") == t.get("family")
    sp = recipe.get("speedups") or {}
    plan = {
        "verification_ladder": [s for s in recipe.get("verification_ladder") or []
                                if s != "reproduce_published_terms_first_or_freeze" or t.get("known_terms") or t.get("terms")],
        "batching": ({"batched_windows": bool(sp.get("batched_windows")), "engines": sp.get("engines"),
                      "suggest_window": sp.get("max_window")} if same_type else
                     {"batched_windows": bool(sp.get("batched_windows")), "note": "different family: batching only"}),
        "match_score": score,
        "same_target_type": same_type,
    }
    return plan


def on_start(t: dict[str, Any]) -> dict[str, Any] | None:
    """First time the colony works a target: retrieve, adapt, and record the use (once)."""
    if t.get("recipe_use"):
        return None
    hits = retrieve(t)
    if not hits:
        return None
    score, rec = hits[0]
    plan = plan_for(t, rec, score)
    use = {"kind": "recipe_use", "ts": _utc(), "target": t["id"], "recipe": rec["id"], "plan": plan,
           "features": features(t), "label": LABEL}
    _append(USES, use)
    t["recipe_use"] = {"recipe": rec["id"], "ts": use["ts"], "match_score": score, "outcome_recorded": False,
                       "applied": {"batched_windows": plan["batching"].get("batched_windows"),
                                   "suggest_window": plan["batching"].get("suggest_window")}}
    # Apply only what is safe and structural: a window hint for the same family when none is set.
    sw = plan["batching"].get("suggest_window")
    if plan["same_target_type"] and sw and not t.get("window"):
        t["window"] = min(int(sw), int(t.get("max_window") or sw))
    return use


def on_result(t: dict[str, Any], res: dict[str, Any]) -> dict[str, Any] | None:
    """Record whether the recipe helped: time-to-first-verified and kills/disagreements seen."""
    u = t.get("recipe_use")
    if not isinstance(u, dict) or u.get("outcome_recorded"):
        return None
    st = u.setdefault("stats", {"windows": 0, "seconds": 0.0, "disagreements": 0, "self_rejects": 0})
    st["windows"] += 1
    st["seconds"] = round(st["seconds"] + float((res.get("primary") or {}).get("seconds") or 0), 4)
    oc = res.get("outcome")
    st["disagreements"] += oc in ("disagreement", "unresolved_anomaly", "counterexample_candidate")
    st["self_rejects"] += oc == "self_rejected"
    verified = res.get("verified_hi") is not None or oc in SUCCESS_OUTCOMES
    if verified or st["disagreements"]:
        u["outcome_recorded"] = True
        row = {"kind": "recipe_outcome", "ts": _utc(), "target": t["id"], "recipe": u.get("recipe"),
               "verified": bool(verified), "time_to_first_verified_s": st["seconds"] if verified else None,
               "windows_to_first_verified": st["windows"] if verified else None,
               "disagreements": st["disagreements"], "self_rejects": st["self_rejects"],
               "helped": None, "note": "helped is judged only by the pre-registered comparison (evidence note)",
               "label": LABEL}
        _append(USES, row)
        return row
    return None


if __name__ == "__main__":
    from colony.frontier import load_catalog, load_log
    print(json.dumps({"new": distill(load_catalog(), load_log(limit=100000)),
                      "recipes": [r["id"] for r in load()]}, indent=2))
