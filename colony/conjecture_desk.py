"""Conjecture desk — propose candidates; mutate hard-tier lemmas; keep on score rise."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from colony.conjecture_mutations import (
    MUTATION_SNIPPETS,
    already_has as _already_has,
    apply_mutation as _apply_mutation,
    recent_revert_counts,
)

ROOT = Path(__file__).resolve().parent.parent
LEMMA_IMPL = ROOT / "society" / "benchmarks" / "artifacts" / "lemma_impl.py"
BACKUP_DIR = ROOT / "society" / "benchmarks" / ".lemma_backups"
HISTORY = ROOT / "society" / "benchmarks" / "conjecture_history.jsonl"
CACHE = ROOT / "data" / "research_cache" / "papers.jsonl"
WITNESS_NOTE = ROOT / "society" / "benchmarks" / "WITNESS_CONJECTURE.md"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _invalidate_pyc(path: Path) -> None:
    cache = path.parent / "__pycache__"
    if cache.is_dir():
        for pyc in cache.glob(f"{path.stem}*.pyc"):
            try:
                pyc.unlink()
            except OSError:
                pass


def run_lemma_bench() -> dict[str, Any]:
    from society.benchmarks.lemma_microbench import run as run_lemma
    return run_lemma()


def _load_paper_themes(limit: int = 12) -> list[dict[str, Any]]:
    if not CACHE.exists():
        return []
    out: list[dict[str, Any]] = []
    for ln in CACHE.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out[-limit:]


@dataclass
class ConjectureResult:
    ts: str
    decision: str
    before_score: float
    after_score: float
    delta: float
    mutation: str = ""
    themes: list[str] = field(default_factory=list)
    proposals: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""
    finding_ids: list[str] = field(default_factory=list)
    kind: str = ""


def propose_from_themes(themes, *, ledger=None, cycle_id: str = ""):
    proposals = []
    for t in themes[:5]:
        title = t.get("title") or "untitled"
        arxiv = t.get("arxiv_id") or ""
        doi = t.get("doi") or ""
        prop = {
            "kind": "conjecture_candidate",
            "theme": title[:120],
            "arxiv_id": arxiv,
            "doi": doi,
            "claim": (
                f"CONJECTURE CANDIDATE (not discovered): themes from `{title[:80]}` "
                f"may suggest hard-tier lemmas. Needs machine-check + authorize. Not Millennium."
            ),
            "status": "candidate",
        }
        proposals.append(prop)
        if ledger is not None:
            fnd = ledger.create(
                role="spark",
                claim=prop["claim"],
                evidence_urls=[u for u in [t.get("url") or "", f"arxiv:{arxiv}" if arxiv else "",
                                           "society/benchmarks/lemma_microbench.py", "artifacts:lemma_impl"] if u],
                provenance="conjecture_desk",
                status="candidate",
                tags=["conjecture", "open-math", "compute-useful-math", "not_discovery", "candidate", "hard_tier"],
                notes="Proposed from paper theme; NOT a discovery claim. Hard-tier pressure.",
                topic_id="open-math-problems",
                title=f"Conjecture candidate from: {title[:70]}",
                meta={"kind": "conjecture_candidate", "cycle_id": cycle_id, "arxiv_id": arxiv,
                      "doi": doi, "not_discovery": True, "hard_tier": True},
            )
            prop["finding_id"] = fnd.id
    return proposals


def improve_once(*, force_mutation=None, ledger=None, cycle_id: str = ""):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    before = run_lemma_bench()
    before_score = float(before.get("score") or 0.0)
    themes = _load_paper_themes()
    proposals = propose_from_themes(themes, ledger=ledger, cycle_id=cycle_id)
    src = LEMMA_IMPL.read_text(encoding="utf-8") if LEMMA_IMPL.exists() else ""
    recent_reverts = recent_revert_counts()
    chosen = kind = snippet = ""
    chosen = None
    try:
        from colony.exploration_budget import pick_mutation_order
        ordered = pick_mutation_order(list(MUTATION_SNIPPETS))
    except Exception:
        ordered = list(MUTATION_SNIPPETS)
    for name, k, snip in ordered:
        if force_mutation and name != force_mutation:
            continue
        if _already_has(src, name):
            continue
        # Autonomy mile: allow one more retry on easy_pad to prove revert; hard uses >=3
        limit = 3 if name.startswith("easy_pad") else 2
        if not force_mutation and recent_reverts.get(name, 0) >= limit:
            continue
        chosen, kind, snippet = name, k, snip
        break
    if not chosen:
        result = ConjectureResult(
            ts=_utc(), decision="skip", before_score=before_score, after_score=before_score,
            delta=0.0, themes=[t.get("title", "")[:60] for t in themes[:4]], proposals=proposals,
            note="No pending hard-tier lemma mutations (catalog exhausted or empty).",
            finding_ids=[p.get("finding_id") for p in proposals if p.get("finding_id")],
        )
        _append_history(result); _write_witness([result]); return result
    backup = BACKUP_DIR / f"lemma_impl_{chosen}_{datetime.now(timezone.utc).strftime('%H%M%S')}.py"
    shutil.copy2(LEMMA_IMPL, backup)
    new_src = _apply_mutation(src, chosen, kind, snippet)
    if not new_src:
        result = ConjectureResult(
            ts=_utc(), decision="skip", before_score=before_score, after_score=before_score, delta=0.0,
            mutation=chosen, kind=kind, themes=[t.get("title", "")[:60] for t in themes[:4]],
            proposals=proposals, note="Mutation apply failed.",
            finding_ids=[p.get("finding_id") for p in proposals if p.get("finding_id")],
        )
        _append_history(result); return result
    LEMMA_IMPL.write_text(new_src, encoding="utf-8"); _invalidate_pyc(LEMMA_IMPL)
    after = run_lemma_bench()
    after_score = float(after.get("score") or 0.0)
    delta = round(after_score - before_score, 4)
    n_before = int(before.get("n_checks") or 0)
    n_after = int(after.get("n_checks") or 0)
    n_hard_before = int(before.get("n_hard_pass") or 0)
    n_hard_after = int(after.get("n_hard_pass") or 0)
    rose = after.get("ok") and (
        after_score > before_score + 1e-6
        or (after_score >= before_score and n_hard_after > n_hard_before)
    )
    if kind == "easy_pad" and n_hard_after <= n_hard_before:
        rose = False
    # Oracle mile: FAIL kills keep. No Oracle pass → no fitness rise.
    oracle_note = ""
    oracle_passed = False
    try:
        from colony.oracle import gate_keep as oracle_gate
        tentative = "keep" if rose else "revert"
        final_dec, ov = oracle_gate(
            tentative_decision=tentative,
            mutation=chosen or "",
            kind=kind or "",
            claim_text=f"lemma mutation {chosen} {before_score}->{after_score}",
            source="conjecture_desk",
            cycle_id=cycle_id,
            after_snapshot=after,
            hard_pass_delta=(n_hard_after - n_hard_before),
            before_score=before_score,
            after_score=after_score,
        )
        oracle_passed = bool(ov.passed and ov.fitness_credit)
        oracle_note = (
            f" | oracle={'PASS' if ov.passed else 'KILL'} "
            f"fitness_credit={ov.fitness_credit} kills={ov.kills}"
        )
        if tentative == "keep" and final_dec != "keep":
            rose = False  # Oracle killed keep
    except Exception as _oracle_exc:  # noqa: BLE001
        # Fail-closed: cannot keep without Oracle
        if rose:
            rose = False
            oracle_note = f" | oracle=ERROR_fail_closed:{_oracle_exc}"
    if rose and oracle_passed:
        decision = "keep"
        note = (f"Kept `{chosen}` ({kind}): lemma score {before_score}→{after_score} "
                f"checks {n_before}→{n_after} hard_pass {n_hard_before}→{n_hard_after} "
                f"(machine-checked + Oracle pass; not novel discovery).{oracle_note}")
    else:
        decision = "revert"
        shutil.copy2(backup, LEMMA_IMPL); _invalidate_pyc(LEMMA_IMPL)
        note = (f"Reverted `{chosen}` ({kind}): score {before_score}→{after_score} "
                f"ok={after.get('ok')} hard_pass {n_hard_before}→{n_hard_after} "
                f"— Oracle/hard-tier required for keep; easy pads die on Oracle."
                f"{oracle_note}")
        after_score = before_score; delta = 0.0
    finding_ids = [p.get("finding_id") for p in proposals if p.get("finding_id")]
    if ledger is not None:
        try:
            ledger.set_extra_roles({"spark", "geometer", "tribute_keeper"})
        except Exception:
            pass
        fnd = ledger.create(
            role="spark",
            claim=(f"LEMMA MUTATION({decision}): `{chosen}` kind={kind} score {before_score}→{after_score}. "
                   f"Machine-checked lemma bench. Not novel theorem. Needs authorize."),
            evidence_urls=["society/benchmarks/lemma_microbench.py",
                           "society/benchmarks/artifacts/lemma_impl.py", f"cycle:{cycle_id}"],
            provenance="conjecture_desk", status="candidate",
            tags=["lemma", "conjecture", "bench", "compute-useful-math", "not_discovery", decision, kind or "mutation"],
            notes=note, topic_id="compute-useful-math",
            title=f"Lemma mutation {decision}: {chosen}",
            meta={"kind": "lemma_mutation", "decision": decision, "mutation": chosen,
                  "mutation_kind": kind, "before_score": before_score, "after_score": after_score,
                  "cycle_id": cycle_id, "not_discovery": True},
        )
        finding_ids.append(fnd.id)
    result = ConjectureResult(
        ts=_utc(), decision=decision, before_score=before_score, after_score=after_score,
        delta=delta, mutation=chosen, kind=kind,
        themes=[t.get("title", "")[:60] for t in themes[:4]], proposals=proposals, note=note,
        finding_ids=[x for x in finding_ids if x],
    )
    try:
        from colony.external_mind import record_desk_outcome
        cites = []
        for pr in proposals:
            if pr.get("arxiv_id"):
                cites.append(f"arxiv:{pr['arxiv_id']}")
            if pr.get("url"):
                cites.append(pr["url"])
        record_desk_outcome(
            decision=decision,
            mutation=chosen or "",
            before_score=before_score,
            after_score=after_score,
            kind=kind or "",
            note=note,
            cycle_id=cycle_id,
            paper_cites=cites,
        )
        # Lift 2: lesson ledger from keep/revert only
        from colony.lessons import write_lesson
        write_lesson(
            decision=decision,
            check="lemma_microbench",
            what=note,
            source="conjecture_desk",
            cycle_id=cycle_id,
            mutation=chosen or "",
            before_score=before_score,
            after_score=after_score,
            family="easy_pad" if kind == "easy_pad" else ("hard_enable" if kind == "hard_enable" else "outcome"),
            skill_bias={
                "geometer.gather": 0.08 if decision == "keep" else -0.04,
                "improver.improve": 0.06 if decision == "keep" else -0.03,
                "spark.emergence": 0.04 if decision == "keep" else -0.02,
            },
            tags=["lemma", kind or "mutation", decision],
            evidence=["society/benchmarks/lemma_microbench.py", "artifacts:lemma_impl"],
        )
        # Autonomy mile B: novelty gate (new-to-commons only)
        try:
            from colony.novelty_gate import evaluate as novelty_evaluate
            nov = novelty_evaluate(
                mutation=chosen or "",
                kind=kind or "",
                claim_text=note,
                cycle_id=cycle_id,
            )
            result.note = (result.note or note) + (
                f" | novelty_gate novel={nov.get('novel_to_commons')} kills={nov.get('kills')}"
            )
        except Exception:
            pass
        # Autonomy mile D: exploration budget — distribution MUST change after reverts
        try:
            from colony.exploration_budget import record_outcome
            record_outcome(chosen or "", decision, kind=kind or "")
        except Exception:
            pass
    except Exception:
        pass
    _append_history(result); _write_witness([result]); return result


def _append_history(r: ConjectureResult) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": r.ts, "decision": r.decision, "before_score": r.before_score,
             "after_score": r.after_score, "delta": r.delta, "mutation": r.mutation,
             "kind": r.kind, "note": r.note, "themes": r.themes}
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _write_witness(results: list[ConjectureResult]) -> None:
    lines = [
        f"# Conjecture desk witness — {_utc()}", "",
        "Hard-tier mutations; keep only if lemma score/hard_pass rises AND Oracle passes. Easy pads die on Oracle. "
        "Not discovery. Not AGI. Not Millennium.", "",
    ]
    for r in results:
        lines.append(
            f"- `{r.mutation or 'none'}` ({r.kind or '-'}) → **{r.decision}** "
            f"{r.before_score}→{r.after_score} ({r.delta:+.4f}) — {r.note}"
        )
        if r.themes:
            lines.append(f"  - themes: {', '.join(r.themes[:3])}")
    lines += ["", "## Honesty", "",
              "- Classical textbook identities != novel mathematics.", ""]
    WITNESS_NOTE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_from_growth(cycle_id: str, ledger=None):
    return improve_once(ledger=ledger, cycle_id=cycle_id)


if __name__ == "__main__":
    r = improve_once()
    print(json.dumps({"decision": r.decision, "mutation": r.mutation, "kind": r.kind,
                      "before": r.before_score, "after": r.after_score, "delta": r.delta,
                      "note": r.note, "n_proposals": len(r.proposals)}, indent=2))
