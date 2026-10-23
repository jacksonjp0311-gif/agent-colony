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
Computable group (DEF_QUERIES, up to MAX_DEF_ENTRIES, listed first): entries whose NAME is an explicit
definition (closed form, recurrence, rational or algebraic g.f.) parsed into a vetted evaluator
(no fetched code is ever executed; FORMULA/PROGRAM lines are never used as the definition, since they
can be the conjecture itself). The definition must reproduce the whole b-file or the entry is dropped.
Stored terms are capped (DEF_DIGITS / MAX_DIGITS); 'published_hi' keeps the real published range.
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
# Sequences whose NAME is a computable definition (g.f. / closed form / recurrence) and that carry a
# conjecture. Only the name is used as the definition: FORMULA and PROGRAM lines can be the conjecture
# itself (a LinearRecurrence[] program typed from a conjectured recurrence would make the check circular).
DEF_QUERIES = ('formula:"Conjecture: D-finite" name:"Expansion of"', 'formula:"Conjecture: D-finite" name:sqrt',
               'formula:"Conjecture: D-finite" name:"a(n) ="', 'formula:Conjecture name:"a(n) ="',
               'comment:Conjecture name:"a(n) ="', 'formula:Conjecture name:"Expansion of"',
               'comment:Conjecture name:"Expansion of"', 'formula:Conjecture name:"G.f."',
               'comment:Conjecture name:"G.f."', 'formula:"Conjecture: D-finite" name:"G.f."',
               'comment:"Conjecture" name:"2^n"', 'comment:"Conjecture" name:"binomial"',
               'comment:"conjecture" name:"prime" name:"a(n) ="',
               'formula:"Conjecture D-finite" name:"Expansion of"', 'formula:"D-finite" formula:Conjecture name:"Expansion of"',
               'formula:"D-finite" formula:Conjecture name:"G.f."', 'formula:Conjecture name:"Expansion of" name:sqrt',
               'formula:"Conjecture: a(n) =" name:"Expansion of"', 'formula:"Conjecture D-finite" name:"G.f."')
DEF_PAGES = 15
MAX_DEF_ENTRIES = 60
BAD_KW = {"tabl", "tabf", "cons", "frac", "fini", "full", "word", "dead", "dumb", "uned", "obsc"}
PAGES = 3
MAX_ENTRIES = 40
MAX_TERMS = 3000
MAX_DIGITS = 150   # stored terms stop here; published_hi keeps the real published range
DEF_DIGITS = 120   # stored terms of computable entries stop here; published_hi keeps the real published range
REF_TERMS = 1100
MIN_TERMS = 40
MIN_DEF_TERMS = 15   # a computable definition supplies the terms beyond the published range


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


def bfile(net, a, data=None, digits=MAX_DIGITS):
    txt = net.get(f"https://oeis.org/{a}/b{a[1:]}.txt", f"b{a[1:]}.txt")
    pairs = N.parse_bfile(txt or "")
    if not pairs:
        return None
    o = pairs[0][0]
    xs = []
    pub = pairs[-1][0]
    for i, (k, v) in enumerate(pairs):
        if k != o + i or len(str(abs(v))) > digits or len(xs) >= MAX_TERMS:
            break
        xs.append(v)
    if data and xs[:len(data)] != data[:len(xs)]:
        return None
    return o, xs, pub


