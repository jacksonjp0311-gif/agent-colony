"""Build the OEIS-conjecture target menu (colony/oeis_conjectures.py).

Free public OEIS only; polite (one request per 2 s, cached via colony.new_data.Net). A mechanism:
fixed OEIS JSON searches for 'Conjecture' in FORMULA / COMMENT lines, then for every hit
  * every line containing 'conjectur' (and the lines of a 'Conjectures from ... (Start)' block) is
    a candidate statement, quoted EXACTLY;
  * the whole entry is skipped when any line says a conjecture is true / proved / false /
    has a counterexample / follows from a known result (oeis_conjectures.RESOLVED);
  * keyword filter: not tabl, tabf, cons, frac, fini, full, word, dead, dumb, uned, obsc;
  * the statement must normalise into a testable form (oeis_conjectures.normalize) and hold on the
    DATA range (a parse sanity check: a failure on terms the author saw is a misparse);
  * a b-file that agrees with DATA (target and every referenced A-number);
ranked fewest-studied first (#comment + #formula + 2 #reference), up to MAX_ENTRIES.
Usage: python tools/build_oeis_conjectures.py"""
import json
import re
import sys
import time
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
from colony import new_data as N  # noqa: E402
from colony import oeis_conjectures as OC  # noqa: E402

TOPICS = ("recurrence", "primes", "divisors", "binary", "partitions", "sum", "digits", "congruence", "mod",
          "positive", "squarefree", "odd")
EXTRA = ('formula:Conjecture name:"Expansion of"', 'formula:Conjecture name:"a(n) ="',
         'comment:Conjecture name:"a(n) ="', 'formula:"(conjectured)"', 'formula:"(conjecture)"')
BAD_KW = {"tabl", "tabf", "cons", "frac", "fini", "full", "word", "dead", "dumb", "uned", "obsc"}
PAGES = 3
MAX_ENTRIES = 60
MAX_TERMS = 3000
MAX_DIGITS = 300
MIN_TERMS = 40


def statements(e):
    out = []
    for sec in ("formula", "comment"):
        lines = [str(x) for x in e.get(sec) or []]
        block = None
        for ln in lines:
            if block is not None:
                if "(End)" in ln and not re.search(r"[a-z]\(n", ln):
                    block = None
                    continue
                out.append((sec, ln, block))
                if "(End)" in ln:
                    block = None
                continue
            if re.search(r"Conjectur\w* from .*\(Start\)", ln):
                block = ln
                continue
            if OC.CONJ.search(ln):
                out.append((sec, ln, None))
    return out


def resolved(e):
    for sec in ("formula", "comment", "example", "extensions"):
        for ln in e.get(sec) or []:
            if OC.RESOLVED.search(str(ln)):
                return True
    return False


def bfile(net, a, data=None):
    txt = net.get(f"https://oeis.org/{a}/b{a[1:]}.txt", f"b{a[1:]}.txt")
    pairs = N.parse_bfile(txt or "")
    if not pairs:
        return None
    o = pairs[0][0]
    xs = []
    for i, (k, v) in enumerate(pairs):
        if k != o + i or len(str(abs(v))) > MAX_DIGITS or len(xs) >= MAX_TERMS:
            break
        xs.append(v)
    if data and xs[:len(data)] != data[:len(xs)]:
        return None
    return o, xs


