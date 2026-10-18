"""Stage 1b: genuinely sparse new-data targets, chosen from the OEIS itself.

Discovery: polite OEIS searches (keyword:more / keyword:hard plus a topic the engine can compute;
<= SEARCH_PER_CYCLE uncached requests per cycle, cached for a month) list entries whose editors want
more terms. A candidate is SPARSE when it has a short published frontier: its data section plus any
b-file / linked table hold at most SHORT_MAX terms.

Identification is by definition-driven recomputation, not by a prefix lookup: the colony gates the
engine families by the entry's name (Collatz / divisors / Goldbach / prime patterns / subsets), then
recomputes EVERY published term with each family item and operation (terms, record positions,
record values, first occurrences) under small index shifts. An entry matches only if all published
terms agree (so low-variety sequences match correctly). If several items reproduce the data but
disagree on the next terms, the definition is ambiguous and nothing is claimed.

Past the frontier: method A computes, an independent method B recomputes the whole range (every
published term and every new one); both must agree. Record / first-occurrence claims are complete
over the scanned range (B rescans the whole range). If nothing new turns up, the search bound is
noted ("no further term up to k = N"), which is not a claim.

Reward: expected new terms per CPU-second, weighted by w = 1 / (1 + published_terms / 50), so
extending a 10,000-term b-file earns ~1/200 of extending a 30-term data section.

"Beyond published frontier" = beyond the OEIS entry (data, b-file, linked tables) on the date checked.
Papers and personal tables are not checked; keyword "more" says the OEIS wants more terms, not that
nobody has them.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import urllib.parse
from typing import Any

import numpy as np

from colony import sparse_engine as E

SEARCH_QUERIES = [
    "keyword:more Collatz", "keyword:more 3x+1", "keyword:hard Collatz",
    "keyword:more Goldbach", "keyword:more \"sum of two primes\"", "keyword:more Lemoine",
    "keyword:more \"twin primes\"", "keyword:more \"cousin primes\"", "keyword:more \"sexy primes\"",
    "keyword:more \"prime triples\"", "keyword:more \"prime quadruplets\"", "keyword:more \"(n+1)^2\" primes",
    "keyword:more \"number of divisors\"", "keyword:more \"number of divisors\" records",
    "keyword:more sigma records", "keyword:more \"d(k)\"", "keyword:more subsets sum prime",
    "keyword:more subsets sum square", "keyword:hard \"number of divisors\"", "keyword:hard Goldbach",
    "keyword:more \"no twin primes\"", "keyword:more \"between n^2 and (n+1)^2\"", "keyword:more \"least even number\" primes",
    "keyword:more \"smallest number\" \"number of divisors\"", "keyword:more \"p + 2q\"", "keyword:more trajectory",
]
PAGES = 3
SEARCH_PER_CYCLE = 3
SHORT_MAX = 300
MIN_TERMS = 6
MATCH_PER_CYCLE = 40           # bounded by 60% of the sparse budget
MATCH_BUDGET_S = 6.0
SKIP_KW = {"tabl", "tabf", "cons", "frac", "fini", "full", "dead", "word", "dumb", "obsc", "less"}
LABEL_NEW = "computed beyond published frontier (verified 2 ways)"
LABEL_MATCH = "matches published"
SHIFTS = (0, 1, -1, 2, -2)


def mode() -> str:
    """COLONY_NEWDATA_SPARSE: off | shadow (default: search, identify, compute, ledger; nothing authored) | live."""
    v = (os.environ.get("COLONY_NEWDATA_SPARSE") or "shadow").strip().lower()
    return v if v in ("live", "shadow", "off") else "shadow"


def deep_mode() -> str:
    v = (os.environ.get("COLONY_NEWDATA_DEEP") or "shadow").strip().lower()
    return v if v in ("live", "shadow", "off") else "shadow"


def short_weight(n_pub: int) -> float:
    return 1.0 / (1.0 + max(0, int(n_pub)) / 50.0)


# ----------------------------------------------------------------------------- discovery
def search_page(net: Any, q: str, start: int) -> list[dict[str, Any]] | None:
    name = "osearch_" + hashlib.sha1(f"{q}|{start}".encode()).hexdigest()[:16] + ".json"
    url = "https://oeis.org/search?" + urllib.parse.urlencode({"q": q, "fmt": "json", "start": start})
    txt = net.get(url, name)
    if txt is None:
        return None
    try:
        js = json.loads(txt or "null")
    except ValueError:
        return []
    if isinstance(js, dict):
        js = js.get("results")
    return [x for x in (js or []) if isinstance(x, dict)]


def _parse_candidate(x: dict[str, Any]) -> dict[str, Any] | None:
    from colony.new_data import _linked_extent
    try:
        num = int(x["number"])
        data = [int(t) for t in str(x.get("data") or "").split(",") if t.strip()]
        off = int(str(x.get("offset") or "1").split(",")[0])
    except (ValueError, KeyError):
        return None
    kws = set(str(x.get("keyword") or "").split(","))
    links = [str(l) for l in x.get("link") or []]
    table = _linked_extent(links)
    has_b = any(f"b{num:06d}.txt" in l for l in links)
    return {"anum": f"A{num:06d}", "name": str(x.get("name") or "")[:240], "keywords": sorted(kws),
            "offset": off, "data": data, "table_extent": table, "has_bfile": has_b,
            "n_pub": max(len(data), table - off + 1 if table else 0),
            "comment_hint": [c[:160] for c in (x.get("comment") or []) if re.search(r"\b(no (other|more|further)|"
                             r"terms? (below|up to|<)|> ?10\^|exhaustive|a\(\d+\) >)", str(c), re.I)][:3]}


def eligible(c: dict[str, Any]) -> str | None:
    if not ({"more", "hard"} & set(c["keywords"])):
        return "not keyword more/hard"
    if set(c["keywords"]) & SKIP_KW:
        return "keyword " + ",".join(sorted(set(c["keywords"]) & SKIP_KW))
    if len(c["data"]) < MIN_TERMS or len(set(c["data"])) < 3:
        return "too few published terms to identify"
    if c["n_pub"] > SHORT_MAX:
        return f"long frontier ({c['n_pub']} published terms)"
    if not E.families_for(c["name"]):
        return "no engine family for its definition"
    return None


def published_rows(c: dict[str, Any], net: Any) -> tuple[list[tuple[int, int]], str] | None:
    rows = [(c["offset"] + i, v) for i, v in enumerate(c["data"])]
    src = f"https://oeis.org/{c['anum']} (data section, {len(rows)} terms)"
    if c.get("has_bfile") or c.get("table_extent", 0) > rows[-1][0]:
        from colony.new_data import parse_bfile
        num = c["anum"][1:]
        txt = net.get(f"https://oeis.org/{c['anum']}/b{num}.txt", f"b{num}.txt")
        if txt is None:
            return None
        b = parse_bfile(txt)
        if b and b[-1][0] >= rows[-1][0]:
            rows = b
            src = f"https://oeis.org/{c['anum']}/b{num}.txt ({len(rows)} terms)"
    return rows, src


def _derive(op: str, v: np.ndarray, n_need: int = 0) -> list[int] | dict[int, int]:
    if op in E.LIST_OPS:
        return E.listing(op, v)
    if op == "terms":
        return np.asarray(v).tolist()
    if op in ("recpos", "recval"):
        pos, val = E.records(v)
        return pos if op == "recpos" else val
    return E.firsts(v, n_need)


def _list_start(ours: list[int], rows: list[tuple[int, int]]) -> int | None:
    """Lists may start past k = 1 (e.g. 'k > 4'): align on the first published member."""
    try:
        return ours.index(rows[0][1])
    except ValueError:
        return None


def _fits(op: str, ours: Any, rows: list[tuple[int, int]], d: int) -> bool:
    if op in E.LIST_OPS:
        if d != 0:
            return False
        i0 = _list_start(ours, rows)
        if i0 is None or i0 > 3:
            return False
        return ours[i0: i0 + len(rows)] == [v for _, v in rows]
    if op == "first":
        return all(ours.get(n + d) == v for n, v in rows)
    base = rows[0][0]
    for n, v in rows:
        i = (n + d - 1) if op == "terms" else (n - base + d)
        if i < 0 or i >= len(ours) or ours[i] != v:
            return False
    return True


def _need_N(op: str, rows: list[tuple[int, int]], item: str) -> int:
    if op == "terms":
        return rows[-1][0] + 3
    if op in ("recpos", "first") or op in E.LIST_OPS:
        return max(v for _, v in rows) + 1
    return max(2000, E.cap(item) // 4)


def match(c: dict[str, Any], rows: list[tuple[int, int]], budget_s: float = MATCH_BUDGET_S) -> dict[str, Any]:
    t0 = time.process_time()
    hits, reach = [], []
    items = E.items_for(c["name"])
    for item in items:
        if time.process_time() - t0 > budget_s:
            return {"status": "match budget spent", "hits": hits, "beyond_reach": reach[:5],
                    "cpu_s": round(time.process_time() - t0, 3)}
        ops = []
        for op in E.OPS:
            if (op in ("recpos", "first") or op in E.LIST_OPS) and min(v for _, v in rows) < 1:
                continue
            N = _need_N(op, rows, item)
            if N > E.cap(item) or N < 2:
                reach.append(f"{item}:{op} needs k up to {N}")
                continue
            ops.append((op, N))
        if not ops:
            continue
        Nmax = max(N for _, N in ops)
        try:
            vall = np.asarray(E.ITEMS[item]["a"](Nmax))
        except Exception:  # noqa: BLE001
            continue
        for op, N in ops:
            v = vall[:N]
            ours = _derive(op, v, max(n for n, _ in rows) + 3)
            for d in SHIFTS:
                if _fits(op, ours, rows, d):
                    hits.append({"item": item, "op": op, "d": d, "N": N})
                    break
    if hits:
        return {"status": "matched", "hits": hits, "cpu_s": round(time.process_time() - t0, 3)}
    if reach:
        return {"status": "beyond engine reach to verify", "beyond_reach": reach[:5],
                "cpu_s": round(time.process_time() - t0, 3)}
    return {"status": "no family item reproduces all published terms", "cpu_s": round(time.process_time() - t0, 3)}


# ----------------------------------------------------------------------------- past the frontier
def _new_terms(op: str, ours: Any, rows: list[tuple[int, int]], d: int, N: int) -> list[tuple[int, int]]:
    """Published-index terms past the last published one, from our computed range."""
    last_n = rows[-1][0]
    out = []
    if op == "terms":
        for n in range(last_n + 1, N - d + 1):
            i = n + d - 1
            if 0 <= i < len(ours):
                out.append((n, int(ours[i])))
        return out
    if op in E.LIST_OPS:
        i0 = _list_start(ours, rows) or 0
        return [(last_n + 1 + j, int(k)) for j, k in enumerate(ours[i0 + len(rows):])]
    if op == "first":
        n = last_n + 1
        while (n + d) in ours:
            out.append((n, ours[n + d]))
            n += 1
        return out
    base = rows[0][0]
    for i in range(last_n - base + d + 1, len(ours)):
        if i >= 0:
            out.append((i + base - d, int(ours[i])))
    return out


def push(e: dict[str, Any], budget_s: float, deep: bool = False) -> dict[str, Any]:
    t0 = time.process_time()
    rows = [tuple(r) for r in e["rows"]]
    h = e["hits"][0]
    item, op, d = h["item"], h["op"], h["d"]
    capN = E.cap(item, deep)
    out = {"anum": e["anum"], "item": item, "op": op, "ts": _utc()}
    if op == "terms":
        per = float(e.get("a_per_k_s") or 1e-6)
        want = rows[-1][0] + d + 1000
        N = min(capN, want, int(rows[-1][0] + d + max(50, budget_s / (3 * per))))
    else:
        start = max(int(e.get("searched_to") or 0), h["N"], 1000)
        N = min(capN, 4 * start)
    if N <= (rows[-1][0] + d if op == "terms" else int(e.get("searched_to") or h["N"])):
        return out | {"status": "intractable", "why": f"engine cap k = {capN} reached ({'deep' if deep else 'cycle'} budget)",
                      "cpu_s": round(time.process_time() - t0, 3)}
    fa = E.ITEMS[item]["a"]
    ta = time.process_time()
    va = np.asarray(fa(N))
    ta = time.process_time() - ta
    e["a_per_k_s"] = max(1e-8, ta / max(N, 1))
    n_need = rows[-1][0] + 400
    ours = _derive(op, va, n_need)
    if not _fits(op, ours, rows, d):
        return out | {"status": "mismatch", "why": "method A no longer reproduces the published terms",
                      "cpu_s": round(time.process_time() - t0, 3)}
    new = _new_terms(op, ours, rows, d, N)
    # ambiguity: every other item that reproduced the published data must agree on the new terms
    for other in e["hits"][1:]:
        if not new:
            break
        vo = np.asarray(E.ITEMS[other["item"]]["a"](N))
        oo = _new_terms(other["op"], _derive(other["op"], vo, n_need), rows, other["d"], N)
        if oo[: len(new)] != new[: len(oo)]:
            return out | {"status": "ambiguous definition", "why": f"{other['item']}:{other['op']} also fits the "
                          "published terms but differs past them", "cpu_s": round(time.process_time() - t0, 3)}
    e["searched_to"] = N
    if not new:
        return out | {"status": LABEL_MATCH, "why": f"no further term up to k = {N}", "searched_to": N,
                      "cpu_s": round(time.process_time() - t0, 3)}
    tb = time.process_time()
    vb = np.asarray(E.ITEMS[item]["b"](N))
    tb = time.process_time() - tb
    ob = _derive(op, vb, n_need)
    newb = _new_terms(op, ob, rows, d, N)
    if not _fits(op, ob, rows, d) or newb[: len(new)] != new:
        return out | {"status": "unverified", "why": "method B disagrees", "cpu_s": round(time.process_time() - t0, 3)}
    # the Oracle bridge recomputes single values: f(k) = value in colony indexing
    pairs = []
    for n, v in new[:3]:
        if op == "terms":
            pairs.append([n + d, int(v)])
        elif op == "first":
            pairs.append([int(v), n + d])
        elif op == "recpos" or op in E.LIST_OPS:
            pairs.append([int(v), int(np.asarray(vb)[int(v) - 1])])
    if op == "recval":
        pos, _val = E.records(vb)
        base = rows[0][0]
        for n, v in new[:3]:
            pairs.append([int(pos[n - base + d]), int(v)])
    return out | {"status": LABEL_NEW, "values": [[int(n), int(v)] for n, v in new], "searched_to": N,
                  "methods": E.ITEMS[item]["methods"], "pairs": pairs, "cpu_a": round(ta, 3), "cpu_b": round(tb, 3),
                  "cpu_s": round(time.process_time() - t0, 3)}


def _utc() -> str:
    from colony.new_data import _utc as u
    return u()


# ----------------------------------------------------------------------------- one cycle
def score(e: dict[str, Any], total: int) -> float:
    s = e.get("stats") or {}
    ev = (s.get("beyond", 0) + 1.0) / (s.get("cpu_s", 0.0) + 1.0)
    return short_weight(e.get("n_pub", 0)) * ev + math.sqrt(2 * math.log(total + 2) / (s.get("tries", 0) + 1))


def run(cycle_id: str, net: Any, st: dict[str, Any], idx: dict[str, Any], claims: dict[str, Any],
        budget_s: float, deep: bool = False, record: bool = True, push_max: int = 4) -> dict[str, Any]:
    t0 = time.process_time()
    sp = st.setdefault("sparse", {"cursor": 0, "seen": {}})
    ents = idx.setdefault("sparse", {})
    # 1. polite searches (cache first)
    fetched, n_req0 = [], net.n
    pages = [(q, s) for q in SEARCH_QUERIES for s in range(0, PAGES * 10, 10)]
    exhausted = set(sp.get("exhausted") or [])
    i_last = -1
    for i in range(len(pages)):
        if net.n - n_req0 >= SEARCH_PER_CYCLE * (6 if deep else 1):
            break
        i_last = i
        q, s0 = pages[(sp.get("cursor", 0) + i) % len(pages)]
        if q in exhausted and s0 > 0:
            continue
        n_before = net.n
        res = search_page(net, q, s0)
        if res is None:
            continue
        fetched_now = net.n > n_before
        if len(res) < 10:
            exhausted.add(q)
        for x in res:
            c = _parse_candidate(x)
            if c and c["anum"] not in sp["seen"]:
                why = eligible(c)
                sp["seen"][c["anum"]] = {"status": why or "candidate", "query": q, "n_pub": c["n_pub"],
                                         "name": c["name"][:100]}
                if not why:
                    sp.setdefault("queue", {})[c["anum"]] = c
        if fetched_now:
            fetched.append(f"{q} @{s0}")
    sp["cursor"] = (sp.get("cursor", 0) + i_last + 1) % len(pages)
    sp["exhausted"] = sorted(exhausted)
    # 2. identify queued candidates by recomputation
    matched_now = []
    queue = sp.setdefault("queue", {})
    for anum in sorted(queue, key=lambda a: queue[a]["n_pub"])[:MATCH_PER_CYCLE * (25 if deep else 1)]:
        left = budget_s * 0.6 - (time.process_time() - t0)
        if left < 1:
            break
        c = queue.pop(anum)
        pr = published_rows(c, net)
        if pr is None:
            queue[anum] = c
            continue
        rows, src = pr
        m = match(c, rows, min(left, MATCH_BUDGET_S * (4 if deep else 1)))
        if m["status"] == "match budget spent" and not m.get("hits"):
            c["match_tries"] = c.get("match_tries", 0) + 1
            if c["match_tries"] < 3:
                queue[anum] = c          # retry later (the shared ranges may be cached by then)
        sp["seen"][anum]["status"] = m["status"]
        if m["status"] == "matched":
            ents[anum] = {k: c[k] for k in ("anum", "name", "keywords", "offset", "n_pub", "comment_hint")} | {
                "rows": [list(r) for r in rows], "source": src, "hits": m["hits"], "checked": _utc(),
                "stats": {"tries": 0, "beyond": 0, "cpu_s": 0.0}, "status": "matched"}
            matched_now.append({"anum": anum, "hits": m["hits"][:3]})
    # 3. push past the frontier, best expected new terms per CPU-second (short frontiers weighted up)
    pushed = []
    for _round in range(50 if deep else 1):     # the deep job keeps pushing until its budget is spent
        n_before = len(pushed)
        _push_round(ents, pushed, t0, budget_s, deep, record, push_max, claims, cycle_id)
        if len(pushed) == n_before or budget_s - (time.process_time() - t0) < 1:
            break
    return {"searches": fetched, "matched": matched_now, "pushed": pushed, "queue": len(queue),
            "candidates_seen": len(sp["seen"]), "cpu_s": round(time.process_time() - t0, 3)}


def _push_round(ents: dict[str, Any], pushed: list[dict[str, Any]], t0: float, budget_s: float, deep: bool,
                record: bool, push_max: int, claims: dict[str, Any], cycle_id: str) -> None:
    cap_key = "intractable_deep" if deep else "intractable"
    live = [e for e in ents.values() if e.get("status") == "matched" and not e.get("claimed")
            and not e.get(cap_key)]
    total = sum((e.get("stats") or {}).get("tries", 0) for e in live)
    live.sort(key=lambda e: -score(e, total))
    for e in live[:push_max]:
        left = budget_s - (time.process_time() - t0)
        if left < 1:
            break
        try:
            r = push(e, left, deep)
        except MemoryError:
            r = {"anum": e["anum"], "status": "intractable", "why": "memory"}
        except Exception as exc:  # noqa: BLE001
            r = {"anum": e["anum"], "status": "error", "why": str(exc)[:160]}
        s = e.setdefault("stats", {"tries": 0, "beyond": 0, "cpu_s": 0.0})
        s["tries"] += 1
        s["cpu_s"] = round(s["cpu_s"] + float(r.get("cpu_s") or 0), 3)
        if r["status"] == "intractable":
            e[cap_key] = r.get("why")
        if r["status"] in ("mismatch", "ambiguous definition"):
            e["status"] = r["status"]
        if r["status"] == LABEL_NEW:
            s["beyond"] += len(r["values"])
            if record:
                record_claim(claims, e, r, cycle_id, deep)
                e["claimed"] = True
        e["last"] = {k: r.get(k) for k in ("status", "why", "searched_to", "cpu_s", "ts")}
        pushed.append({k: v for k, v in r.items() if k not in ("values",)} | {"n_values": len(r.get("values") or [])}
                      | ({"values_head": r["values"][:5]} if r.get("values") else {}))


def record_claim(claims: dict[str, Any], e: dict[str, Any], r: dict[str, Any], cycle_id: str, deep: bool) -> None:
    from colony.new_data import DATA_DIR, ROOT
    anum = e["anum"]
    data = DATA_DIR / f"{anum}_beyond.txt"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data.write_text(f"# {anum} terms computed beyond the OEIS entry ({e['source']}, checked {e['checked']}).\n"
                    f"# Computed by colony.sparse ({r['item']}:{r['op']}, scanned k <= {r['searched_to']}); verified 2 ways: "
                    f"{r['methods'][0]} / {r['methods'][1]}.\n" + "".join(f"{n} {v}\n" for n, v in r["values"]),
                    encoding="utf-8")
    vals = r["values"]
    hint = "; ".join(e.get("comment_hint") or [])
    claims.setdefault("claims", []).append({
        "kind": "sparse", "anum": anum, "name": e.get("name"), "item": r["item"], "op": r["op"],
        "k_range": [vals[0][0], vals[-1][0]], "n_terms": len(vals), "first": vals[0], "last": vals[-1],
        "label": LABEL_NEW, "methods": r["methods"], "frontier_source": e["source"],
        "frontier_k_max": e["rows"][-1][0], "n_pub_terms": len(e["rows"]), "keywords": e.get("keywords"),
        "searched_to": r["searched_to"], "pairs": r["pairs"], "checked": e["checked"], "cpu_s": r["cpu_s"],
        "cycle_id": cycle_id, "deep": deep, "data_file": str(data.relative_to(ROOT)), "ts": _utc(),
        "how_sure": ("beyond the OEIS entry (data section, b-file and linked tables) on the date checked; the entry "
                     f"has keyword {'/'.join(k for k in e.get('keywords') or [] if k in ('more', 'hard'))} (more terms "
                     "wanted); identified by recomputing all published terms, not by parsing the definition; papers "
                     "and personal tables not checked" + (f"; entry comments: {hint}" if hint else ""))})


def point_b(item: str, k: int) -> int:
    """Oracle bridge: f(k) of a sparse engine item, recomputed from scratch by method B (single value)."""
    return int(E.ITEMS[str(item)]["bp"](int(k)))


def self_test() -> dict[str, Any]:
    ok = {}
    for k, it in E.ITEMS.items():
        N = 40 if it["family"] != "subset" else 18
        a, b = np.asarray(it["a"](N)).tolist(), np.asarray(it["b"](N)).tolist()
        ok[k] = a == b and [point_b(k, n) for n in (1, 5, N)] == [a[0], a[4], a[N - 1]]
    # published anchors (hard-coded from the OEIS): A000005, A006577, A046927 (Lemoine, offset 0)
    ok["A000005"] = E.ITEMS["div_d"]["a"](12).tolist() == [1, 2, 2, 3, 2, 4, 2, 4, 3, 4, 2, 6]
    ok["A006577"] = E.ITEMS["col_steps"]["a"](10).tolist() == [0, 1, 7, 2, 5, 8, 16, 3, 19, 6]
    ok["A046927"] = E.ITEMS["gb_lemoine"]["a"](8).tolist() == [0, 0, 1, 2, 2, 2, 2, 4]
    return {"ok": all(ok.values()), "checks": ok}


def run_deep(budget_s: float = 1500.0) -> dict[str, Any]:
    """Nightly longer budget (separate workflow). shadow: report only (society/frontier/deep_shadow.json);
    live: verified terms are recorded as claims like any cycle's."""
    from colony import new_data as N
    m = deep_mode()
    if m == "off":
        return {"skipped": "COLONY_NEWDATA_DEEP=off"}
    N.NET_MAX_PER_CYCLE = max(N.NET_MAX_PER_CYCLE, 24)    # one nightly job: more polite searches (2 s apart, cached)
    net = N.Net()
    st, idx = N._load(N.STATE, {}), N._load(N.INDEX, {"entries": {}})
    claims = N._load(N.CLAIMS, {"claims": []})
    res = run("deep_" + _utc(), net, st, idx, claims, budget_s, deep=True, record=(m == "live"), push_max=12)
    res |= {"mode": m, "ts": _utc(), "budget_s": budget_s, "net_requests": net.n}
    if m == "live":
        N._save(N.STATE, st)
        N._save(N.INDEX, idx)
        N._save(N.CLAIMS, claims)
        N.write_ledger(claims, idx)
    else:
        prev = N._load(N.FRONTIER_DIR / "deep_shadow.json", {"runs": []})
        prev["runs"] = (prev.get("runs") or [])[-20:] + [res]
        N._save(N.FRONTIER_DIR / "deep_shadow.json", prev)
    return res


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ["deep"]:
        b = float(os.environ.get("COLONY_NEWDATA_DEEP_BUDGET_S") or 1500)
        print(json.dumps(run_deep(b), indent=1)[:6000])
    elif sys.argv[1:2] == ["selftest"]:
        print(self_test())
