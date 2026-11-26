"""Reopen the physical controls and locate KV differences after the CPU intervention."""

import argparse
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
N = run_path(str(HERE / "family.py"))
A = run_path(str(HERE.parents[1] / "review.py"))
G, F, need, sha, save = (N[k] for k in ("G", "F", "need", "sha", "save"))
TARGET = "aba8a61c990d7cfb699015e6fc4ee3d6d57b656415858c3e0a8642d2c45391bb"
WINDOW = "2cc3c5c084e9c9f4d812180f52f3ee901c407bb37f0c9c5aa0add2903205c2a0"


def review(build, window, family, previous, client):
    elf = G["read"](build / "receipt.json", N["BUILD"])
    for key, h in elf["files"].items():
        path = build / key
        if not path.exists() and path.name == "libllama.so.0":
            alias = F["read"](path.with_name("alias.json"))
            need(alias == dict(alias=path.name, target=G["IMAGE"], sha256=h), "archived alias")
            path = path.with_name(alias["target"])
        need(sha(path) == h, "build tree")
    timewin = G["read"](window / "receipt.json", WINDOW)
    need(
        timewin["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and sha(window / "samples.jsonl") == timewin["window_sha256"],
        "C55",
    )
    target = G["read"](family / "receipt.json", TARGET)
    A["verify_files"](family, target)
    old = G["read"](previous / "receipt.json", N["NATURAL"])
    cli = G["read"](client / "receipt.json", F["CLIENT"])
    work = G["read"](client / "work.json", cli["work_sha256"])
    need(
        target["window_sha256"] == WINDOW
        and target["build_sha256"] == N["BUILD"]
        and target["intervention_sha256"] == elf["images"]["CPU"]["image_sha256"]
        and target["old_family_sha256"] == N["NATURAL"],
        "identity",
    )
    unit = target["unit"]
    ref = family / "P/raw" / (unit + "-p.capture")
    arms = {}
    for trial in N["ORDER"]:
        root = family / trial
        mode = "P" if trial == "P" else "ON"
        cap = root / "raw" / (unit + "-" + trial.lower() + ".capture")
        scientific = A["process"](family, mode, ref, work, unit, label=trial)
        grade = F["read"](root / "grade.json")
        live = target["arms"][trial]
        proof = {}
        N["check"](SimpleNamespace(natural=previous), old, trial, proof, cap, grade)
        need(
            all(live[k] == v for k, v in proof.items())
            and live["inventory"] == scientific["inventory"]
            and live["maxima"] == scientific["maxima"]
            and live["grade_sha256"] == sha(root / "grade.json")
            and live["image_sha256"]
            == (
                cli["arms"]["HIST"]["image_sha256"]
                if trial == "P"
                else elf["images"]["CPU"]["image_sha256"]
            ),
            "reopened controls and observers",
        )
        cmd = F["read"](root / "invocation.json")
        need(
            (cmd["expected"].get(N["E"]["SWITCH"]) == "1") == (trial == "ROWS"),
            "intervention toggle",
        )
        arms[trial] = scientific | proof | dict(status=live["status"])
    from_pos = len(work["prompt"]) + len(work["prefix"]) - 1
    differences = {}
    for trial in ("B", "ROWS"):
        cap = family / trial / "raw" / (unit + "-" + trial.lower() + ".capture")
        differences[trial] = A["localize_kv"](cap, ref, from_pos + 3, from_pos)
    passed = arms["ROWS"]["parity_vs_P"]
    need(
        arms["P"]["parity_vs_P"]
        and not arms["B"]["parity_vs_P"]
        and target["model_starts"] == 3
        and (target["status"] == "GO_CPU_ROWS_NATURAL_CUT_ONLY") == passed,
        "stopping rule and actual arms",
    )
    return dict(
        decision="GO_FIRST_NATURAL_CUT" if passed else "NO_GO_EXACT_WITH_CPU_ROWS",
        status=target["status"],
        family_sha256=TARGET,
        window_sha256=WINDOW,
        experiment_sha256=N["E"]["METHOD"],
        old_family_sha256=N["NATURAL"],
        build_sha256=N["BUILD"],
        images=elf["images"],
        commit=target["commit"],
        tree=target["tree"],
        arms=arms,
        KV=differences,
        model_starts=3,
        http_requests=0,
        wall_s=target["wall_s"],
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("build", "window", "family", "previous", "client", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    save(
        a.new_output_dir / "result.json", review(a.build, a.window, a.family, a.previous, a.client)
    )
