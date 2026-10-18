"""Cycle metrics over UTC windows: python tools/cycle_metrics.py T0 T1 [T0 T1 ...]. Vetoes = gate rows whose veto.vetoed is true (the old count treated the always-present veto dict as a veto)."""
import json, sys, subprocess, collections
from pathlib import Path
R = Path(__file__).resolve().parent.parent; W = list(zip(sys.argv[1::2], sys.argv[2::2])); T0, T1 = W[0][0], W[-1][1]
def rows(p):
    out=[]
    for l in (R/p).read_text().splitlines():
        try: out.append(json.loads(l))
        except Exception: pass
    return out
inw = lambda r: any(a <= str(r.get("ts","")) <= b for a, b in W)
fit = [r for r in rows("society/systems/fitness_history.jsonl") if inw(r)]
desk = [r for r in rows("society/benchmarks/conjecture_history.jsonl") if inw(r)]
orc = [r for r in rows("data/commons/oracle.jsonl") if inw(r)]
gate = [r for r in json.loads((R/"society/systems/athanor_gate.json").read_text())["rows"] if inw(r)]
fr = [r for r in json.loads((R/"society/systems/frontier_conjectures.json").read_text())["history"] if inw(r)]
print("cycles", len(fit), "desk", dict(collections.Counter(r.get("decision") for r in desk)))
print("keeps", [r["mutation"] for r in desk if r.get("decision")=="keep"])
print("oracle passes", sum(1 for r in orc if r.get("passed")), "kills", sum(1 for r in orc if r.get("passed") is False))
ag=[r["aggregate"] for r in fit]; nv=[r["novelty"] for r in fit]
if ag: print("fitness avg %.4f min %.4f max %.4f novelty avg %.4f" % (sum(ag)/len(ag), min(ag), max(ag), sum(nv)/len(nv)))
print("gate", len(gate), dict(collections.Counter(r.get("verdict") for r in gate)), "blocks", sum(1 for r in gate if r.get("would_block")), "vetoes", sum(1 for r in gate if (r.get("veto") or {}).get("vetoed") if isinstance(r.get("veto"), dict)) + sum(1 for r in gate if r.get("veto") is True), "would_veto", sum(1 for r in gate if r.get("would_veto")))
log = subprocess.run(["git","-C",str(R),"log","--since",T0,"--until",T1,"--format=%H","--","society/shortlist/SHORTLIST.json"],capture_output=True,text=True).stdout.split()
mb=[]
for h in reversed(log):
    try: mb.append(json.loads(subprocess.run(["git","-C",str(R),"show",f"{h}:society/shortlist/SHORTLIST.json"],capture_output=True,text=True).stdout)["n_meet_bar"])
    except Exception: pass
print("shortlist meet_bar", mb)
agg=collections.Counter()
for r in fr:
    for k,v in r.items():
        if isinstance(v,int): agg[k]+=v
print("frontier cycles", len(fr), {k:v for k,v in sorted(agg.items()) if v})
