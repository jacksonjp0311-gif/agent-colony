"""External feeds — the colony's outward senses (James 2026-10-07: "more sensors, more feeds, more data").

Fetched once per CI run (``python -m colony feeds``), read from cache inside cycles.
Every fetch is fail-soft (a feed outage never fails the run), rate-limited per host,
TTL-cached, deduped by a stable source id and size-bounded. Stdlib only.

Fetched text is UNTRUSTED DATA: it is stripped of markup/control characters, truncated,
never evaluated, and never pasted into generated code. The only values that reach code
generation are integers parsed by a digits-only regex and OEIS A-numbers matching
``A\\d{6}``. Feeds never bypass gates: a feed item can only become a seek *theme*, a
bus pointer, or the expected values of a disabled authored check that must still pass
verification, the Oracle and the Hearing like everything else.

Sources (all public, no keys):
- arxiv     — export.arxiv.org Atom API, rotating categories (math.CO, math.NT, cs.LG, cs.MA)
- oeis      — oeis.org search by the colony's OWN computed sequence prefixes ("what is my sequence?")
- crossref  — api.crossref.org works search (recent journal articles, catalog-derived queries)
- wikipedia — en.wikipedia.org summaries for topics derived from lemma names in the catalog
- ci_health — public GitHub Actions run list for this repo (sensor input, stored in state)
"""
from __future__ import annotations

import hashlib
import html
import importlib.util
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "research_cache"
FEEDS_JSONL = CACHE_DIR / "feeds.jsonl"
FEEDS_STATE = CACHE_DIR / "feeds_state.json"
LEMMA_IMPL = ROOT / "society" / "benchmarks" / "artifacts" / "lemma_impl.py"

USER_AGENT = "AgentColony/0.4 (+https://github.com/jacksonjp0311-gif/agent-colony; research feeds; not-AGI)"
TIMEOUT_S = 15
MAX_BYTES = 600_000          # read cap per response
MAX_ITEMS_PER_SOURCE = 6     # new rows per source per run
MAX_TEXT = 480               # chars kept from any fetched text field
MAX_FILE_ROWS = 2000         # rotate (keep newest KEEP_ROWS) past this
KEEP_ROWS = 1500
FEED_TTL_S = 4 * 3600        # do not refetch a source that succeeded within this window
MIN_INTERVAL_S = {"export.arxiv.org": 3.0}
DEFAULT_INTERVAL_S = 1.0
MAX_TERM_DIGITS = 60
MIN_HELDOUT_TERMS = 6
MAX_HELDOUT_TERMS = 20
QUERY_TERMS = 8

ARXIV_CATEGORIES = ("math.CO", "math.NT", "cs.LG", "cs.MA")
CHANNEL_BY_ARXIV = {"math": "math", "cs.LG": "science", "cs.MA": "rsi"}
CHANNEL_BY_SOURCE = {"oeis": "math", "crossref": "science", "wikipedia": "history"}
REPO = os.environ.get("GITHUB_REPOSITORY") or "jacksonjp0311-gif/agent-colony"

# The colony's own sequences, built ONLY from functions in lemma_impl.py. ``expr`` is the
# code-gen template for authored checks; ``fn`` computes the same terms for the OEIS query.
SEQ_GENERATORS: list[dict[str, Any]] = [
    {"name": "catalan", "expr": "binomial(2 * n, n) // (n + 1)", "base_fns": ["binomial"],
     "fn": lambda m, n: m.binomial(2 * n, n) // (n + 1),
     "lemma_fns": ["check_catalan_bounded", "check_catalan_convolution"]},
    {"name": "fibonacci", "expr": "fibonacci(n)", "base_fns": ["fibonacci"],
     "fn": lambda m, n: m.fibonacci(n),
     "lemma_fns": ["check_cassini_identity", "check_fibonacci_addition", "check_gcd_fibonacci"]},
    {"name": "central_binomial", "expr": "binomial(2 * n, n)", "base_fns": ["binomial"],
     "fn": lambda m, n: m.binomial(2 * n, n),
     "lemma_fns": ["check_central_binom_bound"]},
    {"name": "lucas", "expr": "lucas(n)", "base_fns": ["lucas"],
     "fn": lambda m, n: m.lucas(n),
     "lemma_fns": ["check_lucas_addition"]},
    {"name": "binomial_row_sum", "expr": "sum(binomial(n, k) for k in range(n + 1))", "base_fns": ["binomial"],
     "fn": lambda m, n: sum(m.binomial(n, k) for k in range(n + 1)),
     "lemma_fns": ["check_binomial_sum_row"]},
]

