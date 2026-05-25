"""JSON input/output for compressor duties, designs and performance maps."""

from __future__ import annotations

import json
from typing import Any, Dict

from .design import DesignKnobs
from .multistage import DutySpec, MultiStageDesign, design_compressor

_REQUIRED_DUTY = ("fluid", "m", "speed_rpm", "p_in", "t_in", "pr_target")


def validate_duty(d: Dict[str, Any]) -> None:
    """Raise ``ValueError`` if a duty dictionary is missing required keys or
    holds clearly invalid values."""
    missing = [k for k in _REQUIRED_DUTY if k not in d]
    if missing:
        raise ValueError(f"Duty is missing required keys: {missing}")
    if d["m"] <= 0:
        raise ValueError("Mass flow 'm' must be positive.")
    if d["speed_rpm"] <= 0:
        raise ValueError("Shaft speed 'speed_rpm' must be positive.")
    if d["p_in"] <= 0:
        raise ValueError("Inlet pressure 'p_in' must be positive.")
    if d["pr_target"] <= 1:
        raise ValueError("Target pressure ratio 'pr_target' must be > 1.")
    if int(d.get("n_stages", 1)) < 1:
        raise ValueError("'n_stages' must be >= 1.")


def load_duty(path: str) -> DutySpec:
    """Load and validate a duty specification from a JSON file."""
    with open(path, "r") as fp:
        data = json.load(fp)
    validate_duty(data)
    return DutySpec.from_dict(data)


def duty_from_json(text: str) -> DutySpec:
    data = json.loads(text)
    validate_duty(data)
    return DutySpec.from_dict(data)


def save_design(design: MultiStageDesign, path: str) -> None:
    """Write a multi-stage design result to a JSON file."""
    with open(path, "w") as fp:
        json.dump(
            _sanitize(design.to_dict()), fp, indent=2, default=_json_default,
            allow_nan=False,
        )


def design_to_json(design: MultiStageDesign) -> str:
    return json.dumps(
        _sanitize(design.to_dict()), indent=2, default=_json_default,
        allow_nan=False,
    )


def _sanitize(obj):
    """Replace non-finite floats (NaN/Inf) with ``None`` so the output is valid
    strict JSON; infeasible stages otherwise carry NaN performance fields."""
    import math

    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj


def run_duty_file(duty_path: str, out_path: str | None = None) -> MultiStageDesign:
    """Convenience: load a duty file, design it, optionally save the result."""
    duty = load_duty(duty_path)
    design = design_compressor(duty)
    if out_path is not None:
        save_design(design, out_path)
    return design


def _json_default(obj: Any):
    if isinstance(obj, DesignKnobs):
        from dataclasses import asdict

        return asdict(obj)
    try:
        import numpy as np

        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
    except ImportError:
        pass
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
