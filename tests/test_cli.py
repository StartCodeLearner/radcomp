"""Smoke tests for the radcomp command-line interface."""

import json

from radcompressor.cli import main

_REF_GEOM = dict(
    r1=0.0154, r2s=0.0154, r2h=0.0056, beta2=-45.0, beta2s=-56.0, alpha2=0.0,
    r4=0.0238, b4=0.0041, r5=0.0452, b5=0.00225, beta4=-30.0, n_blades=11,
    n_splits=0, blade_e=0.85e-3, rug_imp=1.0e-3, clearance=0.2e-3,
    backface=0.15e-3, rug_ind=1.0e-3, l_ind=0.0154, l_comp=0.01,
    blockage=[1.0, 1.0, 1.0, 1.0, 1.0],
)


def test_cli_analyze_reference(tmp_path, capsys):
    gpath = tmp_path / "geom.json"
    gpath.write_text(json.dumps(_REF_GEOM))
    rc = main(
        [
            "analyze", str(gpath), "--fluid", "Ammonia",
            "--p-in", "465000", "--t-in", "305", "--m", "0.120", "--rpm", "130000",
        ]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["valid"] is True
    assert abs(out["PR"] - 1.4976) < 0.01


def test_cli_design_from_file(tmp_path, capsys):
    duty = dict(
        fluid="air", m=2.0, speed_rpm=20000, p_in=1.0e5, t_in=300.0,
        pr_target=1.5, n_stages=1,
        knobs={"optimize_shape": False, "scan_points": 12},
    )
    dpath = tmp_path / "duty.json"
    opath = tmp_path / "result.json"
    dpath.write_text(json.dumps(duty))
    rc = main(["design", str(dpath), "-o", str(opath)])
    assert rc == 0
    result = json.loads(opath.read_text())
    assert abs(result["pr_total"] - 1.5) / 1.5 < 0.01
    assert result["stages"][0]["performance"]["valid"] is True
