"""Performance-map generation: speed lines over a flow range.

For a fixed geometry and inlet state this sweeps mass flow at several shaft
speeds, returning total pressure ratio and efficiency along each speed line
together with the surge (low-flow) and choke (high-flow) feasibility limits.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

from .design import evaluate
from .geometry import Geometry
from .thermo import Fluid, ThermoProp
from .utils import upper_bounds


def performance_map(
    geom: Geometry,
    fld: Fluid,
    in0: ThermoProp,
    n_speeds: int = 8,
    n_flows: int = 25,
    speed_lo_frac: float = 0.4,
    speed_hi_frac: float = 1.0,
    max_mach_rot: float = 2.5,
    max_mach_flow: float = 0.7,
) -> dict:
    """Generate a performance map (speed lines) for ``geom`` at inlet ``in0``.

    Returns a JSON-serialisable dict with one entry per speed line; each line
    lists the feasible operating points and the surge/choke flow limits.
    """
    n_rot_max, mflow_max = upper_bounds(
        geom, in0, max_mach_rot=max_mach_rot, max_mach_flow=max_mach_flow
    )
    speeds = np.linspace(
        speed_lo_frac * n_rot_max, speed_hi_frac * n_rot_max, n_speeds
    )
    flows = np.linspace(0.02 * mflow_max, mflow_max, n_flows)

    lines = []
    for omega in speeds:
        pts = []
        for m in flows:
            perf = evaluate(geom, fld, in0, float(m), float(omega))
            if perf.valid:
                pts.append(
                    {
                        "m": float(m),
                        "n_rot": float(omega),
                        "rpm": float(omega) * 30.0 / math.pi,
                        "PR": perf.pr,
                        "eff": perf.eff,
                        "power": perf.power,
                    }
                )
        line = {
            "rpm": float(omega) * 30.0 / math.pi,
            "n_rot": float(omega),
            "n_points": len(pts),
            "surge_flow": pts[0]["m"] if pts else None,
            "choke_flow": pts[-1]["m"] if pts else None,
            "points": pts,
        }
        lines.append(line)

    return {
        "inlet": {"P": in0.P, "T": in0.T, "fluid": getattr(fld, "name", "")},
        "n_rot_max": float(n_rot_max),
        "mflow_max": float(mflow_max),
        "speed_lines": lines,
    }
