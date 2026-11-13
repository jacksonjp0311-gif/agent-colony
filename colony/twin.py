"""Twin scoreboard and growth chart: treatment vs control, honestly.

Each paired run appends one history row. Past rows are never rewritten.
Deltas are treatment minus control. Early differences are noise; a
lasting lead needs many paired runs and a gain that traces to a change
the treatment arm chose itself.

The scoreboard lives at ``society/systems/twin_scoreboard.json`` on the
treatment tree (a shared artifact, not arm-specific state). The growth
chart is a static SVG in plaque colors (charcoal, bone, sage) for the
dashboard.

This module does not loosen the Oracle or any gate, and it never
authorizes.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from colony.arm import REPO_ROOT, control_root, control_is_seeded, fork_path

# Shared scoreboard: constructed without Path.__truediv__ so the control
# path hook cannot redirect it.
SCOREBOARD_PATH = Path(REPO_ROOT, "society", "systems", "twin_scoreboard.json")

# Plaque palette. No purple, neon, gold, or emoji.
CHARCOAL = "#1c1c1c"
BONE = "#eeeee6"
SAGE = "#b7c4b6"
SAGE_DIM = "#8a9a89"
BONE_DIM = "#b8b8b0"
GRID = "#3a3a38"

NUMERIC_FIELDS = (
    "oracle_passes",
    "oracle_kills",
    "verified_depth_sum",
    "beyond_published_count",
    "counterexamples",
    "proofs",
    "non_routine_proofs",
    "fitness",
    "novelty",
    "adopts",
    "reverts",
    "cycle_count",
)

NOISE_NOTE = (
    "Treatment is the self-modifying colony. Control runs the same "
    "pipeline with self-modification off, on a state tree forked from "
    "main and then evolved on its own. Differences in the first runs "
    "are noise. A lasting lead needs many paired runs, and a gain that "
    "traces to a change the treatment arm chose itself. This is not a "
    "claim of general intelligence or a breakthrough."
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _jsonl_last(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    last: dict[str, Any] | None = None
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    last = row
    except OSError:
        return None
    return last


def collect_arm_metrics(state_root: Path) -> dict[str, Any]:
    """Read one arm's metrics from its state root. Missing files become 0 / empty."""
    systems = Path(state_root) / "society" / "systems"
    data_dir = Path(state_root) / "data"
    oracle = _load(systems / "oracle.json") or {}
    oeis = _load(systems / "oeis_conjecture_state.json") or {}
    heal = _load(systems / "self_heal.json") or {}
    board = oeis.get("scoreboard") if isinstance(oeis.get("scoreboard"), dict) else {}
    extensions = board.get("extensions") if isinstance(board.get("extensions"), dict) else {}
    proofs = board.get("proofs") if isinstance(board.get("proofs"), dict) else {}
    counters = board.get("counterexamples") if isinstance(board.get("counterexamples"), dict) else {}

    depths: list[dict[str, Any]] = []
    depth_sum = 0
    beyond = 0
    for eid, rec in extensions.items():
        if not isinstance(rec, dict):
            continue
        try:
            to = int(rec.get("to") or 0)
        except (TypeError, ValueError):
            to = 0
        try:
            published = int(rec.get("bfile_hi") or 0)
        except (TypeError, ValueError):
            published = 0
        depth_sum += to
        is_beyond = to > published
        if is_beyond:
            beyond += 1
        depths.append({
            "id": eid,
            "anum": rec.get("anum"),
            "verified_depth": to,
            "published_hi": published,
            "beyond_published": is_beyond,
            "check": rec.get("check"),
        })
    depths.sort(key=lambda r: (-int(r.get("verified_depth") or 0), str(r.get("anum") or "")))

    routine = sum(1 for v in proofs.values() if isinstance(v, dict) and v.get("routine"))
    proofs_n = len(proofs)
    non_routine = proofs_n - routine

    fit_row = _jsonl_last(systems / "fitness_history.jsonl")
    if fit_row is None:
        # Fallback: society_state is large; only open if needed.
        state = _load(data_dir / "society_state.json") or {}
        hist = state.get("fitness_history") or []
        fit_row = hist[-1] if hist and isinstance(hist[-1], dict) else {}
        cycle_count = int(state.get("cycle_count") or 0)
    else:
        cycle_count = 0
        state = _load(data_dir / "society_state.json") or {}
        try:
            cycle_count = int(state.get("cycle_count") or 0)
        except (TypeError, ValueError):
            cycle_count = 0

    fitness = fit_row.get("aggregate") if isinstance(fit_row, dict) else None
    novelty = fit_row.get("novelty") if isinstance(fit_row, dict) else None
    try:
        fitness_v = float(fitness) if fitness is not None else None
    except (TypeError, ValueError):
        fitness_v = None
    try:
        novelty_v = float(novelty) if novelty is not None else None
    except (TypeError, ValueError):
        novelty_v = None

    adopts = int(heal.get("adopted_count") or 0)
    reverts = int(heal.get("reverted_count") or 0)
    frozen = bool(heal.get("frozen"))

    return {
        "oracle_passes": int(oracle.get("passes") or 0),
        "oracle_kills": int(oracle.get("kills") or 0),
        "verified_depth_sum": int(depth_sum),
        "beyond_published_count": int(beyond),
        "depths": depths,
        "counterexamples": int(len(counters)),
        "proofs": int(proofs_n),
        "non_routine_proofs": int(non_routine),
        "fitness": fitness_v,
        "novelty": novelty_v,
        "adopts": adopts,
        "reverts": reverts,
        "cycle_count": cycle_count,
        "self_heal_frozen": frozen,
        "self_heal_trial": (heal.get("trial") or {}).get("knob")
        if isinstance(heal.get("trial"), dict)
        else None,
    }


