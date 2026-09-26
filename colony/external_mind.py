"""External mind — load from b64 parts (bridge dynamics)."""
from __future__ import annotations
import base64, sys, types
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
_briefs = _ROOT / "society" / "briefs"
_b64 = "".join(p.read_text().strip() for p in sorted(_briefs.glob("external_mind_py_*.b64")))
_raw = base64.b64decode(_b64)
_mod = types.ModuleType(__name__)
_mod.__file__ = str(Path(__file__).resolve())
sys.modules[__name__] = _mod
exec(compile(_raw, _mod.__file__, "exec"), _mod.__dict__)
globals().update({k: v for k, v in _mod.__dict__.items() if not k.startswith("_")})
