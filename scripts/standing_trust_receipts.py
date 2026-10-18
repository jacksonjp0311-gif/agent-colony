"""List receipts written by the CI standing-trust step (not by James by hand). Report only; revokes nothing."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RX = re.compile(r"^- `(fnd_\w+)` → `(fnd_\w+)` — \*\*(.+?)\*\*", re.M)


def collect(root: Path = ROOT) -> list[dict]:
    out = []
    for f in sorted((root / "society" / "receipts").glob("AUTHORIZE_authorize_*.md")):
        s = f.read_text(encoding="utf-8", errors="replace")
        if "Delegated via:** GitHub Actions" not in s:
            continue
        ts = re.search(r"\*\*Timestamp:\*\* (\S+)", s)
        acc = s.split("## Accepted", 1)[1].split("## Rejected", 1)[0] if "## Accepted" in s else ""
        for fid, new, title in RX.findall(acc):
            out.append({"receipt": f.name, "ts": ts.group(1) if ts else "", "finding": fid, "title": title})
    return out


if __name__ == "__main__":
    rows = collect()
    (ROOT / "society" / "systems" / "standing_trust_receipts.json").write_text(
        json.dumps({"note": "Accepted by the CI standing-trust step, not by James by hand. Not revoked; for James to review.",
                    "n": len(rows), "items": rows}, indent=1) + "\n", encoding="utf-8")
    print(len(rows), "accepted items in", len({r["receipt"] for r in rows}), "CI receipts")
