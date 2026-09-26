#!/usr/bin/env python3
"""Restore ALIGN mile code files from society/briefs/align_b64/*.b64 (base64 chunks)."""
from __future__ import annotations
import base64
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
B64 = ROOT / "society" / "briefs" / "align_b64"
MAP = {
    "colony__society.py": "colony/society.py",
    "colony__genomes.py": "colony/genomes.py",
    "colony__authorize.py": "colony/authorize.py",
    ".github__workflows__colony-evolve.yml": ".github/workflows/colony-evolve.yml",
}
def main() -> None:
    for prefix, dest in MAP.items():
        chunks = sorted(B64.glob(f"{prefix}.*.b64"))
        if not chunks:
            print("skip missing", prefix); continue
        data = "".join(p.read_text().strip() for p in chunks)
        out = ROOT / dest
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(data))
        print("restored", dest, out.stat().st_size)
if __name__ == "__main__":
    main()
