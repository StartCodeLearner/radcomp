"""Tests for the single-stage inverse design loop."""

import math

import pytest

from radcompressor.design import DesignKnobs, build_geometry, design_stage
from radcompressor.thermo import CoolPropFluid

# Fast, well-conditioned duty (air, far from any critical point).
FLUID = "air"
M = 2.0
RPM = 20000
P_IN = 1.0e5
T_IN = 300.0
OMEGA = RPM * math.pi / 30


def _inlet():
    fld = CoolPropFluid(FLUID)
    return fld, fld.thermo_prop("PT", P_IN, T_IN)


def test_design_stage_meets_target_pr():
    fld, in0 = _inlet()
    knobs = DesignKnobs(optimize_shape=False, scan_points=12)
    d = design_stage(fld, in0, M, OMEGA, 1.5, knobs)
    assert d.performance.valid
    assert d.performance.pr == pytest.approx(1.5, rel=0.01)
    assert 0.5 < d.performance.eff < 1.0
    # Geometry sanity: exit radius larger than inlet eye, positive width.
    assert d.geometry.r4 > d.geometry.r2s > 0
    assert d.geometry.b4 > 0


def test_optimum_inducer_minimises_relative_radius():
    # The optimum-incidence inducer radius is independent of tip speed.
    fld, in0 = _inlet()
    k = DesignKnobs()
    g1 = build_geometry(fld, in0, M, OMEGA, 200.0, 1.6, k)
    g2 = build_geometry(fld, in0, M, OMEGA, 350.0, 1.6, k)
    assert g1.r2s == pytest.approx(g2.r2s, rel=1e-9)


def test_higher_pr_needs_higher_tip_speed():
    fld, in0 = _inlet()
    knobs = DesignKnobs(optimize_shape=False, scan_points=12)
    lo = design_stage(fld, in0, M, OMEGA, 1.3, knobs)
    hi = design_stage(fld, in0, M, OMEGA, 1.6, knobs)
    assert lo.performance.valid and hi.performance.valid
    assert hi.performance.tip_speed > lo.performance.tip_speed
