"""Reproduce the public startup and C55 census from terminal private receipts and logs."""

import argparse
from pathlib import Path

from c270 import STARTUP
from linkage import ORIGINAL, need, read, sha
from smoke import save

WINDOW = "5a8b02b44b857c76ba584f169c3bda60faf7d0879b5ed084b1db21c4ef3c4384"
IMAGENAME = "libllama.so.0.0.9884"


def compact(smoke, window):
    need(
        sha(smoke / "receipt.json") == STARTUP and sha(window / "receipt.json") == WINDOW,
        "campaign identities",
    )
    r = read(smoke / "receipt.json")
    c = read(window / "receipt.json")
    need(
        r["status"] == "PASS_C270_C281_ONE_PROVIDER_STARTUP"
        and c["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not c["reason"]
        and sha(window / "samples.jsonl") == c["window_sha256"]
        and sha(window / "resource-policy.json") == c["canonical_policy_sha256"],
        "terminal evidence",
    )
    rows = []
    for x in r["arms"]:
        tag = x["selection"]
        folder = smoke / (x["arm"] + "-" + tag)
        (journal,) = folder.glob("loader.*")
        need(sha(journal) == x["journal_sha256"], "loader journal")
        lines = [
            line.split("calling init:", 1)[1].strip()
            for line in journal.read_text().splitlines()
            if "calling init:" in line
        ]
        (selected,) = [Path(line) for line in lines if Path(line).name == "libllama.so.0"]
        allowed = Path(x["native_search"].split(":", 1)[0]) / "libllama.so.0"
        need(selected == allowed, "lookup outside selected search")
        wrong = tag == "wrong-original"
        need(
            x["expected_candidate_rejected"] is wrong and x["no_model_fd"] and x["forwards"] == 0,
            "negative or model gate",
        )
        actual = x["loaded_numeric"][IMAGENAME]
        need(actual == (ORIGINAL if wrong else x["selected_sha256"]), "selected image")
        if not wrong:
            need(
                x["loader"]["initialized"][IMAGENAME] == actual
                and len(lines) == len(x["loader"]["initialized"]),
                "positive loader coverage",
            )
        io = {}
        for label in ("stderr", "stdout"):
            need((folder / label).stat().st_size == x[label + "_bytes"], "stream size")
            io[label + "_sha256"] = sha(folder / label)
        rows.append(
            dict(
                executable=x["arm"],
                mode=tag,
                executable_sha256=x["executable_sha256"],
                expected_libllama_sha256=x["selected_sha256"],
                loaded_libllama_sha256=actual,
                actual_object_initializers=len(lines),
                mapped_numerical_dsos=len(x["loaded_numeric"]),
                rejected_wrong_original=wrong,
                exit_code=x["exit"],
                loader_sha256=sha(journal),
                **io,
            )
        )
    cg = r["cgroup"]
    return dict(
        status=r["status"],
        scope="startup and mapped DSOs",
        smoke_receipt_sha256=STARTUP,
        build_sha256=r["build_sha256"],
        preflight_sha256=r["preflight_sha256"],
        commit=r["commit"],
        protocol_sha256=r["protocol_sha256"],
        source_sha256=r["source_sha256"],
        model_launches=r["model_launches"],
        forwards=0,
        startup_processes=len(rows),
        elapsed_s=r["elapsed_s"],
        memory_peak_bytes=cg["memory_peak"],
        memory_limit_bytes=cg["memory_max"],
        swap_limit_bytes=cg["swap_max"],
        arms=rows,
        window=dict(
            receipt_sha256=WINDOW,
            policy_sha256=c["canonical_policy_sha256"],
            samples_sha256=c["window_sha256"],
            samples=c["samples"],
            span_s=c["span_s"],
            memory_available_min_bytes=c["memory"]["available_min_bytes"],
            admitted_cap_bytes=c["canonical_memory"]["cap_max_bytes"],
            gpu_compute_max=c["gpu_compute_max"],
            gpu_c_max=c["gpu_c_max"],
            cpu_c_max=c["cpu_c_max"],
            nvme_c_max=c["nvme_c_max"],
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("smoke-dir", "window", "new-output"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    save(a.new_output, compact(a.smoke_dir, a.window))
