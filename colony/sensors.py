"""Internal sensors — structured signals from the colony's own history.

Read-only over existing logs (fitness history, conjecture history, bench history,
lessons, feed cache/state); writes one snapshot ``society/systems/sensors.json`` per
cycle. Spark priors, seek and the authoring desk read the snapshot. Sensors only
*inform*: they never accept, enable, authorize or change a gate. Fail-soft: any
missing source yields an empty section, never an exception.

Signals:
- lemma_streaks   — per-mutation current keep/revert/skip streak (conjecture history)
                    + Oracle kill counts per theme (lessons)
- trends          — least-squares slope + last value of aggregate / novelty / kill_rate /
                    lesson_uptake over the recent fitness window
- stall           — aggregate flat AND novelty flat at 0 over the window
- catalog         — enabled / disabled / authored checks; recent "catalog exhausted" count
- guides          — number of human guides + which guide-driven behaviours are active
- ci_health       — recent GitHub Actions run conclusions (fetched by colony.feeds in CI)
- bench_timing    — per-bench recent vs baseline seconds ratio (drift flag)
- feeds           — rows per source/kind and last fetch health
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FITNESS_HISTORY = ROOT / "society" / "systems" / "fitness_history.jsonl"
CONJECTURE_HISTORY = ROOT / "society" / "benchmarks" / "conjecture_history.jsonl"
BENCH_HISTORY = ROOT / "society" / "benchmarks" / "history.jsonl"
SENSORS_JSON = ROOT / "society" / "systems" / "sensors.json"

TREND_WINDOW = 12
STALL_WINDOW = 6
STALL_AGG_RANGE = 0.006
DRIFT_RATIO = 1.5
STREAK_ALERT = 2


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tail_jsonl(path: Path, n: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-n:]
    except Exception:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def _slope(ys: list[float]) -> float:
    n = len(ys)
    if n < 2:
        return 0.0
    mx = (n - 1) / 2
    my = sum(ys) / n
    den = sum((i - mx) ** 2 for i in range(n))
    return round(sum((i - mx) * (y - my) for i, y in enumerate(ys)) / den, 6) if den else 0.0


def lemma_streaks(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = rows if rows is not None else _tail_jsonl(CONJECTURE_HISTORY, 200)
    seqs: dict[str, list[str]] = {}
    for r in rows:
        m = str(r.get("mutation") or "")
        d = str(r.get("decision") or "")
        if m and d:
            seqs.setdefault(m, []).append(d)
    streaks = {}
    for m, ds in seqs.items():
        last = ds[-1]
        k = 0
        for d in reversed(ds):
            if d != last:
                break
            k += 1
        streaks[m] = {"last": last, "streak": k, "n": len(ds),
                      "keeps": ds.count("keep"), "reverts": ds.count("revert")}
    kills: dict[str, int] = {}
    try:
        from colony.lessons import oracle_kill_theme_counts
        kills = dict(sorted(oracle_kill_theme_counts().items(), key=lambda kv: -kv[1])[:12])
    except Exception:
        pass
    revert_streaks = sorted([m for m, s in streaks.items() if s["last"] == "revert" and s["streak"] >= STREAK_ALERT])
    return {"by_mutation": streaks, "revert_streaks": revert_streaks, "oracle_kills_by_theme": kills}


def trends(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = rows if rows is not None else _tail_jsonl(FITNESS_HISTORY, TREND_WINDOW)
    out: dict[str, Any] = {"n": len(rows)}
    for key in ("aggregate", "novelty", "kill_rate", "lesson_uptake"):
        ys = [float(r[key]) for r in rows if isinstance(r.get(key), (int, float))]
        if ys:
            out[key] = {"last": round(ys[-1], 4), "slope": _slope(ys), "min": round(min(ys), 4), "max": round(max(ys), 4)}
    return out


def stall(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = rows if rows is not None else _tail_jsonl(FITNESS_HISTORY, STALL_WINDOW)
    rows = rows[-STALL_WINDOW:]
    if len(rows) < STALL_WINDOW:
        return {"stalled": False, "reason": "insufficient_history", "window": len(rows)}
    agg = [float(r.get("aggregate") or 0) for r in rows]
    nov = [float(r.get("novelty") or 0) for r in rows]
    flat = (max(agg) - min(agg)) < STALL_AGG_RANGE
    nov_zero = max(nov) <= 0.0
    return {"stalled": bool(flat and nov_zero), "aggregate_range": round(max(agg) - min(agg), 4),
            "novelty_max": round(max(nov), 4), "window": STALL_WINDOW,
            "reason": "aggregate flat and novelty 0" if (flat and nov_zero) else "moving"}


def catalog() -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        import ast
        from colony.authoring import _entries, _lemma_impl, AUTHORED_PREFIX
        tree = ast.parse(_lemma_impl().read_text(encoding="utf-8"))
        ents = _entries(tree)
        out = {"enabled": sum(1 for _n, _c, f in ents if f is True),
               "disabled": sorted(n for n, _c, f in ents if f is False),
               "authored": sorted(n for n, _c, _f in ents if n.startswith(AUTHORED_PREFIX))}
    except Exception:
        pass
    recent = _tail_jsonl(CONJECTURE_HISTORY, 10)
    out["exhausted_recent"] = sum(1 for r in recent if "exhausted" in str(r.get("note") or ""))
    return out


def guides() -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        from colony import lessons as L
        out["n_guides"] = len(L.load_human_guides())
        active = {}
        for fn in ("guide_process_spam_avoided", "guide_prefers_invariant_chains",
                   "guide_requires_chain_cites", "guide_seeks_unenabled_variants"):
            try:
                active[fn.replace("guide_", "")] = bool(getattr(L, fn)())
            except Exception:
                active[fn.replace("guide_", "")] = None
        try:
            from colony.authoring import guide_authoring_active
            active["authoring_active"] = bool(guide_authoring_active())
        except Exception:
            active["authoring_active"] = None
        out["active"] = active
    except Exception:
        pass
    return out


def bench_timing(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = rows if rows is not None else _tail_jsonl(BENCH_HISTORY, 30)
    series: dict[str, list[float]] = {}
    for r in rows:
        for b in r.get("benches") or []:
            s = b.get("seconds")
            if isinstance(s, (int, float)) and b.get("bench"):
                series.setdefault(b["bench"], []).append(float(s))
    out: dict[str, Any] = {}
    for name, xs in series.items():
        if len(xs) < 8:
            continue
        recent, base = xs[-5:], xs[:-5]
        rb = sum(base) / len(base)
        ratio = (sum(recent) / len(recent)) / rb if rb > 0 else 1.0
        out[name] = {"ratio": round(ratio, 3), "drift": ratio > DRIFT_RATIO}
    return out


def ci_and_feeds() -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        from colony import feeds as Fd
        st = Fd.load_state()
        ci = st.get("ci_health") or {}
        ci_out = {"success_rate": ci.get("success_rate"), "completed": ci.get("completed"),
                  "last": [(r.get("conclusion"), r.get("created_at")) for r in (ci.get("runs") or [])[:3]],
                  "fetched_at": ci.get("fetched_at")}
        fd = Fd.counts()
        fd["last_run"] = st.get("last_run")
        fd["health"] = st.get("health")
        return ci_out, fd
    except Exception:
        return {}, {}


def signals(snap: dict[str, Any]) -> list[str]:
    """Short human-readable signals (priors for spark/seek; not commands)."""
    sig: list[str] = []
    st = snap.get("stall") or {}
    if st.get("stalled"):
        sig.append(f"stall: aggregate flat ({st.get('aggregate_range')}) and novelty 0 for {st.get('window')} cycles "
                   f"→ seek fresh feed themes / author feed-confirmed checks")
    rs = (snap.get("lemma_streaks") or {}).get("revert_streaks") or []
    if rs:
        sig.append(f"revert_streaks: {', '.join(rs[:4])} → deprioritize in seek")
    fd = snap.get("feeds") or {}
    n_seq = (fd.get("by_kind") or {}).get("sequence", 0)
    if n_seq:
        sig.append(f"feeds: {n_seq} OEIS sequence(s) cached → candidate cross-checks for authored checks")
    drift = [k for k, v in (snap.get("bench_timing") or {}).items() if v.get("drift")]
    if drift:
        sig.append(f"bench_timing_drift: {', '.join(drift)}")
    ci = snap.get("ci_health") or {}
    if isinstance(ci.get("success_rate"), (int, float)) and ci["success_rate"] < 0.8:
        sig.append(f"ci_health: success_rate {ci['success_rate']} → be conservative")
    return sig


def compute(cycle_id: str = "") -> dict[str, Any]:
    snap: dict[str, Any] = {"ts": _utc(), "cycle_id": cycle_id}
    for key, fn in (("lemma_streaks", lemma_streaks), ("trends", trends), ("stall", stall),
                    ("catalog", catalog), ("guides", guides), ("bench_timing", bench_timing)):
        try:
            snap[key] = fn()
        except Exception as e:  # noqa: BLE001
            snap[key] = {"error": f"{type(e).__name__}"}
    snap["ci_health"], snap["feeds"] = ci_and_feeds()
    snap["signals"] = signals(snap)
    snap["note"] = "Sensors inform priors only; they never accept, enable, authorize or change a gate."
    return snap


def refresh(cycle_id: str = "", *, write: bool = True) -> dict[str, Any]:
    snap = compute(cycle_id)
    if write:
        try:
            SENSORS_JSON.parent.mkdir(parents=True, exist_ok=True)
            # keep the file small: drop the full per-mutation table, keep alerts
            slim = json.loads(json.dumps(snap))
            ls = slim.get("lemma_streaks") or {}
            by = ls.pop("by_mutation", {}) or {}
            ls["recent"] = dict(list(by.items())[-12:])
            SENSORS_JSON.write_text(json.dumps(slim, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception:
            pass
    return snap


def latest() -> dict[str, Any]:
    try:
        return json.loads(SENSORS_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}


def revert_streak_names() -> set[str]:
    return set(((latest().get("lemma_streaks") or {}).get("revert_streaks") or []))
