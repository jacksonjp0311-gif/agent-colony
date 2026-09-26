"""EXTERNAL ARRAY — agent-queryable real API feeds for cross-domain debate input.

Feeds: arXiv (new publications), NASA/NOAA space data, solar activity indices,
global weather. Prefer real HTTP with graceful degrade + cache snapshots.
Not AGI. Not novel physics discoveries — correlations are debate input only.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "commons" / "external_array"
SNAPSHOT = ROOT / "society" / "systems" / "external_array.json"
LOG = ROOT / "data" / "commons" / "external_array.jsonl"

UA = "agent-colony/spark2 (research; contact=james; not-agi)"
TIMEOUT = 12


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _http_get(url: str, *, accept: str = "application/json") -> tuple[bool, Any, str]:
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
    except Exception as exc:  # noqa: BLE001
        return False, None, f"{type(exc).__name__}: {exc}"


def fetch_arxiv(max_results: int = 5) -> dict[str, Any]:
    """Recent STEM papers via arXiv Atom API (cs.AI + physics + math)."""
    q = urllib.parse.quote("cat:cs.AI OR cat:physics.space-ph OR cat:math.DS")
    url = (
        f"http://export.arxiv.org/api/query?search_query={q}"
        f"&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
    )
    ok, body, note = _http_get(url, accept="application/atom+xml")
    items: list[dict[str, Any]] = []
    if ok and isinstance(body, str):
        # Lightweight Atom parse — titles + ids + published
        chunks = body.split("<entry>")
        for chunk in chunks[1 : max_results + 1]:
            def _tag(t: str) -> str:
                a = chunk.find(f"<{t}")
                if a < 0:
                    return ""
                a = chunk.find(">", a) + 1
                b = chunk.find(f"</{t}>", a)
                return chunk[a:b].strip() if b > a else ""

            title = " ".join(_tag("title").split())
            eid = _tag("id")
            published = _tag("published")
            summary = " ".join(_tag("summary").split())[:280]
            if title:
                items.append(
                    {
                        "title": title,
                        "id": eid,
                        "published": published,
                        "summary": summary,
                        "source": "arxiv",
                    }
                )
    return {
        "feed": "arxiv",
        "ok": ok and bool(items),
        "note": note if ok else note,
        "count": len(items),
        "items": items,
        "ts": _utc(),
    }


def fetch_nasa_donki_solar() -> dict[str, Any]:
    """NASA DONKI notifications (space weather) — no API key needed for recent."""
    # Public DONKI endpoint; graceful degrade if blocked
    url = "https://kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get/notifications?type=all"
    ok, body, note = _http_get(url)
    items: list[dict[str, Any]] = []
    if ok and isinstance(body, list):
        for row in body[:8]:
            if not isinstance(row, dict):
                continue
            items.append(
                {
                    "messageType": row.get("messageType"),
                    "messageID": row.get("messageID"),
                    "messageIssueTime": row.get("messageIssueTime"),
                    "messageURL": row.get("messageURL"),
                    "source": "nasa_donki",
                }
            )
    elif ok and isinstance(body, str):
        items.append({"raw_snip": body[:400], "source": "nasa_donki"})
    return {
        "feed": "nasa_donki_solar",
        "ok": ok and bool(items),
        "note": note,
        "count": len(items),
        "items": items,
        "ts": _utc(),
    }


def fetch_noaa_space_weather() -> dict[str, Any]:
    """NOAA SWPC planetary K-index (solar activity proxy)."""
    url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
    ok, body, note = _http_get(url)
    items: list[dict[str, Any]] = []
    latest_kp = None
    if ok and isinstance(body, list) and len(body) > 1:
        # First row headers, rest data
        headers = body[0] if isinstance(body[0], list) else ["time_tag", "kp", "a_running", "station_count"]
        for row in body[-6:]:
            if not isinstance(row, list):
                continue
            rec = {str(headers[i] if i < len(headers) else i): row[i] for i in range(len(row))}
            rec["source"] = "noaa_kp"
            items.append(rec)
        if items:
            try:
                latest_kp = float(items[-1].get("kp") or items[-1].get("Kp") or 0)
            except (TypeError, ValueError, IndexError):
                latest_kp = None
    return {
        "feed": "noaa_space_weather",
        "ok": ok and bool(items),
        "note": note,
        "count": len(items),
        "latest_kp": latest_kp,
        "items": items,
        "ts": _utc(),
    }


def fetch_global_weather() -> dict[str, Any]:
    """Open-Meteo global sample (no key) — multi-city snapshot."""
    cities = [
        ("NYC", 40.71, -74.01),
        ("London", 51.51, -0.13),
        ("Tokyo", 35.68, 139.76),
        ("Sydney", -33.87, 151.21),
    ]
    items: list[dict[str, Any]] = []
    notes: list[str] = []
    for name, lat, lon in cities:
        url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,wind_speed_10m,weather_code&timezone=UTC"
        )
        ok, body, note = _http_get(url)
        notes.append(f"{name}:{note}")
        if ok and isinstance(body, dict):
            cur = body.get("current") or {}
            items.append(
                {
                    "city": name,
                    "lat": lat,
                    "lon": lon,
                    "temperature_2m": cur.get("temperature_2m"),
                    "wind_speed_10m": cur.get("wind_speed_10m"),
                    "weather_code": cur.get("weather_code"),
                    "time": cur.get("time"),
                    "source": "open_meteo",
                }
            )
    return {
        "feed": "global_weather",
        "ok": bool(items),
        "note": "; ".join(notes)[:240],
        "count": len(items),
        "items": items,
        "ts": _utc(),
    }


def _correlate(feeds: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Cross-domain pattern hypotheses for debate — honest non-claims."""
    patterns: list[dict[str, Any]] = []
    arxiv = feeds.get("arxiv") or {}
    solar = feeds.get("noaa_space_weather") or {}
    donki = feeds.get("nasa_donki_solar") or {}
    weather = feeds.get("global_weather") or {}

    kp = solar.get("latest_kp")
    arxiv_n = int(arxiv.get("count") or 0)
    donki_n = int(donki.get("count") or 0)
    wx_n = int(weather.get("count") or 0)

    if kp is not None and donki_n > 0:
        patterns.append(
            {
                "kind": "space_weather_coherence",
                "summary": (
                    f"NOAA Kp={kp} co-observed with {donki_n} NASA DONKI notification(s). "
                    "Debate: does elevated geomagnetic activity warrant commons attention "
                    "on infrastructure/ops gather→claim? Not causal claim."
                ),
                "signals": {"kp": kp, "donki_n": donki_n},
                "domains": ["cosmos", "government", "gather"],
            }
        )
    if arxiv_n > 0 and (kp is not None or donki_n > 0):
        titles = [i.get("title", "")[:80] for i in (arxiv.get("items") or [])[:3]]
        patterns.append(
            {
                "kind": "publications_x_space",
                "summary": (
                    f"{arxiv_n} fresh arXiv STEM items alongside space-weather signals. "
                    f"Sample titles: {titles}. Multi-hop: math/STEM kinematics ↔ space data "
                    "↔ hearing evidence standard. Not novel physics."
                ),
                "signals": {"arxiv_n": arxiv_n, "kp": kp, "titles": titles},
                "domains": ["math", "cosmos", "hearing", "oracle"],
            }
        )
    if wx_n >= 2:
        temps = [
            (i.get("city"), i.get("temperature_2m"))
            for i in (weather.get("items") or [])
            if i.get("temperature_2m") is not None
        ]
        patterns.append(
            {
                "kind": "global_weather_spread",
                "summary": (
                    f"Open-Meteo snapshot across {wx_n} cities: {temps}. "
                    "Cross-correlate with solar/space feeds for commons resource planning "
                    "debate — kinematics of environment signals, not prophecy."
                ),
                "signals": {"cities": temps, "kp": kp},
                "domains": ["nature", "commons", "government"],
            }
        )
    if not patterns:
        patterns.append(
            {
                "kind": "degraded_or_sparse",
                "summary": (
                    "External array sparse/offline — agents should debate with cached "
                    "snapshots and mark UNKNOWN where feeds failed. Not silence."
                ),
                "signals": {
                    "arxiv_ok": bool(arxiv.get("ok")),
                    "solar_ok": bool(solar.get("ok")),
                    "donki_ok": bool(donki.get("ok")),
                    "weather_ok": bool(weather.get("ok")),
                },
                "domains": ["oracle", "hearing"],
            }
        )
    for p in patterns:
        p["not_discovery"] = True
        p["not_novel_physics"] = True
    return patterns


