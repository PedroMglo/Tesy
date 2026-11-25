"""Reopen each C292 source, its complete numerical tree and the router/worker join."""

import argparse
import json
from pathlib import Path
from runpy import run_path

S = run_path(str(Path(__file__).with_name("profile.py")))
P, grade, need, sha = (S[k] for k in ("P", "grade", "need", "sha"))


def reopen(a):
    family = grade.read(a.family / "receipt.json", a.family_sha256)
    build = grade.read(a.build_dir / "receipt.json", S["BUILD"])
    need(
        family["status"] == "PASS_C292_ROUTER_LOOKAHEAD_NUMERIC"
        and family["model_launch_receipts"] == 2,
        "terminal status",
    )
    need(
        family["candidate_sha256"] == build["candidate_sha256"] == S["IMAGE"]
        and family["build_receipt_sha256"] == S["BUILD"],
        "frozen ELF",
    )
    gold = grade.reference(a.r0_dir)
    tree = P["original"](a.original_family, gold)
    need(family["reference_tree"] == tree, "independent full-tree fingerprint")
    arms, pids = {}, set()
    for mode in S["MODES"]:
        folder = a.family / mode
        raw = folder / "raw"
        digest = family["arms"][mode]["receipt_sha256"]
        arm = grade.read(folder / "receipt.json", digest)
        need(
            arm["status"] == "PASS_C292_ARM_NUMERICS"
            and arm["cleanup"]
            and arm["model_launch_receipts"] == 1,
            "single completed capture",
        )
        c127 = grade.read(folder / "selected.json", arm["c127_sha256"])
        P["base"].measure.check_gate(c127)
        census = grade.read(folder / "numerical.json", arm["numerical_sha256"])
        capture = raw / (arm["unit"] + ".capture")
        measured = grade.check_arm(capture, raw / (arm["unit"] + ".stdout"), gold, c127)
        need(census == measured and measured["c292"]["capture"] == tree, "raw numerical comparison")
        command = grade.read(folder / "argv-observer.json", arm["contract_sha256"])
        launch = grade.read(raw / (arm["unit"] + ".launch.json"), arm["launch_sha256"])
        monitor = grade.read(raw / (arm["unit"] + ".json"), arm["monitor_sha256"])
        need(
            launch["process_identity"] == monitor["process_identity"] and command["mode"] == mode,
            "process identity",
        )
        pids.add(json.dumps(launch["process_identity"], sort_keys=True))
        need(
            monitor["explicit_env"] == command["explicit_env"]
            and monitor["relevant_environment"].get(S["FLAG"])
            == ("1" if mode == "overlay_on" else None),
            "observer flag",
        )
        inv = P["base"].compact.validate_inventory(
            folder, arm["unit"], {"native_explicit_env": command["explicit_env"]}, launch
        )
        need(
            inv == arm["c118"]
            and arm["maxima"] == monitor["maxima"]
            and arm["maxima"]["swap_bytes"] == 0,
            "admission and caps",
        )
        need(
            arm["pack"]["positive_samples"] > 0
            and arm["loader"]["initialized_sha256"]["libllama.so.0.0.9884"] == S["IMAGE"],
            "pack FD and startup ELF",
        )
        journal = S["inspect_journal"](
            raw / "phase.pfj1", True, command["pack_stat"], command["model_stat"]
        )
        need(json.loads(json.dumps(journal)) == arm["journal"], "reopened journal")
        arms[mode] = dict(
            capture=tree,
            c118=inv,
            maxima=arm["maxima"],
            cleanup=True,
            model_s=arm["model_s"],
            scope_s=arm["scoped_wall_s"],
            journal=journal,
            arm_sha256=digest,
        )
    need(len(pids) == 2, "distinct captures")
    return dict(
        status="REPRODUCED_C292_ROUTER_LOOKAHEAD",
        family_sha256=a.family_sha256,
        measurement_commit=family["measurement_commit"],
        build_sha256=S["BUILD"],
        arms=arms,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("family", "build-dir", "original-family", "r0-dir", "new-output-dir"):
        p.add_argument("--" + k, required=True, type=Path)
    p.add_argument("--family-sha256", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = reopen(a)
    except Exception as e:
        (a.new_output_dir / "FAIL.json").write_text(json.dumps({"error": repr(e)}) + "\n")
        raise
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2)
        f.write("\n")
