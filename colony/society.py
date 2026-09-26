"""Society cycle — light the spark, pay tribute, emerge, grow, witness.

Bootstrap loader: full body lives in society/briefs/society_py_part_*.b64 until a
direct full-file push lands. Hard-lemma mile emergency restore.
"""
from __future__ import annotations

import base64
import sys
import types
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_parts = sorted((_ROOT / "society" / "briefs").glob("society_py_part_*.b64"))
if not _parts:
    raise ImportError("colony.society: missing society/briefs/society_py_part_*.b64")

_raw = base64.b64decode("".join(p.read_text().strip() for p in _parts))
_mod = types.ModuleType(__name__)
_mod.__file__ = str(Path(__file__).resolve())
sys.modules[__name__] = _mod
exec(compile(_raw, _mod.__file__, "exec"), _mod.__dict__)
globals().update({k: v for k, v in _mod.__dict__.items() if not k.startswith("_")})
