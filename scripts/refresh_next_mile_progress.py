#!/usr/bin/env python3
"""Refresh society/NEXT_MILE_PROGRESS.{json,html} from filesystem signals."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECEIPTS = ROOT / "society" / "receipts"
SYSTEMS = ROOT / "society" / "systems"
COLONY = ROOT / "colony"
TESTS = ROOT / "tests"
OUT_JSON = ROOT / "society" / "NEXT_MILE_PROGRESS.json"
OUT_HTML = ROOT / "society" / "NEXT_MILE_PROGRESS.html"


def exists_any(paths):
    return any(p.exists() for p in paths)


def score_hold():
    parts = [
        (COLONY / "hold_posture.py").exists(),
        (SYSTEMS / "hold_posture.json").exists(),
        exists_any(list(TESTS.glob("*hold*"))),
        exists_any(list(RECEIPTS.glob("HOLD*"))),
    ]
    # wire into cli/systems counts as progress
    wired = False
    for p in [COLONY / "cli.py", COLONY / "systems.py", COLONY / "__main__.py"]:
        if p.exists() and "hold_posture" in p.read_text(encoding="utf-8", errors="ignore"):
            wired = True
            break
    parts.append(wired)
    return sum(parts) / len(parts), "hold_posture.py" if parts[0] else "queued"


def score_h7():
    md = list(RECEIPTS.glob("H7*"))
    js = list(RECEIPTS.glob("H7*.json"))
    script = exists_any(list((ROOT / "scripts").glob("*h7*")) + list(COLONY.glob("*h7*")) + list(COLONY.glob("*diagnos*")))
    parts = [bool(md), bool(js), script]
    # partial credit if athanor commons freshly touched during diagnosis runs
    detail = "diagnosing residuals"
    if md:
        detail = md[0].name
    elif script:
        detail = "diagnosis script present"
    return (sum(parts) / max(len(parts), 1)) * (1.0 if (md or js) else (0.45 if script else 0.08)), detail


def score_cortex():
    mods = list(COLONY.glob("*cerebr*")) + list(COLONY.glob("*cortex*"))
    sysf = list(SYSTEMS.glob("*cerebr*")) + list(SYSTEMS.glob("*cortex*"))
    tests = list(TESTS.glob("*cerebr*")) + list(TESTS.glob("*cortex*"))
    rcpt = list(RECEIPTS.glob("CORTEX*")) + list(RECEIPTS.glob("*CEREBR*"))
    # Weight modules higher when both cerebrum + cortex exist
    mod_score = min(1.0, 0.35 * len(mods))  # 2 files => 0.70
    parts = [mod_score, 0.15 if sysf else 0.0, 0.1 if tests else 0.0, 0.05 if rcpt else 0.0]
    # wired into oracle/actuation/systems
    wired = False
    for path in [COLONY / "oracle.py", COLONY / "actuation.py", COLONY / "systems.py", COLONY / "cli.py"]:
        if path.exists():
            t = path.read_text(encoding="utf-8", errors="ignore")
            if "cerebrum" in t or "cortex_sidecar" in t:
                wired = True
                break
    if wired:
        parts.append(0.15)
    detail = ", ".join(m.name for m in mods[:3]) if mods else "awaiting module"
    return min(1.0, sum(parts)), detail


def score_verify():
    impl = exists_any(list(RECEIPTS.glob("NEXT_MILE_IMPLEMENTED*")))
    sketch = RECEIPTS / "NEXT_MILE_SKETCH.json"
    sketch_done = False
    if sketch.exists():
        try:
            data = json.loads(sketch.read_text())
            sketch_done = "implement" in str(data.get("status", "")).lower() or data.get("implemented") is True
        except Exception:
            pass
    parts = [impl, sketch_done]
    # pytest evidence file optional
    return (1.0 if impl else (0.35 if sketch_done else 0.05)), ("NEXT_MILE_IMPLEMENTED" if impl else "tests + receipts")


def main():
    steps_meta = [
        ("hold", "Hold + selective authorize", 30, score_hold),
        ("h7", "H₇ residual diagnosis", 25, score_h7),
        ("cortex", "Cortex / Cerebrum sidecar", 30, score_cortex),
        ("verify", "Verify + slim receipts", 15, score_verify),
        ("charters", "Institution standing charters", 15, score_charters),
        ("pilot_lane", "Proposal→pilot sandbox lane", 15, score_pilot_lane),
    ]
    steps = []
    overall = 0.0
    for sid, label, weight, fn in steps_meta:
        pct_f, detail = fn()
        pct = round(100 * max(0.0, min(1.0, pct_f)), 1)
        status = "done" if pct >= 99.5 else ("active" if pct > 5 else "pending")
        steps.append({"id": sid, "label": label, "weight": weight, "pct": pct, "status": status, "detail": detail})
        overall += weight * pct / 100.0
    progress = {
        "title": "Next mile — live progress",
        "updated_et": datetime.now().strftime("%Y-%m-%d %I:%M:%S %p ET"),
        "overall_pct": round(overall, 1),
        "steps": steps,
        "note": "Live bar tracks implementation of hold · H₇ · Cortex/Cerebrum · verify",
    }
    OUT_JSON.write_text(json.dumps(progress, indent=2) + "\n")
    # HTML
    bars = ""
    for s in steps:
        bars += f"""    <div class=\"step\">
      <div class=\"row\"><span class=\"label\">{s['label']}</span><span class=\"badge {s['status']}\">{s['status']} · {s['pct']}%</span></div>
      <div class=\"mini\"><i style=\"width:{s['pct']}%\"></i></div>
      <div class=\"detail\">{s['detail']}</div>
    </div>