_LAST_HIT: dict[str, float] = {}
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_TAGS = re.compile(r"<[^>]{0,400}>")


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_text(s: Any, n: int = MAX_TEXT) -> str:
    """Untrusted text → plain, bounded string (no markup, no control chars)."""
    s = html.unescape(_TAGS.sub(" ", str(s or "")))
    s = _CTRL.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()[:n]


def _throttle(url: str) -> None:
    host = re.sub(r"^https?://", "", url).split("/")[0]
    gap = MIN_INTERVAL_S.get(host, DEFAULT_INTERVAL_S)
    wait = _LAST_HIT.get(host, 0.0) + gap - time.monotonic()
    if wait > 0:
        time.sleep(min(wait, 10.0))
    _LAST_HIT[host] = time.monotonic()


def _http_get(url: str, *, accept: str = "application/json", headers: dict[str, str] | None = None) -> tuple[bool, str]:
    """GET with UA, timeout, byte cap. Never raises: (ok, body_or_error)."""
    try:
        _throttle(url)
        h = {"User-Agent": USER_AGENT, "Accept": accept}
        h.update(headers or {})
        with urlopen(Request(url, headers=h), timeout=TIMEOUT_S) as resp:  # noqa: S310 (fixed https hosts)
            status = getattr(resp, "status", 200)
            body = resp.read(MAX_BYTES).decode("utf-8", errors="replace")
            return (200 <= int(status) < 300), body
    except Exception as e:  # noqa: BLE001 — fail-soft by design
        return False, f"{type(e).__name__}: {str(e)[:160]}"


# ----------------------------------------------------------------------------- state / cache

