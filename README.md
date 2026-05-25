# RadCompressor: Radial compressor mean-line model

Mean-line (1D) model for evaluating radial compressors. The code is adapted
from the version developed by Schiffmann and Favrat[^1], and was used to generate
a turbo-compressor dataset for *DATED*.

Cyril Picard, Jürg Schiffmann and Faez Ahmed, "DATED: Guidelines for Creating Synthetic
Datasets for Engineering Design Applications", 2023.

[^1]: Jürg Schiffmann and Daniel Favrat, “Design, experimental investigation and multi-objective optimization of a small-scale radial compressor for heat pump applications,” Energy, vol. 35, no. 1, pp. 436–450, Jan. 2010, doi: [10.1016/j.energy.2009.10.010](https://doi.org/10.1016/j.energy.2009.10.010).


## Datasets

The dataset related to *DATED* is available on [Zenodo](https://zenodo.org/record/8200792).

## Using the model

### Installation

To install this package, first make sure that you have Python >= 3.9 installed in your environment. If not, we
recommend to install Python using [mambaforge](https://github.com/conda-forge/miniforge#mambaforge).

```bash
git clone https://github.com/cyrilpic/radcomp
cd radcomp
pip install .
```

If you want to install all dependencies to use the dataset generation scripts:

```bash
pip install .[generate]
```

### Basic Usage

A step-by-step example is provided in the [EvaluateCompressor.ipynb notebook](notebooks/EvaluateCompressor.ipynb).

## Compressor design (inverse problem)

The base model is a *forward* analysis (geometry + operating point ->
performance). The `radcompressor.design` and `radcompressor.multistage`
modules add the *inverse* problem: given a duty they synthesise a consistent
mean-line geometry, size the tip speed to hit the target pressure ratio and
tune the shape coefficients for efficiency. Multi-stage trains propagate the
inter-stage state and support optional intercooling.

### Command line

A `radcomp` console script (also `python -m radcompressor.cli`) exposes three
sub-commands:

```bash
radcomp design duty.json -o result.json        # design from a JSON duty
radcomp analyze geometry.json --fluid CO2 --p-in 7.6e6 --t-in 310 --m 15.8 --rpm 27400
radcomp map     geometry.json --fluid CO2 --p-in 7.6e6 --t-in 310 -o map.json
```

### Python API

```python
from radcompressor.io_json import load_duty, save_design
from radcompressor.multistage import design_compressor

design = design_compressor(load_duty("duty.json"))
save_design(design, "result.json")
print(design.pr_total, design.eff_total, design.power_total)
```

A duty JSON uses SI base units (Pa, kg/s, rpm); temperature may be given in
degrees Celsius with `"t_in_unit": "C"`:

```json
{
  "name": "co2_stage", "fluid": "CO2",
  "m": 15.8, "speed_rpm": 27400,
  "p_in": 7600000.0, "t_in": 37.0, "t_in_unit": "C",
  "pr_target": 1.5, "n_stages": 1, "intercooling": false
}
```

The seven benchmark duties in `examples/duties/` are designed end-to-end by
`python examples/run_design_suite.py`.

> **Note on dependencies:** CoolProp requires native Python floats; the
> thermodynamic backend casts NumPy scalars and size-1 solver arrays, so the
> model runs under both NumPy 1.x and NumPy >= 2.


## Citation

If you use the dataset or the model, you can cite our publication:

Cyril Picard, Jürg Schiffmann and Faez Ahmed, "DATED: Guidelines for Creating Synthetic
Datasets for Engineering Design Applications", 2023.
