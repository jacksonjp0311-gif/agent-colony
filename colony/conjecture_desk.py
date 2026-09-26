"""Conjecture desk — propose candidates from paper themes + mutate lemmas.

Honest frame:
- Colony may propose conjectures and small lemmas.
- Durable "discovered" requires machine-check (lemma bench) + human authorize.
- Keep mutations only if lemma microbench score rises (bench_improve pattern).
- Never claim Millennium problems solved.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


# Candidate lemma mutations (educational identities — not novel discoveries)
MUTATION_SNIPPETS: list[tuple[str, str]] = [
    (
        "sum_first_n_cubes",
        '''
def check_sum_first_n_cubes(n: int) -> bool:
    """1^3+...+n^3 = (n(n+1)/2)^2"""
    if n < 0:
        return False
    s = sum(i ** 3 for i in range(1, n + 1))
    return s == (n * (n + 1) // 2) ** 2
''',
    ),
    (
        "geometric_sum",
        '''
def check_geometric_sum(a: int = 2, n: int = 10) -> bool:
    """1+a+...+a^{n-1} = (a^n-1)/(a-1) for a!=1"""
    if a == 1:
        return True
    lhs = sum(a ** i for i in range(n))
    rhs = (a ** n - 1) // (a - 1)
    return lhs == rhs
''',
    ),
    (
        "handshaking_small",
        '''
def check_handshaking_lemma_small() -> bool:
    """Sum of degrees = 2|E| on a tiny complete graph K4."""
    # K4: 4 verts, each deg 3, edges=6
    degrees = [3, 3, 3, 3]
    edges = 6
    return sum(degrees) == 2 * edges
''',
    ),
]


def _already_has(src: str, name: str) -> bool:
    return f"check_{name}" in src or f'"{name}"' in src


def _apply_mutation(src: str, name: str, snippet: str) -> str | None:
    """Append a check function and register it in CANDIDATE_LEMMAS if missing."""
    if _already_has(src, name):
        return None
    # Insert function before CANDIDATE_LEMMAS
    marker = "# Mutable catalog the conjecture desk may extend / mutate."
    if marker not in src:
        return None
    fn_block = snippet.strip() + "\n\n"
    src = src.replace(marker, fn_block + marker, 1)
    # Register in catalog list — inject before closing ]
    entry = (
        f'    ("{name}", '
        f'lambda: all(check_{name}(n) for n in range(0, 30)) if "{name}" == "sum_first_n_cubes" '
        f'else (check_{name}() if "{name}" == "handshaking_small" else all(check_{name}(a, n) for a in (2, 3) for n in range(1, 12))), '
        f"True),\n"
    )
    # Simpler explicit registration per known name
    if name == "sum_first_n_cubes":
        entry = (
            f'    ("{name}", lambda: all(check_sum_first_n_cubes(n) for n in range(0, 30)), True),\n'
        )
    elif name == "geometric_sum":
        entry = (
            f'    ("{name}", lambda: all(check_geometric_sum(a, n) for a in (2, 3, 5) for n in range(1, 12)), True),\n'
        )
    elif name == "handshaking_small":
        entry = f'    ("{name}", check_handshaking_lemma_small, True),\n'
    # Find CANDIDATE_LEMMAS = [ ... ]
    m = re.search(r"CANDIDATE_LEMMAS:\s*list\[.*?\]\s*=\s*\[", src)
    if not m:
        return None
    # Insert before the last ] that closes the list — find after marker
    idx = src.find("]", m.end())
    # Better: insert before the final entry's closing of the list by finding last tuple end
    # Use a unique anchor: last known lemma line
    anchor = '("frobenius_4_7"'
    if anchor in src:
        # insert after frobenius line
        line_end = src.find("\n", src.find(anchor))
        src = src[: line_end + 1] + entry + src[line_end + 1 :]
    else:
        # append before closing bracket of list
        close = src.rfind("]")
        src = src[:close] + entry + src[close:]
    return src


@dataclass
class ConjectureResult:
    ts: str
    decision: str  # keep | revert | skip | propose_only
    before_score: float
    after_score: float
    delta: float
    mutation: str = ""
    themes: list[str] = field(default_factory=list)
    proposals: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""
    finding_ids: list[str] = field(default_factory=list)


def propose_from_themes(
    themes: list[dict[str, Any]],
    *,
    ledger: Any | None = None,
    cycle_id: str = "",
) -> list[dict[str, Any]]:
    """Propose conjecture *candidates* (not discoveries) from paper themes."""
    proposals: list[dict[str, Any]] = []
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
                f"may suggest small algebraic/integer lemmas for the lemma harness. "
                f"Ids=arXiv:{arxiv or 'n/a'} DOI:{doi or 'n/a'}. "
                f"Requires machine-check + human authorize for durable status. "
                f"Never claim Millennium problems solved."
            ),
            "status": "candidate",
        }
        proposals.append(prop)
        if ledger is not None:
            fnd = ledger.create(
                role="spark",
                claim=prop["claim"],
                evidence_urls=[
                    u
                    for u in [
                        t.get("url") or "",
                        f"arxiv:{arxiv}" if arxiv else "",
                        "society/benchmarks/lemma_microbench.py",
                        "artifacts:lemma_impl",
                    ]
                    if u
                ],
                provenance="conjecture_desk",
                status="candidate",
                tags=["conjecture", "open-math", "compute-useful-math", "not_discovery", "candidate"],
                notes="Proposed from paper theme; NOT a discovery claim.",
                topic_id="open-math-problems",
                title=f"Conjecture candidate from: {title[:70]}",
                meta={
                    "kind": "conjecture_candidate",
                    "cycle_id": cycle_id,
                    "arxiv_id": arxiv,
                    "doi": doi,
                    "not_discovery": True,
                },
            )
            prop["finding_id"] = fnd.id
    return proposals


def improve_once(
    *,
    force_mutation: str | None = None,
    ledger: Any | None = None,
    cycle_id: str = "",
) -> ConjectureResult:
    """Mutate lemma_impl → re-run lemma bench → keep if score rises else revert."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    before = run_lemma_bench()
    before_score = float(before.get("score") or 0.0)

    themes = _load_paper_themes()
    proposals = propose_from_themes(themes, ledger=ledger, cycle_id=cycle_id)

    src = LEMMA_IMPL.read_text(encoding="utf-8") if LEMMA_IMPL.exists() else ""
    chosen = None
    snippet = ""
    for name, snip in MUTATION_SNIPPETS:
        if force_mutation and name != force_mutation:
            continue
        if _already_has(src, name):
            continue
        chosen, snippet = name, snip
        break

    if not chosen:
        result = ConjectureResult(
            ts=_utc(),
            decision="skip",
            before_score=before_score,
            after_score=before_score,
            delta=0.0,
            themes=[t.get("title", "")[:60] for t in themes[:4]],
            proposals=proposals,
            note="No pending lemma mutations (catalog already extended or empty).",
            finding_ids=[p.get("finding_id") for p in proposals if p.get("finding_id")],
        )
        _append_history(result)
        _write_witness([result])
        return result

    backup = BACKUP_DIR / f"lemma_impl_{chosen}_{datetime.now(timezone.utc).strftime('%H%M%S')}.py"
    shutil.copy2(LEMMA_IMPL, backup)
    new_src = _apply_mutation(src, chosen, snippet)
    if not new_src:
        result = ConjectureResult(
            ts=_utc(),
            decision="skip",
            before_score=before_score,
            after_score=before_score,
            delta=0.0,
            mutation=chosen,
            themes=[t.get("title", "")[:60] for t in themes[:4]],
            proposals=proposals,
            note="Mutation apply failed.",
            finding_ids=[p.get("finding_id") for p in proposals if p.get("finding_id")],
        )
        _append_history(result)
        return result

    LEMMA_IMPL.write_text(new_src, encoding="utf-8")
    _invalidate_pyc(LEMMA_IMPL)
    after = run_lemma_bench()
    after_score = float(after.get("score") or 0.0)
    delta = round(after_score - before_score, 4)
    n_before = int(before.get("n_checks") or 0)
    n_after = int(after.get("n_checks") or 0)
    rose = after.get("ok") and (
        after_score > before_score + 1e-6
        or (after_score >= before_score and n_after > n_before)
    )
    if rose:
        decision = "keep"
        note = (
            f"Kept `{chosen}`: lemma score {before_score}→{after_score} "
            f"checks {n_before}→{n_after} (machine-checked)."
        )
    else:
        decision = "revert"
        shutil.copy2(backup, LEMMA_IMPL)
        _invalidate_pyc(LEMMA_IMPL)
        note = (
            f"Reverted `{chosen}`: score {before_score}→{after_score} ok={after.get('ok')} "
            f"— checks must pass for keep."
        )
        after_score = before_score
        delta = 0.0

    # Ledger note: keep is still candidate until human authorize; never "discovered"
    finding_ids = [p.get("finding_id") for p in proposals if p.get("finding_id")]
    if ledger is not None:
        try:
            ledger.set_extra_roles({"spark", "geometer", "tribute_keeper"})
        except Exception:
            pass
        fnd = ledger.create(
            role="spark",
            claim=(
                f"LEMMA MUTATION({decision}): `{chosen}` score {before_score}→{after_score}. "
                f"Machine-checked via society/benchmarks/lemma_microbench.py + artifacts/lemma_impl.py. "
                f"NOT a novel theorem discovery. NOT Millennium. Durable accepted needs human authorize."
            ),
            evidence_urls=[
                "society/benchmarks/lemma_microbench.py",
                "society/benchmarks/artifacts/lemma_impl.py",
                f"cycle:{cycle_id}",
            ],
            provenance="conjecture_desk",
            status="candidate",
            tags=["lemma", "conjecture", "bench", "compute-useful-math", "not_discovery", decision],
            notes=note,
            topic_id="compute-useful-math",
            title=f"Lemma mutation {decision}: {chosen}",
            meta={
                "kind": "lemma_mutation",
                "decision": decision,
                "mutation": chosen,
                "before_score": before_score,
                "after_score": after_score,
                "cycle_id": cycle_id,
                "not_discovery": True,
            },
        )
        finding_ids.append(fnd.id)

    result = ConjectureResult(
        ts=_utc(),
        decision=decision,
        before_score=before_score,
        after_score=after_score,
        delta=delta,
        mutation=chosen,
        themes=[t.get("title", "")[:60] for t in themes[:4]],
        proposals=proposals,
        note=note,
        finding_ids=[x for x in finding_ids if x],
    )
    _append_history(result)
    _write_witness([result])
    return result


