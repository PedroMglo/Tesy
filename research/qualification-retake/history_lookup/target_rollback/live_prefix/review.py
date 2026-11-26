"""Reopen the live-prefix experiment, including observed controls and early stops."""

import argparse
import hashlib
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
L = run_path(str(HERE / "grade.py"))
F, need, sha, read = (L[k] for k in ("F", "need", "sha", "read"))


def source_hash(commit, relative):
    root = F["N"]["REPO"]
    path = (HERE / relative).resolve().relative_to(root.resolve())
    data = subprocess.check_output(["git", "-C", root, "show", f"{commit}:{path}"])
    return hashlib.sha256(data).hexdigest()


def kv_difference(first, second):
    parser = F["SWA"]["KV"]

    def parsed(cap):
        blob = (cap / "post3.kv").read_bytes()
        rows, metadata = parser["parse"](blob, 192, F["SWA"]["banks"](cap))
        return blob, rows, metadata

    x, y = parsed(first), parsed(second)
    need(x[2] == y[2] and all(x[0][k : k + n] == y[0][k : k + n] for k, n in x[2]), "KV metadata")
    result = parser["compare"](x[:2], y[:2])
    return dict(
        compared_f16=len(x[1]) * 512,
        different_f16=result["totals"]["differing_words"],
        layers=result["layers"],
        lowest_layer=result["lowest_layer_example"],
        by_position=result["by_position"],
        metadata_bytes=sum(n for _, n in x[2]),
    )


def review(a):
    r = F["R"]["reopen"](a.family, a.family_sha256)
    b = read(a.build / "receipt.json")
    win = read(a.window / "receipt.json")
    need(
        sha(a.build / "receipt.json") == r["build_sha256"] == F["LIVE_BUILD"]
        and b["status"] == "GO_LIVE_AR_CONTROL"
        and (a.build / "rollback.cpp").read_text() == F["B"]["source"](False, True)
        and sha(a.build / "b3-numeric") == b["elf_sha256"]
        and sha(a.build / "libllama.so.0.0.9884") == b["image_sha256"]
        and source_hash(r["commit"], "../family.py") == r["runner_sha256"]
        and source_hash(r["commit"], "grade.py") == r["grader_sha256"]
        and sha(HERE / "protocol.md") == r["protocol_sha256"] == F["B"]["LIVE_METHOD"]
        and sha(a.window / "receipt.json") == r["window_sha256"]
        and sha(a.window / "samples.jsonl") == win["window_sha256"]
        and win["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and win["gpu_driver"] == r["driver"]["release"]
        and r["generation_requests"] == 0,
        "scientific protocol, binary, supervision and C55",
    )
    F["R"]["reopen"](a.cold_import, r["cold_import_sha256"])
    _, target, _, _, _, _ = F["sources"](a)
    ar = F["capture"](a.family, r["unit"], "AR")
    cases = ["AR", "B3"] if r["status"] == "NO_GO_B3_BITWISE" else ["AR", "B3", "RESTORE"]
    need(set(r["arms"]) == set(cases) and r["model_starts"] == len(cases), "stopping rule")
    results = {}
    for mode in cases:
        record = r["arms"][mode]
        root = a.family / mode
        unit = r["unit"] + "-" + mode.lower()
        cfg = read(root / "rollback-resource.json")
        m, launch, inv = F["audit"](root, unit, mode, cfg, read(root / "rollback-argv.json"))
        need(
            record["scope_cleanup"]
            and 0 <= record["c55_age_s"] < 3600
            and 0 < record["scope_s"] <= 320
            and record["samples_live"] > 0
            and m["elapsed_s"] == record["model_s"]
            and m["maxima"] == record["maxima"]
            and m["maxima"]["swap_bytes"] == 0
            and record["c118"] == inv
            and m["process_identity"] == launch["process_identity"]
            and cfg["pinned"]["capture_sha256"] == b["elf_sha256"]
            and cfg["scientific_protocol_sha256"] == r["protocol_sha256"]
            and record["loaded"]["initialized"]["libllama.so.0.0.9884"] == b["image_sha256"],
            "native scope identity",
        )
        cap = F["capture"](a.family, r["unit"], mode)
        grade = L["grade"](cap, mode, target, ar, a.cold_import)
        need(
            grade == read(root / "grade.json")
            and grade["status"] == record["status"]
            and sha(root / "grade.json") == record["grade_sha256"],
            "physical arm",
        )
        results[mode] = dict(
            grade=grade,
            kv_against_serial=kv_difference(ar, cap),
            c118=inv,
            scope_s=record["scope_s"],
            model_s=m["elapsed_s"],
            maxima=m["maxima"],
            energy=F["R"]["power"](root, {"unit": unit}),
        )
    outcome = r["status"]
    need(
        outcome in ("NO_GO_B3_BITWISE", "NO_GO_RESTORE_BITWISE", "GO_LIVE_AND_WARM_CALIBRATION")
        and all(results[mode]["grade"]["status"] == "PASS_" + mode for mode in cases[:-1])
        and (
            results[cases[-1]]["grade"]["status"]
            == ("PASS_RESTORE" if outcome.startswith("GO_") else outcome)
        ),
        "verdict from constituent arms",
    )
    return dict(
        status=outcome,
        arms=results,
        commit=r["commit"],
        tree=r["tree"],
        model_starts=r["model_starts"],
        generation_requests=r["generation_requests"],
        model_sha256=r["model_sha256"],
        family_sha256=a.family_sha256,
        protocol_sha256=r["protocol_sha256"],
        build_sha256=r["build_sha256"],
        window_sha256=r["window_sha256"],
        elf_sha256=b["elf_sha256"],
        dso_sha256=b["image_sha256"],
        target_sha256=r["target_sha256"],
        serial_sha256=r["serial_sha256"],
        cold_import_sha256=r["cold_import_sha256"],
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in (
        "family",
        "build",
        "window",
        "target",
        "serial",
        "reference",
        "cold-import",
        "new-output-dir",
    ):
        p.add_argument("--" + arg, type=Path, required=True)
    p.add_argument("--family-sha256", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    result = review(a)
    F["save"](a.new_output_dir / "result.json", result)
    print(result["status"])
