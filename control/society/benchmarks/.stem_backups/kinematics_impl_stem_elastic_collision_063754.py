"""Kinematics STEM microbench impl — classical 1D/2D motion identities.

Not novel physics. Machine-check of coded kinematics relations for Oracle domain pack.
Mutable catalog: STEM_CHECKS may be extended / enabled by desk.
"""
from __future__ import annotations

import math
from typing import Callable


def check_suvat_displacement(u: float, a: float, t: float) -> bool:
    """s = ut + 0.5 a t^2  and  v = u + a t  →  v^2 = u^2 + 2 a s (within tol)."""
    s = u * t + 0.5 * a * t * t
    v = u + a * t
    lhs = v * v
    rhs = u * u + 2 * a * s
    return abs(lhs - rhs) < 1e-9


def check_projectile_range(v0: float, angle_deg: float, g: float = 9.8) -> bool:
    """R = v0^2 sin(2θ)/g for flat ground (classical). Spot via time-of-flight."""
    if v0 <= 0 or g <= 0:
        return True
    th = math.radians(angle_deg)
    R = (v0 * v0 * math.sin(2 * th)) / g
    # discrete: vy0, time up+down
    vy = v0 * math.sin(th)
    vx = v0 * math.cos(th)
    t_flight = 2 * vy / g if abs(vy) > 1e-12 else 0.0
    R2 = vx * t_flight
    return abs(R - R2) < 1e-9


def check_circular_centripetal(v: float, r: float) -> bool:
    """a = v^2/r; period T=2πr/v → a = 4π^2 r / T^2."""
    if r <= 0 or v == 0:
        return True
    a1 = (v * v) / r
    T = 2 * math.pi * r / abs(v)
    a2 = 4 * math.pi * math.pi * r / (T * T)
    return abs(a1 - a2) < 1e-9


def check_energy_work(m: float, u: float, a: float, s: float) -> bool:
    """ΔKE = Work: 0.5 m (v^2 - u^2) = m a s when v^2 = u^2 + 2 a s."""
    if m <= 0:
        return True
    v2 = u * u + 2 * a * s
    dke = 0.5 * m * (v2 - u * u)
    work = m * a * s
    return abs(dke - work) < 1e-9


def check_easy_pad_units() -> bool:
    """Easy pad — trivial 1==1 style; must die on Oracle STEM pack."""
    return all(x + 0 == x for x in range(-3, 4))


# Mutable catalog — flourish desk may enable hard STEM checks.
STEM_CHECKS: list[tuple[str, Callable[[], bool], bool]] = [
    ("suvat_identity", lambda: all(
        check_suvat_displacement(u, a, t)
        for u in (-5, 0, 2, 7) for a in (-3, 0, 1.5, 4) for t in (0, 0.5, 1, 2, 3)
    ), True),
    ("projectile_range", lambda: all(
        check_projectile_range(v0, ang)
        for v0 in (5, 10, 20) for ang in (15, 30, 45, 60, 75)
    ), True),
    ("circular_centripetal", lambda: all(
        check_circular_centripetal(v, r)
        for v in (1, 2, 5, 10) for r in (0.5, 1, 2, 4)
    ), True),
    # Flourish — start disabled; enable only with Oracle STEM pass
    ("energy_work", lambda: all(
        check_energy_work(m, u, a, s)
        for m in (1, 2, 5) for u in (0, 3, -2) for a in (-1, 0, 2) for s in (0, 1, 4)
    ), True),
]


def run_stem_checks() -> dict[str, bool]:
    out: dict[str, bool] = {}
    for name, fn, enabled in STEM_CHECKS:
        if not enabled:
            continue
        try:
            out[name] = bool(fn())
        except Exception:  # noqa: BLE001
            out[name] = False
    return out


def all_pass() -> bool:
    r = run_stem_checks()
    return bool(r) and all(r.values())


def impl_id() -> str:
    n = sum(1 for _, _, e in STEM_CHECKS if e)
    return f"kinematics_impl_v1_enabled{n}"
