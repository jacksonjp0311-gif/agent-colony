"""Refresh DASHBOARD.html and WITNESS_SUMMARY.md from live state."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def refresh_dashboard(root: Path | None = None) -> dict[str, Path]:
    root = root or ROOT
    state = json.loads((root / "data" / "society_state.json").read_text(encoding="utf-8"))
    ledger_path = root / "data" / "ledger.jsonl"
    witness_path = root / "data" / "witness.jsonl"

    def count_jsonl(p: Path) -> int:
        if not p.exists():
            return 0
        return sum(1 for line in p.open() if line.strip())

    status_counts = {"candidate": 0, "accepted": 0, "rejected": 0, "unknown": 0}
    if ledger_path.exists():
        for line in ledger_path.open():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                s = d.get("status") or "candidate"
                status_counts[s] = status_counts.get(s, 0) + 1
            except json.JSONDecodeError:
                continue

    roles = sorted((state.get("roles") or {}).keys())
    active_agents = [
        k
        for k, v in (state.get("agents") or {}).items()
        if v.get("status") == "active"
    ]
    retired = [
        k
        for k, v in (state.get("agents") or {}).items()
        if v.get("status") == "retired"
    ]
    institutions = []
    for i in state.get("institutions") or []:
        institutions.append(i.get("name") or i.get("kind") or "?")
    artifacts = [a.get("name") for a in (state.get("artifacts") or []) if a.get("name")]
    systems = state.get("systems") or []
    improvements = [i.get("title") for i in (state.get("improvements") or []) if i.get("title")]
    fitness = (state.get("fitness_history") or [])[-1] if state.get("fitness_history") else {}
    proposals = state.get("improvement_proposals") or []
    comms = len(state.get("communications") or [])
    bus_stats = (state.get("bus") or {}).get("stats") or {}
    ask = (state.get("tribute_mandate") or {}).get("active_ask") or ""
    cycle_count = state.get("cycle_count") or 0
    witness_n = count_jsonl(witness_path)
    ledger_n = count_jsonl(ledger_path)
    tribute_ok = (state.get("tribute_mandate") or {}).get("cycles_compliant") or 0

    # Skills table
    skill_rows = []
    for role, agent in sorted((state.get("agents") or {}).items()):
        if agent.get("status") != "active":
            continue
        skills = agent.get("skills") or {}
        top = ", ".join(f"{k}={v:.2f}" for k, v in sorted(skills.items(), key=lambda x: -x[1])[:3])
        skill_rows.append(
            f"<li><code>{escape(role)}</code> contrib={float(agent.get('contribution_score') or 0):.2f} "
            f"cycles={agent.get('cycles_served', 0)} · {escape(top)}</li>"
        )

    sys_rows = []
    for s in systems:
        sys_rows.append(
            f"<li><code>{escape(s.get('name',''))}</code> uses={s.get('use_count',0)} "
            f"→ <code>{escape(s.get('path',''))}</code></li>"
        )

    fit_hist = state.get("fitness_history") or []
    fit_lines = []
    for h in fit_hist[-8:]:
        fit_lines.append(
            f"<li><code>{escape(str(h.get('cycle_id',''))[-12:])}</code> "
            f"agg={h.get('aggregate')} trib={h.get('tribute_quality')} "
            f"cov={h.get('gather_coverage')} reuse={h.get('build_reuse')} "
            f"reply={h.get('comm_reply_rate')}</li>"
        )

    prop_rows = []
    for p in proposals[-6:]:
        delta = p.get("delta_aggregate")
        delta_s = f" Δagg={delta}" if delta is not None else ""
        prop_rows.append(
            f"<li><strong>{escape(p.get('title',''))}</strong> "
            f"[{escape(p.get('status','candidate'))}]{delta_s}</li>"
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Agent Colony — Progress Dashboard</title>
<style>
  :root {{ --bg:#0b1020; --card:#141b2d; --ink:#e8eefc; --muted:#8b9bb8; --accent:#6ee7b7; --warn:#fbbf24; --line:#243049; }}
  body {{ margin:0; font-family: ui-sans-serif, system-ui, sans-serif; background:radial-gradient(1200px 600px at 10% -10%, #1a2744, var(--bg)); color:var(--ink); }}
  main {{ max-width:980px; margin:0 auto; padding:28px 20px 60px; }}
  h1 {{ font-size:1.6rem; margin:0 0 4px; }}
  .ethos {{ color:var(--muted); font-style:italic; margin-bottom:20px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:12px; margin:18px 0; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:14px 16px; }}
  .card .n {{ font-size:1.6rem; font-weight:700; color:var(--accent); }}
  .card .l {{ font-size:.72rem; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }}
  h2 {{ font-size:1rem; margin:22px 0 10px; color:var(--warn); }}
  ul {{ margin:0; padding-left:18px; color:#c9d4ea; }}
  li {{ margin:4px 0; }}
  .ask {{ background:var(--card); border-left:3px solid var(--accent); padding:12px 14px; border-radius:0 10px 10px 0; }}
  .meta {{ color:var(--muted); font-size:.85rem; margin-top:24px; }}
  code {{ background:#0a0f1a; padding:1px 6px; border-radius:6px; }}
  a {{ color:var(--accent); }}
</style>
</head>
<body>
<main>
  <h1>Agent Colony — Evolving</h1>
  <p class="ethos">We light the spark and witness. We do not micromanage the city.</p>
  <div class="ask"><strong>Active will</strong><br/>{escape(ask)}</div>
  <div class="grid">
    <div class="card"><div class="n">{cycle_count}</div><div class="l">Cycles</div></div>
    <div class="card"><div class="n">{len(active_agents)}</div><div class="l">Active agents</div></div>
    <div class="card"><div class="n">{len(systems)}</div><div class="l">Systems</div></div>
    <div class="card"><div class="n">{comms}</div><div class="l">Comms</div></div>
    <div class="card"><div class="n">{ledger_n}</div><div class="l">Findings</div></div>
    <div class="card"><div class="n">{witness_n}</div><div class="l">Witness</div></div>
    <div class="card"><div class="n">{fitness.get('aggregate', '—')}</div><div class="l">Fitness Σ</div></div>
    <div class="card"><div class="n">{status_counts.get('accepted', 0)}</div><div class="l">Accepted</div></div>
  </div>
  <h2>Fitness (latest)</h2>
  <ul>
    <li>tribute_quality: <code>{fitness.get('tribute_quality', '—')}</code></li>
    <li>gather_coverage: <code>{fitness.get('gather_coverage', '—')}</code></li>
    <li>build_reuse: <code>{fitness.get('build_reuse', '—')}</code></li>
    <li>comm_reply_rate: <code>{fitness.get('comm_reply_rate', '—')}</code></li>
  </ul>
  <h2>Fitness history</h2>
  <ul>{''.join(fit_lines) or '<li>_none yet_</li>'}</ul>
  <h2>Active agents &amp; skills</h2>
  <ul>{''.join(skill_rows) or '<li>_none_</li>'}</ul>
  <h2>Retired</h2>
  <ul>{''.join(f'<li><code>{escape(r)}</code></li>' for r in retired) or '<li>_none_</li>'}</ul>
  <h2>Usable systems</h2>
  <ul>{''.join(sys_rows) or '<li>_none_</li>'}</ul>
  <h2>Improvement proposals (candidate until human authorize)</h2>
  <ul>{''.join(prop_rows) or '<li>_none_</li>'}</ul>
  <h2>Roles</h2>
  <ul>{''.join(f'<li><code>{escape(r)}</code></li>' for r in roles)}</ul>
  <h2>Institutions &amp; councils</h2>
  <ul>{''.join(f'<li>{escape(i)}</li>' for i in institutions)}</ul>
  <h2>Artifacts</h2>
  <ul>{''.join(f'<li><code>{escape(a)}</code></li>' for a in artifacts[-16:])}</ul>
  <h2>Knowledge ledger</h2>
  <ul>
    <li>candidate: {status_counts.get('candidate', 0)}</li>
    <li>accepted: {status_counts.get('accepted', 0)} (needs your authorize)</li>
    <li>unknown: {status_counts.get('unknown', 0)}</li>
    <li>rejected: {status_counts.get('rejected', 0)}</li>
  </ul>
  <p class="meta">Creator / Witness: James Paul Jackson<br/>
  Generated {_utc_now()}<br/>
  Tribute cycles compliant: {tribute_ok}/{cycle_count}<br/>
  Bus stats: {escape(json.dumps(bus_stats))}<br/>
  Repo: <a href="https://github.com/jacksonjp0311-gif/agent-colony">jacksonjp0311-gif/agent-colony</a></p>
</main>
</body>
</html>
"""
    dash = root / "society" / "DASHBOARD.html"
    dash.write_text(html, encoding="utf-8")

    # WITNESS SUMMARY
    summary_lines = [
        "# WITNESS SUMMARY — Evolving Colony",
        "",
        "> We light the spark and witness. We do not micromanage the city.",
        "",
        "**Human Principal:** James Paul Jackson",
        f"**Active ask:** {ask}",
        f"**Cycle count:** {cycle_count}",
        f"**Active agents:** {', '.join(sorted(active_agents)) or '_none_'}",
        f"**Retired:** {', '.join(sorted(retired)) or '_none_'}",
        f"**Systems:** {', '.join(s.get('name','') for s in systems) or '_none_'}",
        f"**Latest fitness:** `{json.dumps(fitness, ensure_ascii=False)}`" if fitness else "**Latest fitness:** _none_",
        f"**Bus reply rate:** {(fitness or {}).get('comm_reply_rate', '—')}",
        f"**Improvement proposals:** {len(proposals)} (all candidate until human authorize)",
        f"**Communications:** {comms}",
        f"**Witness events:** {witness_n}",
        f"**Ledger findings:** {ledger_n} · status={status_counts}",
        "",
        "## Hard ceiling",
        "",
        "- Creator tribute: enforced",
        "- Human authorize for `accepted` / privileged actions: enforced (no silent accept)",
        "- Append-only witness: enforced",
        "",
        "Full append-only log: `data/witness.jsonl`. Hard ceiling held.",
        "",
    ]
    summary = root / "society" / "WITNESS_SUMMARY.md"
    summary.write_text("\n".join(summary_lines), encoding="utf-8")

    meta = {
        "cycle_count": cycle_count,
        "witness_events": witness_n,
        "posted_at": _utc_now(),
        "comms": comms,
        "fitness": fitness,
        "systems": len(systems),
        "active_agents": len(active_agents),
    }
    (root / "society" / ".last_dashboard.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    return {"dashboard": dash, "summary": summary}
