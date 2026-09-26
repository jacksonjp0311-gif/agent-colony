"""Society cycle — bootstrap from b64 parts (hard-lemma emergency restore)."""
from __future__ import annotations

import base64
import sys
import types
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_briefs = _ROOT / "society" / "briefs"

def _load_parts():
    # Prefer a/b halves (more reliably pushed); fall back to wholes.
    halves = sorted(_briefs.glob("society_py_part_[0-9][ab].b64"))
    if len(halves) >= 8:
        return "".join(p.read_text().strip() for p in halves)
    wholes = sorted(_briefs.glob("society_py_part_[0-9].b64"))
    if len(wholes) >= 4:
        return "".join(p.read_text().strip() for p in wholes)
    if halves:
        return "".join(p.read_text().strip() for p in halves)
    if wholes:
        return "".join(p.read_text().strip() for p in wholes)
    raise ImportError("colony.society: missing society_py_part_*.b64")

_raw = base64.b64decode(_load_parts())
_mod = types.ModuleType(__name__)
_mod.__file__ = str(Path(__file__).resolve())
sys.modules[__name__] = _mod
exec(compile(_raw, _mod.__file__, "exec"), _mod.__dict__)
globals().update({k: v for k, v in _mod.__dict__.items() if not k.startswith("_")})