def verified_definition(ent):
    """The name's definition must reproduce the WHOLE b-file (fast generator or exact recomputation)."""
    from colony import oeis_deep as D
    from colony import oeis_guess as G
    d, off, terms = ent["definition"], ent["offset"], ent["terms"]
    try:
        if d["kind"] == "alg":
            cr = G.certified_recurrence(d["expr"], off, terms)
            return bool(cr) and D.matches_bfile(D.Holo(cr, off), off, terms)
        g = D.generator(ent)
        if g is not None:
            return D.matches_bfile(g, off, terms)
        return OC.extend(d, off, terms, len(terms) + 1, "A", seconds=6) is not None
    except Exception:  # noqa: BLE001
        return False


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
    for qi, q in enumerate(DEF_QUERIES):
        for page in range(DEF_PAGES):
            qq = q + " -keyword:tabl -keyword:dead"
            url = "https://oeis.org/search?fmt=json&start=%d&q=%s" % (10 * page, qq.replace(" ", "+").replace('"', "%22"))
            txt = net.get(url, "cjd_%d_%d.json" % (qi, page))
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
            has_def = OC.parse_definition(str(e.get("name") or "")) is not None
            stats["def_candidates"] = stats.get("def_candidates", 0) + int(has_def)
            cands.append((0 if has_def else 1, score, a, e, sec, ln, block, claim))
    cands.sort(key=lambda c: (c[0], c[1], c[2]))
    entries, per_anum = [], {}
    n_def = n_plain = 0
    for grp, score, a, e, sec, ln, block, claim in cands:
        if n_def >= MAX_DEF_ENTRIES and n_plain >= MAX_ENTRIES:
            break
        if (grp == 0 and n_def >= MAX_DEF_ENTRIES) or (grp == 1 and n_plain >= MAX_ENTRIES):
            continue
        if per_anum.get(a, 0) >= 3:
            continue
        data = [int(x) for x in str(e.get("data") or "").split(",") if x.strip()]
        off = int(str(e.get("offset") or "0").split(",")[0])
        b = bfile(net, a, data, MAX_DIGITS if grp else DEF_DIGITS)
        if not b or b[0] != off or len(b[1]) < max(MIN_TERMS if grp else MIN_DEF_TERMS, len(data)):
            stats["no_bfile"] += 1
            if not grp:
                stats["def_no_bfile"] = stats.get("def_no_bfile", 0) + 1
            print("  no b-file", a, b and (b[0], len(b[1])), off, len(data), flush=True)
            continue
        refs, ok = {}, True
        for r in OC.refs(claim):
            rb = bfile(net, r, None, max(MAX_DIGITS if grp else DEF_DIGITS, max(len(str(abs(x))) for x in b[1]) + 5))
            if not rb:
                ok = False
                break
            refs[r] = {"offset": rb[0], "terms": rb[1][:min(REF_TERMS, off + len(b[1]) + 12 - rb[0])]}
        if not ok:
            stats["no_bfile"] += 1
            continue
        ent = {"id": "oc_%s_%d" % (a, per_anum.get(a, 0)), "anum": a, "name": str(e.get("name") or "")[:300],
               "offset": off, "keyword": e.get("keyword"), "section": sec, "text": ln,
               "block_header": block, "claim": claim, "obscurity": score, "data_n": len(data),
               "definition": OC.parse_definition(str(e.get("name") or "")), "refs": refs, "terms": b[1],
               "published_hi": b[2]}
        chk = OC.test_claim(claim, OC._tables(ent, b[1][:len(data)]) if claim["form"] != "gf" else
                            OC._tables(ent, b[1][:len(data)]), "A")
        if chk["tested"] < 3 or chk["first_fail"] is not None:
            stats["fails_on_data"] += 1
            if not grp:
                stats["def_fails_on_data"] = stats.get("def_fails_on_data", 0) + 1
            print("  data-check fail", a, chk["tested"], chk["first_fail"], ln[:70], flush=True)
            continue
        if ent["definition"] and not verified_definition(ent):
            ent["definition"] = None   # does not reproduce the b-file: not trusted
            stats["def_mismatch"] = stats.get("def_mismatch", 0) + 1
        if grp == 0 and not ent["definition"]:
            continue
        if ent["definition"]:
            n_def += 1
        else:
            n_plain += 1
        per_anum[a] = per_anum.get(a, 0) + 1
        entries.append(ent)
        print(a, claim["form"], len(b[1]), "def" if ent["definition"] else "-", "|", ln[:90], flush=True)
    stats["kept"] = len(entries)
    stats["with_definition"] = n_def
    stats["definition_kinds"] = {}
    for x in entries:
        if x["definition"]:
            k = x["definition"]["kind"]
            stats["definition_kinds"][k] = stats["definition_kinds"].get(k, 0) + 1
    out = {"note": "OEIS conjectures as colony targets; exact quoted text; built by tools/build_oeis_conjectures.py "
                   "(free OEIS, cached, <= 1 request / 2 s). Nothing here is authorized or posted.",
           "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "stats": stats, "entries": entries}
    OC.MENU.write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
