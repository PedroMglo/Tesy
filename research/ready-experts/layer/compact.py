"""Publish the portable decision from the verified private unit archive."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

MANIFEST = "36257ad557533044a2dd29fab83fe759ac9d8cfe4d26f995c9d76d4087359c07"


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def publish(archive, out):
    manifest = archive / "manifest.json"
    if sha(manifest) != MANIFEST:
        raise ValueError("different unit archive")
    files = json.loads(manifest.read_bytes())["files"]
    for name, (size, expected) in files.items():
        p = archive / name
        if p.is_symlink() or p.stat().st_size != size or sha(p) != expected:
            raise ValueError("archive identity " + name)

    def receipt(label):
        return json.loads((archive / label / "receipt.json").read_bytes())

    physical = receipt("physical")
    policy = receipt("c55")
    proof = receipt("proof")
    combined = receipt("combined")
    if (
        receipt("verification") != proof
        or receipt("combined-verification") != combined
        or physical["status"] != "MEASURED"
        or policy["status"] != "PASS_RESOURCE_WINDOW_ONLY"
    ):
        raise ValueError("missing independent verification or physical admission")
    observation = {
        k: physical[k]
        for k in (
            "status",
            "commit",
            "tree",
            "protocol_sha256",
            "source_sha256",
            "build_sha256",
            "binary_sha256",
            "input_sha256",
            "reference_sha256",
            "plan_sha256",
            "prestate_sha256",
            "placement_sha256",
            "rank_receipt_sha256",
            "c55_sha256",
            "monitor_sha256",
            "stdout_sha256",
            "samples",
            "child_wall_s",
            "elapsed_s",
            "rchar_bytes",
            "full_model_requests",
            "gpu_compute",
            "result",
        )
    }
    observation.update(
        c118=physical["c118"],
        cgroup_peak_bytes=physical["final_cgroup"]["memory_peak"],
        cgroup_cap_bytes=physical["final_cgroup"]["memory_max"],
        swap_cap_bytes=physical["final_cgroup"]["swap_max"],
        energy_j=None,
        monitor=physical["monitor_provider"],
        host={
            k: policy[k]
            for k in (
                "cpu",
                "gpu_name",
                "gpu_total_mib",
                "gpu_driver",
                "model_device",
                "model_fs",
                "cpu_c_max",
                "gpu_c_max",
                "nvme_c_max",
                "gpu_compute_max",
                "concurrent",
                "memory",
            )
        },
    )
    out.mkdir(mode=0o700)
    shutil.copyfile(archive / "proof/proof.json.gz", out / "certificate.json.gz")
    shutil.copyfile(archive / "combined/banks.json", out / "oracle-banks.json")
    result = {
        "schema": "tesy.ready_layer.decision.v1",
        "archive_manifest_sha256": MANIFEST,
        "private_files": len(files),
        "raw_bytes_before_manifest": sum(v[0] for v in files.values()),
        "operator": observation,
        "fixed_parent_bank": receipt("causality"),
        "all_fixed_banks": proof,
        "hypothetical_client_credit": combined,
        "causal_controls": receipt("controls"),
        "preserved_failures": {k: receipt(k) for k in ("physical-r01-fail", "proof-r01-fail")},
    }
    tmp = out / ".pending"
    tmp.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.rename(out / "decision.json")
    print(sha(out / "decision.json"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    publish(args.archive, args.new_output_dir)
