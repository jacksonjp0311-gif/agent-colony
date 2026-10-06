"""Benchmark improver — measure → patch → re-measure → keep/revert.

CLI: python -m colony bench-improve
Also called once per evolve growth cycle.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
BENCH_ROOT = ROOT / "society" / "benchmarks"
ARTIFACTS = BENCH_ROOT / "artifacts"
FFT_IMPL = ARTIFACTS / "fft_impl.py"
AUTODIFF_IMPL = ARTIFACTS / "autodiff_impl.py"
HISTORY = BENCH_ROOT / "improve_history.jsonl"
WITNESS_NOTE = BENCH_ROOT / "WITNESS_IMPROVE.md"
BACKUP_DIR = BENCH_ROOT / ".improve_backups"

def _invalidate_pyc(path: Path) -> None:
    cache = path.parent / "__pycache__"
    if cache.is_dir():
        for pyc in cache.glob(f"{path.stem}*.pyc"):
            try:
                pyc.unlink()
            except OSError:
                pass



def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_harness() -> dict[str, Any]:
    from society.benchmarks.run_benchmarks import main as run_benches

    return run_benches()


@dataclass
class Patch:
    name: str
    target: Path
    description: str
    apply_fn: Callable[[str], str]
    expected: str = "up"  # "up" hope for keep; "down" deliberate for revert demo


def _patch_remove_slow_loops(src: str) -> str:
    """Set SLOW_EXTRA_LOOPS = 0 (speedup)."""
    if "SLOW_EXTRA_LOOPS" not in src:
        return src
    return re.sub(
        r"SLOW_EXTRA_LOOPS\s*=\s*\d+",
        "SLOW_EXTRA_LOOPS = 0",
        src,
        count=1,
    )


def _patch_add_slow_loops(src: str) -> str:
    """Bump SLOW_EXTRA_LOOPS (deliberate regression for revert proof)."""
    m = re.search(r"SLOW_EXTRA_LOOPS\s*=\s*(\d+)", src)
    if not m:
        # inject constant near top
        inject = "\nSLOW_EXTRA_LOOPS = 8\n"
        if "from typing" in src:
            src = src.replace("from typing import Sequence\n", "from typing import Sequence\n" + inject, 1)
        else:
            src = inject + src
        return src
    cur = int(m.group(1))
    return re.sub(
        r"SLOW_EXTRA_LOOPS\s*=\s*\d+",
        f"SLOW_EXTRA_LOOPS = {cur + 5}",
        src,
        count=1,
    )


def _patch_precompute_hint(src: str) -> str:
    """Tiny no-op-ish comment + ensure slow loops stay; used only if no slow knob."""
    if "PRECOMPUTE_MARK" in src:
        return src
    return src.replace(
        '"""Colony FFT artifact',
        '"""Colony FFT artifact [PRECOMPUTE_MARK]',
        1,
    )


def _patch_autodiff_noop_slow(src: str) -> str:
    """Add a tiny busy loop in grads (should hurt / be reverted)."""
    if "BENCH_IMPROVE_SLOW" in src:
        return src
    return src.replace(
        "def grads(x: float, a: float, b: float, c: float) -> dict[str, float]:\n",
        "def grads(x: float, a: float, b: float, c: float) -> dict[str, float]:\n"
        "    # BENCH_IMPROVE_SLOW\n"
        "    _busy = 0.0\n"
        "    for _i in range(2000):\n"
        "        _busy += 0.0000001\n",
        1,
    )


PATCH_CATALOG: list[Patch] = [
    Patch(
        name="fft_remove_slow_loops",
        target=FFT_IMPL,
        description="Zero SLOW_EXTRA_LOOPS — remove deliberate drag",
        apply_fn=_patch_remove_slow_loops,
        expected="up",
    ),
    Patch(
        name="fft_add_slow_loops",
        target=FFT_IMPL,
        description="Increase SLOW_EXTRA_LOOPS — deliberate regression",
        apply_fn=_patch_add_slow_loops,
        expected="down",
    ),
    Patch(
        name="autodiff_busy_loop",
        target=AUTODIFF_IMPL,
        description="Add busy loop in autodiff grads — should revert",
        apply_fn=_patch_autodiff_noop_slow,
        expected="down",
    ),
]


@dataclass
class ImproveResult:
    ts: str
    patch_name: str
    decision: str  # keep | revert | skip
    before_score: float
    after_score: float
    delta: float
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    note: str = ""
    target: str = ""


