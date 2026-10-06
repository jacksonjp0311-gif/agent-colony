"""Agent-queryable telemetry — internal colony + external environment.

Every agent can gather/query during debate/decision-making (not human-only logs).
Persists snapshots agents read mid-cycle. Hooks: bus + society.
Not AGI.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TELEM_DIR = ROOT / "data" / "commons" / "telemetry"
SNAPSHOT = ROOT / "society" / "systems" / "telemetry.json"
TELEM_LOG = ROOT / "data" / "commons" / "telemetry.jsonl"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_oracle_counts() -> dict[str, Any]:
    try:
        from colony.oracle import counts as oracle_counts

        return dict(oracle_counts())
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "passes": 0, "kills": 0, "easy_pad_kills": 0, "total": 0}


def _authorize_rates(root: Path = ROOT) -> dict[str, Any]:
    """Scan recent authorize receipts + AUTHORIZE_STATUS for accept/reject rates."""
    status_path = root / "society" / "AUTHORIZE_STATUS.json"
    accepted = rejected = skipped = 0
    p_min = None
    if status_path.exists():
        try:
            d = json.loads(status_path.read_text(encoding="utf-8"))
            accepted = int(d.get("accepted") or d.get("n_accepted") or 0)
            rejected = int(d.get("rejected") or d.get("n_rejected") or 0)
            skipped = int(d.get("skipped") or d.get("n_skipped") or 0)
            p_min = d.get("P_min") or d.get("p_min")
        except json.JSONDecodeError:
            pass
    # Also tally from slim spark/spark2 receipts if present
    for name in ("SOCIETY_SLIM_SPARK.json", "SOCIETY_SLIM_SPARK2.json", "SOCIETY_SLIM_TELEMETRY.json"):
        p = root / "society" / "receipts" / name
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            auth = d.get("authorize") or {}
            if auth:
                accepted = int(auth.get("accepted") or accepted)
                rejected = int(auth.get("rejected") or rejected)
                skipped = int(auth.get("skipped") or skipped)
                p_min = auth.get("P_min", p_min)
        except json.JSONDecodeError:
            pass
    total = accepted + rejected
    return {
        "accepted": accepted,
        "rejected": rejected,
        "skipped": skipped,
        "accept_rate": round(accepted / total, 4) if total else None,
        "reject_rate": round(rejected / total, 4) if total else None,
        "P_min": p_min,
        "never_accept_all": True,
    }


def _genome_bias_drift(state: dict[str, Any]) -> dict[str, Any]:
    agents = state.get("agents") or {}
    drifts: dict[str, Any] = {}
    for role, ag in agents.items():
        if not isinstance(ag, dict):
            continue
        genome = ag.get("genome") or {}
        traits = genome.get("traits") if isinstance(genome, dict) else None
        if not isinstance(traits, dict):
            continue
        # drift proxy: variance from 0.5 + mutated_keys count
        vals = [float(v) for v in traits.values() if isinstance(v, (int, float))]
        mean = sum(vals) / len(vals) if vals else 0.5
        var = sum((v - mean) ** 2 for v in vals) / len(vals) if vals else 0.0
        drifts[role] = {
            "trait_mean": round(mean, 4),
            "trait_var": round(var, 4),
            "mutated_keys": list(genome.get("mutated_keys") or []),
            "generation": genome.get("generation"),
        }
    return drifts


def _cycle_deltas(state: dict[str, Any]) -> dict[str, Any]:
    hist = state.get("fitness_history") or []
    if len(hist) < 2:
        return {"n": len(hist), "delta_aggregate": None, "before": None, "after": None}
    a, b = hist[-2], hist[-1]
    ag_a = float(a.get("aggregate") or 0) if isinstance(a, dict) else None
    ag_b = float(b.get("aggregate") or 0) if isinstance(b, dict) else None
    delta = round(ag_b - ag_a, 4) if ag_a is not None and ag_b is not None else None
    return {
        "n": len(hist),
        "delta_aggregate": delta,
        "before": {"cycle_id": a.get("cycle_id"), "aggregate": ag_a} if isinstance(a, dict) else None,
        "after": {"cycle_id": b.get("cycle_id"), "aggregate": ag_b} if isinstance(b, dict) else None,
    }


def _external_env() -> dict[str, Any]:
    """Process/box resource + latency probes agents can observe."""
    t0 = time.perf_counter()
    # cheap latency self-probe
    try:
        load = os.getloadavg()
    except (AttributeError, OSError):
        load = (None, None, None)
    try:
        import resource

        ru = resource.getrusage(resource.RUSAGE_SELF)
        rss_kb = getattr(ru, "ru_maxrss", None)
        utime = getattr(ru, "ru_utime", None)
    except Exception:  # noqa: BLE001
        rss_kb = None
        utime = None
    latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)
    # disk free on workspace
    try:
        st = os.statvfs(str(ROOT))
        free_mb = round((st.f_bavail * st.f_frsize) / (1024 * 1024), 1)
    except Exception:  # noqa: BLE001
        free_mb = None
    return {
        "loadavg": list(load),
        "rss_kb": rss_kb,
        "user_time_s": utime,
        "probe_latency_ms": latency_ms,
        "disk_free_mb": free_mb,
        "pid": os.getpid(),
        "ts": _utc(),
    }


def gather_internal(state: dict[str, Any] | None = None, bus: Any | None = None) -> dict[str, Any]:
    """Internal colony telemetry snapshot."""
    if state is None:
        sp = ROOT / "data" / "society_state.json"
        state = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    fit_hist = state.get("fitness_history") or []
    fit_latest = fit_hist[-1] if fit_hist else None
    bus_metrics = {}
    if bus is not None and hasattr(bus, "inner_bus_metrics"):
        try:
            bus_metrics = bus.inner_bus_metrics()
        except Exception:  # noqa: BLE001
            bus_metrics = {}
    if not bus_metrics:
        bus_metrics = state.get("bus_metrics_latest") or {}
        if not bus_metrics and isinstance(state.get("bus"), dict):
            stats = state["bus"].get("stats") or {}
            posted = int(stats.get("posted") or 0)
            replied = int(stats.get("replied") or 0)
            bus_metrics = {
                "reply_rate": round(replied / posted, 4) if posted else None,
                "stats": stats,
            }
    oracle = _safe_oracle_counts()
    auth = _authorize_rates()
    return {
        "fitness_latest": fit_latest,
        "fitness_aggregate": (fit_latest or {}).get("aggregate") if isinstance(fit_latest, dict) else None,
        "reply_rate": bus_metrics.get("reply_rate") or (fit_latest or {}).get("comm_reply_rate"),
        "bus_metrics": bus_metrics,
        "oracle": oracle,
        "authorize": auth,
        "genome_bias_drift": _genome_bias_drift(state),
        "cycle_deltas": _cycle_deltas(state),
        "cycle_count": state.get("cycle_count"),
        "population": state.get("population"),
        "ts": _utc(),
    }


def gather_external_signals() -> dict[str, Any]:
    """External environment + EXTERNAL ARRAY feeds."""
    env = _external_env()
    array = {}
    patterns = []
    try:
        from colony.external_array import query_external

        array = query_external(refresh=False)
        patterns = list(array.get("cross_domain_patterns") or [])
    except Exception as exc:  # noqa: BLE001
        array = {"error": str(exc)}
    residuals = {}
    try:
        from colony.residuals import query_residuals

        residuals = query_residuals()
    except Exception as exc:  # noqa: BLE001
        residuals = {"error": str(exc)}
    revisions = {}
    try:
        from colony.time_revision import revision_stats

        revisions = revision_stats()
    except Exception as exc:  # noqa: BLE001
        revisions = {"error": str(exc)}
    actuation = {}
    try:
        from colony.actuation import actuation_stats

        actuation = actuation_stats()
    except Exception as exc:  # noqa: BLE001
        actuation = {"error": str(exc)}
    return {
        "resource_usage": env,
        "external_array": {
            "ts": array.get("ts"),
            "feed_ok": {
                k: bool((array.get("feeds") or {}).get(k, {}).get("ok"))
                for k in ("arxiv", "nasa_donki_solar", "global_weather")  # noaa quarantined Phase 4
            }
            if isinstance(array, dict)
            else {},
            "pattern_kinds": [p.get("kind") for p in patterns],
            "patterns": patterns[:4],
        },
        "residuals_summary": {
            "n_agents": len((residuals.get("agents") or {})),
            "n_conflicts": len(residuals.get("conflicts") or []),
            "high_residual": residuals.get("high_residual"),
            "stats": residuals.get("stats"),
        }
        if isinstance(residuals, dict)
        else residuals,
        "time_revision": revisions,
        "actuation": {
            "total_actions": actuation.get("total_actions"),
            "successes": actuation.get("successes"),
            "failures": actuation.get("failures"),
            "gated_blocked": actuation.get("gated_blocked"),
            "success_rate": actuation.get("success_rate"),
            "by_kind": actuation.get("by_kind"),
            "examples": (actuation.get("examples") or [])[-3:],
        }
        if isinstance(actuation, dict)
        else actuation,
        "error_rates": {
            "external_array_errors": 1 if array.get("error") else 0,
            "feed_fail_count": sum(
                1
                for k in ("arxiv", "nasa_donki_solar", "global_weather")  # noaa quarantined Phase 4
                if not bool(((array.get("feeds") or {}).get(k) or {}).get("ok"))
            )
            if isinstance(array, dict) and array.get("feeds")
            else None,
        },
        "ts": _utc(),
    }


def snapshot(
    state: dict[str, Any] | None = None,
    bus: Any | None = None,
    *,
    refresh_external_array: bool = False,
) -> dict[str, Any]:
    """Persist full telemetry snapshot; return agent-readable dict."""
    if refresh_external_array:
        try:
            from colony.external_array import gather_external_array

            gather_external_array(force=True)
        except Exception:
            pass
    internal = gather_internal(state, bus)
    external = gather_external_signals()
    snap = {
        "ts": _utc(),
        "version": 1,
        "mile": "spark2_telemetry",
        "internal": internal,
        "external": external,
        "note": (
            "Agent-queryable telemetry. Internal colony metrics + external env/array/residuals. "
            "Query via colony.telemetry.query during debate. Not AGI."
        ),
        "non_claims": ["not_AGI", "not_consciousness", "not_Millennium"],
    }
    TELEM_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (TELEM_DIR / f"snap_{_utc().replace(':','').replace('-','')}.json").write_text(
        json.dumps(snap, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    # keep only last 30 mid-cycle snaps
    snaps = sorted(TELEM_DIR.glob("snap_*.json"))
    for old in snaps[:-30]:
        try:
            old.unlink()
        except OSError:
            pass
    with TELEM_LOG.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": snap["ts"],
                    "fitness": internal.get("fitness_aggregate"),
                    "reply_rate": internal.get("reply_rate"),
                    "oracle": internal.get("oracle"),
                    "authorize": internal.get("authorize"),
                    "cycle_delta": (internal.get("cycle_deltas") or {}).get("delta_aggregate"),
                    "patterns": (external.get("external_array") or {}).get("pattern_kinds"),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    return snap


def query(
    *,
    section: str | None = None,
    state: dict[str, Any] | None = None,
    bus: Any | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Agent API — every agent calls this mid-debate / decision.

    section: None | 'internal' | 'external' | 'oracle' | 'authorize' | 'patterns' | 'residuals'
    """
    if refresh or not SNAPSHOT.exists():
        snap = snapshot(state, bus, refresh_external_array=refresh)
    else:
        try:
            snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            snap = snapshot(state, bus)
    if not section:
        return snap
    if section == "internal":
        return snap.get("internal") or {}
    if section == "external":
        return snap.get("external") or {}
    if section == "oracle":
        return (snap.get("internal") or {}).get("oracle") or {}
    if section == "authorize":
        return (snap.get("internal") or {}).get("authorize") or {}
    if section == "patterns":
        return (snap.get("external") or {}).get("external_array") or {}
    if section == "residuals":
        return (snap.get("external") or {}).get("residuals_summary") or {}
    return snap


# Bus/society hook helpers
def attach_to_state(state: dict[str, Any], bus: Any | None = None) -> dict[str, Any]:
    snap = snapshot(state, bus)
    state["telemetry_latest"] = {
        "ts": snap["ts"],
        "fitness": (snap.get("internal") or {}).get("fitness_aggregate"),
        "reply_rate": (snap.get("internal") or {}).get("reply_rate"),
        "oracle": (snap.get("internal") or {}).get("oracle"),
        "authorize": (snap.get("internal") or {}).get("authorize"),
    }
    return snap
