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


# ---------------------------------------------------------------------------
# Item 94 (2026-11-16): wider STEM pack. Classical, textbook-proven relations checked by an
# independent numerical route (not novel physics). Entries start DISABLED; the Oracle decides.
# ---------------------------------------------------------------------------

def check_elastic_collision_conservation(m1: float, m2: float, u1: float, u2: float) -> bool:
    """1D elastic collision closed form conserves momentum AND kinetic energy."""
    v1 = ((m1 - m2) * u1 + 2 * m2 * u2) / (m1 + m2)
    v2 = ((m2 - m1) * u2 + 2 * m1 * u1) / (m1 + m2)
    p_ok = abs((m1 * u1 + m2 * u2) - (m1 * v1 + m2 * v2)) < 1e-9
    k_ok = abs((m1 * u1 * u1 + m2 * u2 * u2) - (m1 * v1 * v1 + m2 * v2 * v2)) < 1e-7
    return p_ok and k_ok


def check_kepler_third_circular(gm: float, r: float) -> bool:
    """Circular orbit v = sqrt(GM/r), T = 2*pi*r/v  ->  T^2 / r^3 = 4*pi^2 / GM."""
    v = math.sqrt(gm / r)
    t = 2 * math.pi * r / v
    return abs(t * t / r ** 3 - 4 * math.pi ** 2 / gm) < 1e-9 * (4 * math.pi ** 2 / gm)


def check_shm_energy(k: float, m: float, amp: float) -> bool:
    """x = A cos(wt), v = -A w sin(wt), w^2 = k/m: 0.5kx^2 + 0.5mv^2 = 0.5kA^2 at all t."""
    w = math.sqrt(k / m)
    e0 = 0.5 * k * amp * amp
    for i in range(40):
        t = i * 0.173
        x = amp * math.cos(w * t)
        v = -amp * w * math.sin(w * t)
        if abs(0.5 * k * x * x + 0.5 * m * v * v - e0) > 1e-9 * max(1.0, e0):
            return False
    return True


def check_resistor_power_balance(v: float, r1: float, r2: float, r3: float) -> bool:
    """r1 in series with (r2 || r3): source power V*I equals the sum of I^2 R dissipations."""
    rp = r2 * r3 / (r2 + r3)
    i = v / (r1 + rp)
    vp = i * rp
    p_diss = i * i * r1 + vp * vp / r2 + vp * vp / r3
    return abs(v * i - p_diss) < 1e-9 * max(1.0, v * i)


def check_isothermal_work(nrt: float, v1: float, v2: float) -> bool:
    """Ideal gas isotherm: W = nRT ln(V2/V1) equals the numeric integral of P dV (Simpson)."""
    n = 2000
    h = (v2 - v1) / n
    f = lambda vol: nrt / vol  # noqa: E731
    s = f(v1) + f(v2) + sum((4 if j % 2 else 2) * f(v1 + j * h) for j in range(1, n))
    return abs(s * h / 3 - nrt * math.log(v2 / v1)) < 1e-6 * max(1.0, abs(nrt * math.log(v2 / v1)))


def check_snell_least_time(n1: float, n2: float, a: float, b: float, d: float) -> bool:
    """The least-optical-path crossing point (golden-section search) obeys Snell's law."""
    path = lambda x: n1 * math.hypot(x, a) + n2 * math.hypot(d - x, b)  # noqa: E731
    lo, hi = 0.0, d
    g = (math.sqrt(5) - 1) / 2
    for _ in range(200):
        c1, c2 = hi - g * (hi - lo), lo + g * (hi - lo)
        if path(c1) < path(c2):
            hi = c2
        else:
            lo = c1
    x = (lo + hi) / 2
    s1 = x / math.hypot(x, a)
    s2 = (d - x) / math.hypot(d - x, b)
    return abs(n1 * s1 - n2 * s2) < 1e-6


def check_rc_discharge(v0: float, rc: float) -> bool:
    """V(t) = V0 exp(-t/RC) satisfies dV/dt = -V/RC (central difference) and halves at RC ln 2."""
    vt = lambda t: v0 * math.exp(-t / rc)  # noqa: E731
    for i in range(1, 30):
        t, h = i * rc / 7, 1e-5 * rc
        dv = (vt(t + h) - vt(t - h)) / (2 * h)
        if abs(dv + vt(t) / rc) > 1e-5 * max(1.0, abs(v0 / rc)):
            return False
    return abs(vt(rc * math.log(2)) - v0 / 2) < 1e-12 * max(1.0, abs(v0))


