"""Tests for multi-stage design, intercooling and JSON I/O."""

import json

import pytest

from radcompressor.design import DesignKnobs
from radcompressor.io_json import duty_from_json, validate_duty
from radcompressor.multistage import DutySpec, design_compressor

FAST_KNOBS = DesignKnobs(optimize_shape=False, scan_points=12)


def _duty(**kw):
    base = dict(
        fluid="air", m=2.0, speed_rpm=20000, p_in=1.0e5, t_in=300.0,
        pr_target=2.0, n_stages=2, knobs=FAST_KNOBS,
    )
    base.update(kw)
    return DutySpec(**base)


def test_two_stage_meets_total_pr():
    d = design_compressor(_duty())
    assert all(s.performance.valid for s in d.stages)
    assert d.pr_total == pytest.approx(2.0, rel=0.01)
    assert 0.0 < d.eff_total <= 1.0


def test_intercooling_resets_interstage_temperature():
    hot = design_compressor(_duty(intercooling=False))
    cool = design_compressor(_duty(intercooling=True, t_cool=300.0))
    # Stage-2 inlet temperature is the second interstage entry.
    assert cool.interstage[1].t < hot.interstage[1].t
    assert cool.interstage[1].t == pytest.approx(300.0, abs=1.0)


def test_efficiency_bounded_with_intercooling():
    cool = design_compressor(_duty(intercooling=True, t_cool=300.0))
    assert 0.0 < cool.eff_total <= 1.0


def test_validate_duty_rejects_bad_input():
    with pytest.raises(ValueError):
        validate_duty({"fluid": "air"})  # missing keys
    with pytest.raises(ValueError):
        validate_duty(
            dict(fluid="air", m=1, speed_rpm=1, p_in=1, t_in=300, pr_target=0.9)
        )


def test_duty_json_roundtrip():
    text = json.dumps(
        dict(fluid="CO2", m=15.8, speed_rpm=27400, p_in=7.6e6, t_in=37,
             t_in_unit="C", pr_target=1.5, n_stages=1)
    )
    duty = duty_from_json(text)
    assert duty.fluid == "CO2"
    assert duty.t_in_k == pytest.approx(310.15)
    assert duty.n_stages == 1
