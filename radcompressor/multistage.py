"""Multi-stage centrifugal-compressor design with optional intercooling.

Builds on :func:`radcompressor.design.design_stage` to design a train of
stages on a single shaft.  The total pressure ratio is distributed across the
stages, the thermodynamic state is propagated from one stage discharge to the
next stage inlet, and optional intercoolers reset the inter-stage temperature
(modelled as a constant-pressure heat removal with a small pressure drop).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from .design import DesignKnobs, StageDesign, design_stage
from .thermo import Fluid


def _to_kelvin(t: float, unit: str) -> float:
    unit = unit.upper()
    if unit in ("K",):
        return float(t)
    if unit in ("C", "DEGC", "CELSIUS"):
        return float(t) + 273.15
    raise ValueError(f"Unknown temperature unit: {unit}")


@dataclass
class DutySpec:
    """Compressor duty specification (SI base units unless noted)."""

    fluid: str
    m: float  # kg/s
    speed_rpm: float  # rpm
    p_in: float  # Pa
    t_in: float  # temperature, see t_in_unit
    pr_target: float  # total-to-total pressure ratio
    n_stages: int = 1
    t_in_unit: str = "K"  # "K" or "C"
    # Intercooling -------------------------------------------------------
    intercooling: bool = False
    t_cool: Optional[float] = None  # intercooler outlet T; default = inlet T
    t_cool_unit: str = "K"
    intercooler_dp_frac: float = 0.0  # fractional total-pressure drop per cooler
    intercool_after: Optional[List[int]] = None  # 1-based stage indices; None=all
    # Design knobs -------------------------------------------------------
    knobs: Optional[DesignKnobs] = None
    name: str = ""

    @property
    def t_in_k(self) -> float:
        return _to_kelvin(self.t_in, self.t_in_unit)

    @property
    def t_cool_k(self) -> Optional[float]:
        if self.t_cool is None:
            return None
        return _to_kelvin(self.t_cool, self.t_cool_unit)

    @property
    def omega(self) -> float:
        return self.speed_rpm * math.pi / 30.0

    @classmethod
    def from_dict(cls, d: dict) -> "DutySpec":
        d = dict(d)
        knobs = d.pop("knobs", None)
        if isinstance(knobs, dict):
            knobs = DesignKnobs(**knobs)
        return cls(knobs=knobs, **d)


@dataclass
class InterStageState:
    stage: int  # 1-based; the inlet to this stage
    p: float
    t: float
    cooled: bool = False


@dataclass
class MultiStageDesign:
    duty: DutySpec
    stages: List[StageDesign] = field(default_factory=list)
    interstage: List[InterStageState] = field(default_factory=list)
    pr_total: float = math.nan
    eff_total: float = math.nan  # overall isentropic (total-to-total) efficiency
    power_total: float = math.nan  # aerodynamic power summed over stages [W]
    converged: bool = False

    def to_dict(self) -> dict:
        return {
            "duty": _duty_to_dict(self.duty),
            "pr_total": self.pr_total,
            "pr_target": self.duty.pr_target,
            "eff_total": self.eff_total,
            "power_total": self.power_total,
            "converged": self.converged,
            "interstage": [asdict(s) for s in self.interstage],
            "stages": [s.to_dict() for s in self.stages],
        }


def _duty_to_dict(duty: DutySpec) -> dict:
    d = asdict(duty)
    if isinstance(d.get("knobs"), dict) or d.get("knobs") is None:
        pass
    return d


def _aggregate_efficiency(stages) -> float:
    """Power-weighted mean of the per-stage isentropic efficiencies.

    This is well defined with or without intercooling (each stage efficiency is
    bounded by 1), unlike a single end-to-end isentropic efficiency which is
    meaningless once heat is removed between stages.
    """
    num = 0.0
    den = 0.0
    for s in stages:
        p = s.performance
        if p.valid and math.isfinite(p.eff) and math.isfinite(p.power):
            num += p.power * p.eff
            den += p.power
    if den <= 0.0:
        return math.nan
    return num / den


def design_compressor(duty: DutySpec, fld: Optional[Fluid] = None) -> MultiStageDesign:
    """Design a (possibly multi-stage, possibly intercooled) compressor."""
    from .thermo import CoolPropFluid

    if fld is None:
        fld = CoolPropFluid(duty.fluid)

    omega = duty.omega
    n = int(duty.n_stages)
    knobs = duty.knobs or DesignKnobs()
    t_cool_k = duty.t_cool_k if duty.t_cool_k is not None else duty.t_in_k

    in0_first = fld.thermo_prop("PT", float(duty.p_in), float(duty.t_in_k))

    result = MultiStageDesign(duty=duty)
    in_state = in0_first
    cumulative_pr = 1.0
    overall_dh = 0.0  # actual enthalpy rise summed over stages (work)
    converged_all = True

    for i in range(n):
        # Adaptive split: distribute the *remaining* pressure ratio as a
        # geometric mean over the *remaining* stages so drift is corrected.
        remaining = duty.pr_target / cumulative_pr
        pr_stage = remaining ** (1.0 / (n - i))

        result.interstage.append(
            InterStageState(
                stage=i + 1,
                p=in_state.P,
                t=in_state.T,
                cooled=(i > 0 and _cools_before(duty, i + 1)),
            )
        )

        sd = design_stage(fld, in_state, duty.m, omega, pr_stage, knobs)
        result.stages.append(sd)
        converged_all = converged_all and sd.converged and sd.performance.valid

        if not sd.performance.valid:
            # Cannot propagate a meaningful state; stop early.
            converged_all = False
            break

        cumulative_pr *= sd.performance.pr
        overall_dh += sd.performance.h_out - in_state.H

        # Build discharge total state and propagate to the next stage inlet.
        disch = fld.thermo_prop("PT", sd.performance.p_out, sd.performance.t_out)

        if i < n - 1 and _cools_before(duty, i + 2):
            p_next = sd.performance.p_out * (1.0 - duty.intercooler_dp_frac)
            in_state = fld.thermo_prop("PT", p_next, t_cool_k)
        else:
            in_state = disch

    result.pr_total = cumulative_pr
    result.converged = converged_all
    if result.stages and result.stages[-1].performance.valid:
        result.power_total = sum(
            s.performance.power for s in result.stages if s.performance.valid
        )
        result.eff_total = _aggregate_efficiency(result.stages)
    return result


def _cools_before(duty: DutySpec, stage_1based: int) -> bool:
    """Whether an intercooler sits before the given (1-based) stage inlet."""
    if not duty.intercooling or stage_1based <= 1:
        return False
    if duty.intercool_after is None:
        return True  # cool before every stage after the first
    # intercool_after lists the stage *after which* cooling occurs.
    return (stage_1based - 1) in duty.intercool_after
