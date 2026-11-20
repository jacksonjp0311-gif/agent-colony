"""Item 120 replay: why Hive's pending apply kept deferring, and what the deferral cap would do.

Read-only. Rebuilds Hive's evidence and the self-heal metric rows (cycle -> environment
digest) from the committed history of society/systems/swarm_learn.json and
society/systems/self_heal.json via ``git show`` (no checkout, nothing written), then
replays every ``apply_deferred`` row:

* per reason, how many deferrals and how many distinct environment digests;
* per pending episode (create -> drop / trial), how many digests it spanned;
* the item-120 cap (PENDING_DEFER_CAP ``no_signal_baseline`` deferrals of one action under
  one unchanged digest, counted across drop / re-create) -> how often it would fire.
Usage: python scripts/item120_replay.py [since=2026-11-15] [cap]
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REMEMBER = ("confounded_baseline", "no_signal_baseline", "self_heal_trial_running", "self_heal_trial_open",
            "self_build_trial_open", "hive_rule_trial_open", "reservation_unreadable")
SIGNAL = ("score", "new_oracle_targets", "new_depth", "oracle_pass_delta")


def _history(path: str, since: str) -> list[dict]:
    revs = subprocess.check_output(["git", "-C", str(ROOT), "log", "--since", since, "--format=%h", "--", path],
                                   text=True).split()[::-1]
    out = []
    for r in revs:
        try:
            out.append(json.loads(subprocess.check_output(["git", "-C", str(ROOT), "show", f"{r}:{path}"],
                                                          text=True, stderr=subprocess.DEVNULL)))
        except Exception:  # noqa: BLE001
            continue
    return out


def collect(since: str) -> tuple[list[dict], dict[str, str]]:
    ev: dict[tuple, dict] = {}
    for d in _history("society/systems/swarm_learn.json", since):
        for e in d.get("evidence") or []:
            ev.setdefault((e.get("event"), e.get("cycle_id"), e.get("id") or e.get("reason")), e)
    env: dict[str, str] = {}
    for d in _history("society/systems/self_heal.json", since):
        for r in d.get("metrics") or []:
            if r.get("cycle_id"):
                env[r["cycle_id"]] = str(r.get("env_fingerprint") or "")
    return sorted(ev.values(), key=lambda e: str(e.get("cycle_id") or "")), env


def replay(evidence: list[dict], env: dict[str, str], cap: int = 3) -> dict:
    reasons: Counter = Counter()
    digests: dict[str, set] = {}
    episodes, pend = [], None
    ledger: Counter = Counter()
    capped: set = set()
    fires = []
    for e in evidence:
        ev, cid = e.get("event"), str(e.get("cycle_id") or "")
        digest = env.get(cid, "")
        if ev == "apply_deferred" and e.get("reason") in REMEMBER:
            r = str(e["reason"])
            reasons[r] += 1
            digests.setdefault(r, set()).add(digest)
            if pend is None:
                pend = {"first": cid, "fingerprint": e.get("fingerprint"), "n": 0, "digests": set(), "reasons": Counter()}
            pend["n"] += 1
            pend["digests"].add(digest)
            pend["reasons"][r] += 1
            key = (str(e.get("fingerprint")), digest)
            if r == "no_signal_baseline" and digest and key not in capped:
                ledger[key] += 1
                if ledger[key] >= cap:
                    capped.add(key)
                    fires.append({"cycle_id": cid, "fingerprint": key[0], "digest": digest[:12],
                                  "episode_deferrals": pend["n"]})
        elif ev in ("pending_apply_dropped", "trial_start", "pending_resolved_by_trial") and pend is not None:
            episodes.append({"first": pend["first"], "end": cid, "end_event": ev, "deferrals": pend["n"],
                             "digests": len(pend["digests"]), "reasons": dict(pend["reasons"]),
                             "fingerprint": pend["fingerprint"]})
            pend = None
    return {"deferrals": sum(reasons.values()), "by_reason": dict(reasons),
            "digests_by_reason": {k: len(v) for k, v in digests.items()},
            "episodes": len(episodes),
            "episodes_spanning_2plus_digests": sum(1 for x in episodes if x["digests"] >= 2),
            "longest_episode": max(episodes, key=lambda x: x["deferrals"]) if episodes else None,
            "open_episode": None if pend is None else {**pend, "digests": len(pend["digests"]),
                                                        "reasons": dict(pend["reasons"])},
            "episode_fingerprints": dict(Counter(x["fingerprint"] for x in episodes)),
            "cap": cap, "cap_fires": len(fires), "fires": fires}


if __name__ == "__main__":
    since = sys.argv[1] if len(sys.argv) > 1 else "2026-11-15"
    cap = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    evidence, env = collect(since)
    print(json.dumps({"evidence_rows": len(evidence), "cycles_with_digest": len(env),
                      **replay(evidence, env, cap)}, indent=1, default=str))
