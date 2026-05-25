"""Inverse (preliminary) mean-line design for a single radial-compressor stage.

The :mod:`radcompressor` model is a *forward* analysis tool: given a geometry
and an operating point it returns the performance.  This module adds the
*inverse* problem required for design -- given a duty (fluid, mass flow, shaft
speed, inlet state and a target pressure ratio) it synthesises a consistent
mean-line geometry and refines it against the forward model.

Strategy
--------
1. A consistent geometry is parametrised by the impeller tip speed ``U4``
   (everything else -- ``r4``, exit width, inlet sizing and blade angles --
   follows from a small set of non-dimensional shape coefficients).
2. Pressure ratio is dominated by the Euler work ``U4 * c4t``, so the target
   pressure ratio is met by root-finding ``U4`` (monotonic in ``PR`` within the
   feasible window).
3. The shape coefficients (exit flow coefficient, back-sweep, inlet Mach
   number, hub/tip ratio, diffuser radius ratio) are then optimised to
   maximise isentropic efficiency while keeping the stage feasible.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Optional

import numpy as np
from scipy import optimize

from .compressor import Compressor
from .condition import OperatingCondition
from .geometry import Geometry
from .thermo import Fluid, ThermoException, ThermoProp


@dataclass
class DesignKnobs:
    """Non-dimensional shape choices and optimiser budget for a stage design."""

    flow_coeff: float = 0.28  # exit flow coefficient phi4 = c4m / U4
    beta4_deg: float = -40.0  # impeller exit blade (back-sweep) angle
    inlet_mach: float = 0.6  # ceiling on the absolute inlet Mach number
    hub_tip_ratio: float = 0.4  # r2h / r2s
    diffuser_ratio: float = 1.5  # r5 / r4
    n_blades: int = 9  # number of full blades
    n_splits: int = 9  # number of splitter blades
    eta_guess: float = 0.80  # first-guess efficiency to size the tip speed
    # Mechanical / aerodynamic guard rails
    max_tip_speed: float = 550.0  # m/s, centrifugal-stress driven limit (steel)
    # Optimiser budget
    optimize_shape: bool = True
    scan_points: int = 14  # tip-speed scan resolution
    # Shape search grid (reaches the target PR and then maximises efficiency)
    flow_coeff_grid: tuple = (0.16, 0.22, 0.28, 0.34)
    beta4_grid: tuple = (-25.0, -35.0, -45.0, -55.0)


@dataclass
class StagePerformance:
    """Scalar performance summary of an evaluated stage."""

    valid: bool
    pr: float = math.nan
    eff: float = math.nan
    power: float = math.nan
    tip_speed: float = math.nan
    head: float = math.nan
    mach_in: float = math.nan
    mach_out_abs: float = math.nan
    mach_out_rel: float = math.nan
    alpha_out: float = math.nan
    p_out: float = math.nan
    t_out: float = math.nan
    h_out: float = math.nan
    s_out: float = math.nan

    @classmethod
    def from_compressor(cls, comp: Compressor, valid: bool) -> "StagePerformance":
        if not valid:
            return cls(valid=False, tip_speed=comp.tip_speed)
        out = comp.out.total
        return cls(
            valid=True,
            pr=comp.PR,
            eff=comp.eff,
            power=comp.power,
            tip_speed=comp.tip_speed,
            head=comp.head,
            mach_in=comp.m_in,
            mach_out_abs=comp.imp.out.m_abs,
            mach_out_rel=comp.imp.out.m_rel,
            alpha_out=comp.imp.out.alpha,
            p_out=out.P,
            t_out=out.T,
            h_out=out.H,
            s_out=out.S,
        )


@dataclass
class StageDesign:
    """Result of designing a single stage."""

    geometry: Geometry
    performance: StagePerformance
    pr_target: float
    knobs: DesignKnobs
    converged: bool

    def to_dict(self) -> dict:
        g = asdict(self.geometry)
        return {
            "pr_target": self.pr_target,
            "converged": self.converged,
            "geometry": g,
            "performance": asdict(self.performance),
            "knobs": asdict(self.knobs),
        }


def evaluate(
    geom: Geometry,
    fld: Fluid,
    in0: ThermoProp,
    m: float,
    omega: float,
    delta_check: bool = False,
) -> StagePerformance:
    """Evaluate a geometry at an operating point, never raising.

    Returns a :class:`StagePerformance` with ``valid=False`` for any infeasible
    or non-converging point (choke, surge, two-phase, solver failure).

    ``delta_check`` (the negative-slope/surge stability re-run) doubles the
    cost, so it defaults off for the design search and is applied only when
    verifying an accepted design.
    """
    op = OperatingCondition(in0=in0, fld=fld, m=float(m), n_rot=float(omega))
    comp = Compressor(geom, op)
    try:
        with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
            valid = comp.calculate(delta_check=delta_check)
    except (ThermoException, ValueError, FloatingPointError):
        valid = False
    return StagePerformance.from_compressor(comp, valid)


def build_geometry(
    fld: Fluid,
    in0: ThermoProp,
    m: float,
    omega: float,
    u4: float,
    pr_hint: float,
    knobs: DesignKnobs,
) -> Geometry:
    """Build a consistent mean-line geometry for a target tip speed ``u4``.

    ``pr_hint`` is only used to estimate the discharge density when sizing the
    exit width; the achieved pressure ratio comes from the forward model.
    """
    r4 = u4 / omega
    c4m = knobs.flow_coeff * u4

    # --- exit width from continuity, using an estimated discharge density ---
    # Total discharge enthalpy from a first-guess work input; density from the
    # (approximate) total discharge state at the hinted pressure.
    beta4 = math.radians(knobs.beta4_deg)
    z_total = knobs.n_blades + knobs.n_splits
    slip = 1.0 - math.sqrt(max(math.cos(beta4), 1e-6)) / z_total**0.7
    c4t = c4m * math.tan(beta4) + slip * u4
    dh0_est = u4 * c4t  # Euler work (no inlet swirl)
    # Discharge density from the work-consistent pressure: the isentropic
    # enthalpy rise (eta * Euler work) fixes the discharge pressure far more
    # reliably than the loosely-related ``pr_hint`` (which becomes inconsistent
    # with the work at high tip speed and yielded a too-small exit width).
    dh0s_est = max(knobs.eta_guess, 0.3) * dh0_est
    c4 = math.hypot(c4m, c4t)
    try:
        tot_isen = fld.thermo_prop("HS", in0.H + dh0s_est, in0.S)
        tot_out = fld.thermo_prop("PH", tot_isen.P, in0.H + dh0_est)
        stat_out = fld.thermo_prop("HS", tot_out.H - 0.5 * c4**2, tot_out.S)
        rho4 = stat_out.D
    except ThermoException:
        rho4 = in0.D * pr_hint ** 0.75  # crude fallback
    b4 = m / (rho4 * 2.0 * math.pi * r4 * c4m)

    # --- inducer sizing: minimise the shroud relative Mach number ---
    # With r1 = r2s and axial inlet flow, the inlet axial velocity follows from
    # continuity as c1 = K / r2s**2 with K = m / (rho * pi * (1 - nu**2)); the
    # shroud relative speed is w2s**2 = c1**2 + (omega*r2s)**2.  Minimising over
    # r2s gives the classic optimum-incidence inducer radius below.
    nu = knobs.hub_tip_ratio
    rho1 = in0.D
    big_k = m / (rho1 * math.pi * (1.0 - nu**2))
    r2s = (2.0 * big_k**2 / omega**2) ** (1.0 / 6.0)
    c1 = big_k / r2s**2
    # Respect an absolute inlet-Mach ceiling (enlarge the eye if exceeded).
    if c1 > knobs.inlet_mach * in0.A:
        c1 = knobs.inlet_mach * in0.A
        a1_eff = m / (rho1 * c1)
        r2s = math.sqrt(a1_eff / (math.pi * (1.0 - nu**2)))
    r2h = nu * r2s
    r1 = r2s
    r2rms = math.sqrt((r2s**2 + r2h**2) / 2.0)

    # --- inlet relative-flow blade angles (no pre-swirl, alpha2 = 0) ---
    u2s = r2s * omega
    u2rms = r2rms * omega
    beta2s_deg = -math.degrees(math.atan2(u2s, c1))
    beta2_deg = -math.degrees(math.atan2(u2rms, c1))

    r5 = knobs.diffuser_ratio * r4
    b5 = 0.9 * b4

    blade_e = max(0.2e-3, 0.012 * r4)
    clearance = max(20e-6, 0.04 * b4)

    return Geometry(
        r1=r1,
        r2s=r2s,
        r2h=r2h,
        beta2=beta2_deg,
        beta2s=beta2s_deg,
        alpha2=0.0,
        r4=r4,
        b4=b4,
        r5=r5,
        b5=b5,
        beta4=knobs.beta4_deg,
        n_blades=int(knobs.n_blades),
        n_splits=int(knobs.n_splits),
        blade_e=blade_e,
        rug_imp=1.0e-5,
        clearance=clearance,
        backface=clearance,
        rug_ind=1.0e-5,
        l_ind=2.0 * r4,
        l_comp=0.5 * r4,
        blockage=[1.0, 1.0, 1.0, 1.0, 1.0],
    )


def _initial_tip_speed(
    fld: Fluid, in0: ThermoProp, pr_target: float, knobs: DesignKnobs
) -> float:
    """Analytic first guess for the tip speed from the Euler relation."""
    p_out = pr_target * in0.P
    try:
        dh0s = fld.thermo_prop("PS", p_out, in0.S).H - in0.H
    except ThermoException:
        # Ideal-gas-ish fallback
        dh0s = in0.A**2 * (pr_target ** 0.2857 - 1.0)
    dh0 = dh0s / max(knobs.eta_guess, 0.3)
    beta4 = math.radians(knobs.beta4_deg)
    z_total = knobs.n_blades + knobs.n_splits
    slip = 1.0 - math.sqrt(max(math.cos(beta4), 1e-6)) / z_total**0.7
    lam = slip + knobs.flow_coeff * math.tan(beta4)  # work coefficient
    lam = max(lam, 0.2)
    return math.sqrt(dh0 / lam)


def _match_tip_speed(
    fld: Fluid,
    in0: ThermoProp,
    m: float,
    omega: float,
    pr_target: float,
    knobs: DesignKnobs,
    u_hint: Optional[float] = None,
) -> tuple[Optional[Geometry], StagePerformance, bool, float]:
    """Find the tip speed giving ``pr_target`` and return the matched stage.

    Scans the feasible tip-speed window, then refines with a bracketed solver.
    A ``u_hint`` (from a previous match) enables a narrow, cheap local scan.
    Returns ``(geometry, performance, converged, u_star)``.
    """
    u0 = _initial_tip_speed(fld, in0, pr_target, knobs)
    if u_hint is not None:
        u_lo, u_hi = 0.7 * u_hint, 1.4 * u_hint
        npts = max(6, knobs.scan_points // 2)
    else:
        u_lo, u_hi = 0.25 * u0, min(2.5 * u0, knobs.max_tip_speed)
        npts = knobs.scan_points
    grid = np.linspace(u_lo, min(u_hi, knobs.max_tip_speed), npts)

    feas: list[tuple[float, float, StagePerformance, Geometry]] = []
    for u4 in grid:
        geom = build_geometry(fld, in0, m, omega, float(u4), pr_target, knobs)
        perf = evaluate(geom, fld, in0, m, omega)
        if perf.valid:
            feas.append((float(u4), perf.pr - pr_target, perf, geom))

    if not feas:
        geom = build_geometry(fld, in0, m, omega, u0, pr_target, knobs)
        return geom, evaluate(geom, fld, in0, m, omega), False, u0

    bracket = None
    for (ua, fa, _, _), (ub, fb, _, _) in zip(feas, feas[1:]):
        if fa == 0.0:
            bracket = (ua, ua)
            break
        if fa * fb < 0.0:
            bracket = (ua, ub)
            break

    if bracket is not None and bracket[0] != bracket[1]:
        def err(u4: float) -> float:
            geom = build_geometry(fld, in0, m, omega, u4, pr_target, knobs)
            perf = evaluate(geom, fld, in0, m, omega)
            if not perf.valid:
                return 1e3
            return perf.pr - pr_target

        try:
            u_star = optimize.brentq(err, bracket[0], bracket[1], xtol=1e-2, rtol=1e-5)
            geom = build_geometry(fld, in0, m, omega, u_star, pr_target, knobs)
            perf = evaluate(geom, fld, in0, m, omega)
            if perf.valid:
                conv = abs(perf.pr - pr_target) / pr_target < 5e-3
                return geom, perf, conv, u_star
        except (ValueError, RuntimeError):
            pass

    best = min(feas, key=lambda t: abs(t[1]))
    converged = abs(best[1]) / pr_target < 1e-2
    return best[3], best[2], converged, best[0]


def design_stage(
    fld: Fluid,
    in0: ThermoProp,
    m: float,
    omega: float,
    pr_target: float,
    knobs: Optional[DesignKnobs] = None,
) -> StageDesign:
    """Design a single stage for the given duty.

    Parameters
    ----------
    fld : Fluid
        Working-fluid backend (e.g. ``CoolPropFluid``).
    in0 : ThermoProp
        Inlet total thermodynamic state.
    m : float
        Mass flow rate [kg/s].
    omega : float
        Shaft angular speed [rad/s].
    pr_target : float
        Target total-to-total pressure ratio for the stage.
    knobs : DesignKnobs, optional
        Shape coefficients and optimiser budget.
    """
    knobs = knobs or DesignKnobs()

    # Base design at the default shape (full tip-speed scan; warm-start hint).
    base_geom, base_perf, base_conv, u_hint = _match_tip_speed(
        fld, in0, m, omega, pr_target, knobs
    )

    candidates = []
    if base_geom is not None and base_perf.valid:
        candidates.append((base_perf, base_geom, base_conv, knobs))

    if knobs.optimize_shape:
        # The shape grid serves two purposes: extend the feasible pressure-ratio
        # window so the target can be reached, and then maximise efficiency.  A
        # narrow local scan is used when the base design is already feasible.
        hint = u_hint if (base_geom is not None and base_perf.valid) else None
        for phi in knobs.flow_coeff_grid:
            for b4 in knobs.beta4_grid:
                k = DesignKnobs(**{**asdict(knobs), "optimize_shape": False})
                k.flow_coeff = float(phi)
                k.beta4_deg = float(b4)
                g, p, c, _ = _match_tip_speed(
                    fld, in0, m, omega, pr_target, k, u_hint=hint
                )
                if g is not None and p.valid:
                    candidates.append((p, g, c, k))

    def _tol(p) -> float:
        return abs(p.pr - pr_target) / pr_target

    on_target = [ci for ci in candidates if _tol(ci[0]) < 0.01]
    if on_target:
        # Among designs that hit the target, keep the most efficient.
        perf, geom, converged, best_knobs = max(on_target, key=lambda ci: ci[0].eff)
    elif candidates:
        # None reached the target: keep the closest achievable pressure ratio.
        perf, geom, converged, best_knobs = min(candidates, key=lambda ci: _tol(ci[0]))
    else:
        return StageDesign(base_geom, base_perf, pr_target, knobs, False)

    # Final verification with the surge negative-slope check enabled.
    verified = evaluate(geom, fld, in0, m, omega, delta_check=True)
    if verified.valid:
        perf = verified
    converged = perf.valid and abs(perf.pr - pr_target) / pr_target < 5e-3

    return StageDesign(geom, perf, pr_target, best_knobs, converged)
