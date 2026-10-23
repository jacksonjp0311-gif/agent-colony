"""Build the cached pool of OEIS entries with an open problem (colony/open_targets.py).

Free public OEIS only; polite (one request per 2 s, cached in ~/.cache/colony/bfiles via
colony.new_data.Net). A mechanism, not a pick: fixed OEIS searches, then a fixed filter:
  keyword 'nonn'; not 'core', 'nice' (heavily studied), 'tabl', 'tabf', 'cons', 'frac', 'base',
  'word', 'fini', 'full', 'sign', 'dead', 'dumb'; offset 0 or 1; a b-file of >= MIN_TERMS terms
  that agrees with DATA; not already a colony primitive or obscure-pool entry; and one of
    conjecture_formula  a FORMULA line starting "Conjecture"
    conjecture_comment  a COMMENT line containing "Conjecture:" / "conjecture that" / "Conjecture"
    no_formula          no FORMULA lines and no "G.f." / "a(n) =" / "a(n)=" in comments
Up to PER_KIND entries per kind, fewest-studied first (#comment + #formula + 2 #reference).
Usage: python tools/build_open_targets.py"""
import json
import sys
import time
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
from colony import new_data as N  # noqa: E402
from colony import obscure_pool as OP  # noqa: E402
from colony import open_targets as OT  # noqa: E402

TOPICS = ("recurrence", "partitions", "primes", "binary", "divisors", "permutations", "sum", "digits")
QUERIES = {"conjecture_formula": "formula:Conjecture", "conjecture_comment": "comment:Conjecture",
           "no_formula": "keyword:hard"}
BAD_KW = {"core", "nice", "tabl", "tabf", "cons", "frac", "base", "word", "fini", "full", "sign", "dead", "dumb",
          "uned", "obsc"}
MIN_TERMS = 300
PAGES = 2
PER_KIND = 10


def kind_of(e):
    fl = [str(x) for x in e.get("formula") or []]
    cm = [str(x) for x in e.get("comment") or []]
    f = next((x for x in fl if x.lstrip().startswith("Conjecture")), None)
    if f:
        return "conjecture_formula", f
    c = next((x for x in cm if "Conjecture" in x or "conjecture that" in x), None)
    if c:
        return "conjecture_comment", c
    if not fl and not any(s in x for x in cm for s in ("G.f.", "a(n) =", "a(n)=", "recurrence")):
        return "no_formula", "no formula, recurrence or g.f. in the entry"
    return None, None


def main():
    N.NET_MAX_PER_CYCLE = 10 ** 6
    net = N.Net()
    seen = set(OP.taken_anums()) | {e["anum"] for e in OP.load()}
    cands = {k: [] for k in QUERIES}
    for want, qk in QUERIES.items():
        for t in TOPICS:
            for page in range(PAGES):
                q = f"{qk} keyword:nonn -keyword:core -keyword:nice -keyword:tabl -keyword:cons {t}"
                url = "https://oeis.org/search?fmt=json&start=%d&q=%s" % (10 * page, q.replace(" ", "+"))
                txt = net.get(url, f"ot_{want}_{t}_{page}.json")
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
                    kw = set(str(e.get("keyword") or "").split(","))
                    off = int(str(e.get("offset") or "0").split(",")[0])
                    if "nonn" not in kw or kw & BAD_KW or off > 1:
                        continue
                    k, why = kind_of(e)
                    if k != want:
                        continue
                    if not any("b-file" in str(x) or "Table of n, a(n)" in str(x) for x in e.get("link") or []):
                        continue
                    seen.add(a)
                    score = len(e.get("comment") or []) + len(e.get("formula") or []) + 2 * len(e.get("reference") or [])
                    cands[k].append((score, a, off, e, why))
                if not res:
                    break
    pool = []
    for k, lst in cands.items():
        lst.sort(key=lambda x: (x[0], x[1]))
        got = 0
        for score, a, off, e, why in lst:
            if got >= PER_KIND:
                break
            b = net.get(f"https://oeis.org/{a}/b{a[1:]}.txt", f"b{a[1:]}.txt")
            pairs = N.parse_bfile(b or "")
            data = [int(x) for x in str(e.get("data") or "").split(",") if x.strip()]
            if len(pairs) < MIN_TERMS or not data:
                continue
            bvals = {i: v for i, v in pairs}
            if any(bvals.get(off + i) != v for i, v in enumerate(data)):
                continue
            terms = OP.to_table(bvals, off)
            if terms is None or len(terms) <= MIN_TERMS:
                continue
            got += 1
            pool.append({"anum": a, "target": k, "open_problem": why[:400], "name": str(e.get("name") or "")[:160],
                         "keyword": e.get("keyword"), "offset": off, "obscurity": score,
                         "n_comment": len(e.get("comment") or []), "n_formula": len(e.get("formula") or []),
                         "n_reference": len(e.get("reference") or []), "n_bfile": len(pairs),
                         "verified": "b-file agrees with DATA on all %d DATA terms" % len(data), "terms": terms})
            print(k, a, len(terms), e.get("name", "")[:60], "|", why[:80], flush=True)
    out = {"note": OT.NOTE, "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "topics": list(TOPICS),
           "queries": QUERIES, "filter": {"min_terms": MIN_TERMS, "excluded_keywords": sorted(BAD_KW), "per_kind": PER_KIND},
           "candidates": {k: len(v) for k, v in cands.items()}, "pool": pool}
    OT.POOL.write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print("pool", len(pool), {k: len(v) for k, v in cands.items()})


if __name__ == "__main__":
    main()
