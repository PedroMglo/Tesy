"""Recheck the build ELF hashes and the ten CPU controls from a sealed build directory."""

import argparse
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
b = run_path(HERE / "build.py")
SHA = "4762116405b6f4bf3fee225be62b4485c01228dccc647febdfd36b8515b5d5bc"


def verify(directory):
    sha, need, rv = b["sha"], b["need"], b["rv"]
    r = b["pinned_json"](directory / "receipt.json", SHA)
    need(
        r["policy_status"] == "PASS_POLICY_DSO_CPU_BUILD_ONLY"
        and r["status"] == "PASS_C269_PHASE_FD_PRIVATE_BUILD"
        and sha(directory / r["candidate_file"]) == r["candidate_sha256"]
        and sha(directory / r["gold_file"]) == r["gold_sha256"] == b["old"]["ORIGINAL"]
        and sha(HERE / "build.py") == r["program_sha256"]
        and sha(HERE / "build-protocol.md") == r["protocol_sha256"],
        "authentic code and two binaries",
    )
    for name, digest in r["objects"].items():
        need(sha(directory / "candidate" / (Path(name).name + ".o")) == digest, "shipped object")
    for mode, info in r["cpu_objects"].items():
        need(sha(directory / mode / "fixture") == info["executable_sha256"], "CPU executable")
    need(
        r["cpu_objects"]["cpu-candidate"]["manager_sha256"] == r["objects"][b["old"]["MGR"]],
        "shared object",
    )
    images = {
        "gold": r["gold_sha256"],
        "pfj_control": b["PFJ_CONTROL"],
        "candidate": r["candidate_sha256"],
    }
    summary = {}
    for client, profiles in r["startup"].items():
        controls = profiles["pfj_control"]
        for mode, digest in images.items():
            changed = {k for k in controls if profiles[mode].get(k) != controls[k]}
            need(
                set(profiles[mode]) == set(controls)
                and changed == (set() if mode == "pfj_control" else {"libllama.so.0"})
                and profiles[mode]["libllama.so.0"]["sha256"] == digest,
                "startup delta",
            )
        summary[client] = len(controls)
    family = json.loads(json.dumps(rv["family"](directory / "cpu-candidate")))
    need(family == r["fixture"], "candidate controls")
    parse = run_path(rv["PFJ_SOURCE"])["read_journal"]
    for arm in ("off", "heat-a"):
        d = directory / "cpu-pfj1" / arm
        rows, _ = parse(d / "journal.pfj")
        original = rv["witness"](rows, arm)[1]
        need(
            original == family["arms"][arm]["projection_sha256"]
            and json.loads((d / "native.json").read_bytes()) == family["arms"][arm]["choices"]
            and not (d / "policy.bin").exists(),
            "PFJ control",
        )
    keys = (
        "commit",
        "tree",
        "objects",
        "cpu_objects",
        "protocol_sha256",
        "prior_build_sha256",
        "static_preflight_sha256",
        "inputs_sha256",
        "policy_header_sha256",
        "server_starts",
        "gpu_calls",
        "model_forwards",
        "elapsed_s",
        "scope_peak",
        "output_bytes_before_receipt",
    )
    return {k: r[k] for k in keys} | dict(
        status=r["policy_status"],
        build_receipt_sha256=SHA,
        image_hashes=images,
        startup_objects=summary,
        abi_exports=r["abi"]["exports"],
        abi_exports_sha256=r["abi"]["exports_sha256"],
        pfj_control_cases=2,
        candidate_cases={
            k: {
                n: row[n]
                for n in ("status", "records", "choices", "sidecar_bytes", "sidecar_sha256")
            }
            for k, row in family["arms"].items()
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = verify(a.build)
    except (ValueError, KeyError, OSError) as err:
        result = {"status": "FAIL_PRESERVED", "reason": str(err)}
    tmp = a.new_output_dir / "receipt.tmp"
    tmp.write_text(json.dumps(result, sort_keys=True, allow_nan=False, indent=2) + "\n")
    tmp.rename(a.new_output_dir / "receipt.json")
    raise SystemExit(int(result["status"] == "FAIL_PRESERVED"))
