import pytest

from radcompressor.thermo import CoolPropFluid


def test_coolprop_fluid():
    # Test that the CoolPropFluid class returns the correct properties.
    # Use approximate comparisons: exact values vary slightly between CoolProp
    # releases (e.g. T_crit = 647.0959999999873 in CoolProp 7.x).
    water = CoolPropFluid("water")
    assert water.T_crit == pytest.approx(647.096, rel=1e-6)
    assert water.P_crit == pytest.approx(22064000.0, rel=1e-6)

    tp = water.thermo_prop("TQ", 290, 0)
    assert tp.D == pytest.approx(998.7578446208877, rel=1e-6)