def _append_history(r: ConjectureResult) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": r.ts,
        "decision": r.decision,
        "before_score": r.before_score,
        "after_score": r.after_score,
        "delta": r.delta,
        "mutation": r.mutation,
        "note": r.note,
        "themes": r.themes,
    }
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _write_witness(results: list[ConjectureResult]) -> None:
    lines = [
        f"# Conjecture desk witness — {_utc()}",
        "",
        "Propose conjecture candidates from paper themes; mutate lemmas; "
        "**keep** only if lemma_microbench score rises. Not discovery claims. Not AGI.",
        "",
    ]
    for r in results:
        lines.append(
            f"- `{r.mutation or 'none'}` → **{r.decision}** "
            f"{r.before_score}→{r.after_score} ({r.delta:+.4f}) — {r.note}"
        )
        if r.themes:
            lines.append(f"  - themes: {', '.join(r.themes[:3])}")
    lines.append("")
    WITNESS_NOTE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_from_growth(cycle_id: str, ledger: Any | None = None) -> ConjectureResult:
    return improve_once(ledger=ledger, cycle_id=cycle_id)


if __name__ == "__main__":
    r = improve_once()
    print(
        json.dumps(
            {
                "decision": r.decision,
                "mutation": r.mutation,
                "before": r.before_score,
                "after": r.after_score,
                "delta": r.delta,
                "note": r.note,
                "n_proposals": len(r.proposals),
            },
            indent=2,
        )
    )
