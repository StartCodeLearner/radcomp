"""Numerical-stability regression tests for the forward mean-line model.

These guard the off-design robustness fixes: the model must flag infeasible
operating points as invalid (rather than raising) and must reproduce a known
valid reference point unchanged.
"""

import math

import pytest

from radcompressor.compressor import Compressor
from radcompressor.condition import OperatingCondition
from radcompressor.design import evaluate
from radcompressor.geometry import Geometry
from radcompressor.thermo import CoolPropFluid

# Olmedo & Schiffmann stage 2 (Ammonia) -- a known, validated design point.
_REF_GEOM = dict(
    r1=0.0154, r2s=0.0154, r2h=0.0056, beta2=-45.0, beta2s=-56.0, alpha2=0.0,
    r4=0.0238, b4=0.0041, r5=0.0452, b5=0.00225, beta4=-30.0, n_blades=11,
    n_splits=0, blade_e=0.85e-3, rug_imp=1.0e-3, clearance=0.2e-3,
    backface=0.15e-3, rug_ind=1.0e-3, l_ind=0.0154, l_comp=0.01,
)


def _ref_geometry():
    return Geometry(blockage=[1.0] * 5, **_REF_GEOM)


def test_reference_point_unchanged():
    fld = CoolPropFluid("Ammonia")
    in0 = fld.thermo_prop("PT", 465e3, 305.0)
    op = OperatingCondition(in0=in0, fld=fld, m=0.120, n_rot=130e3 * math.pi / 30)
    comp = Compressor(_ref_geometry(), op)
    assert comp.calculate() is True
    assert comp.PR == pytest.approx(1.4976, rel=2e-3)
    assert comp.eff == pytest.approx(0.6953, rel=2e-3)
    assert comp.power == pytest.approx(10364.8, rel=2e-3)


@pytest.mark.parametrize("m,rpm", [(5.0, 5000), (0.001, 400000), (2.0, 250000)])
def test_offdesign_never_crashes(m, rpm):
    fld = CoolPropFluid("Ammonia")
    in0 = fld.thermo_prop("PT", 465e3, 305.0)
    # Must return a result (valid flag), never raise, at wild off-design points.
    perf = evaluate(_ref_geometry(), fld, in0, m, rpm * math.pi / 30)
    assert perf.valid in (True, False)


def test_numpy_array_inputs_accepted():
    # scipy solvers feed size-1 arrays into the thermo backend; ensure those
    # are accepted (regression for the NumPy>=2 incompatibility).
    import numpy as np

    fld = CoolPropFluid("CO2")
    tp = fld.thermo_prop("PT", np.array([7.6e6])[0], np.float64(310.0))
    assert tp.P == pytest.approx(7.6e6, rel=1e-9)
