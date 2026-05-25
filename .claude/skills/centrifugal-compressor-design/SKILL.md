---
name: centrifugal-compressor-design
description: >-
  Design and analyse centrifugal (radial) compressors with radcomp. Use when
  the user wants to size a compressor to a target pressure ratio, run a
  multi-stage train (with optional intercooling), evaluate a geometry, or
  generate a performance map. Handles a JSON duty in / design JSON out workflow
  and the `radcomp` CLI. The design JSON also feeds the rotordynamics handoff to
  ROSS (rotor build, critical speeds / stability, DyRoBeS export) via the
  `compressor_rotor` package in the ross repository.
---

# Centrifugal compressor design harness

This skill drives the `radcompressor` package to take a compressor **duty**
(fluid, mass flow, shaft speed, inlet state, target pressure ratio, number of
stages) through to a complete mean-line **aerodynamic design**.

## When to use

- "Design a compressor for PR=X at N rpm handling m kg/s of <fluid>."
- "Size a 4-stage CO2 compressor with intercooling."
- "Evaluate this impeller geometry / make a performance map."

## The workflow

1. **Write a duty JSON** (SI base units; temperature may be given in °C with
   `"t_in_unit": "C"`):

   ```json
   {
     "name": "case3_co2", "fluid": "CO2",
     "m": 15.8, "speed_rpm": 27400,
     "p_in": 7600000.0, "t_in": 37.0, "t_in_unit": "C",
     "pr_target": 1.5, "n_stages": 1,
     "intercooling": false
   }
   ```

   Intercooling (default off, per project convention) is enabled with
   `"intercooling": true` and optionally `"t_cool"`, `"t_cool_unit"`,
   `"intercooler_dp_frac"` and `"intercool_after": [1,2]` (1-based stage
   indices after which a cooler sits).

2. **Run the design** either via the CLI or the API:

   ```bash
   radcomp design duty.json -o result.json
   # or: python -m radcompressor.cli design duty.json -o result.json
   ```

   ```python
   from radcompressor.io_json import load_duty, save_design
   from radcompressor.multistage import design_compressor
   design = design_compressor(load_duty("duty.json"))
   save_design(design, "result.json")
   ```

3. **Read the result.** The result JSON contains `pr_total`, `eff_total`
   (power-weighted stage efficiency, valid with or without intercooling),
   `power_total`, per-stage geometry + performance, and the inter-stage states.
   A stage with `performance.valid == false` was rejected by the model's
   validity checks (choke, surge, two-phase) -- report this honestly with the
   reason rather than forcing a number.

## How the design works (so you can reason about results)

- radcomp is a **forward** model (geometry + operating point -> performance).
  The design layer adds the inverse problem.
- A consistent mean-line geometry is parametrised by tip speed **U4**; the
  inducer is sized at the **relative-Mach-minimising radius**
  (optimum-incidence inducer).
- Target pressure ratio is met by root-finding U4 (work ~ U4*c4t), then the
  exit flow coefficient and back-sweep are tuned to maximise efficiency.
- Multi-stage: the total PR is split as an adaptive geometric mean over the
  remaining stages; discharge state propagates to the next inlet; an optional
  intercooler resets the inter-stage temperature (constant-pressure cooling
  with an optional pressure-drop fraction).

## Other commands

```bash
radcomp analyze geometry.json --fluid CO2 --p-in 7.6e6 --t-in 310 --m 15.8 --rpm 27400
radcomp map geometry.json --fluid CO2 --p-in 7.6e6 --t-in 310 -o map.json
```

`analyze` and `map` accept either a bare geometry JSON or a full design-result
JSON (they read its `geometry` block).

## Rotordynamics handoff (ROSS + DyRoBeS)

The design `result.json` is the bridge contract to the rotor stage, implemented
in the **ross** repository under `compressor_rotor/`. From the ross repo root:

```bash
python -m compressor_rotor analyze result.json -o rotor_analysis.json
python -m compressor_rotor dyrobes result.json -o rotor.dyr
python -m compressor_rotor build   result.json --outdir rotor_out/   # both + rotor.toml
```

It lays out a between-bearing rotor (shaft sized to the impeller eye, impellers
as disks via a fill factor, size-consistent journal bearings -- all overridable
with a structural-config JSON via `-s`), runs damped critical speeds, modal
log-decrement stability and a synchronous unbalance sweep, and writes a DyRoBeS
ASCII model. Bearing coefficients default to a size estimate -- replace them
with real data for a final analysis.

## End-to-end suite

`examples/run_design_suite.py` designs the seven benchmark duties in
`examples/duties/` and prints a summary table. Use it as the template for
batch design studies.

## Gotchas

- **Near-critical CO2** (inlet just above the critical point) has a very low
  speed of sound, so high single-stage pressure ratios choke. Prefer more
  stages or more inlet superheat.
- **Near-saturated vapour** (e.g. steam at ~0 K superheat) goes two-phase as
  soon as the flow accelerates; the stage is correctly flagged invalid.
- CoolProp needs native Python floats; the backend already casts NumPy
  scalars/size-1 arrays, so the model is safe under NumPy >= 2.
