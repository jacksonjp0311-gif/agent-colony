"""PulseMesh feed collectors — ported into agent-colony EXTERNAL ARRAY.

Collectors: arXiv (via external_array), NASA DONKI, NOAA Kp, Open-Meteo,
plus PulseMesh live API / system-stat / TCP probe collectors.

Agent-queryable. Correlations = debate input only (not discovery claims).
Adapted from jacksonjp0311-gif/PulseMesh (providers + local) — slim, no vendor tree.
Not AGI. Not novel physics.
"""
from __future__ import annotations

import json
import math
import os
import platform
import shutil
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "commons" / "external_array" / "pulsemesh"
SNAPSHOT = ROOT / "society" / "systems" / "pulsemesh_feeds.json"
LOG = ROOT / "data" / "commons" / "pulsemesh_feeds.jsonl"

UA = "agent-colony/spark3-port PulseMesh-feeds (research; contact=james; not-agi)"
TIMEOUT = 12.0


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _http_get(
    url: str,
    *,
    accept: str = "application/json",
    retries: int = 3,
) -> tuple[bool, Any, str]:
    """GET with bounded retries/backoff on 429/503 so rate limits degrade softly."""
    last_note = "no_attempt"
    for attempt in range(max(1, retries)):
        req = urllib.request.Request(
            url,
            headers={"User-Agent": UA, "Accept": accept},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read()
                ctype = (resp.headers.get("Content-Type") or "").lower()
                if "json" in ctype or accept.endswith("json"):
                    try:
                        return True, json.loads(raw.decode("utf-8", errors="replace")), "ok"
                    except json.JSONDecodeError:
                        return True, raw.decode("utf-8", errors="replace")[:4000], "ok_text"
                return True, raw.decode("utf-8", errors="replace")[:4000], "ok_text"
        except urllib.error.HTTPError as exc:
            last_note = f"HTTPError: HTTP Error {exc.code}: {exc.reason}"
            if exc.code in (429, 503) and attempt < retries - 1:
                ra = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    delay = float(ra) if ra is not None else (1.25 * (2 ** attempt))
                except (TypeError, ValueError):
                    delay = 1.25 * (2 ** attempt)
                time.sleep(min(max(delay, 0.5), 20.0))
                continue
            return False, None, last_note
        except Exception as exc:  # noqa: BLE001
            return False, None, f"{type(exc).__name__}: {exc}"
    return False, None, last_note


# In-cycle / short-TTL memo so gather_external_array + gather_pulsemesh do not
# double-hit Open-Meteo within the same evolve cycle.
_OPENMETEO_MEM: dict[str, Any] | None = None
_OPENMETEO_MEM_TS: float = 0.0
_OPENMETEO_TTL_S = 90.0
_OPENMETEO_LAST_GOOD = CACHE_DIR / "openmeteo_last_good.json"
_OPENMETEO_MIN_INTERVAL_S = 1.25
_OPENMETEO_LAST_REQ_TS: float = 0.0


def _openmeteo_rate_limit() -> None:
    global _OPENMETEO_LAST_REQ_TS
    now = time.monotonic()
    wait = _OPENMETEO_MIN_INTERVAL_S - (now - _OPENMETEO_LAST_REQ_TS)
    if wait > 0:
        time.sleep(wait)
    _OPENMETEO_LAST_REQ_TS = time.monotonic()


def _load_openmeteo_last_good() -> dict[str, Any] | None:
    try:
        if not _OPENMETEO_LAST_GOOD.exists():
            return None
        data = json.loads(_OPENMETEO_LAST_GOOD.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _save_openmeteo_last_good(payload: dict[str, Any]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _OPENMETEO_LAST_GOOD.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    except Exception:
        pass


def _finite(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def _series_ok(values: list[float], min_n: int = 4) -> bool:
    return len(values) >= min_n


# ---------------------------------------------------------------------------
# Live API collectors (PulseMesh-style)
# ---------------------------------------------------------------------------

def collect_goes_xray(max_points: int = 64) -> dict[str, Any]:
    urls = [
        "https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json",
        "https://services.swpc.noaa.gov/json/goes/primary/xrays-6-hour.json",
    ]
    last_note = "no_url"
    for url in urls:
        ok, body, note = _http_get(url)
        last_note = note
        if not ok or not isinstance(body, list):
            continue
        values: list[float] = []
        times: list[str] = []
        for item in body:
            if not isinstance(item, dict):
                continue
            flux = _finite(item.get("flux"))
            if flux is None or flux <= 0.0:
                continue
            values.append(math.log10(flux))
            times.append(str(item.get("time_tag") or item.get("time") or ""))
        if _series_ok(values, 8):
            return {
                "feed": "pulsemesh_goes_xray",
                "ok": True,
                "note": note,
                "count": len(values[-max_points:]),
                "latest": values[-1],
                "unit": "log10 W/m^2",
                "source_url": url,
                "items": [
                    {"t": times[-max_points:][i], "v": values[-max_points:][i]}
                    for i in range(min(max_points, len(values)))
                ][-8:],
                "live": True,
                "ts": _utc(),
            }
    return {
        "feed": "pulsemesh_goes_xray",
        "ok": False,
        "note": last_note,
        "count": 0,
        "items": [],
        "live": False,
        "ts": _utc(),
    }


def collect_openmeteo_series(
    *,
    lat: float = 40.71,
    lon: float = -74.01,
    variable: str = "temperature_2m",
    max_points: int = 48,
) -> dict[str, Any]:
    global _OPENMETEO_MEM, _OPENMETEO_MEM_TS
    now = time.monotonic()
    if _OPENMETEO_MEM is not None and (now - _OPENMETEO_MEM_TS) < _OPENMETEO_TTL_S:
        cached = dict(_OPENMETEO_MEM)
        cached["note"] = f"mem_ttl:{cached.get('note')}"
        cached["live"] = False
        cached["cached"] = True
        cached["ts"] = _utc()
        return cached

    query = {
        "latitude": lat,
        "longitude": lon,
        "hourly": variable,
        "past_days": 1,
        "forecast_days": 1,
        "timezone": "UTC",
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(query)
    _openmeteo_rate_limit()
    ok, body, note = _http_get(url, retries=3)
    if not ok or not isinstance(body, dict):
        last = _load_openmeteo_last_good()
        if last and last.get("ok"):
            out = dict(last)
            out["note"] = f"cached_last_good_after:{note}"
            out["live"] = False
            out["cached"] = True
            out["ok"] = True  # degrade gracefully — cycle continues on last-good
            out["ts"] = _utc()
            _OPENMETEO_MEM = dict(out)
            _OPENMETEO_MEM_TS = time.monotonic()
            return out
        return {
            "feed": "pulsemesh_openmeteo",
            "ok": False,
            "note": note,
            "count": 0,
            "items": [],
            "live": False,
            "cached": False,
            "ts": _utc(),
        }
    hourly = body.get("hourly") or {}
    times = [str(x) for x in (hourly.get("time") or [])]
    values = [v for v in (_finite(x) for x in (hourly.get(variable) or [])) if v is not None]
    if not _series_ok(values, 8):
        last = _load_openmeteo_last_good()
        if last and last.get("ok"):
            out = dict(last)
            out["note"] = f"cached_last_good_after:too_few:{note}"
            out["live"] = False
            out["cached"] = True
            out["ok"] = True
            out["ts"] = _utc()
            return out
        return {
            "feed": "pulsemesh_openmeteo",
            "ok": False,
            "note": f"too_few:{note}",
            "count": len(values),
            "items": [],
            "live": False,
            "cached": False,
            "ts": _utc(),
        }
    units = (body.get("hourly_units") or {}).get(variable, "")
    result = {
        "feed": "pulsemesh_openmeteo",
        "ok": True,
        "note": note,
        "count": len(values[-max_points:]),
        "latest": values[-1],
        "unit": str(units),
        "variable": variable,
        "lat": lat,
        "lon": lon,
        "source_url": url,
        "items": [
            {"t": times[-max_points:][i] if i < len(times[-max_points:]) else "", "v": values[-max_points:][i]}
            for i in range(min(8, len(values[-max_points:])))
        ],
        "live": True,
        "cached": False,
        "ts": _utc(),
    }
    _OPENMETEO_MEM = dict(result)
    _OPENMETEO_MEM_TS = time.monotonic()
    _save_openmeteo_last_good(result)
    return result


def collect_usgs_quakes(max_points: int = 40, days: int = 7, min_mag: float = 2.5) -> dict[str, Any]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    query = {
        "format": "geojson",
        "starttime": start.strftime("%Y-%m-%d"),
        "endtime": end.strftime("%Y-%m-%d"),
        "minmagnitude": min_mag,
        "orderby": "time",
        "limit": max(max_points, 100),
    }
    url = "https://earthquake.usgs.gov/fdsnws/event/1/query?" + urllib.parse.urlencode(query)
    ok, body, note = _http_get(url)
    values: list[float] = []
    items: list[dict[str, Any]] = []
    if ok and isinstance(body, dict):
        for feature in body.get("features") or []:
            props = feature.get("properties") or {} if isinstance(feature, dict) else {}
            mag = _finite(props.get("mag"))
            if mag is None:
                continue
            values.append(mag)
            items.append(
                {
                    "mag": mag,
                    "place": props.get("place"),
                    "time": props.get("time"),
                    "source": "usgs",
                }
            )
    return {
        "feed": "pulsemesh_usgs_quakes",
        "ok": ok and _series_ok(values, 4),
        "note": note,
        "count": len(values),
        "latest": values[0] if values else None,  # USGS orderby=time newest first
        "items": items[:8],
        "live": bool(ok and values),
        "source_url": url,
        "ts": _utc(),
    }


# ---------------------------------------------------------------------------
# System-stat + TCP probe collectors (PulseMesh local)
# ---------------------------------------------------------------------------

def collect_system_stat(samples: int = 4) -> dict[str, Any]:
    """Local system health: load, disk free %, process count, uptime."""
    values_load: list[float] = []
    disk_free_pct = None
    proc_n = None
    uptime_h = None
    try:
        total, used, free = shutil.disk_usage(str(ROOT))
        disk_free_pct = 100.0 * free / total if total else None
    except Exception as exc:  # noqa: BLE001
        disk_free_pct = None
        disk_err = str(exc)
    else:
        disk_err = ""
    try:
        load = os.getloadavg()[0]
        values_load = [float(load)] * samples
    except (AttributeError, OSError) as exc:
        values_load = []
        load_err = str(exc)
    else:
        load_err = ""
    try:
        # Linux-friendly process count
        proc_n = sum(1 for name in os.listdir("/proc") if name.isdigit())
    except Exception:
        proc_n = None
    try:
        with open("/proc/uptime", encoding="utf-8") as f:
            uptime_h = float(f.read().split()[0]) / 3600.0
    except Exception:
        uptime_h = None
    ok = bool(values_load) or disk_free_pct is not None
    return {
        "feed": "pulsemesh_system_stat",
        "ok": ok,
        "note": ";".join(x for x in (load_err, disk_err) if x) or "ok",
        "count": len(values_load),
        "items": [
            {
                "load1": values_load[-1] if values_load else None,
                "disk_free_percent": disk_free_pct,
                "process_count": proc_n,
                "uptime_hours": uptime_h,
                "platform": platform.platform(),
                "node": platform.node(),
                "source": "system_stat",
            }
        ],
        "latest_load1": values_load[-1] if values_load else None,
        "live": True,
        "ts": _utc(),
    }


def collect_tcp_probe(
    host: str = "1.1.1.1",
    port: int = 443,
    count: int = 4,
    timeout: float = 3.0,
) -> dict[str, Any]:
    values: list[float] = []
    oks = 0
    for i in range(max(1, count)):
        started = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=timeout):
                ok = True
        except OSError:
            ok = False
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        values.append(elapsed_ms if ok else timeout * 1000.0)
        if ok:
            oks += 1
    return {
        "feed": "pulsemesh_tcp_probe",
        "ok": oks > 0,
        "note": f"ok={oks}/{len(values)} host={host}:{port}",
        "count": len(values),
        "latest_ms": values[-1] if values else None,
        "mean_ms": (sum(values) / len(values)) if values else None,
        "items": [{"probe": i, "ms": values[i]} for i in range(len(values))],
        "live": True,
        "host": host,
        "port": port,
        "ts": _utc(),
    }


# ---------------------------------------------------------------------------
# Aggregate + correlate (debate input only)
# ---------------------------------------------------------------------------

def gather_pulsemesh(*, include_external_core: bool = True) -> dict[str, Any]:
    """Collect PulseMesh-style feeds; optional core EXTERNAL ARRAY refresh merge."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    feeds: dict[str, dict[str, Any]] = {
        "goes_xray": collect_goes_xray(),
        "openmeteo_series": collect_openmeteo_series(),
        "usgs_quakes": collect_usgs_quakes(),
        "system_stat": collect_system_stat(),
        "tcp_probe": collect_tcp_probe(),
    }
    core = {}
    if include_external_core:
        try:
            from colony.external_array import (
                fetch_arxiv,
                fetch_global_weather,
                fetch_nasa_donki_solar,
                fetch_noaa_space_weather,
            )

            core = {
                "arxiv": fetch_arxiv(),
                "nasa_donki_solar": fetch_nasa_donki_solar(),
                "noaa_space_weather": fetch_noaa_space_weather(),
                "global_weather": fetch_global_weather(),
            }
            feeds.update(core)
        except Exception as exc:  # noqa: BLE001
            feeds["core_merge_error"] = {
                "feed": "core_merge_error",
                "ok": False,
                "note": str(exc),
                "count": 0,
                "items": [],
                "ts": _utc(),
            }
    patterns = _correlate_pulsemesh(feeds)
    health = {k: {"ok": bool(v.get("ok")), "note": v.get("note"), "count": v.get("count")} for k, v in feeds.items()}
    snap = {
        "ts": _utc(),
        "version": 1,
        "mile": "spark3-port",
        "feeds": feeds,
        "feed_health": health,
        "cross_domain_patterns": patterns,
        "note": (
            "PulseMesh collectors in EXTERNAL ARRAY. Agent-queryable. "
            "Correlations are debate input — not discovery claims."
        ),
        "non_claims": ["not_AGI", "not_novel_physics", "not_Millennium", "debate_input_only"],
    }
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    day = _utc()[:10].replace("-", "")
    (CACHE_DIR / f"pm_{day}.json").write_text(
        json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": snap["ts"],
                    "feed_ok": {k: bool(v.get("ok")) for k, v in feeds.items()},
                    "pattern_kinds": [p.get("kind") for p in patterns],
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    return snap


def _correlate_pulsemesh(feeds: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []
    goes = feeds.get("goes_xray") or {}
    quakes = feeds.get("usgs_quakes") or {}
    sysf = feeds.get("system_stat") or {}
    probe = feeds.get("tcp_probe") or {}
    solar = feeds.get("noaa_space_weather") or {}
    donki = feeds.get("nasa_donki_solar") or {}
    arxiv = feeds.get("arxiv") or {}

    kp = solar.get("latest_kp")
    goes_ok = bool(goes.get("ok"))
    if goes_ok and (kp is not None or int(donki.get("count") or 0) > 0):
        patterns.append(
            {
                "kind": "pulsemesh_space_weather_mesh",
                "summary": (
                    f"PulseMesh GOES X-ray live (latest log10 flux={goes.get('latest')}) "
                    f"with NOAA Kp={kp} / DONKI n={donki.get('count')}. "
                    "Debate: ops attention on space-weather posture — not causal physics claim."
                ),
                "signals": {"goes_latest": goes.get("latest"), "kp": kp, "donki_n": donki.get("count")},
                "domains": ["cosmos", "government", "gather"],
                "not_discovery": True,
                "not_novel_physics": True,
            }
        )
    if bool(quakes.get("ok")) and int(arxiv.get("count") or 0) > 0:
        patterns.append(
            {
                "kind": "pulsemesh_quakes_x_pubs",
                "summary": (
                    f"USGS quakes n={quakes.get('count')} (latest mag={quakes.get('latest')}) "
                    f"alongside arXiv STEM n={arxiv.get('count')}. "
                    "Multi-hop debate input across nature↔math — not discovery."
                ),
                "signals": {"quake_n": quakes.get("count"), "arxiv_n": arxiv.get("count")},
                "domains": ["nature", "math", "hearing"],
                "not_discovery": True,
                "not_novel_physics": True,
            }
        )
    if bool(sysf.get("ok")) or bool(probe.get("ok")):
        patterns.append(
            {
                "kind": "pulsemesh_local_ops_health",
                "summary": (
                    f"Local system_stat load1={sysf.get('latest_load1')} "
                    f"tcp_probe mean_ms={probe.get('mean_ms')} ok={probe.get('ok')}. "
                    "Ops health for actuation throttle debates — not consciousness."
                ),
                "signals": {
                    "load1": sysf.get("latest_load1"),
                    "probe_ms": probe.get("mean_ms"),
                    "probe_ok": probe.get("ok"),
                },
                "domains": ["government", "commons", "oracle"],
                "not_discovery": True,
                "not_novel_physics": True,
            }
        )
    if not patterns:
        patterns.append(
            {
                "kind": "pulsemesh_degraded_or_sparse",
                "summary": (
                    "PulseMesh feeds sparse/offline — debate with cache; mark UNKNOWN where failed."
                ),
                "signals": {k: bool(v.get("ok")) for k, v in feeds.items()},
                "domains": ["oracle", "hearing"],
                "not_discovery": True,
                "not_novel_physics": True,
            }
        )
    return patterns


def query_pulsemesh(*, refresh: bool = False) -> dict[str, Any]:
    if refresh or not SNAPSHOT.exists():
        return gather_pulsemesh()
    try:
        return json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return gather_pulsemesh()


def feed_health() -> dict[str, Any]:
    snap = query_pulsemesh(refresh=False)
    return snap.get("feed_health") or {
        k: {"ok": bool(v.get("ok")), "note": v.get("note"), "count": v.get("count")}
        for k, v in (snap.get("feeds") or {}).items()
    }


__all__ = [
    "collect_goes_xray",
    "collect_openmeteo_series",
    "collect_usgs_quakes",
    "collect_system_stat",
    "collect_tcp_probe",
    "gather_pulsemesh",
    "query_pulsemesh",
    "feed_health",
]
