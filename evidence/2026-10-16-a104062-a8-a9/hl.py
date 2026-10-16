"""Hardy-Littlewood prediction for CONSECUTIVE primes p, p+6, p+12, p+18 (no prime strictly between),
by inclusion-exclusion over the interior points (method of Odlyzko-Rubinstein-Wolf 1999).
Conjectural heuristic (HL k-tuple conjecture is unproven)."""
import itertools, json, math
import numpy as np
from scipy.integrate import quad

LIM = 10**7
s = np.ones(LIM + 1, bool); s[:2] = False
for i in range(2, int(LIM**.5) + 1):
    if s[i]: s[i*i::i] = False
PR = np.nonzero(s)[0]

def sing(H):
    H = sorted(set(H)); k = len(H); lg = 0.0
    for p in PR:
        p = int(p); nu = len({h % p for h in H})
        if nu == p: return 0.0
        if p > H[-1] - H[0]:
            q = PR[PR >= p].astype(float)
            lg += float(np.sum(np.log1p(-k / q) - k * np.log1p(-1 / q)))
            return math.exp(lg)
        lg += math.log(1 - nu / p) - k * math.log(1 - 1 / p)

def Li(x, k):
    return quad(lambda u: math.exp(u) / u**k, math.log(2), math.log(x), limit=400)[0]

BASE = [0, 6, 12, 18]; INTER = [2, 4, 8, 10, 14, 16]
terms = [(S, c) for r in range(7) for S in itertools.combinations(INTER, r) if (c := sing(BASE + list(S)))]
pred = lambda x: sum((-1)**len(S) * c * Li(x, 4 + len(S)) for S, c in terms)

rows = []
for d in (l.split() for l in open("qk.txt")):
    N = int(d[0].split("=")[1]); x = int(d[1]); a = int(d[4])
    full = pred(x); lead = terms[0][1] * Li(x, 4)
    rows.append({"n": len(rows) + 1, "N": N, "p_N": x, "a": a, "hl_tuple_only": lead, "hl_consecutive": full,
                 "actual_over_consecutive": a / full, "actual_over_tuple": a / lead})
json.dump({"C_0_6_12_18": terms[0][1], "terms": [[list(S), c] for S, c in terms], "rows": rows},
          open("hl.json", "w"), indent=1)
print("C(0,6,12,18) =", round(terms[0][1], 6), "| nonzero sets:", len(terms))
for S, c in terms: print("  ", S, round(c, 5))
prev = None
for r in rows:
    print(f"n={r['n']} a={r['a']:>8} a(n)/a(n-1)={'-' if prev is None else f'{r['a']/prev:.4f}':>7} "
          f"HLtuple={r['hl_tuple_only']:12.1f} HLconsec={r['hl_consecutive']:12.1f} act/consec={r['actual_over_consecutive']:.4f} act/tuple={r['actual_over_tuple']:.4f}")
    prev = r["a"]
