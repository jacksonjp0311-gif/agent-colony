"""Build the curated, cached pool of less-studied OEIS entries (colony/obscure_pool.py).

Free public OEIS only; polite (one request per 2 s, cached on disk in ~/.cache/colony/bfiles via
colony.new_data.Net). Selection is a mechanism, not a pick: OEIS searches narrowed by topic words,
then a fixed filter:
  keyword 'easy' and 'nonn'; not 'core', 'nice', 'more', 'hard', 'dead', 'dumb', 'obsc', 'tabl',
  'tabf', 'cons', 'frac', 'base', 'word', 'fini', 'full', 'sign'; offset 0 or 1;
  obscurity = #comment + #formula + 2 #reference lines <= OBSCURE_MAX;
  a b-file with >= MIN_TERMS terms; the b-file agrees with the entry's DATA (two independent
  sources of the same terms); not already a colony primitive.
Ranked by obscurity (fewest notes first), up to POOL_MAX entries.
Usage: python tools/build_obscure_pool.py [topic ...]"""
import json
import sys
import time
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
from colony import new_data as N  # noqa: E402
from colony import obscure_pool as OP  # noqa: E402

TOPICS = ("recurrence", "partitions", "graph", "matrix", "divisors", "primes", "binary", "permutations",
          "sum", "product", "Fibonacci", "triangular", "squares", "digits", "polynomial")
BAD_KW = {"core", "nice", "more", "hard", "dead", "dumb", "obsc", "tabl", "tabf", "cons", "frac", "base", "word",
          "fini", "full", "sign", "uned", "less"}
OBSCURE_MAX = 4
MIN_TERMS = 300
PAGES = 3
POOL_MAX = 40


def main(topics):
    N.NET_MAX_PER_CYCLE = 10 ** 6
    net = N.Net()
    seen, cands = set(OP.taken_anums()), []
    for t in topics:
        for page in range(PAGES):
            q = f"keyword:easy keyword:nonn -keyword:core -keyword:nice -keyword:more -keyword:tabl {t}"
            url = "https://oeis.org/search?fmt=json&start=%d&q=%s" % (10 * page, q.replace(" ", "+"))
            txt = net.get(url, f"search_{t}_{page}.json")
            try:
                res = json.loads(txt or "null") or []
            except ValueError:
                res = []
            if isinstance(res, dict):
                res = res.get("results") or []
            for e in res:
                a = "A%06d" % e["number"]
                if a in seen:
                    continue
                seen.add(a)
                kw = set(str(e.get("keyword") or "").split(","))
                off = int(str(e.get("offset") or "0").split(",")[0])
                score = len(e.get("comment") or []) + len(e.get("formula") or []) + 2 * len(e.get("reference") or [])
                if not {"easy", "nonn"} <= kw or kw & BAD_KW or off > 1 or score > OBSCURE_MAX:
                    continue
                if not any("b-file" in str(x) or "Table of n, a(n)" in str(x) for x in e.get("link") or []):
                    continue
                cands.append((score, a, off, e))
            if not res:
                break
    cands.sort(key=lambda x: (x[0], x[1]))
    pool = []
    for score, a, off, e in cands:
        if len(pool) >= POOL_MAX:
            break
        b = net.get(f"https://oeis.org/{a}/b{a[1:]}.txt", f"b{a[1:]}.txt")
        pairs = N.parse_bfile(b or "")
        data = [int(x) for x in str(e.get("data") or "").split(",") if x.strip()]
        if len(pairs) < MIN_TERMS or not data:
            continue
        bvals = {k: v for k, v in pairs}
        if any(bvals.get(off + i) != v for i, v in enumerate(data)):      # two sources must agree
            continue
        terms = OP.to_table(bvals, off)
        if terms is None:
            continue
        pool.append({"anum": a, "name": str(e.get("name") or "")[:160], "keyword": e.get("keyword"), "offset": off,
                     "obscurity": score, "n_comment": len(e.get("comment") or []),
                     "n_formula": len(e.get("formula") or []), "n_reference": len(e.get("reference") or []),
                     "n_bfile": len(pairs), "verified": "b-file agrees with DATA on all %d DATA terms" % len(data),
                     "terms": terms})
        print(a, score, len(terms), e.get("name", "")[:70], flush=True)
    out = {"note": OP.NOTE, "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "topics": list(topics),
           "filter": {"obscurity_max": OBSCURE_MAX, "min_terms": MIN_TERMS, "excluded_keywords": sorted(BAD_KW)},
           "candidates_seen": len(seen), "candidates_passing": len(cands), "pool": pool}
    OP.POOL.write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print("pool", len(pool), "of", len(cands), "passing,", len(seen), "seen")


if __name__ == "__main__":
    main(tuple(sys.argv[1:]) or TOPICS)