def _delta(treatment: dict[str, Any], control: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in NUMERIC_FIELDS:
        t, c = treatment.get(k), control.get(k)
        if t is None or c is None:
            out[k] = None
            continue
        try:
            d = float(t) - float(c)
        except (TypeError, ValueError):
            out[k] = None
            continue
        # Integers stay integers when both sides were ints (or int-valued).
        if isinstance(t, int) and isinstance(c, int) and k not in {"fitness", "novelty"}:
            out[k] = int(t) - int(c)
        else:
            out[k] = round(d, 6)
    return out


def empty_scoreboard(*, fork: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "version": 1,
        "note": NOISE_NOTE,
        "fork": fork or {},
        "updated_at": None,
        "paired_runs": 0,
        "treatment_cycles": 0,
        "control_cycles": 0,
        "treatment": {},
        "control": {},
        "delta": {},
        "history": [],
    }


def load_scoreboard(path: Path | None = None) -> dict[str, Any]:
    p = path or SCOREBOARD_PATH
    data = _load(p)
    if not data:
        return empty_scoreboard()
    data.setdefault("version", 1)
    data.setdefault("note", NOISE_NOTE)
    data.setdefault("history", [])
    data.setdefault("paired_runs", 0)
    return data


def _fork_info() -> dict[str, Any]:
    data = _load(fork_path()) or {}
    return {
        "fork_sha": data.get("fork_sha"),
        "fork_ts": data.get("fork_ts"),
        "seeded_sha": data.get("seeded_sha"),
        "seeded_ts": data.get("seeded_ts"),
        "fork_source": data.get("fork_source") or "origin/main",
        "control_seeded": control_is_seeded(),
    }


def _job_ok(result: str | None) -> bool:
    """A GitHub Actions job result of success (or an unset local result)."""
    if result is None or result == "":
        return True
    return str(result).strip().lower() == "success"


def _is_paired_row(row: Any) -> bool:
    """True for a history row that records a successful paired run.

    Legacy rows (no ``paired`` flag) count as paired unless they
    already marked the control as missing.
    """
    if not isinstance(row, dict):
        return False
    if row.get("paired") is False:
        return False
    if (row.get("control") or {}).get("missing"):
        return False
    return True


def paired_history(history: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """History rows that may contribute to a paired delta or chart series."""
    return [row for row in (history or []) if _is_paired_row(row)]


def update_scoreboard(
    *,
    treatment_root: Path | None = None,
    control_root_path: Path | None = None,
    path: Path | None = None,
    cycles_this_run: int | None = None,
    run_id: str | None = None,
    append: bool = True,
    treatment: dict[str, Any] | None = None,
    control: dict[str, Any] | None = None,
    treatment_result: str | None = None,
    control_result: str | None = None,
) -> dict[str, Any]:
    """Refresh latest snapshots from live state; optionally append history.

    Treatment metrics, cycle counts, and the current self-heal trial
    are always reread from disk, even when the control arm failed or
    is missing. A paired history row (and a treatment-minus-control
    delta) is recorded only when both arms succeeded and control is
    seeded. Existing history rows are copied through unchanged.
    """
    dest = path or SCOREBOARD_PATH
    board = load_scoreboard(dest)
    # Preserve recorded fork metadata; always refresh live fields so
    # a later seed or a voided trial is not stuck at the first write.
    fork = dict(board.get("fork") or {})
    live_fork = _fork_info()
    for k, v in live_fork.items():
        if k in {"control_seeded", "seeded_sha", "seeded_ts"}:
            fork[k] = v
        elif v and not fork.get(k):
            fork[k] = v
    if not fork:
        fork = live_fork

    t_root = Path(treatment_root) if treatment_root is not None else REPO_ROOT
    c_root = Path(control_root_path) if control_root_path is not None else control_root()

    t = treatment if treatment is not None else collect_arm_metrics(t_root)

    control_seeded = control_is_seeded(c_root)
    control_tree = (c_root / "society").exists() or (
        c_root / "data" / "society_state.json"
    ).is_file()
    control_job_ok = _job_ok(control_result)
    treatment_job_ok = _job_ok(treatment_result)

    if control is not None:
        c = dict(control)
    elif control_seeded or control_tree:
        c = collect_arm_metrics(c_root)
    else:
        c = _empty_metrics()

    control_missing = bool(c.get("missing")) or (not control_seeded and not control_tree)
    if not control_job_ok:
        control_missing = True
    if control_missing:
        c = dict(c)
        c["missing"] = True
        if not control_job_ok:
            c["result"] = str(control_result)
        if not control_seeded:
            c["seed_failed"] = not control_tree
            c.setdefault("result", c.get("result") or "unseeded")

    paired = bool(
        treatment_job_ok
        and control_job_ok
        and not control_missing
        and control_seeded
    )
    # Paired deltas only count runs where both arms succeeded.
    delta = _delta(t, c) if paired else {}

    # History is a new list; old rows are not mutated.
    history = [dict(row) for row in (board.get("history") or [])]
    if append:
        row = {
            "ts": _utc(),
            "run_id": run_id or os.environ.get("GITHUB_RUN_ID") or "",
            "cycles_this_run": cycles_this_run,
            "paired": paired,
            "treatment_result": treatment_result,
            "control_result": control_result,
            "treatment": {k: t.get(k) for k in (*NUMERIC_FIELDS, "self_heal_frozen", "self_heal_trial")},
            "control": {k: c.get(k) for k in (*NUMERIC_FIELDS, "self_heal_frozen", "self_heal_trial", "missing")},
            "delta": delta if paired else {},
            "treatment_cycles": t.get("cycle_count"),
            "control_cycles": 0 if control_missing else c.get("cycle_count"),
        }
        history.append(row)

    paired_runs = sum(1 for row in history if _is_paired_row(row))

    # Top-level delta is only for a paired run. A failed or missing
    # control does not invent a treatment-minus-control lead.
    board = {
        "version": 1,
        "note": NOISE_NOTE,
        "fork": fork,
        "updated_at": _utc(),
        "paired_runs": paired_runs,
        "treatment_cycles": t.get("cycle_count") or 0,
        "control_cycles": (c.get("cycle_count") or 0) if (control_seeded and not control_missing) else 0,
        "treatment": t,
        "control": c,
        "delta": delta if paired else {},
        "last_paired": paired,
        "treatment_result": treatment_result,
        "control_result": control_result,
        "history": history,
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(board, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return board


def _empty_metrics() -> dict[str, Any]:
    return {
        "oracle_passes": 0,
        "oracle_kills": 0,
        "verified_depth_sum": 0,
        "beyond_published_count": 0,
        "depths": [],
        "counterexamples": 0,
        "proofs": 0,
        "non_routine_proofs": 0,
        "fitness": None,
        "novelty": None,
        "adopts": 0,
        "reverts": 0,
        "cycle_count": 0,
        "self_heal_frozen": True,
        "self_heal_trial": None,
        "missing": True,
    }


def _svg_series(history: list[dict[str, Any]], arm: str, field: str) -> list[tuple[int, float]]:
    pts: list[tuple[int, float]] = []
    for i, row in enumerate(history, start=1):
        side = row.get(arm) or {}
        v = side.get(field)
        if v is None:
            continue
        try:
            pts.append((i, float(v)))
        except (TypeError, ValueError):
            continue
    return pts


def _poly(pts: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)


def _chart_panel(
    *,
    title: str,
    history: list[dict[str, Any]],
    field: str,
    x: float,
    y: float,
    w: float,
    h: float,
) -> str:
    pad_l, pad_r, pad_t, pad_b = 44, 12, 24, 28
    inner_w = w - pad_l - pad_r
    inner_h = h - pad_t - pad_b
    t_pts = _svg_series(history, "treatment", field)
    c_pts = _svg_series(history, "control", field)
    vals = [v for _, v in t_pts + c_pts]
    n = max(len(history), 1)
    ymin = 0.0
    ymax = max(vals) if vals else 1.0
    if ymax <= ymin:
        ymax = ymin + 1.0
    # A little headroom.
    span = ymax - ymin
    ymax = ymax + span * 0.08

    def xy(i: int, v: float) -> tuple[float, float]:
        # i is 1-based run index.
        px = x + pad_l + (0 if n <= 1 else (i - 1) / (n - 1) * inner_w)
        py = y + pad_t + (1 - (v - ymin) / (ymax - ymin)) * inner_h
        return px, py

    # Grid and y labels (4 ticks).
    grid = []
    for t in range(5):
        frac = t / 4
        gy = y + pad_t + (1 - frac) * inner_h
        val = ymin + frac * (ymax - ymin)
        label = _fmt_tick(val, field)
        grid.append(
            f'<line x1="{x+pad_l:.1f}" y1="{gy:.1f}" x2="{x+w-pad_r:.1f}" y2="{gy:.1f}" '
            f'stroke="{GRID}" stroke-width="0.6"/>'
            f'<text x="{x+pad_l-6:.1f}" y="{gy+3:.1f}" fill="{BONE_DIM}" '
            f'font-size="9" text-anchor="end" font-family="ui-sans-serif, system-ui, sans-serif">{label}</text>'
        )

    def polyline(pts: list[tuple[int, float]], color: str, dash: str = "") -> str:
        if not pts:
            return ""
        mapped = [xy(i, v) for i, v in pts]
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        dots = "".join(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2.4" fill="{color}"/>'
            for px, py in mapped
        )
        if len(mapped) == 1:
            return dots
        return (
            f'<polyline fill="none" stroke="{color}" stroke-width="1.8" '
            f'stroke-linejoin="round" stroke-linecap="round"{dash_attr} '
            f'points="{_poly(mapped)}"/>' + dots
        )

    # X labels: first, middle, last run.
    xlabels = []
    if history:
        ticks = {1, len(history)}
        if len(history) >= 3:
            ticks.add((1 + len(history)) // 2)
        for i in sorted(ticks):
            px, _ = xy(i, ymin)
            xlabels.append(
                f'<text x="{px:.1f}" y="{y+h-8:.1f}" fill="{BONE_DIM}" font-size="9" '
                f'text-anchor="middle" font-family="ui-sans-serif, system-ui, sans-serif">run {i}</text>'
            )

    return f"""
  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="#141414" stroke="{GRID}" stroke-width="0.8"/>
  <text x="{x+pad_l}" y="{y+16}" fill="{BONE}" font-size="12" font-family="ui-sans-serif, system-ui, sans-serif">{title}</text>
  {''.join(grid)}
  {polyline(c_pts, BONE, "4 3")}
  {polyline(t_pts, SAGE)}
  {''.join(xlabels)}
"""


def _fmt_tick(v: float, field: str) -> str:
    if field in {"fitness", "novelty"}:
        return f"{v:.2f}"
    if abs(v) >= 10000:
        return f"{v:.0f}"
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.1f}"


def growth_chart_svg(board: dict[str, Any] | None = None) -> str:
    """Static plaque-style SVG: treatment (sage, solid) vs control (bone, dashed)."""
    b = board if board is not None else load_scoreboard()
    # Only paired runs belong on the comparison chart.
    history = paired_history(list(b.get("history") or []))
    width, height = 860, 620
    panel_h = 170
    gap = 16
    top = 58
    panels = [
        ("Oracle passes", "oracle_passes"),
        ("Total verified depth", "verified_depth_sum"),
        ("Cumulative adopts", "adopts"),
    ]
    body = []
    for i, (title, field) in enumerate(panels):
        body.append(
            _chart_panel(
                title=title,
                history=history,
                field=field,
                x=16,
                y=top + i * (panel_h + gap),
                w=width - 32,
                h=panel_h,
            )
        )
    empty = ""
    if not history:
        empty = (
            f'<text x="{width/2}" y="{top+panel_h}" fill="{BONE_DIM}" font-size="13" '
            f'text-anchor="middle" font-family="ui-sans-serif, system-ui, sans-serif">'
            f"No paired runs yet. Both arms start from the same snapshot; "
            f"early differences are noise.</text>"
        )
    t_cyc = b.get("treatment_cycles") or 0
    c_cyc = b.get("control_cycles") or 0
    runs = b.get("paired_runs") or len(history)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="Treatment versus control growth chart">
  <title>Treatment vs control: Oracle passes, verified depth, and adopts</title>
  <rect width="{width}" height="{height}" fill="{CHARCOAL}"/>
  <text x="16" y="24" fill="{BONE}" font-size="16" font-family="ui-sans-serif, system-ui, sans-serif">Treatment vs control</text>
  <text x="16" y="42" fill="{BONE_DIM}" font-size="11" font-family="ui-sans-serif, system-ui, sans-serif">Paired runs {runs} · treatment cycles {t_cyc} · control cycles {c_cyc} · early differences are noise</text>
  <g>
    <line x1="620" y1="18" x2="650" y2="18" stroke="{SAGE}" stroke-width="1.8"/>
    <text x="656" y="22" fill="{BONE}" font-size="11" font-family="ui-sans-serif, system-ui, sans-serif">treatment</text>
    <line x1="740" y1="18" x2="770" y2="18" stroke="{BONE}" stroke-width="1.8" stroke-dasharray="4 3"/>
    <text x="776" y="22" fill="{BONE}" font-size="11" font-family="ui-sans-serif, system-ui, sans-serif">control</text>
  </g>
  {''.join(body)}
  {empty}
</svg>
"""


def dashboard_section(board: dict[str, Any] | None = None) -> str:
    """HTML section for the existing dashboard, plaque-styled and self-contained."""
    from html import escape

    b = board if board is not None else load_scoreboard()
    svg = growth_chart_svg(b)
    t = b.get("treatment") or {}
    c = b.get("control") or {}
    d = b.get("delta") or {}
    seeded = (b.get("fork") or {}).get("control_seeded")
    if not t and not c and not (b.get("history") or []):
        status = "No paired run has been recorded yet."
    elif not (c or seeded) and not c.get("cycle_count"):
        status = "Control has not been seeded yet. The next evolve run with the control job will take the snapshot."
    else:
        status = (
            f"Latest: Oracle passes {t.get('oracle_passes', '—')} vs {c.get('oracle_passes', '—')} "
            f"(Δ { _fmt_delta(d.get('oracle_passes')) }); "
            f"verified depth sum {t.get('verified_depth_sum', '—')} vs {c.get('verified_depth_sum', '—')} "
            f"(Δ { _fmt_delta(d.get('verified_depth_sum')) }); "
            f"adopts {t.get('adopts', '—')} vs {c.get('adopts', '—')} "
            f"(Δ { _fmt_delta(d.get('adopts')) })."
        )
    return f"""
  <h2>Treatment vs control</h2>
  <p>{escape(NOISE_NOTE)}</p>
  <p>{escape(status)}</p>
  <div class="twin-plaque">
    {svg}
  </div>
  <style>
    .twin-plaque {{
      background: {CHARCOAL};
      color: {BONE};
      border-radius: 12px;
      padding: 8px 4px 4px;
      border: 1px solid {GRID};
      overflow: auto;
    }}
    .twin-plaque svg {{ width: 100%; height: auto; display: block; }}
  </style>
"""


def _fmt_delta(v: Any) -> str:
    if v is None:
        return "—"
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "—"
    if n == int(n):
        n = int(n)
        return f"{n:+d}"
    return f"{n:+.4f}"


def format_visibility(board: dict[str, Any] | None = None) -> str:
    b = board if board is not None else load_scoreboard()
    d = b.get("delta") or {}
    return (
        f"paired_runs {b.get('paired_runs') or 0}; "
        f"Δpasses {_fmt_delta(d.get('oracle_passes'))}; "
        f"Δdepth {_fmt_delta(d.get('verified_depth_sum'))}; "
        f"Δadopts {_fmt_delta(d.get('adopts'))} "
        f"(early differences are noise)"
    )