def load_state() -> dict[str, Any]:
    try:
        return json.loads(FEEDS_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(st: dict[str, Any]) -> None:
    FEEDS_STATE.parent.mkdir(parents=True, exist_ok=True)
    FEEDS_STATE.write_text(json.dumps(st, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_items(*, kind: str | None = None, source: str | None = None, limit: int = 400) -> list[dict[str, Any]]:
    if not FEEDS_JSONL.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        lines = FEEDS_JSONL.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    for ln in lines:
        if not ln.strip():
            continue
        try:
            e = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if kind and e.get("kind") != kind:
            continue
        if source and e.get("source") != source:
            continue
        out.append(e)
    return out[-limit:]


def _existing_ids() -> set[str]:
    return {str(e.get("id")) for e in load_items(limit=MAX_FILE_ROWS * 2)}


def _append(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    FEEDS_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with FEEDS_JSONL.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    try:
        lines = [ln for ln in FEEDS_JSONL.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if len(lines) > MAX_FILE_ROWS:
            FEEDS_JSONL.write_text("\n".join(lines[-KEEP_ROWS:]) + "\n", encoding="utf-8")
    except Exception:
        pass


def _item(source: str, key: str, kind: str, title: str, text: str, url: str, channel: str,
          endpoint: str, query: str, **extra: Any) -> dict[str, Any]:
    row = {
        "id": f"{source}:{key}",
        "source": source,
        "kind": kind,
        "title": clean_text(title, 200),
        "text": clean_text(text),
        "url": clean_text(url, 300),
        "channel": channel,
        "fetched_at": _utc(),
        "provenance": {"endpoint": endpoint, "query": clean_text(query, 200),
                       "fetched_by": "colony.feeds", "untrusted": True},
        "tags": ["feed", source, kind],
    }
    row.update(extra)
    return row


# ----------------------------------------------------------------------------- sources

def arxiv_channel(category: str) -> str:
    if category in CHANNEL_BY_ARXIV:
        return CHANNEL_BY_ARXIV[category]
    return CHANNEL_BY_ARXIV.get(category.split(".")[0], "science")


def parse_arxiv(body: str, category: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ent in body.split("<entry>")[1:]:
        tm = re.search(r"<title>(.*?)</title>", ent, re.S)
        sm = re.search(r"<summary>(.*?)</summary>", ent, re.S)
        im = re.search(r"<id>(.*?)</id>", ent, re.S)
        pm = re.search(r"<published>(\d{4}-\d{2}-\d{2})", ent)
        raw_id = (im.group(1) if im else "").strip()
        m = re.search(r"arxiv\.org/abs/([A-Za-z.\-/]*\d{4}\.\d{4,5}|[a-z\-]+/\d{7})", raw_id)
        if not (tm and m):
            continue
        aid = m.group(1)
        out.append(_item(
            "arxiv", aid, "paper", tm.group(1), sm.group(1) if sm else "",
            f"https://arxiv.org/abs/{aid}", arxiv_channel(category),
            "export.arxiv.org/api/query", f"cat:{category}",
            arxiv_id=aid, category=category, published=pm.group(1) if pm else "",
        ))
    return out


def fetch_arxiv(categories: list[str], *, per_cat: int = 4) -> tuple[bool, list[dict[str, Any]], str]:
    items: list[dict[str, Any]] = []
    errs: list[str] = []
    for cat in categories:
        q = urlencode({"search_query": f"cat:{cat}", "start": 0, "max_results": per_cat,
                       "sortBy": "submittedDate", "sortOrder": "descending"})
        ok, body = _http_get(f"https://export.arxiv.org/api/query?{q}", accept="application/atom+xml")
        if ok:
            items.extend(parse_arxiv(body, cat))
        else:
            errs.append(f"{cat}:{body[:80]}")
    return (bool(items) or not errs), items, "; ".join(errs)


def _lemma_module() -> Any | None:
    try:
        spec = importlib.util.spec_from_file_location("feeds_lemma_impl", LEMMA_IMPL)
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(mod)  # the colony's own artifact, not fetched content
        return mod
    except Exception:
        return None


def generator_terms(gen: dict[str, Any], start: int, count: int, mod: Any | None = None) -> list[int] | None:
    mod = mod or _lemma_module()
    if mod is None:
        return None
    try:
        return [int(gen["fn"](mod, n)) for n in range(start, start + count)]
    except Exception:
        return None


def _parse_terms(data: str) -> list[int]:
    out: list[int] = []
    for tok in str(data or "").split(","):
        tok = tok.strip()
        if not re.fullmatch(r"-?\d{1,%d}" % MAX_TERM_DIGITS, tok):
            break  # stop at the first non-integer / oversize term (untrusted data)
        out.append(int(tok))
    return out


def parse_oeis(body: str, query_terms: list[int], query_start: int, gen: dict[str, Any]) -> dict[str, Any] | None:
    """First OEIS result containing the queried run → held-out terms past the query window.

    Regex over the raw body (robust to truncation at MAX_BYTES); values are ints only.
    """
    results = re.split(r'"number"\s*:\s*', body)[1:]
    q = list(query_terms)
    for chunk in results[:5]:
        nm = re.match(r"(\d{1,7})", chunk)
        dm = re.search(r'"data"\s*:\s*"([0-9,\-\s]*)"', chunk)
        if not (nm and dm):
            continue
        terms = _parse_terms(dm.group(1))
        idx = next((i for i in range(len(terms) - len(q) + 1) if terms[i:i + len(q)] == q), None)
        if idx is None:
            continue
        held = terms[idx + len(q): idx + len(q) + MAX_HELDOUT_TERMS]
        if len(held) < MIN_HELDOUT_TERMS:
            continue
        anum = f"A{int(nm.group(1)):06d}"
        name_m = re.search(r'"name"\s*:\s*"((?:[^"\\]|\\.){0,400})"', chunk)
        return {
            "oeis_id": anum,
            "name": clean_text(name_m.group(1) if name_m else "", 200),
            "query_terms": q,
            "query_start": query_start,
            "heldout_start": query_start + len(q),
            "terms": held,
            "generator": gen["name"],
        }
    return None


def fetch_oeis(gens: list[dict[str, Any]]) -> tuple[bool, list[dict[str, Any]], str]:
    mod = _lemma_module()
    if mod is None:
        return False, [], "lemma_impl_unavailable"
    items: list[dict[str, Any]] = []
    errs: list[str] = []
    for gen in gens:
        start = 1
        q = generator_terms(gen, start, QUERY_TERMS, mod)
        if not q:
            continue
        query = ",".join(str(x) for x in q)
        ok, body = _http_get(f"https://oeis.org/search?{urlencode({'q': query, 'fmt': 'json'})}")
        if not ok:
            errs.append(f"{gen['name']}:{body[:80]}")
            continue
        hit = parse_oeis(body, q, start, gen)
        if not hit:
            continue
        items.append(_item(
            "oeis", f"{hit['oeis_id']}:{gen['name']}", "sequence", f"{hit['oeis_id']} {hit['name']}",
            f"OEIS {hit['oeis_id']} matches the colony's `{gen['name']}` terms n={start}..{start + len(q) - 1}; "
            f"{len(hit['terms'])} held-out terms from n={hit['heldout_start']}.",
            f"https://oeis.org/{hit['oeis_id']}", CHANNEL_BY_SOURCE["oeis"],
            "oeis.org/search", query, **hit,
        ))
    return (bool(items) or not errs), items, "; ".join(errs)


def catalog_topics() -> list[str]:
    """Human-readable topics derived from lemma names in the catalog (mechanism, not a list)."""
    try:
        import ast
        src = LEMMA_IMPL.read_text(encoding="utf-8")
        tree = ast.parse(src)
        names = [n.name[len("check_"):] for n in tree.body
                 if isinstance(n, ast.FunctionDef) and n.name.startswith("check_")
                 and not n.name.startswith(("check_authored_", "check_adversarial_", "check_easy"))]
    except Exception:
        return []
    drop = {"first", "of", "n", "bounded", "small", "stress", "deep", "ext", "row", "two", "check", "identity", "lemma",
            "recurrence", "multiplicative", "asymmetric", "companion", "generation", "derived", "chain"}
    out: list[str] = []
    for nm in names:
        words = [w for w in nm.split("_") if len(w) > 1 and w not in drop and not w.isdigit()]
        t = " ".join(words[:3]).strip()
        if len(t) >= 4 and t not in out:
            out.append(t)
    return out


def parse_crossref(body: str, query: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(body)
    except Exception:
        return []
    out = []
    for w in ((data.get("message") or {}).get("items") or [])[:MAX_ITEMS_PER_SOURCE]:
        doi = clean_text(w.get("DOI") or "", 120)
        title = clean_text(" ".join(w.get("title") or []), 200)
        if not doi or not title:
            continue
        words = {w for w in query.lower().split() if len(w) >= 4}
        if words and not any(w in title.lower() for w in words):
            continue  # relevance guard
        venue = clean_text(" ".join(w.get("container-title") or []), 120)
        out.append(_item("crossref", doi.lower(), "paper", title, w.get("abstract") or venue,
                         f"https://doi.org/{doi}", CHANNEL_BY_SOURCE["crossref"],
                         "api.crossref.org/works", query, doi=doi, venue=venue))
    return out


def fetch_crossref(queries: list[str]) -> tuple[bool, list[dict[str, Any]], str]:
    today = datetime.now(timezone.utc).date()
    frm = (today - timedelta(days=365)).isoformat()
    items: list[dict[str, Any]] = []
    errs: list[str] = []
    for q in queries:
        params = urlencode({
            "query": f"{q} combinatorics identity", "rows": 5,
            "filter": f"from-pub-date:{frm},until-pub-date:{today.isoformat()},type:journal-article",
            "select": "DOI,title,URL,container-title,abstract",
            "mailto": "agent-colony@users.noreply.github.com",
        })
        ok, body = _http_get(f"https://api.crossref.org/works?{params}")
        if ok:
            items.extend(parse_crossref(body, q))  # q (topic) drives the relevance guard
        else:
            errs.append(f"{q}:{body[:80]}")
    return (bool(items) or not errs), items, "; ".join(errs)


def fetch_wikipedia(topics: list[str]) -> tuple[bool, list[dict[str, Any]], str]:
    items: list[dict[str, Any]] = []
    errs: list[str] = []
    for t in topics:
        ok, body = _http_get("https://en.wikipedia.org/w/api.php?" + urlencode(
            {"action": "query", "list": "search", "srsearch": f"{t} mathematics", "srlimit": 3,
             "srnamespace": 0, "format": "json"}))
        if not ok:
            errs.append(f"{t}:{body[:80]}")
            continue
        try:
            hits = [str(h.get("title") or "") for h in ((json.loads(body).get("query") or {}).get("search") or [])]
        except Exception:
            continue
        # relevance guard: the article title must share a word (>=4 chars) with the topic
        words = {w for w in t.lower().split() if len(w) >= 4}
        ok_hits = [h for h in hits if "disambiguation" not in h.lower()
                   and words and words <= {w.strip("'(),.").lower() for w in h.split()}]
        title = min(ok_hits, key=lambda h: (len(h.split()), hits.index(h))) if ok_hits else ""
        if not title:
            continue
        ok, body = _http_get("https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(title.replace(" ", "_")))
        if not ok:
            errs.append(f"{title}:{body[:80]}")
            continue
        try:
            s = json.loads(body)
        except Exception:
            continue
        extract = s.get("extract") or ""
        if not extract:
            continue
        url = ((s.get("content_urls") or {}).get("desktop") or {}).get("page") or f"https://en.wikipedia.org/wiki/{quote(title)}"
        items.append(_item("wikipedia", clean_text(title, 120).lower(), "summary", title, extract, url,
                           CHANNEL_BY_SOURCE["wikipedia"], "en.wikipedia.org/api/rest_v1/page/summary", t))
    return (bool(items) or not errs), items, "; ".join(errs)


def fetch_ci_health(limit: int = 12) -> dict[str, Any] | None:
    headers = {}
    tok = os.environ.get("GITHUB_TOKEN") or ""
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    ok, body = _http_get(f"https://api.github.com/repos/{REPO}/actions/runs?per_page={limit}",
                         accept="application/vnd.github+json", headers=headers)
    if not ok:
        return None
    try:
        runs = json.loads(body).get("workflow_runs") or []
    except Exception:
        return None
    rows = [{"id": r.get("id"), "name": clean_text(r.get("name"), 60), "conclusion": r.get("conclusion"),
             "status": r.get("status"), "created_at": r.get("created_at"), "updated_at": r.get("updated_at")}
            for r in runs[:limit]]
    done = [r for r in rows if r["status"] == "completed"]
    succ = sum(1 for r in done if r["conclusion"] == "success")
    return {"fetched_at": _utc(), "runs": rows, "completed": len(done),
            "success_rate": round(succ / len(done), 4) if done else None}


# ----------------------------------------------------------------------------- orchestration

def _due(st: dict[str, Any], source: str, force: bool) -> bool:
    if force:
        return True
    last = (st.get("last_ok") or {}).get(source)
    if not last:
        return True
    try:
        t = datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - t).total_seconds() >= FEED_TTL_S


def _rotate(seq: list[Any], k: int, n: int) -> list[Any]:
    if not seq:
        return []
    return [seq[(k * n + i) % len(seq)] for i in range(min(n, len(seq)))]


def fetch_all(*, force: bool = False, sources: list[str] | None = None) -> dict[str, Any]:
    """Fetch every due source once. Never raises; returns per-source summary."""
    st = load_state()
    run_k = int(st.get("runs") or 0)
    st["runs"] = run_k + 1
    have = _existing_ids()
    seq_have = {str(e.get("generator")) for e in load_items(kind="sequence")}
    gens_fresh = [g for g in SEQ_GENERATORS if g["name"] not in seq_have] or SEQ_GENERATORS
    topics = catalog_topics()
    plan: dict[str, Callable[[], tuple[bool, list[dict[str, Any]], str]]] = {
        "arxiv": lambda: fetch_arxiv(_rotate(list(ARXIV_CATEGORIES), run_k, 2)),
        "oeis": lambda: fetch_oeis(_rotate(gens_fresh, 0 if gens_fresh is not SEQ_GENERATORS else run_k, 2)),
        "crossref": lambda: fetch_crossref(_rotate(topics, run_k, 1)),
        "wikipedia": lambda: fetch_wikipedia(_rotate(topics, run_k + 1, 2)),
    }
    summary: dict[str, Any] = {"ts": _utc(), "sources": {}}
    for name, fn in plan.items():
        if sources and name not in sources:
            continue
        if not _due(st, name, force):
            summary["sources"][name] = {"ok": True, "new": 0, "skipped": "ttl"}
            continue
        try:
            ok, items, err = fn()
        except Exception as e:  # noqa: BLE001
            ok, items, err = False, [], f"{type(e).__name__}: {str(e)[:120]}"
        new = []
        for it in items:
            if it["id"] in have:
                continue
            have.add(it["id"])
            new.append(it)
            if len(new) >= MAX_ITEMS_PER_SOURCE:
                break
        try:
            _append(new)
        except Exception as e:  # noqa: BLE001
            ok, err = False, f"write:{e}"
        hs = st.setdefault("health", {}).setdefault(name, {"ok": 0, "fail": 0})
        if ok:
            hs["ok"] += 1
            st.setdefault("last_ok", {})[name] = _utc()
        else:
            hs["fail"] += 1
            st.setdefault("last_error", {})[name] = clean_text(err, 200)
        summary["sources"][name] = {"ok": ok, "new": len(new), "fetched": len(items), "error": clean_text(err, 160) if err else ""}
    if not sources or "ci_health" in sources:
        try:
            ci = fetch_ci_health()
        except Exception:
            ci = None
        if ci:
            st["ci_health"] = ci
        summary["sources"]["ci_health"] = {"ok": ci is not None, "new": 0}
    st["last_run"] = summary
    try:
        _save_state(st)
    except Exception:
        pass
    return summary


# ----------------------------------------------------------------------------- readers used in cycles

def _pick(items: list[dict[str, Any]], cycle_id: str) -> dict[str, Any] | None:
    if not items:
        return None
    h = int(hashlib.sha1((cycle_id or "x").encode()).hexdigest()[:8], 16)
    return items[h % len(items)]


def pick_seek_theme(cycle_id: str = "", *, window: int = 12) -> dict[str, Any] | None:
    """A recent feed paper/summary as a seek theme (rotates by cycle). Pointer only."""
    items = [e for e in load_items(limit=400) if e.get("kind") in ("paper", "summary") and e.get("title")]
    items.sort(key=lambda e: str(e.get("fetched_at") or ""))
    return _pick(items[-window:], cycle_id)


def channel_item(channel: str, cycle_id: str = "", *, window: int = 8) -> dict[str, Any] | None:
    items = [e for e in load_items(limit=400) if e.get("channel") == channel and e.get("title")]
    return _pick(items[-window:], cycle_id)


def channel_note(channel: str, cycle_id: str = "") -> tuple[str, dict[str, Any]] | None:
    it = channel_item(channel, cycle_id)
    if not it:
        return None
    note = f" Feed[{it['source']}]: {it['title'][:110]} <{it['url']}> (pointer, not a claim)."
    return note, {"feed_item": it["id"], "feed_source": it["source"], "feed_url": it["url"]}


def sequence_items() -> list[dict[str, Any]]:
    out = []
    for e in load_items(kind="sequence"):
        if not re.fullmatch(r"A\d{6}", str(e.get("oeis_id") or "")):
            continue
        terms = e.get("terms") or []
        if not (isinstance(terms, list) and all(isinstance(t, int) and not isinstance(t, bool) for t in terms)):
            continue
        if not isinstance(e.get("heldout_start"), int) or len(terms) < MIN_HELDOUT_TERMS:
            continue
        if any(len(str(abs(t))) > MAX_TERM_DIGITS for t in terms):
            continue
        out.append(e)
    return out


def generator_by_name(name: str) -> dict[str, Any] | None:
    return next((g for g in SEQ_GENERATORS if g["name"] == name), None)


def counts() -> dict[str, Any]:
    by_source: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for e in load_items(limit=MAX_FILE_ROWS * 2):
        by_source[e.get("source") or "?"] = by_source.get(e.get("source") or "?", 0) + 1
        by_kind[e.get("kind") or "?"] = by_kind.get(e.get("kind") or "?", 0) + 1
    return {"by_source": by_source, "by_kind": by_kind}


if __name__ == "__main__":
    import sys
    print(json.dumps(fetch_all(force="--force" in sys.argv), indent=2))