"""
    html = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\"/>
<meta http-equiv=\"refresh\" content=\"8\"/>
<title>Next mile progress</title>
<style>
  :root {{ --bg:#0b1020; --bar:#1a2540; --fill:#5b8cff; --fill2:#7cf0c3; --active:#ffd166; --done:#5eead4; --muted:#8b9bb8; --ink:#e8eefc; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center; font-family: ui-sans-serif, system-ui, sans-serif; background: radial-gradient(1200px 600px at 20% 0%, #182447 0%, var(--bg) 55%); color:var(--ink); }}
  .card {{ width:min(720px, 94vw); background:linear-gradient(180deg,#15203a,#101828); border:1px solid #243356; border-radius:20px; padding:28px; box-shadow:0 20px 60px rgba(0,0,0,.45); }}
  h1 {{ margin:0 0 4px; font-size:22px; }}
  .meta {{ color:var(--muted); font-size:13px; margin-bottom:22px; }}
  .overall {{ display:flex; justify-content:space-between; align-items:baseline; margin-bottom:8px; }}
  .pct {{ font-size:34px; font-weight:700; color:var(--fill2); }}
  .track {{ height:18px; background:var(--bar); border-radius:999px; overflow:hidden; border:1px solid #2a3b63; margin-bottom:26px; }}
  .fill {{ height:100%; width:{progress['overall_pct']}%; background:linear-gradient(90deg,var(--fill),var(--fill2)); box-shadow:0 0 18px rgba(124,240,195,.35); transition:width .8s ease; }}
  .step {{ margin:14px 0; }}
  .row {{ display:flex; justify-content:space-between; font-size:14px; margin-bottom:6px; }}
  .label {{ font-weight:600; }}
  .badge {{ font-size:11px; text-transform:uppercase; letter-spacing:.06em; padding:2px 8px; border-radius:999px; border:1px solid #33466f; color:var(--muted); }}
  .badge.active {{ color:#1a1400; background:var(--active); border-color:transparent; }}
  .badge.done {{ color:#042f2e; background:var(--done); border-color:transparent; }}
  .mini {{ height:8px; background:#18233d; border-radius:999px; overflow:hidden; }}
  .mini > i {{ display:block; height:100%; background:linear-gradient(90deg,#4f7cff,#9ae6ff); }}
  .detail {{ color:var(--muted); font-size:12px; margin-top:4px; }}
  .foot {{ margin-top:18px; color:var(--muted); font-size:12px; }}
</style>
</head>
<body>
  <div class=\"card\">
    <h1>Agent Colony — next mile</h1>
    <div class=\"meta\">Live progress · auto-refreshes · {progress['updated_et']}</div>
    <div class=\"overall\"><span>Overall</span><span class=\"pct\">{progress['overall_pct']}%</span></div>
    <div class=\"track\"><div class=\"fill\"></div></div>
{bars}    <div class=\"foot\">{progress['note']}</div>
  </div>
</body>
</html>
"""
    OUT_HTML.write_text(html)
    print(json.dumps({"overall_pct": progress["overall_pct"], "steps": [(s["id"], s["pct"], s["status"]) for s in steps]}))




def score_charters():
    parts = [
        (COLONY / "institution_charters.py").exists(),
        (SYSTEMS / "institution_charters.json").exists(),
        exists_any(list(TESTS.glob("*charter*"))),
        exists_any(list(RECEIPTS.glob("INSTITUTION_CHARTERS*"))),
    ]
    wired = False
    for path in [COLONY / "systems.py", COLONY / "emergence" / "growth.py", COLONY / "cli.py"]:
        if path.exists() and "institution_charters" in path.read_text(encoding="utf-8", errors="ignore"):
            wired = True
            break
    parts.append(wired)
    detail = "institution_charters.py" if parts[0] else "queued"
    return sum(parts) / len(parts), detail


def score_pilot_lane():
    parts = [
        (COLONY / "pilot_lane.py").exists(),
        (SYSTEMS / "pilot_lane.json").exists(),
        (ROOT / "society" / "sandbox_pilots").exists(),
        exists_any(list(TESTS.glob("*pilot*"))),
        exists_any(list(RECEIPTS.glob("PILOT_LANE*"))),
    ]
    wired = False
    for path in [COLONY / "systems.py", COLONY / "emergence" / "growth.py", COLONY / "cli.py"]:
        if path.exists() and "pilot_lane" in path.read_text(encoding="utf-8", errors="ignore"):
            wired = True
            break
    parts.append(wired)
    detail = "pilot_lane.py" if parts[0] else "queued"
    return sum(parts) / len(parts), detail


if __name__ == "__main__":
    main()
