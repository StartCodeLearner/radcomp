"""Command-line interface for radial-compressor design and analysis.

Usage examples
--------------
    radcomp design duty.json -o result.json
    radcomp analyze geometry.json --fluid CO2 --p-in 7.6e6 --t-in 310 \
        --m 15.8 --rpm 27400
    radcomp map geometry.json --fluid CO2 --p-in 7.6e6 --t-in 310 -o map.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict

from .geometry import Geometry


def _add_inlet_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--fluid", required=True, help="CoolProp fluid name")
    p.add_argument("--p-in", type=float, required=True, help="inlet pressure [Pa]")
    p.add_argument("--t-in", type=float, required=True, help="inlet temperature [K]")
    p.add_argument("--m", type=float, required=True, help="mass flow [kg/s]")
    p.add_argument("--rpm", type=float, required=True, help="shaft speed [rpm]")


def cmd_design(args: argparse.Namespace) -> int:
    from .io_json import load_duty, save_design, design_to_json
    from .multistage import design_compressor

    duty = load_duty(args.duty)
    design = design_compressor(duty)
    if args.output:
        save_design(design, args.output)
        print(f"Wrote design to {args.output}", file=sys.stderr)
    if args.print or not args.output:
        print(design_to_json(design))

    p = design
    ok = p.converged and abs(p.pr_total - duty.pr_target) / duty.pr_target < 0.01
    print(
        f"[{duty.name or duty.fluid}] stages={duty.n_stages} "
        f"PR={p.pr_total:.3f} (target {duty.pr_target:.3f}) "
        f"eff={p.eff_total:.3f} power={p.power_total/1e3:.0f} kW "
        f"converged={ok}",
        file=sys.stderr,
    )
    return 0 if ok else 1


def cmd_analyze(args: argparse.Namespace) -> int:
    from .compressor import Compressor
    from .condition import OperatingCondition
    from .thermo import CoolPropFluid

    with open(args.geometry) as fp:
        gdata = json.load(fp)
    if "geometry" in gdata:  # accept a full design-result file
        gdata = gdata["geometry"]
    geom = Geometry.from_dict(gdata, blockage=gdata.get("blockage"))

    fld = CoolPropFluid(args.fluid)
    in0 = fld.thermo_prop("PT", float(args.p_in), float(args.t_in))
    op = OperatingCondition(
        in0=in0, fld=fld, m=float(args.m), n_rot=float(args.rpm) * math.pi / 30.0
    )
    comp = Compressor(geom, op)
    valid = comp.calculate()
    out = {
        "valid": bool(valid),
        "PR": comp.PR,
        "eff": comp.eff,
        "power": comp.power,
        "tip_speed": comp.tip_speed,
        "head": comp.head,
        "mach_in": comp.m_in,
    }
    print(json.dumps(out, indent=2))
    return 0 if valid else 1


def cmd_map(args: argparse.Namespace) -> int:
    from .thermo import CoolPropFluid
    from .maps import performance_map

    with open(args.geometry) as fp:
        gdata = json.load(fp)
    if "geometry" in gdata:
        gdata = gdata["geometry"]
    geom = Geometry.from_dict(gdata, blockage=gdata.get("blockage"))
    fld = CoolPropFluid(args.fluid)
    in0 = fld.thermo_prop("PT", float(args.p_in), float(args.t_in))

    result = performance_map(
        geom, fld, in0, n_speeds=args.speeds, n_flows=args.flows
    )
    if args.output:
        with open(args.output, "w") as fp:
            json.dump(result, fp, indent=2)
        print(f"Wrote map to {args.output}", file=sys.stderr)
    else:
        print(json.dumps(result, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="radcomp", description="Radial-compressor design and analysis"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    pd = sub.add_parser("design", help="design a compressor from a duty JSON file")
    pd.add_argument("duty", help="path to duty JSON file")
    pd.add_argument("-o", "--output", help="path to write the design result JSON")
    pd.add_argument("--print", action="store_true", help="also print result to stdout")
    pd.set_defaults(func=cmd_design)

    pa = sub.add_parser("analyze", help="evaluate a geometry at one operating point")
    pa.add_argument("geometry", help="path to geometry (or design-result) JSON")
    _add_inlet_args(pa)
    pa.set_defaults(func=cmd_analyze)

    pm = sub.add_parser("map", help="generate a performance map for a geometry")
    pm.add_argument("geometry", help="path to geometry (or design-result) JSON")
    _add_inlet_args_map(pm)
    pm.add_argument("--speeds", type=int, default=8, help="number of speed lines")
    pm.add_argument("--flows", type=int, default=20, help="points per speed line")
    pm.add_argument("-o", "--output", help="path to write the map JSON")
    pm.set_defaults(func=cmd_map)

    return parser


def _add_inlet_args_map(p: argparse.ArgumentParser) -> None:
    p.add_argument("--fluid", required=True, help="CoolProp fluid name")
    p.add_argument("--p-in", type=float, required=True, help="inlet pressure [Pa]")
    p.add_argument("--t-in", type=float, required=True, help="inlet temperature [K]")


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
