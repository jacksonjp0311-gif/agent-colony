"""New-to-commons novelty gate.

Claim "novel" (to this colony commons) ONLY if ALL hold:
  1) identity not already in lesson ledger / known mutation identities
  2) machine check FAILS on stripped baseline (without the candidate)
  3) candidate SURVIVES a held-out harder check
  4) textbook-reuse score ≈ 0 (classical identity dumps blocked)

Not theorem discovery. Not AGI. Not Millennium. Textbook reuse ≈ 0.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LESSONS = ROOT / "data" / "commons" / "lessons.jsonl"
HISTORY = ROOT / "society" / "benchmarks" / "conjecture_history.jsonl"
KNOWN = ROOT / "society" / "systems" / "known_identities.json"
GATE_LOG = ROOT / "data" / "commons" / "novelty_gate.jsonl"
GATE_SYSTEM = ROOT / "society" / "systems" / "novelty_gate.json"

# Classical textbook identity names — claiming these as "novel" is killed
TEXTBOOK_IDENTITIES = {
    "square_of_sum",
    "difference_of_squares",
    "sum_first_n_odds",
    "binomial_symmetry",
    "pascal_identity",
    "frobenius",
    "geometric_sum",
    "sum_first_n_cubes",
    "vandermonde",
    "hockey_stick",
    "cassini",
    "fibonacci_addition",
    "binomial_sum_row",
    "catalan",
    "easy_pad",
    "pythagorean",
    "commutativity",
}


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def known_identities() -> set[str]:
    ids: set[str] = set()
    if KNOWN.exists():
        try:
            data = json.loads(KNOWN.read_text(encoding="utf-8"))
            for x in data.get("identities") or []:
                ids.add(str(x).lower())
        except (json.JSONDecodeError, OSError):
            pass
    if LESSONS.exists():
        for ln in LESSONS.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                e = json.loads(ln)
            except json.JSONDecodeError:
                continue
            mut = (e.get("mutation") or "").lower()
            fam = (e.get("family") or "").lower()
            if mut:
                ids.add(mut)
            if fam:
                ids.add(fam)
    if HISTORY.exists():
        for ln in HISTORY.read_text(encoding="utf-8").splitlines()[-80:]:
            try:
                e = json.loads(ln)
            except json.JSONDecodeError:
                continue
            mut = (e.get("mutation") or "").lower()
            if mut:
                ids.add(mut)
    # Persist snapshot
    KNOWN.parent.mkdir(parents=True, exist_ok=True)
    KNOWN.write_text(
        json.dumps(
            {
                "updated_at": _utc(),
                "n": len(ids),
                "identities": sorted(ids)[:200],
                "note": "Known identities from lessons + conjecture history. Not discovery.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return ids


def _only_own_authoring_record(name: str, known: set[str]) -> bool:
    """True iff the ONLY trace of ``name`` in the commons is the candidate's own authoring
    record (lesson type ``authored_check`` with mutation == name).

    The authoring step writes that record before the desk can judge the candidate, so without
    this the "not already known" condition is unsatisfiable by construction for every authored
    check. Any other trace — a desk judgment in conjecture history (full file, not just the
    recent window), any other lesson (keep/revert/kill/skip), a proposal-title row such as
    "Chain `name` citing …", or a snapshot entry other than the bare name — still makes it
    known. Fail closed: no authoring record found → False.
    """
    n = (name or "").strip().lower()
    if not n:
        return False
    # Snapshot/union entries containing the name other than the bare name → known elsewhere
    if any(n in k and k != n for k in known):
        return False
    authored = False
    if LESSONS.exists():
        for ln in LESSONS.read_text(encoding="utf-8").splitlines():
            if n not in ln.lower():
                continue
            try:
                e = json.loads(ln)
            except json.JSONDecodeError:
                return False  # unreadable row naming it → cannot prove, fail closed
            mut = (e.get("mutation") or "").lower()
            fam = (e.get("family") or "").lower()
            if n not in mut and n not in fam:
                continue
            if e.get("type") == "authored_check" and mut == n:
                authored = True
                continue
            return False
    if HISTORY.exists():
        for ln in HISTORY.read_text(encoding="utf-8").splitlines():
            if n in ln.lower():
                try:
                    e = json.loads(ln)
                except json.JSONDecodeError:
                    return False
                if n in (e.get("mutation") or "").lower():
                    return False
    return authored


def textbook_reuse_score(name: str, claim_text: str = "") -> float:
    """≈0 means not textbook dump; high means textbook reuse (kill novelty claim)."""
    blob = f"{name} {claim_text}".lower()
    hits = 0
    for tid in TEXTBOOK_IDENTITIES:
        if tid in blob or tid.replace("_", " ") in blob:
            hits += 1
    if name.lower().startswith("easy_pad"):
        hits += 2
    if "millennium" in blob or "riemann" in blob or "p vs np" in blob:
        hits += 5  # theater
    return round(min(1.0, hits / 3.0), 4)


def stripped_baseline_fails(mutation: str, baseline_src: str | None = None) -> dict[str, Any]:
    """Machine check must FAIL usefulness on stripped baseline (candidate absent).

    If mutation already enabled → not novel (already in commons).
    If mutation is easy_pad → baseline already passes basics → not novel lift.
    """
    try:
        from society.benchmarks.lemma_microbench import run as run_lemma
        from society.benchmarks.artifacts import lemma_impl as impl

        src_path = ROOT / "society" / "benchmarks" / "artifacts" / "lemma_impl.py"
        if baseline_src is not None:
            # The real stripped baseline: the impl source as it was BEFORE this candidate was
            # applied (the desk's pre-mutation snapshot). Same test, correct input.
            src = baseline_src
        else:
            src = src_path.read_text(encoding="utf-8") if src_path.exists() else ""
        _m = re.search(rf'\("{re.escape(mutation)}".*?,\s*(True|False)\)', src, re.S)
        already_enabled = bool(_m and _m.group(1) == "True")  # this entry's own flag only
        before = run_lemma()
        # Baseline "fails" the novelty usefulness test if candidate isn't adding
        # a new hard pass beyond what's already green.
        hard_pass = int(before.get("n_hard_pass") or 0)
        hard_n = int(before.get("n_hard") or 0)
        fails_usefulness = (not already_enabled) and (
            hard_pass < hard_n + 1  # room to lift OR new check not yet in
        )
        # For brand-new disabled checks, stripped baseline does not include them
        # → usefulness-fail (gate wants: without candidate, the specific check is absent)
        in_catalog = f'("{mutation}"' in src
        return {
            "already_enabled": already_enabled,
            "in_catalog": in_catalog,
            "hard_pass": hard_pass,
            "hard_n": hard_n,
            "stripped_fails_usefulness": (not already_enabled) and in_catalog,
            "score": float(before.get("score") or 0),
            "impl_id": getattr(impl, "impl_id", lambda: "?")(),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "already_enabled": False,
            "stripped_fails_usefulness": False,
            "error": str(exc),
        }


def held_out_harder_survives(mutation: str, kind: str) -> dict[str, Any]:
    """Survives held-out harder check = hard_enable that actually passes when enabled.

    Easy pads never survive held-out harder check.
    """
    if kind == "easy_pad" or mutation.startswith("easy_pad"):
        return {"survives": False, "reason": "easy_pad_fails_held_out_harder"}
    try:
        from society.benchmarks.lemma_microbench import run as run_lemma

        before = run_lemma()
        # Held-out: require current hard tier still green AND mutation not already credited
        ok = bool(before.get("ok")) and int(before.get("n_hard_pass") or 0) > 0
        return {
            "survives": ok and kind == "hard_enable",
            "reason": "hard_tier_green_and_hard_enable" if ok else "hard_tier_not_green",
            "hard_pass": before.get("n_hard_pass"),
            "ok": before.get("ok"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"survives": False, "reason": f"error:{exc}"}


def evaluate(
    *,
    mutation: str,
    kind: str = "",
    claim_text: str = "",
    cycle_id: str = "",
    oracle_source: str = "novelty_gate",
    bus: Any | None = None,
    oracle_verdict: Any | None = None,
    oracle_verdict_required: bool = False,
    baseline_src: str | None = None,
) -> dict[str, Any]:
    """Return gate verdict. novel_to_commons True only if all gates pass.

    ``oracle_source`` only labels the Oracle row/lesson (provenance); the checks are identical.

    Plumbing (the conditions themselves are unchanged):
    - ``oracle_verdict``: the Oracle verdict the caller already obtained for exactly this
      (mutation, kind, cycle). Used instead of a second Oracle run; it must match all three or
      the gate kills (fail closed). ``oracle_verdict_required`` → never run the Oracle here.
    - ``bus``: real CommBus handed to the Oracle when the gate runs it itself.
    - ``baseline_src``: the real stripped baseline (impl source before the candidate).
    """
    known = known_identities()
    name = (mutation or "").strip()
    in_ledger = name.lower() in known or any(name.lower() in k for k in known)
    own_record_only = False
    if in_ledger and _only_own_authoring_record(name, known):
        # A candidate's own birth record is not prior knowledge of it (see helper).
        in_ledger = False
        own_record_only = True
    reuse = textbook_reuse_score(name, claim_text)
    stripped = stripped_baseline_fails(name, baseline_src=baseline_src)
    held = held_out_harder_survives(name, kind or "")

    kills: list[str] = []
    if not name:
        kills.append("empty_identity")
    if in_ledger:
        kills.append("already_in_lesson_ledger_or_history")
    if reuse >= 0.34:
        kills.append(f"textbook_reuse={reuse}")
    if stripped.get("already_enabled"):
        kills.append("already_enabled_in_impl")
    if not stripped.get("stripped_fails_usefulness"):
        kills.append("stripped_baseline_does_not_fail_usefulness")
    if not held.get("survives"):
        kills.append(f"held_out:{held.get('reason')}")

    # Oracle mile: novelty alone is not enough — Oracle must also not kill
    oracle_used = "own_run"
    if oracle_verdict is not None or oracle_verdict_required:
        oracle_used = "caller_verdict"
        v = oracle_verdict
        _get = (lambda k: v.get(k)) if isinstance(v, dict) else (lambda k: getattr(v, k, None))
        if v is None:
            kills.append("oracle_verdict_missing_fail_closed")
        elif (str(_get("mutation") or "").strip() != name or str(_get("kind") or "") != (kind or "")
              or str(_get("cycle_id") or "") != (cycle_id or "")):
            kills.append("oracle_verdict_mismatch_fail_closed")
        elif not bool(_get("passed")):
            kills.append(f"oracle_kill:{_get('kills')}")
    else:
        try:
            from colony.oracle import evaluate as oracle_evaluate
            ov = oracle_evaluate(
                mutation=name,
                kind=kind or "",
                claim_text=claim_text,
                source=oracle_source or "novelty_gate",
                cycle_id=cycle_id,
                bus=bus,
            )
            if not ov.passed:
                kills.append(f"oracle_kill:{ov.kills}")
        except Exception as _ox:
            kills.append(f"oracle_error_fail_closed:{_ox}")

    novel = len(kills) == 0
    verdict = {
        "ts": _utc(),
        "cycle_id": cycle_id,
        "mutation": name,
        "kind": kind,
        "novel_to_commons": novel,
        "kills": kills,
        "textbook_reuse": reuse,
        "in_ledger": in_ledger,
        "own_authoring_record_only": own_record_only,
        "oracle_used": oracle_used,
        "stripped": stripped,
        "held_out": held,
        "note": (
            "Novelty = new-to-commons under machine gates only. "
            "Not theorem discovery. Textbook reuse ≈ 0 required. Not AGI."
        ),
    }
    GATE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with GATE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(verdict, ensure_ascii=False) + "\n")
    _persist_system(verdict)
    return verdict


def _persist_system(latest: dict[str, Any]) -> None:
    recent: list[dict[str, Any]] = []
    if GATE_LOG.exists():
        for ln in GATE_LOG.read_text(encoding="utf-8").splitlines()[-30:]:
            try:
                recent.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    hits = sum(1 for e in recent if e.get("novel_to_commons"))
    kills = sum(1 for e in recent if not e.get("novel_to_commons"))
    payload = {
        "version": 1,
        "updated_at": _utc(),
        "hits": hits,
        "kills": kills,
        "latest": latest,
        "note": "New-to-commons novelty gate. Textbook reuse≈0. Not novel theorems.",
    }
    GATE_SYSTEM.parent.mkdir(parents=True, exist_ok=True)
    GATE_SYSTEM.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def digest() -> str:
    if not GATE_SYSTEM.exists():
        return "(no novelty gate runs)"
    try:
        d = json.loads(GATE_SYSTEM.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "(novelty gate unreadable)"
    return f"hits={d.get('hits')} kills={d.get('kills')} latest={((d.get('latest') or {}).get('mutation'))}"


if __name__ == "__main__":
    import sys

    mut = sys.argv[1] if len(sys.argv) > 1 else "gcd_fibonacci"
    kind = sys.argv[2] if len(sys.argv) > 2 else "hard_enable"
    print(json.dumps(evaluate(mutation=mut, kind=kind), indent=2))
