"""Reconstruct each accepted physical arm against independent R0, serial and block receipts."""

import argparse
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
T = run_path(str(HERE / "family.py"))
K, F, R, P, need, read, sha, save = (
    T[k] for k in ("K", "F", "R", "P", "need", "read", "sha", "save")
)


def review(a):
    r = R["reopen"](a.family, a.family_sha256)
    b = read(a.build / "receipt.json")
    need(
        sha(a.build / "receipt.json") == r["build_sha256"] == T["BUILD"]
        and b["status"] == "GO_TARGET_FFN_FAMILY"
        and sha(a.build / "b3-numeric") == b["elf_sha256"]
        and sha(a.build / "libllama.so.0.0.9884") == b["image_sha256"]
        and sha(a.build / "llama-graph.cpp") == b["graph_source_sha256"]
        and all(sha(HERE / f) == v for f, v in b["method_sources"].items())
        and sha(HERE / "protocol.md") == r["protocol_sha256"] == K["METHOD"]
        and r["runner_sha256"] == sha(HERE / "family.py")
        and r["model_starts"] == 3
        and r["generation_requests"] == 0,
        "published implementation and starts",
    )
    refs, neutral, ctrl, gold, pins, _ = T["inputs"](a)
    window = read(a.window / "receipt.json")
    need(
        window["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and sha(a.window / "receipt.json") == r["window_sha256"]
        and sha(a.window / "samples.jsonl") == window["window_sha256"]
        and window["gpu_driver"] == r["driver"]["release"],
        "C55 receipt",
    )
    arms = {}
    for mode in T["ARMS"]:
        directory = a.family / mode
        entry = r["arms"][mode]
        unit = r["unit"] + "-" + mode.lower()
        cfg = read(directory / "full-resource.json")
        mon, launch, inv = T["audit"](
            directory, unit, cfg, read(directory / "full-argv.json"), mode
        )
        need(
            entry["model_s"] == mon["elapsed_s"]
            and entry["maxima"] == mon["maxima"]
            and entry["c118"] == inv
            and entry["scope_cleanup"]
            and entry["samples_live"] > 0
            and 0 <= entry["c55_age_s"] < 3600
            and cfg["pinned"]["capture_sha256"] == b["elf_sha256"]
            and cfg["pinned"]["numerical_dso_sha256"]["libllama.so.0.0.9884"] == b["image_sha256"]
            and entry["loaded"]["initialized"]["libllama.so.0.0.9884"] == b["image_sha256"],
            "scope and live target",
        )
        out = T["grade"](directory, unit, mode, refs, neutral, gold, pins)
        need(
            out == read(directory / "grade.json")
            and sha(directory / "grade.json") == entry["grade_sha256"]
            and out["status"] == entry["status"],
            "reconstructed grade",
        )
        arms[mode] = out | dict(
            scope_s=entry["scope_s"],
            model_s=entry["model_s"],
            maxima=mon["maxima"],
            c118=inv,
            gpu_energy=R["power"](directory, {"unit": unit}),
            mapped_samples=entry["samples_live"],
        )
    need(
        r["status"] == arms["CUDA"]["status"] and arms["BASE"]["status"] == "PASS_NEUTRAL_BASE",
        "family decision",
    )
    return dict(
        decision=r["status"],
        arms=arms,
        commit=r["commit"],
        tree=r["tree"],
        unit=r["unit"],
        family_sha256=a.family_sha256,
        build_sha256=r["build_sha256"],
        window_sha256=r["window_sha256"],
        protocol_sha256=r["protocol_sha256"],
        model_sha256=r["model_sha256"],
        capture_sha256=b["elf_sha256"],
        image_sha256=b["image_sha256"],
        source_sha256=b["graph_source_sha256"],
        serial_sha256=r["serial_sha256"],
        block_sha256=r["block_sha256"],
        model_starts=r["model_starts"],
        generation_requests=r["generation_requests"],
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("family", "serial", "block", "reference", "build", "window", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--family-sha256", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    result = review(a)
    save(a.new_output_dir / "result.json", result)
    print(result["decision"])
