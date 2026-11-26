"""Check original and archived physical native hook results without GPU or weights."""

import argparse
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
R = run_path(str(HERE / "run.py"))
G, sha, need = R["G"], R["sha"], R["need"]


def review(a):
    root = R["load"](a.family / "receipt.json", a.family_sha256)
    state = root["authority"]
    need(
        root["status"] == "PASS_NATIVE_CACHE_HOOK"
        and root["swap_peak_B"] == 0
        and set(root["arms"]) == set(R["LABELS"]),
        "family outcome",
    )
    files = {
        str(f.relative_to(a.family)): sha(f)
        for f in a.family.rglob("*")
        if f.is_file() and f != a.family / "receipt.json"
    }
    need(files == root["raw_sha256"] and sha(a.tiny) == R["D"]["TINY"], "raw inventory")
    G["R"]["review"](a.graph, G["GRAPH"], a.historical, a.tiny)
    refs = G["reference"](a.graph)
    arms = {}
    for label in R["LABELS"]:
        native = a.family / label
        arm = root["arms"][label]
        grade = G["grade"](label, native, a.tiny, a.historical, refs)
        need(
            arm["grade"] == grade
            and arm["starts"] == 1
            and arm["observed_handoffs"] == 3
            and arm["returncode"] == 0
            and arm["child_gone"],
            "native evidence",
        )
        libs = [p for p in arm["A_providers"] if Path(p).name == "libllama.so"]
        key = "baseline_library_sha256" if label == "ORIGINAL" else "candidate_library_sha256"
        need(
            len(libs) == 1 and state["files"][libs[0]]["sha256"] == state[key], "native mapped DSO"
        )
        arms[label] = grade | dict(
            libllama_sha256=state[key], vram_peak_MiB=arm["sampled_vram_mib_max"]
        )
    return dict(
        decision="GO_NATIVE_C110",
        commit=state["commit"],
        tree=state["tree"],
        family_sha256=a.family_sha256,
        build_sha256=state["build_sha256"],
        c55_sha256=state["c55_sha256"],
        arms=arms,
        model_sha256=sha(a.tiny),
        scratch_B=G["CAP"],
        physical_model_starts=3,
        forwards=6,
        equal_finite_F32=1056,
        equal_ordered_quartets=66,
        scope_memory_peak_B=root["memory_peak_B"],
        swap_B=0,
        real_120B_forwards=0,
        http_requests=0,
        energy_J=None,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("family", "graph", "historical", "tiny", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--family-sha256", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    result = review(a)
    (a.new_output_dir / "result.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n"
    )
    print(result["decision"])
