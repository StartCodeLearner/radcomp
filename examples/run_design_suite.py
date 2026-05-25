#!/usr/bin/env python3
"""End-to-end aerodynamic-design suite for the seven benchmark duties.

Designs every duty JSON in ``examples/duties``, writes the full design result
to ``examples/results`` and prints a summary table.  Duties that the mean-line
model cannot satisfy (e.g. choke near the CO2 critical point, or a near-
saturated steam inlet) are reported as infeasible with their stage state rather
than silently producing nonsense -- this exercises the model's validity checks.

Run from the repository root:

    python examples/run_design_suite.py
"""

from __future__ import annotations

import glob
import os
import time

from radcompressor.io_json import load_duty, save_design
from radcompressor.multistage import design_compressor

HERE = os.path.dirname(os.path.abspath(__file__))
DUTY_DIR = os.path.join(HERE, "duties")
OUT_DIR = os.path.join(HERE, "results")


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    duty_files = sorted(glob.glob(os.path.join(DUTY_DIR, "*.json")))

    header = (
        f"{'case':<14}{'fluid':<7}{'stg':>3}{'PR':>8}{'target':>8}"
        f"{'eff':>7}{'P[kW]':>9}{'Umax':>7}{'t[s]':>6}  status"
    )
    print(header)
    print("-" * len(header))

    n_ok = 0
    for path in duty_files:
        duty = load_duty(path)
        t0 = time.perf_counter()
        design = design_compressor(duty)
        dt = time.perf_counter() - t0

        save_design(design, os.path.join(OUT_DIR, f"{duty.name or duty.fluid}.json"))

        valid_stages = [s for s in design.stages if s.performance.valid]
        all_valid = len(valid_stages) == duty.n_stages
        pr_ok = (
            all_valid
            and abs(design.pr_total - duty.pr_target) / duty.pr_target < 0.01
        )
        umax = max((s.performance.tip_speed for s in valid_stages), default=float("nan"))
        status = "OK" if pr_ok else f"INFEASIBLE ({len(valid_stages)}/{duty.n_stages} stages)"
        n_ok += int(pr_ok)

        print(
            f"{(duty.name or duty.fluid):<14}{duty.fluid:<7}{duty.n_stages:>3}"
            f"{design.pr_total:>8.3f}{duty.pr_target:>8.3f}"
            f"{design.eff_total:>7.3f}{design.power_total/1e3:>9.0f}"
            f"{umax:>7.0f}{dt:>6.0f}  {status}"
        )

    print("-" * len(header))
    print(f"{n_ok}/{len(duty_files)} duties met their target pressure ratio.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
