import json
import subprocess
from pathlib import Path


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_capacity_publication_helper_copies_valid_capacity_only_campaign(tmp_path):
    root = Path(__file__).resolve().parents[1]
    campaign = tmp_path / "n-cpu-moe-capacity-test"
    capacity_dir = campaign / "capacity"
    capacity_dir.mkdir(parents=True)

    for name in ("model.json", "doctor.json", "backend.json"):
        _write_json(campaign / name, {})

    _write_json(
        campaign / "build-provenance.json",
        {
            "schema": "tesy.llama_build_provenance.v1",
            "status": "PASS",
        },
    )
    _write_json(
        campaign / "admission-context.json",
        {
            "schema": "tesy.placement_admission_context.v1",
            "campaign_mode": "capacity-only",
        },
    )
    _write_json(
        campaign / "auto-fit.json",
        {
            "schema": "tesy.llama_fit_args.v1",
            "ctx_size": 4096,
            "argv": ["-c", "4096", "-ngl", "12"],
        },
    )
    _write_json(
        campaign / "capacity-summary.json",
        {
            "schema": "tesy.n_cpu_moe_capacity_gate.v1",
            "admitted_n_cpu_moe": [12, 16, 20, 24],
            "rejected_n_cpu_moe": [0, 4, 8],
            "performance_gate": "PASS",
        },
    )

    for name in (
        "tesy-head.txt",
        "llama-head.txt",
        "server-sha256.txt",
        "fit-tool-sha256.txt",
        "prompt-sha256.txt",
        "fit-tool-version.txt",
        "auto-fit.stdout.txt",
        "auto-fit.stderr.txt",
    ):
        (campaign / name).write_text("x\n", encoding="utf-8")
    (campaign / "tesy-status.txt").write_text("", encoding="utf-8")
    (campaign / "llama-status.txt").write_text("", encoding="utf-8")

    for n in (0, 4, 8, 12, 16, 20, 24):
        _write_json(capacity_dir / f"n{n:02d}.json", {"n_cpu_moe": n})
        (capacity_dir / f"n{n:02d}.stdout.txt").write_text("", encoding="utf-8")
        (capacity_dir / f"n{n:02d}.stderr.txt").write_text("", encoding="utf-8")

    publish = tmp_path / "published"
    completed = subprocess.run(
        [
            "bash",
            str(root / "scripts" / "publish_n_cpu_moe_capacity_result.sh"),
            str(campaign),
            str(publish),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "PASS_CAPACITY_PUBLICATION_PREPARED" in completed.stdout
    manifest = json.loads(
        (publish / "publication-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["classification"] == "SOURCE_BACKED_CAPACITY_GATE"
    assert manifest["admitted_n_cpu_moe"] == [12, 16, 20, 24]
    result = (publish / "RESULT.md").read_text(encoding="utf-8")
    assert "stops before timed llama-server observations" in result
