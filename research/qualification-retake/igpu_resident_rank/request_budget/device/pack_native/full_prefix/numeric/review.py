"""Reopen both full-prefix C292 arms, the original capture and the native projection."""

import argparse
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
B = run_path(str(HERE / "bridge.py"))
check = B["checked"]


def reopen(a):
    p = B["previous"]()
    need = p["need"]
    family = B["verify_natural_gate"](a.family, a.family_sha256, a.build_dir, a.build_sha256)
    gold = p["grade"].reference(a.r0_dir)
    original = p["original"](a.original_family, gold)
    need(original == family["independent_reference"]["capture_tree"], "independent gold tree")
    r = {}
    identities = set()
    for mode in B["MODES"]:
        folder = a.family / mode
        raw = folder / "raw"
        arm = check(folder / "receipt.json", family["arms"][mode]["receipt_sha256"])
        census = check(folder / "numerical.json", arm["numerical_sha256"])
        grade = check(folder / "selected.json", arm["c127_sha256"])
        p["base"].measure.check_gate(grade)
        identity = check(raw / (arm["unit"] + ".launch.json"), arm["launch_sha256"])[
            "process_identity"
        ]
        identities.add(json.dumps(identity, sort_keys=True))
        command = check(folder / "argv-observer.json", arm["contract_sha256"])
        need(command["mode"] == mode and census["c292"]["capture"] == original, "arm numerics")
        name = "libllama.so.0.0.9884"
        need(
            arm["loader"]["initialized_sha256"][name] == family["candidate_sha256"]
            and arm["pack"]["positive_samples"] > 0
            and arm["maxima"]["swap_bytes"] == 0,
            "loaded image/FD/swap",
        )
        path = raw / "phase.pfj1"
        if mode == "overlay_on":
            spec = command["pack_stat"], command["model_stat"]
            full = run_path(str(HERE.parent / "audit.py"))["audit_numeric"](path, *spec)
            need(full == arm["journal"], "native journal changed")
        else:
            full = p["inspect_journal"](path, False, None, None)
        r[mode] = dict(
            journal=full,
            maxima=arm["maxima"],
            ELF=arm["image_sha256"],
            model_s=arm["model_s"],
            scope_s=arm["scoped_wall_s"],
            cleanup=arm["cleanup"],
            receipt_sha256=family["arms"][mode]["receipt_sha256"],
            capture=original,
        )
    need(len(identities) == 2, "two different native processes")
    return dict(
        status="REPRODUCED_FULL_PREFIX_C292",
        family_sha256=a.family_sha256,
        build_sha256=a.build_sha256,
        measurement_commit=family["measurement_commit"],
        arms=r,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for k in ("family", "build-dir", "original-family", "r0-dir", "new-output-dir"):
        parser.add_argument("--" + k, type=Path, required=True)
    for k in ("family-sha256", "build-sha256"):
        parser.add_argument("--" + k, required=True)
    a = parser.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = reopen(a)
    except Exception as exc:
        (a.new_output_dir / "FAIL.json").write_text(json.dumps({"error": str(exc)}) + "\n")
        raise
    with (a.new_output_dir / "receipt.json").open("x") as out:
        json.dump(result, out, sort_keys=True, indent=2)
        out.write("\n")