def gather_external_array(*, force: bool = False) -> dict[str, Any]:
    """Fetch all feeds (+ PulseMesh collectors), correlate, cache snapshot. Agent-callable."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    feeds = {
        "arxiv": fetch_arxiv(),
        "nasa_donki_solar": fetch_nasa_donki_solar(),
        "noaa_space_weather": fetch_noaa_space_weather(),
        "global_weather": fetch_global_weather(),
    }
    # SPARK3: PulseMesh live API / system-stat / probe collectors (debate input only)
    pulsemesh_health: dict[str, Any] = {}
    try:
        from colony.pulsemesh_feeds import (
            collect_goes_xray,
            collect_openmeteo_series,
            collect_system_stat,
            collect_tcp_probe,
            collect_usgs_quakes,
        )

        pm = {
            "pulsemesh_goes_xray": collect_goes_xray(),
            "pulsemesh_openmeteo": collect_openmeteo_series(),
            "pulsemesh_usgs_quakes": collect_usgs_quakes(),
            "pulsemesh_system_stat": collect_system_stat(),
            "pulsemesh_tcp_probe": collect_tcp_probe(),
        }
        feeds.update(pm)
        pulsemesh_health = {
            k: {"ok": bool(v.get("ok")), "note": v.get("note"), "count": v.get("count")}
            for k, v in pm.items()
        }
        # Persist dedicated PulseMesh snapshot (non-fatal)
        try:
            from colony.pulsemesh_feeds import gather_pulsemesh

            gather_pulsemesh(include_external_core=False)
        except Exception:
            pass
    except Exception as exc:  # noqa: BLE001
        pulsemesh_health = {"error": str(exc)}
    patterns = _correlate(feeds)
    # Append PulseMesh-specific pattern hints when local/live sensors speak
    sysf = feeds.get("pulsemesh_system_stat") or {}
    probe = feeds.get("pulsemesh_tcp_probe") or {}
    goes = feeds.get("pulsemesh_goes_xray") or {}
    if bool(goes.get("ok")):
        patterns.append(
            {
                "kind": "pulsemesh_goes_live",
                "summary": (
                    f"PulseMesh GOES X-ray live latest={goes.get('latest')}. "
                    "Space-weather debate input — not novel physics."
                ),
                "signals": {"goes_latest": goes.get("latest")},
                "domains": ["cosmos", "gather"],
                "not_discovery": True,
                "not_novel_physics": True,
            }
        )
    if bool(sysf.get("ok")) or bool(probe.get("ok")):
        patterns.append(
            {
                "kind": "pulsemesh_ops_health",
                "summary": (
                    f"PulseMesh system_stat/tcp_probe: load1={sysf.get('latest_load1')} "
                    f"probe_ms={probe.get('mean_ms')}. Ops health for actuation — not consciousness."
                ),
                "signals": {"load1": sysf.get("latest_load1"), "probe_ms": probe.get("mean_ms")},
                "domains": ["government", "commons", "oracle"],
                "not_discovery": True,
                "not_novel_physics": True,
            }
        )
    snap = {
        "ts": _utc(),
        "version": 2,
        "mile": "spark3-port",
        "feeds": feeds,
        "pulsemesh_health": pulsemesh_health,
        "cross_domain_patterns": patterns,
        "note": (
            "EXTERNAL ARRAY + PulseMesh collectors for agent query during debate. "
            "Graceful degrade. Correlations are debate input — not discovery."
        ),
        "non_claims": ["not_AGI", "not_novel_physics", "not_Millennium"],
    }
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    day = _utc()[:10].replace("-", "")
    (CACHE_DIR / f"snap_{day}.json").write_text(
        json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "ts": snap["ts"],
                    "pattern_count": len(patterns),
                    "feed_ok": {k: bool(v.get("ok")) for k, v in feeds.items()},
                    "patterns": [p.get("kind") for p in patterns],
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    return snap


def query_external(*, refresh: bool = False) -> dict[str, Any]:
    """Agent API: read latest snapshot; optionally refresh feeds."""
    if refresh or not SNAPSHOT.exists():
        return gather_external_array(force=True)
    try:
        return json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return gather_external_array(force=True)


def patterns_for_debate(limit: int = 3) -> list[dict[str, Any]]:
    snap = query_external(refresh=False)
    return list((snap.get("cross_domain_patterns") or [])[:limit])