def check_thin_lens_ray_matrix(f: float, do: float) -> bool:
    """Thin-lens equation 1/f = 1/do + 1/di agrees with paraxial ABCD ray-transfer matrices:
    at di the system matrix has B = 0 (imaging) and A = magnification -di/do."""
    di = 1.0 / (1.0 / f - 1.0 / do)
    # M = T(di) * L(f) * T(do), T(d) = [[1, d], [0, 1]], L(f) = [[1, 0], [-1/f, 1]]
    a1, b1, c1, d1 = 1.0, do, -1.0 / f, 1.0 - do / f            # L(f) * T(do)
    a, b = a1 + di * c1, b1 + di * d1                             # T(di) * (...)
    return abs(b) < 1e-9 * max(1.0, abs(do * di)) and abs(a - (-di / do)) < 1e-9


def check_velocity_addition_rapidity(u: float, v: float) -> bool:
    """(u+v)/(1+uv) (c = 1) equals tanh(atanh u + atanh v) and stays below 1 in magnitude."""
    w = (u + v) / (1 + u * v)
    return abs(w - math.tanh(math.atanh(u) + math.atanh(v))) < 1e-12 and abs(w) < 1


def check_wheatstone_balance(r1: float, r2: float, r3: float, r4: float, rg: float) -> bool:
    """Bridge node analysis (Kirchhoff, 2x2 solve): galvanometer current is zero iff r1/r2 == r3/r4."""
    vs = 10.0
    # Nodes A (between r1, r2) and B (between r3, r4); r1, r3 to +V; r2, r4 to ground; rg A-B.
    g1, g2, g3, g4, gg = 1 / r1, 1 / r2, 1 / r3, 1 / r4, 1 / rg
    a11, a12, b1 = g1 + g2 + gg, -gg, g1 * vs
    a21, a22, b2 = -gg, g3 + g4 + gg, g3 * vs
    det = a11 * a22 - a12 * a21
    va = (b1 * a22 - a12 * b2) / det
    vb = (a11 * b2 - a21 * b1) / det
    balanced = abs(r1 * r4 - r2 * r3) < 1e-12
    return (abs(va - vb) < 1e-9) == balanced


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
    # Item 94: wider STEM pack — classical relations, DISABLED until the Oracle decides
    ("stem_elastic_collision", lambda: all(
        check_elastic_collision_conservation(m1, m2, u1, u2)
        for m1 in (0.5, 1, 3) for m2 in (1, 2, 7) for u1 in (-4, 0, 3) for u2 in (-2, 0, 5)
    ), False),
    ("stem_kepler_third_law", lambda: all(
        check_kepler_third_circular(gm, r) for gm in (1.0, 3.986e14, 1.327e20) for r in (1.0, 7.0e6, 1.5e11)
    ), False),
    ("stem_shm_energy", lambda: all(
        check_shm_energy(k, m, a) for k in (1, 4, 50) for m in (0.2, 1, 3) for a in (0.1, 1, 2.5)
    ), False),
    ("stem_resistor_power_balance", lambda: all(
        check_resistor_power_balance(v, r1, r2, r3)
        for v in (1.5, 9, 230) for r1 in (1, 10) for r2 in (2, 47) for r3 in (3, 100)
    ), False),
    ("stem_isothermal_work", lambda: all(
        check_isothermal_work(nrt, v1, v2) for nrt in (1.0, 8.314 * 300) for v1, v2 in ((1, 2), (0.5, 3), (2, 1))
    ), False),
    ("stem_snell_least_time", lambda: all(
        check_snell_least_time(n1, n2, a, b, d)
        for n1, n2 in ((1.0, 1.33), (1.5, 1.0), (1.0, 2.4)) for a, b, d in ((1, 1, 2), (2, 0.5, 3))
    ), False),
    ("stem_rc_discharge", lambda: all(
        check_rc_discharge(v0, rc) for v0 in (1, 5, 12) for rc in (0.001, 1, 47)
    ), False),
    ("stem_thin_lens_matrix", lambda: all(
        check_thin_lens_ray_matrix(f, do) for f in (0.05, 0.1, 0.5) for do in (0.2, 1.0, 3.0) if do != f
    ), False),
    ("stem_velocity_addition", lambda: all(
        check_velocity_addition_rapidity(u, v) for u in (-0.99, -0.5, 0, 0.3, 0.9) for v in (-0.7, 0.1, 0.6, 0.999)
    ), False),
    ("stem_wheatstone_balance", lambda: all(
        check_wheatstone_balance(r1, r2, r3, r4, rg)
        for r1, r2, r3, r4 in ((1, 2, 3, 6), (10, 10, 5, 5), (1, 2, 3, 7), (4, 1, 2, 3)) for rg in (1, 50)
    ), False),
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
