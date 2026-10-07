"""Oracle domain packs — widen mutate search beyond current lemmas.

Each pack: held-out harder check + stripped baseline + CAS-style probe.
FAIL kills keep. Math pack + STEM (kinematics) pack for flourish mile.
Not AGI. Not novel theorems / novel physics.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent

# Pack id → metadata
DOMAIN_PACKS: dict[str, dict[str, Any]] = {
    "math_lemmas": {
        "label": "Math lemmas (beyond current catalog)",
        "bench": "lemma_microbench",
        "kinds": ("hard_enable", "easy_pad", "hard_check"),
        "note": "Classical coded identities. Not theorem discovery.",
    },
    "stem_kinematics": {
        "label": "STEM kinematics (non-math physics microbench)",
        "bench": "kinematics_microbench",
        "kinds": ("stem_enable", "stem_easy_pad", "stem_check"),
        "note": "Classical 1D/2D motion. Not novel physics.",
    },
}


def list_packs() -> list[str]:
    return list(DOMAIN_PACKS.keys())


def pack_for_kind(kind: str, mutation: str = "") -> str:
    k = (kind or "").lower()
    name = (mutation or "").lower()
    if k.startswith("stem") or name.startswith("stem_") or "kinematics" in name or "suvat" in name or "projectile" in name or "energy_work" in name:
        return "stem_kinematics"
    return "math_lemmas"


def sense_stripped_pack(mutation: str, kind: str = "") -> dict[str, Any]:
    """Without candidate, usefulness must fail (not already enabled)."""
    pack = pack_for_kind(kind, mutation)
    name = (mutation or "").strip()
    if kind in ("easy_pad", "stem_easy_pad") or name.startswith("easy_pad") or name.startswith("stem_easy"):
        return {
            "pack": pack,
            "stripped_fails_usefulness": False,
            "ok_for_oracle": False,
            "reason": "easy_pad_baseline_already_useful",
        }
    if pack == "stem_kinematics":
        try:
            path = ROOT / "society" / "benchmarks" / "artifacts" / "kinematics_impl.py"
            src = path.read_text(encoding="utf-8") if path.exists() else ""
            _m = re.search(rf'\("{re.escape(name)}".*?,\s*(True|False)\)', src, re.S)
            already = bool(_m and _m.group(1) == "True")  # this entry's own flag only
            in_catalog = f'("{name}"' in src
            fails = (not already) and in_catalog
            return {
                "pack": pack,
                "already_enabled": already,
                "in_catalog": in_catalog,
                "stripped_fails_usefulness": fails,
                "ok_for_oracle": fails and not already,
                "reason": "stem_stripped_ok" if fails and not already else "stem_stripped_not_useful",
            }
        except Exception as exc:  # noqa: BLE001
            return {"pack": pack, "ok_for_oracle": False, "reason": f"error:{exc}"}
    # math — delegate signal shape (oracle.sense_stripped_baseline does real work)
    return {"pack": pack, "delegate": "math_lemma", "ok_for_oracle": None, "reason": "delegate_math"}


def sense_held_out_pack(
    mutation: str,
    kind: str = "",
    *,
    after_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    name = (mutation or "").strip()
    pack = pack_for_kind(kind, mutation)
    if kind in ("easy_pad", "stem_easy_pad") or name.startswith("easy_pad") or name.startswith("stem_easy"):
        return {
            "pack": pack,
            "survives": False,
            "ok_for_oracle": False,
            "reason": "easy_pad_dies_on_held_out",
        }
    if pack == "stem_kinematics":
        try:
            snap = after_snapshot
            if snap is None:
                from society.benchmarks.kinematics_microbench import run as run_stem
                snap = run_stem()
            ok = bool(snap.get("ok")) and int(snap.get("n_pass") or 0) > 0
            kind_ok = kind in ("stem_enable", "stem_check", "bench_keep", "") or kind.startswith("stem")
            survives = ok and kind_ok and not name.startswith("easy_pad")
            return {
                "pack": pack,
                "survives": survives,
                "ok_for_oracle": survives,
                "n_pass": snap.get("n_pass"),
                "n_checks": snap.get("n_checks"),
                "score": snap.get("score"),
                "reason": "stem_held_out_green" if survives else "stem_held_out_fail",
            }
        except Exception as exc:  # noqa: BLE001
            return {"pack": pack, "survives": False, "ok_for_oracle": False, "reason": f"error:{exc}"}
    return {"pack": pack, "delegate": "math_lemma", "ok_for_oracle": None, "reason": "delegate_math"}


def sense_cas_pack(mutation: str, kind: str = "", claim_text: str = "") -> dict[str, Any]:
    """CAS-style probes per pack. Easy pads fail."""
    name = (mutation or "").strip().lower()
    pack = pack_for_kind(kind, mutation)
    blob = f"{name} {claim_text}".lower()
    if kind in ("easy_pad", "stem_easy_pad") or name.startswith("easy_pad") or name.startswith("stem_easy"):
        return {
            "pack": pack,
            "cas_ok": False,
            "ok_for_oracle": False,
            "engine": "reject_easy_pad",
            "reason": "easy_pad_fails_cas_usefulness",
            "checks": [],
        }
    if any(t in blob for t in ("millennium", "riemann", "consciousness", "agi", "perpetual motion")):
        return {
            "pack": pack,
            "cas_ok": False,
            "ok_for_oracle": False,
            "engine": "theater_filter",
            "reason": "theater_language",
            "checks": [],
        }
    if pack == "stem_kinematics":
        checks: list[dict[str, Any]] = []
        # Pure-Python kinematics probes (CAS-style numeric)
        ok_suvat = all(
            abs((u + a * t) ** 2 - (u * u + 2 * a * (u * t + 0.5 * a * t * t))) < 1e-9
            for u in (-2, 0, 3)
            for a in (-1, 2)
            for t in (0.5, 1.0, 2.0)
        )
        checks.append({"label": "suvat_v2", "ok": ok_suvat})
        ok_circ = all(
            abs((v * v) / r - (4 * math.pi * math.pi * r) / ((2 * math.pi * r / abs(v)) ** 2)) < 1e-9
            for v in (1.0, 3.0, 5.0)
            for r in (0.5, 2.0)
        )
        checks.append({"label": "centripetal_T", "ok": ok_circ})
        if "energy" in name or "work" in name:
            ok_e = all(
                abs(0.5 * m * (2 * a * s) - m * a * s) < 1e-9
                for m in (1, 2)
                for a in (1, -1)
                for s in (1, 3)
            )
            checks.append({"label": "energy_work_numeric", "ok": ok_e})
        cas_ok = all(c.get("ok") for c in checks)
        return {
            "pack": pack,
            "cas_ok": cas_ok,
            "ok_for_oracle": cas_ok,
            "engine": "pure_python_stem",
            "reason": "stem_cas_pass" if cas_ok else "stem_cas_fail",
            "checks": checks,
        }
    return {"pack": pack, "delegate": "math_lemma", "ok_for_oracle": None, "reason": "delegate_math"}


def enable_stem(src: str, name: str) -> str | None:
    """Flip STEM_CHECKS entry False→True."""
    pat = re.compile(rf'(\("{re.escape(name)}",\s*.*?,\s*)False(\))', re.S)
    m = pat.search(src)
    if not m:
        return None
    return src[: m.start()] + m.group(1) + "True" + m.group(2) + src[m.end() :]


STEM_MUTATIONS: list[tuple[str, str, str]] = [
    ("energy_work", "stem_enable", "enable:energy_work"),
    ("stem_easy_pad_units", "stem_easy_pad", "pad"),
]


def digest_packs() -> dict[str, Any]:
    return {
        "packs": DOMAIN_PACKS,
        "stem_mutations": [n for n, _, _ in STEM_MUTATIONS],
        "note": "Widen Oracle mutate distribution. Fail kills keep. Not discovery.",
    }
