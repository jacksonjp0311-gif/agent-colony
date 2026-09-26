"""PulseMesh collectors smoke — offline-safe unit checks + optional live."""
from __future__ import annotations

from colony.pulsemesh_feeds import (
    collect_system_stat,
    collect_tcp_probe,
    feed_health,
    gather_pulsemesh,
)


def test_system_stat_collector():
    row = collect_system_stat(samples=2)
    assert row["feed"] == "pulsemesh_system_stat"
    assert "ok" in row
    assert row["ts"]


def test_tcp_probe_collector():
    row = collect_tcp_probe(host="1.1.1.1", port=443, count=2, timeout=2.0)
    assert row["feed"] == "pulsemesh_tcp_probe"
    assert row["count"] == 2
    # ok may be True/False depending on network; structure must hold
    assert "latest_ms" in row


def test_gather_pulsemesh_structure():
    # include_external_core=False keeps this faster / less dependent on arxiv
    snap = gather_pulsemesh(include_external_core=False)
    assert "feeds" in snap
    assert "feed_health" in snap
    assert "cross_domain_patterns" in snap
    for p in snap["cross_domain_patterns"]:
        assert p.get("not_discovery") is True or p.get("kind")
    h = feed_health()
    assert isinstance(h, dict)
