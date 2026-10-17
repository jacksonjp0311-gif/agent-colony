"""Replay HISTORICAL lemma-desk changes through the state probe (evidence for calibration).

For every recorded hard_enable desk decision in society/benchmarks/conjecture_history.jsonl:
  base   = lemma_impl.py at the first commit after the decision (git history)
  before = base with the entry's flag False, after = base with it True (exactly the desk's
           one-flag change; diff-scope allows nothing else)
  both are benchmarked for real (society.benchmarks.lemma_microbench.run in a child process),
  the Oracle pass window is rebuilt from data/commons/oracle.jsonl at the decision time.
Synthetic perturbation CONTROLS (mechanical source edits, rerun for real) on every 3rd change:
  bulk_enable  also enable 10 other disabled entries in the same edit
  drop_checks  also disable 5 enabled entries
  slow         the new check sleeps 0.6 s
  break_one    one existing enabled check is replaced by ``lambda: False``
Output: evals/athanor_probe/replay.jsonl (raw per-block drift + inputs needed to re-judge).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from colony.athanor_coherence import structural_distance  # noqa: E402
from colony.trust.athanor_gate import behaviour_drift  # noqa: E402
from colony.trust.athanor_probe import block_drift, state_blocks  # noqa: E402

IMPL = "society/benchmarks/artifacts/lemma_impl.py"
OUT = Path(__file__).resolve().parent / "replay.jsonl"
CHILD = r"""
import json, sys, pathlib
import society.benchmarks.lemma_microbench as LM
LM.ROOT = pathlib.Path(sys.argv[1])
print("SNAP " + json.dumps(LM.run()))
"""
CACHE: dict[str, dict] = {}


def _ts(s: str) -> float:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def _set_flag(src: str, name: str, value: bool) -> str | None:
    want, have = ("True", "False") if value else ("False", "True")
    m = re.compile(rf'(\("{re.escape(name)}",\s*.*?,\s*)({have}|{want})(\))', re.S).search(src)
    if not m or '\n    ("' in m.group(1):
        return None
    return src[: m.start()] + m.group(1) + want + m.group(3) + src[m.end():]


def _entries(src: str) -> list[tuple[str, bool]]:
    return [(m.group(1), m.group(2) == "True")
            for m in re.finditer(r'^\s{4}\("([A-Za-z0-9_]+)",\s*lambda[^\n]*?,\s*(True|False)\),\s*$', src, re.M)]


def bench(src: str) -> dict:
    key = hashlib.sha256(src.encode()).hexdigest()
    if key in CACHE:
        return CACHE[key]
    import tempfile
    with tempfile.TemporaryDirectory(prefix="probe_replay_") as td:
        (Path(td) / "artifacts").mkdir()
        (Path(td) / "artifacts" / "lemma_impl.py").write_text(src, encoding="utf-8")
        env = {**os.environ, "PYTHONPATH": str(ROOT)}
        try:
            p = subprocess.run([sys.executable, "-c", CHILD, td], cwd=ROOT, env=env, capture_output=True,
                               text=True, timeout=120)
            line = next((l for l in p.stdout.splitlines() if l.startswith("SNAP ")), None)
            snap = json.loads(line[5:]) if line else {"error": (p.stderr or "")[-200:]}
        except subprocess.TimeoutExpired:
            snap = {"error": "timeout"}
    CACHE[key] = snap
    return snap


def main() -> None:
    rows = [json.loads(l) for l in (ROOT / "society/benchmarks/conjecture_history.jsonl").read_text().splitlines() if l.strip()]
    desk = [r for r in rows if r.get("kind") == "hard_enable" and r.get("decision") in ("keep", "revert") and r.get("mutation")]
    commits = [l.split() for l in subprocess.run(["git", "log", "--format=%H %ct", "main"], cwd=ROOT,
                                                 capture_output=True, text=True).stdout.split("\n") if l.strip()][::-1]
    oracle = [json.loads(l) for l in (ROOT / "data/commons/oracle.jsonl").read_text().splitlines() if l.strip()]
    blobs: dict[str, str] = {}

    def impl_at(t: float) -> str | None:
        h = next((c for c, ct in commits if int(ct) > t), None)
        if h is None:
            return None
        if h not in blobs:
            p = subprocess.run(["git", "show", f"{h}:{IMPL}"], cwd=ROOT, capture_output=True, text=True)
            blobs[h] = p.stdout if p.returncode == 0 else ""
        return blobs[h] or None

    jobs = []
    for i, r in enumerate(desk):
        t = _ts(r["ts"])
        base = impl_at(t)
        if not base:
            continue
        name = r["mutation"]
        before, after = _set_flag(base, name, False), _set_flag(base, name, True)
        if not before or not after:
            continue
        prior = [o for o in oracle if _ts(o["ts"]) <= t + 1]
        own = next((j for j in range(len(prior) - 1, max(-1, len(prior) - 40), -1)
                    if prior[j].get("mutation") == name and t - _ts(prior[j]["ts"]) < 900), None)
        win_b = [bool(o.get("passed")) for k, o in enumerate(prior) if k != own][-20:]
        win_a = (win_b + [bool(prior[own].get("passed"))])[-20:] if own is not None else win_b
        oracle_passed = bool(prior[own].get("passed")) if own is not None else None
        base_job = dict(idx=i, ts=r["ts"], mutation=name, decision=r["decision"], oracle_passed=oracle_passed,
                        before_score=r.get("before_score"), oracle=(win_b, win_a))
        jobs.append({**base_job, "variant": "historical", "src": before, "new": after})
        if i % 3 == 0:
            ents = _entries(after)
            off = sorted([n for n, on in ents if not on and n != name], key=lambda n: hashlib.md5(n.encode()).hexdigest())
            on = sorted([n for n, on in ents if on and n != name], key=lambda n: hashlib.md5(n.encode()).hexdigest())
            s = after
            for n in off[:10]:
                s = _set_flag(s, n, True) or s
            jobs.append({**base_job, "variant": "bulk_enable", "src": before, "new": s})
            s = after
            for n in on[:5]:
                s = _set_flag(s, n, False) or s
            jobs.append({**base_job, "variant": "drop_checks", "src": before, "new": s})
            m = re.compile(rf'(\("{re.escape(name)}",\s*)(.*?)(,\s*True\))', re.S).search(after)
            if m and '\n    ("' not in m.group(2):
                s = (after[: m.start()] + m.group(1) + f"(lambda _f=({m.group(2)}): "
                     "(__import__('time').sleep(0.6), _f())[1])" + m.group(3) + after[m.end():])
                jobs.append({**base_job, "variant": "slow", "src": before, "new": s})
            if on:
                m = re.search(rf'(\("{re.escape(on[0])}",\s*)lambda[^\n]*?(,\s*True\),)', after)
                if m:
                    s = after[: m.start()] + m.group(1) + "lambda: False" + m.group(2) + after[m.end():]
                    jobs.append({**base_job, "variant": "break_one", "src": before, "new": s})
    print(f"{len(desk)} desk rows -> {len(jobs)} replay jobs", flush=True)

    def run(j):
        b, a = bench(j["src"]), bench(j["new"])
        if b.get("error") or a.get("error"):
            return {k: v for k, v in j.items() if k not in ("src", "new", "oracle")} | {"error": (b.get("error") or a.get("error"))[:200]}
        sd = structural_distance(j["src"], j["new"])
        cur, new = state_blocks(b, a, oracle=j["oracle"], structural=sd)
        return {k: v for k, v in j.items() if k not in ("src", "new", "oracle")} | {
            "legacy_behaviour": [round(x, 6) for x in behaviour_drift(b, a)],
            "drift": {k: round(v, 6) for k, v in block_drift(cur, new).items()},
            "after_ok": bool(a.get("ok")), "before_ok": bool(b.get("ok")),
            "n_checks": [b.get("n_checks"), a.get("n_checks")], "seconds": [b.get("seconds"), a.get("seconds")],
            "score": [b.get("score"), a.get("score")]}

    # benches run 3 at a time so wall-clock noise resembles a small CI runner, not a idle core
    with ThreadPoolExecutor(max_workers=3) as ex:
        res = list(ex.map(run, jobs))
    OUT.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in res), encoding="utf-8")
    print(f"wrote {len(res)} rows ({sum(1 for r in res if r.get('error'))} errors) -> {OUT}")


if __name__ == "__main__":
    main()