def _pick_patch(force: str | None = None) -> Patch | None:
    if force:
        for p in PATCH_CATALOG:
            if p.name == force:
                return p
        return None
    # Prefer speedup if slow loops present
    fft_src = FFT_IMPL.read_text(encoding="utf-8") if FFT_IMPL.exists() else ""
    m = re.search(r"SLOW_EXTRA_LOOPS\s*=\s*(\d+)", fft_src)
    if m and int(m.group(1)) > 0:
        return PATCH_CATALOG[0]  # remove slow
    hist = _load_history()
    recent = hist[-12:]
    # Avoid hammering a patch that just reverted many times
    revert_counts: dict[str, int] = {}
    for h in recent:
        if h.get("decision") == "revert":
            revert_counts[h.get("patch_name") or ""] = revert_counts.get(h.get("patch_name") or "", 0) + 1
    for p in PATCH_CATALOG:
        if p.name == "fft_remove_slow_loops":
            continue  # already at 0
        if revert_counts.get(p.name, 0) >= 2:
            continue
        return p
    # Rotate: try autodiff slow if fft_add exhausted
    for p in PATCH_CATALOG:
        if p.expected == "down" and revert_counts.get(p.name, 0) < 3:
            return p
    return PATCH_CATALOG[1]


def _load_history() -> list[dict[str, Any]]:
    if not HISTORY.exists():
        return []
    out: list[dict[str, Any]] = []
    for ln in HISTORY.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def _append_history(entry: dict[str, Any]) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _write_witness(results: list[ImproveResult], cycle_note: str = "") -> None:
    lines = [
        f"# Benchmark improve witness — {_utc()}",
        "",
        "Measure → patch → re-measure → **keep** if aggregate_score rises, else **revert**.",
        "",
    ]
    if cycle_note:
        lines.append(f"- note: {cycle_note}")
        lines.append("")
    for r in results:
        lines.append(
            f"- `{r.patch_name}` → **{r.decision}** "
            f"before={r.before_score} after={r.after_score} delta={r.delta:+.4f} "
            f"— {r.note}"
        )
    lines.append("")
    lines.append("## Recent history")
    lines.append("")
    for h in _load_history()[-12:]:
        lines.append(
            f"- {h.get('ts')} `{h.get('patch_name')}` **{h.get('decision')}** "
            f"{h.get('before_score')}→{h.get('after_score')} ({h.get('delta'):+})"
        )
    lines.append("")
    WITNESS_NOTE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def improve_once(
    *,
    force_patch: str | None = None,
    cycle_id: str | None = None,
) -> ImproveResult:
    """Run one measure→patch→remeasure→keep/revert cycle."""
    patch = _pick_patch(force_patch)
    if patch is None:
        return ImproveResult(
            ts=_utc(),
            patch_name="none",
            decision="skip",
            before_score=0.0,
            after_score=0.0,
            delta=0.0,
            note="no patch selected",
        )
    if not patch.target.exists():
        return ImproveResult(
            ts=_utc(),
            patch_name=patch.name,
            decision="skip",
            before_score=0.0,
            after_score=0.0,
            delta=0.0,
            note=f"missing target {patch.target}",
            target=str(patch.target),
        )

    before = run_harness()
    before_score = float(before.get("aggregate_score") or 0.0)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    original = patch.target.read_text(encoding="utf-8")
    new_bytes = original.encode("utf-8")
    latest = None
    cands = sorted(
        BACKUP_DIR.glob(f"{patch.target.name}.*.bak"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if cands and cands[0].read_bytes() == new_bytes:
        backup = cands[0]
    else:
        backup = BACKUP_DIR / f"{patch.target.name}.{_utc().replace(':', '')}.bak"
        backup.write_bytes(new_bytes)
        # Cap: keep last 5 distinct hashes per target
        seen_hashes = set()
        keep = []
        for p in cands:
            h = hash(p.read_bytes())
            if h in seen_hashes:
                try:
                    p.unlink()
                except OSError:
                    pass
                continue
            seen_hashes.add(h)
            keep.append(p)
        for p in keep[5:]:
            try:
                p.unlink()
            except OSError:
                pass
    patched = patch.apply_fn(original)
    if patched == original:
        return ImproveResult(
            ts=_utc(),
            patch_name=patch.name,
            decision="skip",
            before_score=before_score,
            after_score=before_score,
            delta=0.0,
            before=before,
            after=before,
            note="patch was a no-op",
            target=str(patch.target.relative_to(ROOT)),
        )

    patch.target.write_text(patched, encoding="utf-8")
    _invalidate_pyc(patch.target)
    try:
        after = run_harness()
    except Exception as exc:  # noqa: BLE001 — always revert on harness crash
        patch.target.write_text(original, encoding="utf-8")
        _invalidate_pyc(patch.target)
        result = ImproveResult(
            ts=_utc(),
            patch_name=patch.name,
            decision="revert",
            before_score=before_score,
            after_score=before_score,
            delta=0.0,
            before=before,
            after={},
            note=f"harness error: {exc}; reverted",
            target=str(patch.target.relative_to(ROOT)),
        )
        _record(result, cycle_id)
        return result

    trial_score = float(after.get("aggregate_score") or 0.0)
    trial_delta = round(trial_score - before_score, 4)
    trial_after = after
    tentative_keep = trial_score > before_score + 0.01 and after.get("ok_all")
    oracle_note = ""
    if tentative_keep:
        try:
            from colony.oracle import gate_keep as oracle_gate
            final_dec, ov = oracle_gate(
                tentative_decision="keep",
                mutation=patch.name,
                kind="bench_keep",
                claim_text=patch.description,
                source="bench_improve",
                cycle_id=cycle_id or "",
                before_score=before_score,
                after_score=trial_score,
            )
            oracle_note = f" | oracle={'PASS' if ov.passed else 'KILL'} kills={ov.kills}"
            if final_dec != "keep":
                tentative_keep = False
        except Exception as _ox:
            tentative_keep = False
            oracle_note = f" | oracle=ERROR_fail_closed:{_ox}"
    if tentative_keep:
        decision = "keep"
        note = f"aggregate rose; kept patch ({patch.description}){oracle_note}"
        result = ImproveResult(
            ts=_utc(),
            patch_name=patch.name,
            decision=decision,
            before_score=before_score,
            after_score=trial_score,
            delta=trial_delta,
            before=before,
            after=trial_after,
            note=note,
            target=str(patch.target.relative_to(ROOT)),
        )
    else:
        decision = "revert"
        note = (
            f"aggregate did not rise or Oracle killed keep "
            f"(trial={trial_score}, delta={trial_delta}); "
            f"reverted ({patch.description}){oracle_note}"
        )
        patch.target.write_text(original, encoding="utf-8")
        _invalidate_pyc(patch.target)
        # Re-run so latest.json matches kept artifact
        restored = run_harness()
        result = ImproveResult(
            ts=_utc(),
            patch_name=patch.name,
            decision=decision,
            before_score=before_score,
            after_score=trial_score,  # record rejected trial score for witness
            delta=trial_delta,
            before=before,
            after=trial_after,  # rejected patch metrics
            note=note + f"; restored_agg={restored.get('aggregate_score')}",
            target=str(patch.target.relative_to(ROOT)),
        )
    _record(result, cycle_id)
    return result


def _record(result: ImproveResult, cycle_id: str | None) -> None:
    entry = {
        "ts": result.ts,
        "cycle_id": cycle_id,
        "patch_name": result.patch_name,
        "decision": result.decision,
        "before_score": result.before_score,
        "after_score": result.after_score,
        "delta": result.delta,
        "target": result.target,
        "note": result.note,
        "before_benches": [
            {"bench": b.get("bench"), "score": b.get("score"), "seconds": b.get("seconds"), "impl": b.get("impl_id")}
            for b in (result.before.get("benches") or [])
        ],
        "after_benches": [
            {"bench": b.get("bench"), "score": b.get("score"), "seconds": b.get("seconds"), "impl": b.get("impl_id")}
            for b in (result.after.get("benches") or [])
        ],
    }
    _append_history(entry)
    _write_witness([result], cycle_note=f"cycle_id={cycle_id}" if cycle_id else "")
    try:
        from colony.lessons import write_lesson
        write_lesson(
            decision=result.decision,
            check="bench_harness",
            what=result.note,
            source="bench_improve",
            cycle_id=cycle_id or "",
            mutation=result.patch_name,
            before_score=result.before_score,
            after_score=result.after_score,
            family="bench_hard" if result.decision == "keep" else "outcome",
            skill_bias={
                "improver.improve": 0.07 if result.decision == "keep" else -0.05,
                "builder.build": 0.05 if result.decision == "keep" else -0.03,
            },
            tags=["bench", result.decision, result.patch_name],
            evidence=[result.target, "society/benchmarks/run_benchmarks.py"],
        )
    except Exception:
        pass


def improve_demo() -> list[ImproveResult]:
    """Prove keep vs revert: speedup keep, then deliberate slowdown revert."""
    results: list[ImproveResult] = []
    # 1) Remove slow loops → expect keep (if loops > 0)
    r1 = improve_once(force_patch="fft_remove_slow_loops", cycle_id="demo_keep")
    results.append(r1)
    # 2) Add slow loops → expect revert
    r2 = improve_once(force_patch="fft_add_slow_loops", cycle_id="demo_revert")
    results.append(r2)
    _write_witness(results, cycle_note="demo: keep then revert")
    return results


def run_from_growth(cycle_id: str) -> ImproveResult:
    """One improve attempt per growth/evolve cycle."""
    return improve_once(cycle_id=cycle_id)
