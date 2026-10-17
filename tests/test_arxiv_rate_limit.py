"""arXiv feed: https endpoint, 429/Retry-After backoff, last-good cache, honest live counting."""
import pytest

from colony import research_gather as rg

ATOM = ("<feed><entry><id>http://arxiv.org/abs/2610.00001v1</id><title>A sieve note</title>"
        "<summary>s</summary><published>2026-10-16</published><name>A B</name></entry></feed>")
T0 = 1_760_000_000.0


@pytest.fixture(autouse=True)
def _state(tmp_path, monkeypatch):
    monkeypatch.setattr(rg, "ARXIV_STATE", tmp_path / "arxiv_feed.json")


def _get(status=200, body=ATOM, ra=None, calls=None):
    def g(url, accept=""):
        if calls is not None:
            calls.append(url)
        return {"ok": status == 200, "status": status, "body": body if status == 200 else "",
                "retry_after": ra, "error": "" if status == 200 else f"HTTP {status}"}
    return g


def test_https_endpoint():
    assert rg.ARXIV_API.startswith("https://export.arxiv.org/")


def test_live_then_cache_within_interval():
    calls = []
    h, s, _ = rg.fetch_arxiv_cached(now=T0, getter=_get(calls=calls))
    assert s == "live_ok" and h and calls[0].startswith("https://")
    h2, s2, _ = rg.fetch_arxiv_cached(now=T0 + 60, getter=_get(calls=calls))
    assert s2 == "cache_fresh" and h2[0].title == "A sieve note" and len(calls) == 1


def test_429_honors_retry_after_and_uses_cache():
    rg.fetch_arxiv_cached(now=T0, getter=_get())
    t = T0 + rg.ARXIV_MIN_INTERVAL_S + 1
    h, s, why = rg.fetch_arxiv_cached(now=t, getter=_get(429, ra="3600"))
    assert s == "throttled_cache_fresh" and h and "429" in why
    calls = []
    _, s2, _ = rg.fetch_arxiv_cached(now=t + rg.ARXIV_MIN_INTERVAL_S + 10, getter=_get(calls=calls))
    assert s2 == "cache_fresh" and calls == []  # still inside Retry-After window
    _, s3, _ = rg.fetch_arxiv_cached(now=t + 3700, getter=_get(calls=calls))
    assert s3 == "live_ok" and len(calls) == 1


def test_429_without_cache_is_a_real_fail():
    h, s, _ = rg.fetch_arxiv_cached(now=T0, getter=_get(429))
    assert s == "fail" and h == []


def test_stale_cache_counts_as_fail():
    rg.fetch_arxiv_cached(now=T0, getter=_get())
    _, s, _ = rg.fetch_arxiv_cached(now=T0 + rg.CACHE_MAX_AGE_S + 3600, getter=_get(429))
    assert s == "fail"


def test_http_error_is_fail():
    _, s, why = rg.fetch_arxiv_cached(now=T0, getter=_get(500))
    assert s == "fail" and "500" in why


def test_gather_counts_cache_separately(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(rg, "FINDINGS_CACHE", tmp_path / "papers.jsonl")
    monkeypatch.setattr(rg, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(rg, "fetch_arxiv_cached", lambda **k: ([], "throttled_cache_fresh", "HTTP 429"))
    monkeypatch.setattr(rg, "fetch_openalex", lambda **k: [])
    r = rg.gather_papers(live=True)
    assert (r.live_ok, r.live_fail, r.cached) == (0, 1, 1)
    out = capsys.readouterr().out
    assert "source=arxiv status=throttled_cache_fresh" in out and "source=openalex status=fail" in out
