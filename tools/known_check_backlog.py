"""Pre-test of the strong known-results check on the surprise backlog (report only; writes
society/frontier/known_check_backlog.json). Backlog = the 31 past surprises of the Stage 2 calibration
(24 settled by hand) + every claim still labelled a surprise in the frontier registry.
Usage: python tools/known_check_backlog.py"""
import json
import re
import sys
from pathlib import Path

R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R))
from colony import frontier_conjectures as FC  # noqa: E402
from colony import known_check as KC  # noqa: E402
from colony import reference_check as RC  # noqa: E402

PAT = [
    (re.compile(r"^(\S+)\(n\) = (-?\d+) \(mod (\d+)\) for all n = (\d+) \(mod (\d+)\)$"), "cong_cls"),
    (re.compile(r"^(\S+)\(n\) = (-?\d+) \(mod (\d+)\) for all n >= 1$"), "cong"),
    (re.compile(r"^(\S+)\(n\) divides (\S+)\(n\) for all n >= 1$"), "divides"),
    (re.compile(r"^(\S+)\(n\) <= (\S+)\(n\) for all n >= 1.*$"), "le"),
    (re.compile(r"^a\(n\) = (\S+)\(n\) satisfies a\(n\+(\d+)\) = (.*)$"), "rec"),
]


def parse_statement(s: str) -> dict | None:
    for rx, k in PAT:
        m = rx.match(s.strip())
        if not m:
            continue
        g = m.groups()
        if k == "cong_cls":
            return {"kind": "cong", "lhs": g[0], "rhs": "", "params": {"r": int(g[1]), "m": int(g[2]), "s": int(g[3]), "q": int(g[4])}}
        if k == "cong":
            return {"kind": "cong", "lhs": g[0], "rhs": "", "params": {"r": int(g[1]), "m": int(g[2]), "s": 0, "q": 1}}
        if k in ("divides", "le"):
            return {"kind": k, "lhs": g[0], "rhs": g[1], "params": {}}
        cs = [0] * int(g[1])
        for ci, j in re.findall(r"(-?\d+)\*a\(n\+(\d+)\)", g[2]):
            cs[int(j)] = int(ci)
        return {"kind": "rec", "lhs": g[0], "rhs": "", "params": {"c": cs}}
    return None


def main() -> None:
    T = FC.Tables(lim=60000, exp_n=2004)
    lookup = FC.default_lookup()
    cal = json.loads((R / "society/frontier/refcheck_calibration.json").read_text())
    st = json.loads((R / "society/systems/frontier_conjectures.json").read_text())
    items = [{"statement": r["statement"], "source": "calibration",
              "hand": not r["hand_rule_now"].startswith("(none"), "old_explained": r["explained"]} for r in cal["rows"]]
    seen = {i["statement"] for i in items}
    for r in st["registry"].values():
        if r.get("unknown") and r["statement"] not in seen:
            items.append({"statement": r["statement"], "source": "registry", "hand": False, "old_explained": None,
                          "oeis_anums": r.get("oeis_anums") or []})
    net, rnet = KC.Net(budget=200), RC.Net()
    rows = []
    for it in items:
        c = parse_statement(it["statement"])
        if c is None:
            rows.append({**it, "new": "unparsed"})
            continue
        c["_le"], c["_re"] = FC.parse(c["lhs"]), FC.parse(c["rhs"]) if c["rhs"] else None
        c["oeis_anums"] = it.get("oeis_anums") or []
        if it["old_explained"] is None:
            it["old_explained"] = bool(RC.check(c, T, rnet, lookup)["explained"])
        kc = KC.check(c, T, net, lookup)
        rows.append({**it, "new_explained": bool(it["old_explained"] or kc["explained"]), "known_check": kc["label"],
                     "step": kc["step"]})
    def tally(sel):
        xs = [r for r in rows if sel(r)]
        return {"n": len(xs), "old": sum(bool(r["old_explained"]) for r in xs), "new": sum(bool(r.get("new_explained")) for r in xs)}
    out = {"note": "Strong known-results check (colony/known_check.py) on the surprise backlog; old = Stage 2 "
                   "reference check alone, new = Stage 2 OR the strong check. Report only.",
           "hand_settled": tally(lambda r: r["hand"]), "calibration_all": tally(lambda r: r["source"] == "calibration"),
           "registry_surprises": tally(lambda r: r["source"] == "registry"),
           "by_step": {s: sum(1 for r in rows if r.get("step") == s) for s in
                       ("tautology", "kernel", "cfinite", "periodic", "oeis_derived", "oeis_text")},
           "rows": rows}
    p = R / "society/frontier/known_check_backlog.json"
    p.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))
    for r in rows:
        if not r.get("new_explained"):
            print("OPEN |", r["source"], "|", r["statement"])


if __name__ == "__main__":
    main()