def main():
    N.NET_MAX_PER_CYCLE = 10 ** 6
    net = N.Net()
    raw = {}
    queries = []
    for f in ("formula", "comment"):
        for t in TOPICS:
            queries += [(f"{f}:Conjecture keyword:nonn -keyword:core -keyword:nice -keyword:tabl -keyword:cons {t}",
                         f"cj_{f}_{t}_%d.json")]
    for i, q in enumerate(EXTRA):
        queries.append((q + " keyword:nonn -keyword:tabl", f"cjx_{i}_%d.json"))
    for q, fn in queries:
        for page in range(PAGES):
            url = "https://oeis.org/search?fmt=json&start=%d&q=%s" % (10 * page, q.replace(" ", "+").replace('"', "%22"))
            txt = net.get(url, fn % page)
            try:
                res = json.loads(txt or "null") or []
            except ValueError:
                res = []
            if isinstance(res, dict):
                res = res.get("results") or []
            for e in res:
                raw["A%06d" % e["number"]] = e
            if len(res) < 10:
                break
    print("entries", len(raw), flush=True)
    stats = {"entries": len(raw), "resolved_skipped": 0, "keyword_skipped": 0, "statements": 0, "parsed": 0,
             "no_bfile": 0, "fails_on_data": 0, "kept": 0, "reasons": {}}
    cands = []
    for a, e in sorted(raw.items()):
        kw = set(str(e.get("keyword") or "").split(","))
        if kw & BAD_KW:
            stats["keyword_skipped"] += 1
            continue
        if resolved(e):
            stats["resolved_skipped"] += 1
            continue
        for sec, ln, block in statements(e):
            stats["statements"] += 1
            try:
                claim = OC.normalize(ln)
            except (OC.Unparsed, Exception) as ex:  # noqa: BLE001
                r = str(ex).split(":")[0][:30]
                stats["reasons"][r] = stats["reasons"].get(r, 0) + 1
                continue
            stats["parsed"] += 1
            score = len(e.get("comment") or []) + len(e.get("formula") or []) + 2 * len(e.get("reference") or [])
            cands.append((score, a, e, sec, ln, block, claim))
    cands.sort(key=lambda c: (c[0], c[1]))
    entries, per_anum = [], {}
    for score, a, e, sec, ln, block, claim in cands:
        if len(entries) >= MAX_ENTRIES:
            break
        if per_anum.get(a, 0) >= 2:
            continue
        data = [int(x) for x in str(e.get("data") or "").split(",") if x.strip()]
        off = int(str(e.get("offset") or "0").split(",")[0])
        b = bfile(net, a, data)
        if not b or b[0] != off or len(b[1]) < max(MIN_TERMS, len(data)):
            stats["no_bfile"] += 1
            print("  no b-file", a, b and (b[0], len(b[1])), off, len(data), flush=True)
            continue
        refs, ok = {}, True
        for r in OC.refs(claim):
            rb = bfile(net, r)
            if not rb:
                ok = False
                break
            refs[r] = {"offset": rb[0], "terms": rb[1]}
        if not ok:
            stats["no_bfile"] += 1
            continue
        ent = {"id": "oc_%s_%d" % (a, per_anum.get(a, 0)), "anum": a, "name": str(e.get("name") or "")[:300],
               "offset": off, "keyword": e.get("keyword"), "section": sec, "text": ln,
               "block_header": block, "claim": claim, "obscurity": score, "data_n": len(data),
               "definition": OC.parse_definition(str(e.get("name") or "")), "refs": refs, "terms": b[1]}
        chk = OC.test_claim(claim, OC._tables(ent, b[1][:len(data)]) if claim["form"] != "gf" else
                            OC._tables(ent, b[1][:len(data)]), "A")
        if chk["tested"] < 3 or chk["first_fail"] is not None:
            stats["fails_on_data"] += 1
            print("  data-check fail", a, chk["tested"], chk["first_fail"], ln[:70], flush=True)
            continue
        if ent["definition"] and OC.extend(ent["definition"], off, b[1], len(b[1]) + 1, "A", seconds=3) is None:
            ent["definition"] = None   # does not reproduce the b-file: not trusted
        per_anum[a] = per_anum.get(a, 0) + 1
        entries.append(ent)
        print(a, claim["form"], len(b[1]), "def" if ent["definition"] else "-", "|", ln[:90], flush=True)
    stats["kept"] = len(entries)
    out = {"note": "OEIS conjectures as colony targets; exact quoted text; built by tools/build_oeis_conjectures.py "
                   "(free OEIS, cached, <= 1 request / 2 s). Nothing here is authorized or posted.",
           "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "stats": stats, "entries": entries}
    OC.MENU.write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
