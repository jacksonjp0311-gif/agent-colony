"""Calibrate the hunt expected-discount prior K (colony.hunt_shadow.K_PRIOR) on Oracle history.

Model: the hunt rule's "expected" = s / (s + K) is read literally as a predictive probability:
the chance that the next member of a claim family, after s kept (Oracle-passed) members, does what
its family already did (is kept too), i.e. brings NO new information. That is the Laplace /
Dirichlet rule of succession with prior weight K on "something new". K is fitted by maximum
likelihood of exactly that prediction on the TUNING split (events with s >= 1; s = 0 gives
expected = 0 by definition). Closed form: 1/K = mean over tuning events of 1/(s + K) times the
number of events / number of surprises; solved on a log grid. The held-out split reports the
predictive log-loss of the fitted K against the old hand-set K = 3.

Data: society/benchmarks/conjecture_history.jsonl hard_enable rows, the FIRST desk decision per
member (later retries of the same member add no member information); family =
colony.hunt_shadow.claim_family; n = earlier members of the family that were kept (Oracle-passed),
matching the hunt rule's s; "new information" = the member was NOT kept (Oracle kill / desk revert /
gate block: the family did something its kept members had not).
Split: the Athanor-probe split (2026-10-16T23:20:31Z) is tried first. If its tuning side holds no
event with n >= 1, K is unidentifiable there (multi-member families only appeared after it), so the
script falls back to a chronological split at the 60th percentile of the n >= 1 events and says so.
Writes colony/hunt_calibration.json and docs/HUNT_TUNING_LOG.md.
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from colony.hunt_shadow import claim_family  # noqa: E402

SPLIT = "2026-10-16T23:20:31Z"
OUT = ROOT / "colony" / "hunt_calibration.json"
LOG = ROOT / "docs" / "HUNT_TUNING_LOG.md"
K_GRID = [round(0.01 * 1.05 ** i, 5) for i in range(200)]  # 0.01 .. ~170


def sequences(rows):
    """Chronological (family, n_prior_kept, n_prior_surprises, surprise, ts) events."""
    fam_kept, fam_s, seen, ev = defaultdict(set), defaultdict(int), set(), []
    for r in sorted(rows, key=lambda r: r.get("ts", "")):
        m = str(r.get("mutation") or "")
        if r.get("kind") != "hard_enable" or not m or m in seen:
            continue
        seen.add(m)
        f = claim_family(m)
        y = r.get("decision") != "keep"
        ev.append((f, len(fam_kept[f]), fam_s[f], y, r["ts"]))
        if y:
            fam_s[f] += 1
        else:
            fam_kept[f].add(m)
    return ev


def loglik(ev, K):
    """Log-likelihood of P(repeat) = s/(s+K) over events with s >= 1."""
    ll = 0.0
    for _f, s, _d, y, _ts in ev:
        if s < 1:
            continue
        p = K / (s + K)  # chance of new information
        ll += math.log(p if y else 1 - p)
    return ll


def fit(ev):
    pts = [(loglik(ev, K), K) for K in K_GRID]
    best = max(pts)
    edge = best[1] in (K_GRID[0], K_GRID[-1])
    return {"K": best[1], "loglik": round(best[0], 4), "at_grid_edge": edge}


def main():
    rows = [json.loads(l) for l in (ROOT / "society/benchmarks/conjecture_history.jsonl").read_text().splitlines()
            if l.strip()]
    ev = sequences(rows)
    split, split_note = SPLIT, "athanor-probe split"
    if not any(e[1] > 0 for e in ev if e[4] < SPLIT):
        later = sorted(e[4] for e in ev if e[1] > 0)
        split = later[int(0.6 * len(later))]
        split_note = (f"fallback: the {SPLIT} split has no repeat-family members on its tuning side "
                      "(K unidentifiable); chronological split at the 60th percentile of repeat members")
    tune = [e for e in ev if e[4] < split]
    held = [e for e in ev if e[4] >= split]
    f = fit(tune)
    rep_t = [e for e in tune if e[1] > 0]
    base = sum(e[3] for e in rep_t) / max(1, len(rep_t))

    def ll_const(es):
        p = min(max(base, 1e-9), 1 - 1e-9)
        return sum(math.log(p if e[3] else 1 - p) for e in es if e[1] > 0)

    nh = max(1, sum(1 for e in held if e[1] > 0))

    rep = {
        "fitted": f,
        "tuning": {"events": len(tune), "surprises": sum(e[3] for e in tune),
                   "surprises_after_first_member": sum(e[3] for e in tune if e[1] > 0),
                   "members_after_first": sum(1 for e in tune if e[1] > 0)},
        "held_out": {"events": len(held), "surprises": sum(e[3] for e in held),
                     "surprises_after_first_member": sum(e[3] for e in held if e[1] > 0),
                     "members_after_first": sum(1 for e in held if e[1] > 0),
                     "logloss_per_event": {
                         "fitted_K": round(-loglik(held, f["K"]) / nh, 4),
                         "K=3": round(-loglik(held, 3.0) / nh, 4),
                         "constant_rate_from_tuning": round(-ll_const(held) / nh, 4)},
                     "mean_expected_fitted_K": round(sum(e[1] / (e[1] + f["K"]) for e in held if e[1] > 0) / nh, 4),
                     "mean_expected_K3": round(sum(e[1] / (e[1] + 3.0) for e in held if e[1] > 0) / nh, 4)},
    }
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cal = {"version": 1, "calibrated_at": ts, "K_PRIOR": f["K"], "split": split, "split_note": split_note,
           "source": "evals/hunt/calibrate_k.py (rule-of-succession ML on tuning desk history)", **rep}
    OUT.write_text(json.dumps(cal, indent=2) + "\n", encoding="utf-8")
    h = rep["held_out"]
    LOG.write_text("\n".join([
        "# Hunt expected-discount prior K — tuning log", "",
        f"Calibrated {ts} by `evals/hunt/calibrate_k.py`. Model: rule of succession — expected = s/(s+K) is the "
        "predicted chance that the next member of a claim family, after s kept members, is kept too (no new "
        "information); 1-expected = K/(s+K) is the chance it brings something new (Oracle kill / revert / block). "
        "K fitted by maximum likelihood on the tuning split only.", "",
        f"- Split: {split} ({split_note}).",
        f"- Tuning (< {split}): {rep['tuning']['events']} family-member verdicts, {rep['tuning']['surprises']} surprises; "
        f"members after a family's first: {rep['tuning']['members_after_first']}, surprises among them: "
        f"{rep['tuning']['surprises_after_first_member']}.",
        f"- Fitted K = {f['K']} (log-lik {f['loglik']}, at grid edge: {f['at_grid_edge']}); was K = 3 (hand-set).",
        f"- Held-out: {h['events']} verdicts, {h['surprises']} surprises; members after first {h['members_after_first']}, "
        f"surprises among them {h['surprises_after_first_member']}.",
        f"- Held-out predictive log-loss per verdict: fitted K {h['logloss_per_event']['fitted_K']}, "
        f"K=3 {h['logloss_per_event']['K=3']}, constant rate {h['logloss_per_event']['constant_rate_from_tuning']} "
        "(lower is better; over members with s >= 1).",
        f"- Mean held-out expected: fitted K {h['mean_expected_fitted_K']}, K=3 {h['mean_expected_K3']}.",
        "- Caveat: surprises are rare (single digits), so K is estimated from very few events; it is re-fitted "
        "by re-running the script, and the loader falls back to K=3 if the file is missing.", ""]), encoding="utf-8")
    print(json.dumps(cal, indent=1))


if __name__ == "__main__":
    main()
