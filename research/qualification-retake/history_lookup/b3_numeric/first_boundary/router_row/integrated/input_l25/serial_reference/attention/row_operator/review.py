"""Reopen the full-graph controls, paired outputs and refused first run."""

import argparse
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
D = run_path(str(HERE / "operands.py"))
R, need, sha, read, save = (D[k] for k in ("R", "need", "sha", "read", "save"))


def review(a):
    family = R["reopen"](a.family, D["FAMILY"])
    build = R["reopen"](a.build, a.build_sha256)
    first = R["reopen"](a.first_build, a.first_build_sha256)
    failure = R["reopen"](a.failed, a.failed_sha256)
    run = R["reopen"](a.run, a.run_sha256)
    need(
        run["build_sha256"] == a.build_sha256
        and sha(a.build / "fixture")
        == build["elf_sha256"]
        == first["elf_sha256"]
        == sha(a.first_build / "fixture")
        and build["files"] == first["files"]
        and build["sources"]["fixture.cpp"]
        == first["sources"]["fixture.cpp"]
        == sha(HERE / "fixture.cpp")
        and build["sources"]["operands.py"] == sha(HERE / "operands.py")
        and build["sources"]["run.py"] == sha(HERE / "run.py")
        and run["commit"] == build["commit"]
        and run["protocol_sha256"] == build["protocol_sha256"] == sha(HERE / "protocol.md"),
        "provenance",
    )
    need(
        failure["status"] == "FAIL_PRESERVED"
        and failure["reason"] == "ValueError: provider device/inode"
        and failure["operator_starts"] == 1
        and not list((a.failed / "device").glob("*.f32")),
        "first gate",
    )
    data, ref1 = D["from_arm"](a.family, family, "AR")
    other, ref2 = D["from_arm"](a.family, family, "B3")
    need(
        data == other and all(v == (a.build / "inputs" / k).read_bytes() for k, v in data.items()),
        "reconstructed K/V, Q, mask",
    )
    need(
        all(
            sha(a.build / "inputs" / k) == v == sha(a.first_build / "inputs" / k)
            for k, v in build["files"].items()
        ),
        "two builds",
    )
    refs = {"AR": ref1, "B3": ref2}
    need(
        all(ref == (a.build / "inputs" / (k + ".gold")).read_bytes() for k, ref in refs.items()),
        "graph controls",
    )
    outputs = {
        k: (a.run / "device" / (k + ".f32")).read_bytes()
        for k in ("A", "B", "S", "B-alt", "S-alt", "mutant")
    }
    result = D["grade"](outputs, refs)
    need(
        result == read(a.run / "grade.json")
        and sha(a.run / "grade.json") == run["grade_sha256"]
        and run["status"] == result["decision"]
        and run["operator_starts"] == 1
        and run["model_forwards"] == 0
        and all(
            run["loaded"][p]["libggml-cuda.so.0.15.3"]
            == build["permitted_providers"]["libggml-cuda.so.0.15.3"]
            for p in ("before", "after")
        ),
        "numerical and runtime bridges",
    )
    return dict(
        decision=result["decision"],
        rows=result["rows"],
        commit=run["commit"],
        tree=run["tree"],
        parts={
            "target": D["FAMILY"],
            "first_build": a.first_build_sha256,
            "first_run": a.failed_sha256,
            "build": a.build_sha256,
            "physical": a.run_sha256,
        },
        inputs_sha256=build["files"],
        elf_sha256=build["elf_sha256"],
        protocol_sha256=D["METHOD"],
        first_failure=failure["reason"],
        before_compute_results=0,
        model_forwards=0,
        successful_operator_processes=1,
        build_s=build["wall_s"],
        process_scope_s=run["wall_s"],
        cgroup_peak_B=run["cgroup_peak_B"],
        sampled_GPU_MiB={k: v["gpu"]["used_mib"] for k, v in run["live"].items()},
        resources={k: run[k] for k in ("admission", "live", "after_exit", "device_free_min_B")},
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("family", "first-build", "failed", "build", "run", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    for k in ("first-build", "failed", "build", "run"):
        p.add_argument("--" + k + "-sha256", required=True)
    args = p.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    result = review(args)
    save(args.new_output_dir / "result.json", result)
    print(result["decision"])
